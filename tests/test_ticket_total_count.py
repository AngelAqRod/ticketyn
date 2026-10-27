"""X-Total-Count: total filtrado real, independiente de la paginación y de la autorización."""
from test_tickets import create_ticket
from test_security_foundation import security_client, make_account, login, authorize  # noqa: F401


def total(response):
    assert response.status_code == 200, response.text
    return int(response.headers['X-Total-Count'])


def test_total_ignores_page_size_and_matches_filters(api_client, ticket_payload):
    for index in range(5):
        create_ticket(api_client, {**ticket_payload, 'status': 'OPEN' if index < 3 else 'CLOSED',
                                   'end_at': None if index < 3 else '2020-01-02T00:00:00Z'})
    page = api_client.get('/api/tickets', params={'limit': 2, 'offset': 0})
    assert len(page.json()) == 2 and total(page) == 5
    assert total(api_client.get('/api/tickets', params={'limit': 2, 'offset': 4})) == 5      # última página parcial
    out_of_range = api_client.get('/api/tickets', params={'limit': 2, 'offset': 100})
    assert out_of_range.json() == [] and total(out_of_range) == 5                           # fuera de rango
    open_page = api_client.get('/api/tickets', params={'status': 'OPEN', 'limit': 1})
    assert len(open_page.json()) == 1 and total(open_page) == 3                             # filtro de estado
    combined = api_client.get('/api/tickets', params={'status': 'CLOSED', 'customer_id': ticket_payload['customer_id'], 'search': 'Caída'})
    assert total(combined) == 2 and len(combined.json()) == 2                                # filtros combinados
    empty = api_client.get('/api/tickets', params={'search': 'sin-coincidencias'})
    assert empty.json() == [] and total(empty) == 0                                          # sin coincidencias


def test_total_for_internal_tickets(api_client):
    response = api_client.get('/api/internal-tickets', params={'limit': 1})
    assert response.status_code == 200 and response.headers['X-Total-Count'] == str(len(api_client.get('/api/internal-tickets', params={'limit': 200}).json()))


def test_denied_role_gets_no_total(security_client):
    client, app, factory = security_client
    make_account(factory, role='CUSTOM')
    authorize(client, login(client))
    response = client.get('/api/tickets')
    assert response.status_code == 403 and 'X-Total-Count' not in response.headers
