"""Quick close through real authorization and disposable PostgreSQL only."""
from datetime import datetime, timezone
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from ticketyn.models import Ticket, InternalTicket, Responsible, Sector, Department, InternalIncidentType, InternalTicketUpdate
from ticketyn.models.security import SecurityRole, SecurityRolePermission
from ticketyn.schemas.ticket_close import TicketClose
from ticketyn.api.ticket_close import close_ticket
from ticketyn.api import internal_ticket_data, ticket_data
from security_helpers import fixture_password


@pytest.fixture(params=[False, True], ids=['customer', 'internal'])
def context(api_client, ticket_payload, request):
    internal = request.param
    payload = {**ticket_payload, 'resolution': 'Resolución anterior'}
    if internal:
        payload = {k: v for k, v in payload.items() if k not in ('customer_id', 'circuit_id')}
        payload['incident_type_id'] = api_client.post('/api/internal-incident-types', json={'name': 'Incidente interno'}).json()['id']
    else:
        payload['customer_resolution'] = 'Información pública anterior'
    base = '/api/internal-tickets' if internal else '/api/tickets'
    response = api_client.post(base, json=payload)
    assert response.status_code == 201, response.text
    item = response.json()
    return dict(internal=internal, base=base, path=f"{base}/{item['id']}", item=item,
                model=InternalTicket if internal else Ticket, module='internal_tickets' if internal else 'tickets')


def close(api_client, context, **values):
    return api_client.post(context['path'] + '/close', json={'expected_updated_at': context['item']['updated_at'], **values})


def test_now_and_preserved_resolution(api_client, context):
    before = datetime.now(timezone.utc)
    response = close(api_client, context)
    assert response.status_code == 200, response.text
    item = response.json()
    assert item['status'] == 'CLOSED' and item['resolution'] == 'Resolución anterior'
    assert before <= datetime.fromisoformat(item['end_at']) <= datetime.now(timezone.utc)
    assert item['duration_seconds'] > 0
    if not context['internal']:
        assert item['customer_resolution'] == 'Información pública anterior'
    assert api_client.get(context['path'] + '/recommendations').json()['ticket_status'] == 'CLOSED'
    assert close(api_client, context).status_code == 409


@pytest.mark.parametrize('resolution', [None, 'Diagnóstico y solución\nComprobación <correcta> & estable'])
def test_optional_and_edited_resolutions(api_client, context, resolution):
    values = dict(resolution=resolution, end_at='2020-01-01T08:00:00-06:00')
    if not context['internal']: values['customer_resolution'] = resolution
    response = close(api_client, context, **values)
    assert response.status_code == 200, response.text
    item = response.json()
    assert item['resolution'] == resolution and item['duration_seconds'] == 7200
    if not context['internal']: assert item['customer_resolution'] == resolution


@pytest.mark.parametrize('end_at', ['incorrecta', '2020-01-01T11:59:59Z', '2020-01-01T13:00:00', '2999-01-01T13:00:00Z'])
def test_invalid_dates_do_not_write_resolutions(api_client, context, end_at):
    response = close(api_client, context, end_at=end_at, resolution='No persistir')
    assert response.status_code == 422, response.text
    item = api_client.get(context['path']).json()
    assert item['status'] == 'OPEN' and item['end_at'] is None and item['resolution'] == 'Resolución anterior'


def test_remote_edit_conflict(api_client, context):
    assert api_client.patch(context['path'], json={'resolution': 'Cambio remoto'}).status_code == 200
    assert close(api_client, context, resolution='Edición obsoleta').status_code == 409
    item = api_client.get(context['path']).json()
    assert item['status'] == 'OPEN' and item['resolution'] == 'Cambio remoto'


def test_existing_edit_reopen_correct_date_and_close_again(api_client, context, db_session):
    first = close(api_client, context, end_at='2020-01-01T14:00:00Z').json()
    assert first['status'] == 'CLOSED'
    changed = api_client.patch(context['path'], json={'end_at': '2020-01-01T15:00:00Z', 'resolution': 'Corregida'})
    assert changed.status_code == 200 and changed.json()['duration_seconds'] == 10800
    reopened = api_client.patch(context['path'], json={'status': 'OPEN', 'end_at': None})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()['status'] == 'OPEN'
    assert db_session.get(context['model'], first['id']).closed_seconds > 0
    context['item'] = reopened.json()
    assert close(api_client, context).json()['status'] == 'CLOSED'


def test_full_rollback_on_persistence_error(api_client, context, db_session, monkeypatch):
    def fail(*args): raise RuntimeError('simulated persistence failure')
    monkeypatch.setattr(internal_ticket_data if context['internal'] else ticket_data, 'save_item', fail)
    with pytest.raises(RuntimeError, match='simulated'):
        close(api_client, context, resolution='No persistir')
    db_session.expire_all()
    item = db_session.get(context['model'], context['item']['id'])
    assert item.status == 'OPEN' and item.end_at is None and item.resolution == 'Resolución anterior'


def authenticate_with(api_client, db_session, permissions):
    role = SecurityRole(name='Permisos de cierre'); db_session.add(role); db_session.flush()
    db_session.add_all(SecurityRolePermission(role_id=role.id, permission_code=code) for code in permissions)
    person = Responsible(name='Operador de prueba', username='quick-close-fixture', password_hash=fixture_password(),
                         access_granted=True, password_change_required=False, security_role_id=role.id)
    db_session.add(person); db_session.flush(); db_session.commit()
    api_client.headers['Authorization'] = 'Bearer ' + api_client.app.state.security.create(person.id, person.access_revision)


@pytest.mark.parametrize('permission', ['view', 'edit', 'close'])
def test_backend_close_permission(api_client, context, db_session, permission):
    authenticate_with(api_client, db_session, [context['module'] + '.' + permission])
    response = close(api_client, context)
    assert response.status_code == (200 if permission == 'close' else 403), response.text


def test_anonymous_and_internal_public_field_rejected(api_client, context):
    if context['internal']:
        assert close(api_client, context, customer_resolution='No corresponde').status_code == 422
    assert api_client.post(context['path'] + '/close', headers={'Authorization': ''}, json={}).status_code == 401
    assert api_client.post(context['path'] + '/close', json={}).status_code == 422


def test_public_resolution_keeps_existing_edit_requirement(api_client, context, db_session):
    if context['internal']: return
    authenticate_with(api_client, db_session, ['tickets.close'])
    assert close(api_client, context, customer_resolution='Sin permiso de edición').status_code == 403
    # The forbidden combined write did not close or modify either resolution.
    item = db_session.get(Ticket, context['item']['id'])
    assert item.status == 'OPEN' and item.customer_resolution == 'Información pública anterior'


def test_simultaneous_closes_serialize_in_postgresql(postgres_engine):
    suffix = str(uuid4())
    with Session(postgres_engine) as session:
        sector, department, kind = Sector(name=suffix), Department(name=suffix), InternalIncidentType(name=suffix)
        session.add_all([sector, department, kind]); session.flush()
        item = InternalTicket(ticket_number=1000000000, reference=suffix, title='Concurrente', description='Prueba',
            sector_id=sector.id, department_id=department.id, incident_type_id=kind.id,
            status='OPEN', start_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        session.add(item); session.commit(); session.refresh(item)
        id, revision = item.id, item.updated_at
        ids = sector.id, department.id, kind.id
    barrier = Barrier(2)
    def attempt(number):
        with Session(postgres_engine) as session:
            barrier.wait(timeout=5)
            try:
                close_ticket(session, InternalTicket, id, TicketClose(expected_updated_at=revision, resolution=f'Resolución {number}'),
                    SimpleNamespace(permissions={'internal_tickets.close'}), 'internal_tickets',
                    lambda s, id, values: internal_ticket_data.persist(s, values, id))
                return 200
            except HTTPException as error: return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool: assert sorted(pool.map(attempt, [1, 2])) == [200, 409]
        with Session(postgres_engine) as session:
            assert session.get(InternalTicket, id).status == 'CLOSED'
            assert session.scalar(select(func.count()).select_from(InternalTicketUpdate).where(InternalTicketUpdate.ticket_id == id)) == 1
    finally:
        with Session(postgres_engine) as session:
            session.execute(delete(InternalTicketUpdate).where(InternalTicketUpdate.ticket_id == id))
            session.execute(delete(InternalTicket).where(InternalTicket.id == id))
            for model, key in zip((Sector, Department, InternalIncidentType), ids): session.execute(delete(model).where(model.id == key))
            session.commit()


def test_closure_preserves_escalations_and_ack_history(api_client, context):
    reason = api_client.post('/api/escalation-reasons', json={'name': 'Apoyo de prueba'}).json()
    escalation = api_client.post(context['path'] + '/escalations', json={
        'department_id': context['item']['department_id'], 'reason_id': reason['id'],
        'description': 'Apoyo documentado', 'started_at': context['item']['start_at']})
    assert escalation.status_code == 201, escalation.text
    ack = api_client.post(context['path'] + '/ack', json={'duration_type': 'INDEFINITE', 'reason': 'Trabajo en curso'})
    assert ack.status_code == 201, ack.text
    before = api_client.get(context['path'] + '/escalations').json()
    assert close(api_client, context).status_code == 200
    assert api_client.get(context['path'] + '/escalations').json() == before
    history = api_client.get(context['path'] + '/acks').json()
    assert len(history) == 1 and history[0]['id'] == ack.json()['id']
    assert history[0]['active'] is False and history[0]['revoked_reason'] == 'Cierre de ticket'
    assert api_client.get(context['path'] + '/ack').status_code == 204
    recommendations = api_client.get(context['path'] + '/recommendations').json()
    assert recommendations['recommendations'] == [] and recommendations['has_active_ack'] is False
