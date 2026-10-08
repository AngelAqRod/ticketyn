from io import BytesIO
import re

import pytest
from sqlalchemy import event

from test_ticket_exports import pdf_strings  # shared ReportLab text capture
from test_ticket_updates import ticket, create
from ticketyn.api.ticket_reports import customer_report


def report(client, item, kind='internal', **params):
    return client.get(f"/api/tickets/{item['id']}/reports/{kind}/pdf", params=params)


@pytest.mark.parametrize('audience', ['internal', 'customer'])
@pytest.mark.parametrize('status', ['OPEN', 'CLOSED'])
def test_valid_empty_history_and_duration(api_client, ticket_payload, audience, status, pdf_strings):
    item = ticket(api_client, ticket_payload, status=status, end_at='2020-01-01T13:00:00Z' if status == 'CLOSED' else None)
    before = api_client.get(f"/api/tickets/{item['id']}").json()
    response = report(api_client, item, audience, timezone='Etc/GMT+6')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert 'attachment;' in response.headers['content-disposition']
    assert ('interno' if audience == 'internal' else 'cliente') in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    assert response.content.startswith(b'%PDF-') and b'%%EOF' in response.content
    words = ' '.join(pdf_strings)
    assert 'Ticketyn' in words and 'Emitido:' in words and 'Página 1 / 1' in words
    assert '01/01/2020 06:00:00 -0600' in words
    assert ('Tiempo transcurrido' if status == 'OPEN' else '1 h') in words
    assert ('Sin intervenciones' in words)
    assert api_client.get(f"/api/tickets/{item['id']}").json() == before


def test_customer_projection_and_pdf_exclude_all_unauthorized_fields(api_client, ticket_payload, db_session, pdf_strings):
    responsible = api_client.post('/api/responsibles', json={'name': 'PRIVADO-RESPONSABLE'}).json()
    api_client.patch(f"/api/incident-types/{ticket_payload['incident_type_id']}", json={'name': 'PRIVADO-TIPO'})
    item = ticket(api_client, ticket_payload, responsible_id=responsible['id'], title='Título del incidente', description='PRIVADO-DESCRIPCION 10.44.55.66', resolution='PRIVADO-RESOLUCION')
    create(api_client, item, content='PRIVADO-INTERVENCION', visibility='INTERNAL')
    create(api_client, item, content='PUBLICO-INTERVENCION', visibility='PUBLIC', responsible_id=responsible['id'])
    projection = customer_report(db_session, item['id'])
    assert not hasattr(projection, 'description') and not hasattr(projection, 'resolution')
    assert not hasattr(projection, 'department') and not hasattr(projection, 'responsible')
    response = report(api_client, item, 'customer')
    assert response.status_code == 200
    words = ' '.join(pdf_strings)
    assert 'PUBLICO-INTERVENCION' in words and 'Título del incidente' in words
    for secret in ['PRIVADO-', '10.44.55.66', 'Cambio de resolución', 'Departamento', 'Sin asignar', 'Tipo de incidencia']:
        assert secret not in words
    assert 'Sin descripción autorizada' in words and 'Sin resolución autorizada' in words
    pdf_strings.clear()
    api_client.patch(f"/api/tickets/{item['id']}", json={'customer_description': 'AUTORIZADO-DESCRIPCION', 'customer_resolution': 'AUTORIZADO-RESOLUCION'})
    assert report(api_client, item, 'customer').status_code == 200
    words = ' '.join(pdf_strings)
    assert 'AUTORIZADO-DESCRIPCION' in words and 'AUTORIZADO-RESOLUCION' in words
    assert 'PRIVADO-' not in words
    pdf_strings.clear()
    api_client.patch(f"/api/tickets/{item['id']}", json={'customer_description': None, 'customer_resolution': None})
    report(api_client, item, 'customer')
    assert 'AUTORIZADO-' not in ' '.join(pdf_strings)


@pytest.mark.parametrize('audience', ['internal', 'customer'])
def test_chronology_retroactive_and_equal_dates(api_client, ticket_payload, audience, pdf_strings):
    item = ticket(api_client, ticket_payload)
    create(api_client, item, content='POSTERIOR', occurred_at='2025-01-01T12:00:00Z', visibility='PUBLIC')
    create(api_client, item, content='RETROACTIVA-UNO', occurred_at='2010-01-01T12:00:00Z', visibility='PUBLIC')
    create(api_client, item, content='RETROACTIVA-DOS', occurred_at='2010-01-01T12:00:00Z', visibility='PUBLIC')
    assert report(api_client, item, audience).status_code == 200
    words = ' '.join(pdf_strings)
    assert words.index('RETROACTIVA-UNO') < words.index('RETROACTIVA-DOS') < words.index('POSTERIOR')


def test_internal_fields_responsible_and_both_visibilities(api_client, ticket_payload, pdf_strings):
    responsible = api_client.post('/api/responsibles', json={'name': 'Técnico histórico'}).json()
    node = api_client.post('/api/nodes', json={'name': 'Nodo histórico'}).json()
    api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={'node_id': node['id']})
    item = ticket(api_client, ticket_payload, responsible_id=responsible['id'], description='DESCRIPCION-INTERNA', resolution='RESOLUCION-INTERNA')
    create(api_client, item, content='INTERNA', responsible_id=responsible['id'])
    create(api_client, item, content='PUBLICA', visibility='PUBLIC')
    api_client.patch(f"/api/responsibles/{responsible['id']}", json={'active': False})
    api_client.patch(f"/api/nodes/{node['id']}", json={'active': False})
    assert report(api_client, item).status_code == 200
    words = ' '.join(pdf_strings)
    for required in ['DESCRIPCION-INTERNA', 'RESOLUCION-INTERNA', 'INTERNA', 'PUBLICA', 'Técnico histórico', 'Nodo histórico', 'Departamento', 'Tipo de incidencia']:
        assert required in words


@pytest.mark.parametrize('audience', ['internal', 'customer'])
def test_long_special_content_multipage_all_updates(api_client, ticket_payload, audience, pdf_strings):
    long = ('Caracteres ñ á & <texto> /\n' * 80) + 'SINESPACIOS' * 80
    item = ticket(api_client, ticket_payload, description=long, resolution=long, customer_description=long, customer_resolution=long)
    for number in range(24):
        create(api_client, item, content=f'Intervención-{number:02} ' + long, visibility='PUBLIC')
    response = report(api_client, item, audience)
    assert response.status_code == 200
    pages = re.findall(rb'/Type\s*/Page\b', response.content)
    assert len(pages) > 2
    words = ' '.join(pdf_strings)
    assert 'Intervención-00' in words and 'Intervención-23' in words and '<texto>' in words
    assert f'Página {len(pages)} / {len(pages)}' in words


@pytest.mark.parametrize('audience', ['internal', 'customer'])
def test_closed_without_end_and_open_with_end_not_last_update(api_client, ticket_payload, audience, pdf_strings):
    item = ticket(api_client, ticket_payload, status='CLOSED')
    create(api_client, item, occurred_at='2030-01-01T00:00:00Z')
    assert report(api_client, item, audience).status_code == 200
    assert 'No disponible' in ' '.join(pdf_strings)
    pdf_strings.clear()
    api_client.patch(f"/api/tickets/{item['id']}", json={'status': 'OPEN', 'end_at': '2020-01-01T13:00:00Z'})
    assert report(api_client, item, audience).status_code == 200
    words = ' '.join(pdf_strings)
    assert 'Tiempo transcurrido' in words and 'no es tiempo de resolución' in words


@pytest.mark.parametrize('audience', ['internal', 'customer'])
def test_missing_ticket_and_query_cannot_enable_private_content(api_client, ticket_payload, audience):
    assert api_client.get(f'/api/tickets/999999/reports/{audience}/pdf').status_code == 404
    item = ticket(api_client, ticket_payload)
    for query in [{'timezone': 'Not/AZone'}, {'visibility': 'INTERNAL'}, {'include_internal': 'true'}, {'audience': 'internal'}]:
        assert report(api_client, item, audience, **query).status_code == 422


def test_error_response_redacted_and_spool_closed(api_client, ticket_payload, monkeypatch):
    from ticketyn.api import ticket_reports
    item = ticket(api_client, ticket_payload)
    spool = BytesIO()
    monkeypatch.setattr(ticket_reports, 'SpooledTemporaryFile', lambda **kwargs: spool)
    def fail(*args): raise RuntimeError('PRIVADO password DB description')
    monkeypatch.setattr(ticket_reports, 'customer_pdf', fail)
    result = report(api_client, item, 'customer')
    assert result.status_code == 500
    assert 'PRIVADO' not in result.text and spool.closed


def test_customer_query_does_not_fetch_internal_texts(api_client, ticket_payload, db_session):
    item = ticket(api_client, ticket_payload)
    statements = []
    connection = db_session.connection()
    def capture(conn, cursor, statement, parameters, context, many): statements.append(statement)
    event.listen(connection, 'before_cursor_execute', capture)
    try:
        data = customer_report(db_session, item['id'])
        assert data.interventions == []
    finally:
        event.remove(connection, 'before_cursor_execute', capture)
    assert len(statements) == 2
    assert all('tickets.description' not in sql and 'tickets.resolution' not in sql and 'responsibles' not in sql for sql in statements)


@pytest.mark.parametrize('audience', ['internal', 'customer'])
def test_renderer_directly_without_prior_exports(api_client, ticket_payload, db_session, audience):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from ticketyn.api.ticket_reports import internal_pdf, customer_pdf
    item = ticket(api_client, ticket_payload)
    output = BytesIO()
    (internal_pdf if audience == 'internal' else customer_pdf)(db_session, item['id'], output, ZoneInfo('UTC'), datetime.now(timezone.utc))
    assert output.getvalue().startswith(b'%PDF-')


def test_real_pdf_parser_validates_document_and_privacy(api_client, ticket_payload):
    import shutil
    import subprocess
    if not shutil.which('pdfinfo') or not shutil.which('pdftotext'):
        pytest.skip('Poppler opcional para validación independiente del documento')
    item = ticket(api_client, ticket_payload, description='SECRETO-ORIGINAL', resolution='SECRETO-RESOLUCION',
                  customer_description='Autorizado ñ & <contenido>')
    create(api_client, item, content='SECRETO-SEGUIMIENTO', visibility='INTERNAL')
    create(api_client, item, content='Seguimiento público á', visibility='PUBLIC')
    for kind in ('internal', 'customer'):
        response = report(api_client, item, kind)
        assert response.status_code == 200
        info = subprocess.run(['pdfinfo', '-'], input=response.content, capture_output=True, check=True)
        assert b'Pages:' in info.stdout
        extracted = subprocess.run(['pdftotext', '-', '-'], input=response.content, capture_output=True, check=True).stdout.decode()
        assert 'Ticketyn' in extracted and 'Emitido:' in extracted and 'Página' in extracted
        if kind == 'customer':
            assert 'SECRETO-' not in extracted
            assert 'Autorizado ñ & <contenido>' in extracted and 'Seguimiento público á' in extracted
        else:
            assert all(secret in extracted for secret in ['SECRETO-ORIGINAL', 'SECRETO-RESOLUCION', 'SECRETO-SEGUIMIENTO'])
