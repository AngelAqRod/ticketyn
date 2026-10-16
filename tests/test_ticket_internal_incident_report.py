"""Only the internal client-ticket PDF may project a related internal incident."""
import pytest
from sqlalchemy import event
from test_ticket_exports import pdf_strings
from test_ticket_reports import report
from test_ticket_updates import ticket


def linked_ticket(client, ticket_payload, *, node=True, provider=True):
    def create(path, values):
        response = client.post('/api/' + path, json=values)
        assert response.status_code == 201, response.text
        return response.json()
    sector = create('sectors', {'name': 'SECTOR-INTERNO-RESERVADO'})
    kind = create('internal-incident-types', {'name': 'Infraestructura reservada'})
    n = create('nodes', {'name': 'NODO-INTERNO-RESERVADO'}) if node else None
    p = create('providers', {'name': 'PROVEEDOR-INTERNO-RESERVADO'}) if provider else None
    internal = create('internal-tickets', {
        'title': 'INCIDENCIA-INTERNA-RESERVADA & <NOC>',
        'description': 'DESCRIPCION-INTERNA-RESERVADA',
        'sector_id': sector['id'], 'node_id': n['id'] if n else None,
        'provider_id': p['id'] if p else None,
        'department_id': ticket_payload['department_id'], 'incident_type_id': kind['id'],
        'start_at': '2026-10-15T08:00:00-06:00',
    })
    normal = ticket(client, ticket_payload, internal_ticket_id=internal['id'])
    return normal, internal, sector, n, p


def test_linked_internal_report_current_state_and_inactive_references(api_client, ticket_payload, db_session, pdf_strings):
    normal, internal, sector, node, provider = linked_ticket(api_client, ticket_payload)
    api_client.patch(f"/api/internal-tickets/{internal['id']}", json={'status': 'CLOSED'})
    for path, row in [('sectors', sector), ('nodes', node), ('providers', provider)]:
        assert api_client.patch(f"/api/{path}/{row['id']}", json={'active': False}).status_code == 200
    statements = []
    def capture(_connection, _cursor, statement, *_args):
        statements.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        result = report(api_client, normal)
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert result.status_code == 200
    words = ' '.join(pdf_strings)
    for text in ['Incidencia interna relacionada', internal['reference'], internal['title'], sector['name'], node['name'], provider['name'], 'Estado actual', 'Cerrado']:
        assert text in words
    assert words.count('Incidencia interna relacionada') == 1
    assert sum('FROM internal_tickets' in sql for sql in statements) == 1
    assert 'DESCRIPCION-INTERNA-RESERVADA' not in words  # Title suffices; no duplicate incidence text.
    assert api_client.get(f"/api/tickets/{normal['id']}").json()['node_id'] == ticket_payload['node_id']


def test_optional_node_and_provider(api_client, ticket_payload, pdf_strings):
    normal, internal, *_ = linked_ticket(api_client, ticket_payload, node=False, provider=False)
    assert report(api_client, normal).status_code == 200
    words = ' '.join(pdf_strings)
    assert internal['reference'] in words and 'Proveedor atribuible' in words and 'Ninguno' in words
    assert 'NODO-INTERNO-RESERVADO' not in words
    assert 'Abierto' in words


@pytest.mark.parametrize('linked', [False, True])
def test_customer_report_never_reads_or_discloses_internal_incident(api_client, ticket_payload, db_session, pdf_strings, linked):
    normal = linked_ticket(api_client, ticket_payload)[0] if linked else ticket(api_client, ticket_payload)
    statements = []
    def capture(_connection, _cursor, statement, *_args): statements.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        assert report(api_client, normal, 'customer').status_code == 200
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    words = ' '.join(pdf_strings)
    assert 'Incidencia interna relacionada' not in words
    assert 'INTERNO-RESERVADO' not in words and 'INTERNA-RESERVADA' not in words
    assert not any('internal_tickets' in sql for sql in statements)


def test_unlinked_internal_report_does_not_query_related_incidents(api_client, ticket_payload, db_session, pdf_strings):
    normal = ticket(api_client, ticket_payload)
    statements = []
    def capture(_connection, _cursor, statement, *_args): statements.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        assert report(api_client, normal).status_code == 200
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert 'Incidencia interna relacionada' not in ' '.join(pdf_strings)
    assert not any('internal_tickets' in sql for sql in statements)
