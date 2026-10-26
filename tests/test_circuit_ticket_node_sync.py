"""Recent-only node (HUB) corrections; all databases are disposable test fixtures."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from ticketyn.api import circuit_ticket_nodes as sync
from ticketyn.api.circuits import patch_circuit
from ticketyn.api.ticket_data import create_ticket
from ticketyn.models import Circuit, Node, Ticket, TicketUpdate
from ticketyn.schemas.circuit import CircuitUpdate
from test_ticket_concurrency import concurrent_database


@pytest.fixture
def correction_clock(monkeypatch):
    clock = [datetime(2026, 10, 16, 18, 0, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(sync, 'correction_time', lambda session: clock[0])
    return clock


def new_node(client, name='Nodo Corregido B'):
    response = client.post('/api/nodes', json={'name': name})
    assert response.status_code == 201, response.text
    return response.json()


def ticket(client, session, payload, created_at, **values):
    response = client.post('/api/tickets', json={**payload, **values})
    assert response.status_code == 201, response.text
    id = response.json()['id']
    session.execute(update(Ticket).where(Ticket.id == id).values(
        created_at=created_at,
        updated_at=datetime(2026, 10, 16, 17, 59, tzinfo=timezone.utc)
    ))
    session.commit()
    session.expire_all()
    return id


def snapshot(session, id):
    return dict(session.execute(select(Ticket.__table__).where(Ticket.id == id)).mappings().one())


def history(session, id):
    return [dict(row) for row in session.execute(
        select(TicketUpdate.__table__).where(TicketUpdate.ticket_id == id).order_by(TicketUpdate.id)
    ).mappings()]


@pytest.mark.parametrize('status', ['OPEN', 'CLOSED'])
@pytest.mark.parametrize('age,eligible', [
    (timedelta(days=1), True),
    (timedelta(days=6), True),
    (timedelta(hours=168), True),
    (timedelta(hours=168, microseconds=1), False),
    (timedelta(days=8), False),
    (timedelta(days=15), False),
    (timedelta(days=30), False),
    (timedelta(0), True),
    (timedelta(seconds=-1), False),
])
def test_exact_creation_window_and_status_preserves_every_other_field(
    api_client, ticket_payload, db_session, correction_clock, status, age, eligible
):
    now = correction_clock[0]
    node = new_node(api_client, 'HUB B')
    id = ticket(
        api_client, db_session, ticket_payload, now - age,
        status=status, end_at='2020-01-01T13:00:00Z' if status == 'CLOSED' else None
    )
    before = snapshot(db_session, id)

    # Modificar el HUB del circuito
    response = api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={'node_id': node['id']})
    assert response.status_code == 200, response.text

    after = snapshot(db_session, id)
    assert after == {**before, 'node_id': node['id'] if eligible else before['node_id']}

    # Comprobar que updated_at, status, start_at, end_at, etc. no fueron alterados
    assert after['updated_at'] == before['updated_at']
    assert after['status'] == before['status']
    assert after['responsible_id'] == before['responsible_id']

    logs = history(db_session, id)
    assert len(logs) == int(eligible)
    if eligible:
        assert logs[0]['content'] == 'Nodo actualizado automáticamente de «Nodo de prueba» a «HUB B» por modificación del circuito asociado.'
        assert logs[0]['occurred_at'] == now and logs[0]['created_at'] == now
        assert logs[0]['responsible_id'] is None and logs[0]['escalation_id'] is None
        assert logs[0]['visibility'] == 'INTERNAL'

        # Lectura posterior desde la ficha (GET /api/tickets/{id})
        detail = api_client.get(f'/api/tickets/{id}').json()
        assert detail['node']['id'] == node['id']
        assert detail['node']['name'] == 'HUB B'
    else:
        # Ticket histórico conserva su HUB original
        detail = api_client.get(f'/api/tickets/{id}').json()
        assert detail['node']['id'] == before['node_id']


def test_list_and_detail_consistency_after_hub_change(api_client, ticket_payload, db_session, correction_clock):
    now = correction_clock[0]
    hub_b = new_node(api_client, 'HUB B')
    cid = ticket_payload['circuit_id']

    # Ticket 1: 2 días (elegible)
    t1 = ticket(api_client, db_session, ticket_payload, now - timedelta(days=2))
    # Ticket 2: 6 días (elegible)
    t2 = ticket(api_client, db_session, ticket_payload, now - timedelta(days=6))
    # Ticket 3: 15 días (histórico, no elegible)
    t3 = ticket(api_client, db_session, ticket_payload, now - timedelta(days=15))

    # Cambiar HUB de A -> B
    res = api_client.patch(f'/api/circuits/{cid}', json={'node_id': hub_b['id']})
    assert res.status_code == 200

    # Lectura desde ficha de detalle
    assert api_client.get(f'/api/tickets/{t1}').json()['node']['id'] == hub_b['id']
    assert api_client.get(f'/api/tickets/{t2}').json()['node']['id'] == hub_b['id']
    assert api_client.get(f'/api/tickets/{t3}').json()['node']['id'] == ticket_payload['node_id']

    # Lectura desde listado con filtros por HUB
    hub_b_tickets = api_client.get('/api/tickets', params={'node_id': hub_b['id']}).json()
    hub_b_ids = [t['id'] for t in hub_b_tickets]
    assert t1 in hub_b_ids
    assert t2 in hub_b_ids
    assert t3 not in hub_b_ids

    hub_a_tickets = api_client.get('/api/tickets', params={'node_id': ticket_payload['node_id']}).json()
    hub_a_ids = [t['id'] for t in hub_a_tickets]
    assert t3 in hub_a_ids
    assert t1 not in hub_a_ids
    assert t2 not in hub_a_ids


def test_ticket_edit_and_save_preserves_hub_without_reversion(api_client, ticket_payload, db_session, correction_clock):
    now = correction_clock[0]
    hub_b = new_node(api_client, 'HUB B')
    cid = ticket_payload['circuit_id']

    # Crear ticket reciente (1 día) y ticket histórico (15 días)
    recent_id = ticket(api_client, db_session, ticket_payload, now - timedelta(days=1))
    historical_id = ticket(api_client, db_session, ticket_payload, now - timedelta(days=15))

    # Cambiar HUB del circuito
    api_client.patch(f'/api/circuits/{cid}', json={'node_id': hub_b['id']})

    # Editar y guardar el ticket reciente: debe mantener HUB B
    patch_recent = api_client.patch(f'/api/tickets/{recent_id}', json={'title': 'Título actualizado'})
    assert patch_recent.status_code == 200
    assert patch_recent.json()['node']['id'] == hub_b['id']
    assert api_client.get(f'/api/tickets/{recent_id}').json()['node']['id'] == hub_b['id']

    # Editar y guardar el ticket histórico: debe conservar HUB A
    patch_hist = api_client.patch(f'/api/tickets/{historical_id}', json={'title': 'Histórico actualizado'})
    assert patch_hist.status_code == 200
    assert patch_hist.json()['node']['id'] == ticket_payload['node_id']
    assert api_client.get(f'/api/tickets/{historical_id}').json()['node']['id'] == ticket_payload['node_id']


def test_unrelated_circuit_tickets_untouched(api_client, ticket_payload, db_session, correction_clock):
    now = correction_clock[0]
    hub_b = new_node(api_client, 'HUB B')

    # Crear otro circuito
    other_circuit = api_client.post('/api/circuits', json={
        'customer_id': ticket_payload['customer_id'],
        'node_id': ticket_payload['node_id'],
        'sector_id': ticket_payload['sector_id'],
        'circuit_code': 'OTHER-CIRC-HUB',
        'description': 'Circuito B'
    }).json()

    # Ticket de otro circuito creado hace 1 día
    other_ticket = ticket(api_client, db_session, {**ticket_payload, 'circuit_id': other_circuit['id']}, now - timedelta(days=1))
    before_other = snapshot(db_session, other_ticket)

    # Modificar el circuito principal
    api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={'node_id': hub_b['id']})

    # El ticket del otro circuito no sufre ningún cambio
    assert snapshot(db_session, other_ticket) == before_other
    assert history(db_session, other_ticket) == []


def test_second_hub_change_sliding_window(api_client, ticket_payload, db_session, correction_clock):
    now = correction_clock[0]
    hub_b = new_node(api_client, 'HUB B')
    hub_c = new_node(api_client, 'HUB C')
    cid = ticket_payload['circuit_id']

    aging = ticket(api_client, db_session, ticket_payload, now - timedelta(hours=167))
    recent = ticket(api_client, db_session, ticket_payload, now - timedelta(hours=1))

    # Primer cambio: A -> B
    assert api_client.patch(f'/api/circuits/{cid}', json={'node_id': hub_b['id']}).status_code == 200
    assert snapshot(db_session, aging)['node_id'] == hub_b['id']
    assert snapshot(db_session, recent)['node_id'] == hub_b['id']

    # Avanza el reloj 2 horas: aging ahora tiene 169 horas (> 168h), recent tiene 3 horas
    correction_clock[0] += timedelta(hours=2)

    # Segundo cambio: B -> C
    assert api_client.patch(f'/api/circuits/{cid}', json={'node_id': hub_c['id']}).status_code == 200

    # aging conserva HUB B (quedó fuera de la ventana de 7 días al momento del 2do cambio)
    assert snapshot(db_session, aging)['node_id'] == hub_b['id']
    assert len(history(db_session, aging)) == 1

    # recent se actualiza a HUB C (sigue dentro de la ventana)
    assert snapshot(db_session, recent)['node_id'] == hub_c['id']
    recent_history = history(db_session, recent)
    assert len(recent_history) == 2
    assert recent_history[1]['content'] == 'Nodo actualizado automáticamente de «HUB B» a «HUB C» por modificación del circuito asociado.'
    assert recent_history[1]['occurred_at'] == correction_clock[0]


def test_circuit_save_failure_rolls_back_nodes(api_client, ticket_payload, db_session, correction_clock):
    hub_b = new_node(api_client, 'HUB B')
    cid = ticket_payload['circuit_id']
    id = ticket(api_client, db_session, ticket_payload, correction_clock[0] - timedelta(days=1))
    before = snapshot(db_session, id)

    # Crear circuito duplicado para forzar 409
    dup = api_client.post('/api/circuits', json={
        'customer_id': ticket_payload['customer_id'],
        'node_id': ticket_payload['node_id'],
        'sector_id': ticket_payload['sector_id'],
        'circuit_code': 'DUPLICATE-CODE',
        'description': 'Circuito duplicado'
    }).json()

    # Intentar cambiar node_id y circuit_code al duplicado
    res = api_client.patch(f'/api/circuits/{cid}', json={'node_id': hub_b['id'], 'circuit_code': dup['circuit_code']})
    assert res.status_code == 409

    # Todo se revirtió
    assert snapshot(db_session, id) == before
    assert history(db_session, id) == []
    assert api_client.get(f'/api/circuits/{cid}').json()['node_id'] == ticket_payload['node_id']


def test_ticket_lock_conflict_on_node_sync_is_atomic(concurrent_database, correction_clock):
    from ticketyn.security.permissions import DEFAULT_GRANTS
    request = SimpleNamespace(state=SimpleNamespace(principal=SimpleNamespace(permissions=DEFAULT_GRANTS['SUPERADMIN'])))
    engine, payload = concurrent_database
    with Session(engine) as session:
        hub_b = Node(name='HUB B Concurrente')
        session.add(hub_b)
        session.commit()
        hub_id = hub_b.id
        item = create_ticket(session, payload.copy())
        id = item.id
        session.execute(update(Ticket).where(Ticket.id == id).values(
            created_at=correction_clock[0] - timedelta(days=1),
            updated_at=Ticket.updated_at
        ))
        session.commit()

    with Session(engine) as holder:
        holder.execute(select(Ticket.id).where(Ticket.id == id).with_for_update())
        with Session(engine) as contender:
            with pytest.raises(HTTPException) as failure:
                patch_circuit(payload['circuit_id'], CircuitUpdate(node_id=hub_id), contender, request)
            assert failure.value.status_code == 409
            assert contender.scalar(select(Circuit.node_id).where(Circuit.id == payload['circuit_id'])) == payload['node_id']
            assert contender.scalar(select(func.count()).select_from(TicketUpdate)) == 0

    with Session(engine) as session:
        patch_circuit(payload['circuit_id'], CircuitUpdate(node_id=hub_id), session, request)
        assert snapshot(session, id)['node_id'] == hub_id
        assert len(history(session, id)) == 1
