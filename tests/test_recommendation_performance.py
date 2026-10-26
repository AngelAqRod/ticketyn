"""Bounded recommendation reads in ephemeral PostgreSQL, for both ticket domains."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select, inspect
from sqlalchemy.orm import Session
from ticketyn.api import recommendations, recommendation_data
from ticketyn.models import Ticket, InternalTicket, Responsible, Position
from ticketyn.models.ack import TicketEscalationAck, InternalTicketEscalationAck
from test_escalation_recommendations import create_position


@pytest.fixture(params=[False, True], ids=['customer', 'internal'])
def context(api_client, ticket_payload, request):
    internal = request.param
    department = ticket_payload['department_id']
    destinations = [create_position(api_client, f'Destino {i}', department).json() for i in range(12)]
    source = create_position(api_client, 'Origen', department, general_time=15,
        destinations=[{'target_position_id': d['id']} for d in destinations]).json()
    person = api_client.post('/api/responsibles', json={'name': 'Guardia', 'department_id': department, 'position_id': source['id']}).json()
    payload = {**ticket_payload, 'responsible_id': person['id'],
               'start_at': (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()}
    if internal:
        payload = {k: v for k, v in payload.items() if k not in ('customer_id', 'circuit_id')}
        payload['incident_type_id'] = api_client.post('/api/internal-incident-types', json={'name': 'Prueba interna'}).json()['id']
    base = '/api/internal-tickets' if internal else '/api/tickets'
    response = api_client.post(base, json=payload)
    assert response.status_code == 201, response.text
    item = response.json()
    return dict(base=base, item=item, model=InternalTicket if internal else Ticket,
                ack=InternalTicketEscalationAck if internal else TicketEscalationAck,
                endpoint=recommendations.get_internal_recommendations if internal else recommendations.get_recommendations,
                source=source, destinations=destinations)


@contextmanager
def trace(bind):
    statements = []
    def record(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith(('SELECT', 'UPDATE', 'INSERT', 'DELETE')):
            statements.append(statement)
    event.listen(bind, 'before_cursor_execute', record)
    try:
        yield statements
    finally:
        event.remove(bind, 'before_cursor_execute', record)


def evaluate(db_session, context):
    # Fresh identity map: eager-loading or N+1 cannot hide behind fixture objects.
    bind = db_session.get_bind()
    actor = SimpleNamespace(id=2147000000, role='SUPERADMIN', permissions=())
    request = SimpleNamespace(state=SimpleNamespace(principal=actor))
    with Session(bind=bind, join_transaction_mode='create_savepoint') as session, trace(bind) as statements:
        result = context['endpoint'](context['item']['id'], session, request)
        return result, statements


def test_closed_endpoint_does_not_evaluate_stage_destinations_or_acks(api_client, db_session, context, monkeypatch):
    base, id = context['base'], context['item']['id']
    assert api_client.post(f'{base}/{id}/ack', json={'reason': 'Historia conservada', 'duration_type': 'INDEFINITE'}).status_code == 201
    assert api_client.patch(f'{base}/{id}', json={'status': 'CLOSED'}).status_code == 200
    before = api_client.get(f'{base}/{id}/acks').json()
    def no_stage(*args, **kwargs):
        pytest.fail('Un ticket cerrado no debe calcular su etapa')
    monkeypatch.setattr(recommendation_data, 'get_ticket_stage', no_stage)
    result, statements = evaluate(db_session, context)
    assert result.ticket_status == 'CLOSED'
    assert result.recommendations == [] and not result.has_active_ack and not result.can_acknowledge
    assert result.elapsed_minutes == 0
    assert len(statements) == 1, statements
    assert 'JOIN' not in statements[0].upper()
    direct = api_client.get(f'{base}/{id}/recommendations')
    assert direct.status_code == 200 and direct.json()['recommendations'] == []
    assert api_client.get(f'{base}/{id}/ack').status_code == 204
    assert api_client.get(f'{base}/{id}/acks').json() == before


def test_open_query_count_is_constant_with_twelve_destinations(api_client, db_session, context):
    result, statements = evaluate(db_session, context)
    assert len(result.recommendations) == 12
    assert len(statements) == 6, '\n'.join(statements)
    stage = [s for s in statements if 'escalations' in s]
    assert len(stage) == 2 and all('LIMIT' in s for s in stage)
    assert all('ticket_id' in s for s in stage)
    # More or fewer destinations use one joined query, never a query per destination.
    assert api_client.patch(f"/api/positions/{context['source']['id']}", json={
        'destinations': [{'target_position_id': context['destinations'][0]['id']}]}).status_code == 200
    smaller, fewer = evaluate(db_session, context)
    assert len(smaller.recommendations) == 1
    assert len(fewer) == len(statements)


def test_ack_keeps_elapsed_time_without_loading_destinations(api_client, db_session, context):
    base, id = context['base'], context['item']['id']
    before, _ = evaluate(db_session, context)
    ack = api_client.post(f'{base}/{id}/ack', json={'reason': 'Investigación', 'duration_type': '1H'})
    assert ack.status_code == 201, ack.text
    active, statements = evaluate(db_session, context)
    assert active.has_active_ack and active.recommendations == []
    assert active.elapsed_minutes == before.elapsed_minutes
    assert len(statements) == 5, '\n'.join(statements)
    assert not any('position_escalation_destinations' in s for s in statements)
    item = db_session.get(context['ack'], ack.json()['id'])
    item.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    expired, after = evaluate(db_session, context)
    assert not expired.has_active_ack and len(expired.recommendations) == 12
    assert expired.elapsed_minutes == before.elapsed_minutes
    assert len(after) == 7, '\n'.join(after)
    history = api_client.get(f'{base}/{id}/acks').json()
    assert history[0]['revoked_reason'] == 'Vencimiento automático de plazo'


def test_historical_ticket_without_position_is_safe(api_client, db_session, context):
    item = db_session.get(context['model'], context['item']['id'])
    item.initial_position_id = None; item.responsible_id = None
    db_session.commit()
    result, statements = evaluate(db_session, context)
    assert result.recommendations == [] and result.reference_position_id is None
    assert len(statements) == 4


def test_reopen_resumes_recommendations_without_losing_history(api_client, db_session, context):
    base, id = context['base'], context['item']['id']
    assert api_client.patch(f'{base}/{id}', json={'status': 'CLOSED'}).status_code == 200
    assert api_client.post(f'{base}/{id}/ack', json={'duration_type': 'INDEFINITE', 'reason': 'ACK previo'}).status_code == 201
    # Even an inconsistent imported/late ACK must not activate evaluation while closed.
    closed, statements = evaluate(db_session, context)
    assert len(statements) == 1 and not closed.has_active_ack
    assert api_client.post(f'{base}/{id}/ack/revoke', json={'reason': 'Retiro de prueba'}).status_code == 200
    assert api_client.patch(f'{base}/{id}', json={'status': 'OPEN', 'end_at': None}).status_code == 200
    reopened, _ = evaluate(db_session, context)
    assert reopened.ticket_status == 'OPEN' and len(reopened.recommendations) == 12


def test_existing_indexes_cover_ticket_scoped_lookups(db_session, context):
    names = {index['name'] for index in inspect(db_session.get_bind()).get_indexes(context['ack'].__tablename__)}
    expected = 'uq_internal_active_ack' if context['base'].endswith('internal-tickets') else 'uq_ticket_active_ack'
    assert expected in names


def test_closed_http_request_does_not_load_actor_destination_graph(api_client, db_session, context):
    account = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    account.department_id = context['item']['department_id']
    account.position_id = context['source']['id']
    db_session.commit()
    base, id = context['base'], context['item']['id']
    assert api_client.patch(f'{base}/{id}', json={'status': 'CLOSED'}).status_code == 200
    with trace(db_session.get_bind()) as statements:
        response = api_client.get(f'{base}/{id}/recommendations')
    assert response.status_code == 200, response.text
    assert len(statements) == 3, '\n'.join(statements)  # principal + security configuration + ticket
    assert not any('position_escalation_destinations' in s or 'escalation_acks' in s for s in statements)
