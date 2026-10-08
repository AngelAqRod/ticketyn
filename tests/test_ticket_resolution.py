import pytest
from sqlalchemy import select

from ticketyn.models import TicketUpdate
from test_ticket_updates import ticket, url


def test_legacy_ticket_defaults_and_resolution_on_close(api_client, ticket_payload):
    item = ticket(api_client, ticket_payload)
    assert all(item[field] is None for field in ('resolution', 'customer_description', 'customer_resolution'))
    response = api_client.patch(f"/api/tickets/{item['id']}", json={'status': 'CLOSED', 'resolution': 'Se reemplazó el enlace ñ.'})
    assert response.status_code == 200
    changed = response.json()
    assert changed['resolution'] == 'Se reemplazó el enlace ñ.' and changed['status'] == 'CLOSED'
    assert (changed['start_at'], changed['end_at']) == (item['start_at'], item['end_at'])
    changes = api_client.get(url(item)).json()
    assert len(changes) == 1 and changes[0]['visibility'] == 'INTERNAL'
    assert 'Se reemplazó el enlace ñ.' in changes[0]['content']
    assert changes[0]['responsible_id'] is None


def test_correct_and_clear_resolution_without_changing_closed_dates(api_client, ticket_payload):
    item = ticket(api_client, ticket_payload, status='CLOSED', end_at='2020-01-01T13:00:00Z')
    path = f"/api/tickets/{item['id']}"
    for resolution in ('Original', 'Corregida', 'Corregida', None):
        response = api_client.patch(path, json={'resolution': resolution})
        assert response.status_code == 200
        changed = response.json()
        assert changed['resolution'] == resolution
        assert (changed['start_at'], changed['end_at'], changed['status']) == (item['start_at'], item['end_at'], 'CLOSED')
    changes = api_client.get(url(item)).json()
    assert len(changes) == 3  # guardar sin cambios no fabrica historial
    assert 'Anterior: Original\nNueva: Corregida' in changes[1]['content']
    assert 'Anterior: Corregida\nNueva: Sin resolución' in changes[2]['content']
    assert all(update['visibility'] == 'INTERNAL' for update in changes)


def test_resolution_on_create_is_recorded_atomically(api_client, ticket_payload):
    item = ticket(api_client, ticket_payload, resolution='Solución inicial', status='CLOSED')
    assert item['resolution'] == 'Solución inicial'
    assert len(api_client.get(url(item)).json()) == 1


@pytest.mark.parametrize('field', ['resolution', 'customer_description', 'customer_resolution'])
@pytest.mark.parametrize('value', ['', ' \n\t', 'x' * 10001, 123])
def test_content_validation_and_failed_patch_preserves_ticket(api_client, ticket_payload, field, value):
    item = ticket(api_client, ticket_payload)
    path = f"/api/tickets/{item['id']}"
    assert api_client.patch(path, json={field: value}).status_code == 422
    assert api_client.get(path).json() == item
    assert api_client.get(url(item)).json() == []
    assert api_client.post('/api/tickets', json={**ticket_payload, field: value}).status_code == 422


@pytest.mark.parametrize('field', ['resolution', 'customer_description', 'customer_resolution'])
def test_limit_and_explicit_authorization_no_fallback(api_client, ticket_payload, field):
    item = ticket(api_client, ticket_payload, **{field: 'ñ' * 10000})
    assert len(item[field]) == 10000
    for other in {'resolution', 'customer_description', 'customer_resolution'} - {field}:
        assert item[other] is None
    changed = api_client.patch(f"/api/tickets/{item['id']}", json={field: None}).json()
    assert changed[field] is None


def test_invalid_relation_does_not_record_resolution_change(api_client, ticket_payload, db_session):
    item = ticket(api_client, ticket_payload)
    result = api_client.patch(f"/api/tickets/{item['id']}", json={'resolution': 'No guardar', 'circuit_id': 999999})
    assert result.status_code == 404
    assert db_session.scalars(select(TicketUpdate).where(TicketUpdate.ticket_id == item['id'])).all() == []
    assert api_client.get(f"/api/tickets/{item['id']}").json() == item
