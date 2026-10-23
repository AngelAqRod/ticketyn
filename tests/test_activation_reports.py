from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import event
from ticketyn.models.fms import Activation, ActivationIntervention
from test_fms import operation_payload
from test_ticket_exports import pdf_strings


@pytest.fixture
def activation(api_client, operation_payload):
    response = api_client.post('/api/activations', json={**operation_payload, 'effective_at': '2020-01-01T12:00:00Z'})
    assert response.status_code == 201
    return response.json()


def report(client, id, **query):
    return client.get(f'/api/activations/{id}/reports/pdf', params=query)


def test_general_empty_log_and_historical_values(api_client, activation, ticket_payload, pdf_strings):
    service = api_client.post('/api/service-types', json={'name': 'Servicio actual & especial'}).json()
    node = api_client.post('/api/nodes', json={'name': 'NODO ACTUAL DIFERENTE'}).json()
    sector = api_client.post('/api/sectors', json={'name': 'SECTOR ACTUAL DIFERENTE'}).json()
    assert api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={'node_id': node['id'], 'sector_id': sector['id'], 'service_type_id': service['id']}).status_code == 200
    before = api_client.get(f"/api/activations/{activation['id']}").json()
    response = report(api_client, activation['id'])
    assert response.status_code == 200 and response.content.startswith(b'%PDF') and b'%%EOF' in response.content
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert f"ticketyn-activacion-{activation['id']}.pdf" in response.headers['content-disposition']
    content = ' '.join(pdf_strings)
    for value in [activation['reference'], 'Cliente de prueba', 'MANUAL-CIRCUIT', 'Enlace de prueba', 'Sector de prueba', 'Nodo de prueba', 'Operador FMS', 'Tipo de servicio histórico', 'Capacidad inicial histórica', 'Sin registrar', '01/01/2020 06:00:00 -0600', 'Sin intervenciones registradas.', 'Fecha de creación:', 'Generado:', 'Página 1 / 1']:
        assert value in content
    assert 'Servicio actual & especial' not in content
    assert 'NODO ACTUAL DIFERENTE' not in content and 'SECTOR ACTUAL DIFERENTE' not in content
    assert 'Última actualización' not in content  # This model has no such metadata.
    assert api_client.get(f"/api/activations/{activation['id']}").json() == before
    Path('/tmp/ticketyn-activation-empty.pdf').write_bytes(response.content)


def test_complete_log_is_ordered_and_scoped_with_multiple_pages(api_client, activation, operation_payload, db_session, pdf_strings):
    other = api_client.post('/api/activations', json=operation_payload).json()
    records = []
    for index in range(65):
        # Equal effective dates are ordered by ID; a retroactive entry comes first.
        records.append(ActivationIntervention(activation_id=activation['id'], responsible_id=operation_payload['responsible_id'], occurred_at=datetime(2019 if index == 64 else 2020,1,1,tzinfo=timezone.utc), content=f'ENTRY-{index:03} texto & <especial>\n' + ('Intervención extensa con acentos áéíóú.\n' * 150 if index == 25 else 'Trabajo documentado.')))
    records.append(ActivationIntervention(activation_id=other['id'], responsible_id=operation_payload['responsible_id'], occurred_at=datetime(2018,1,1,tzinfo=timezone.utc), content='NO EXPORTAR OTRA ACTIVACIÓN'))
    db_session.add_all(records); db_session.commit()
    assert len(api_client.get(f"/api/activations/{activation['id']}/interventions").json()) == 50
    pdf_strings.clear()
    response = report(api_client, activation['id'])
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    assert 'NO EXPORTAR OTRA ACTIVACIÓN' not in content and other['reference'] not in content
    expected = [64, *range(64)]
    positions = [content.index(f'ENTRY-{index:03}') for index in expected]
    assert positions == sorted(positions)
    for index in range(65): assert content.count(f'ENTRY-{index:03}') == 1
    assert 'texto & <especial>' in content
    assert any('Página 2 /' in value for value in pdf_strings)
    assert 'Fecha de creación:' in content
    Path('/tmp/ticketyn-activation-complete.pdf').write_bytes(response.content)


def test_optional_historical_fields_are_not_filled_from_circuit(api_client, activation, db_session, pdf_strings):
    row = db_session.get(Activation, activation['id']); row.node_id = row.sector_id = None
    row.circuit.description = ''; row.circuit.service_type_id = None; db_session.commit()
    response = report(api_client, activation['id'])
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    assert 'Sin registrar' in content and 'Sin descripción' in content
    assert 'Nodo de prueba' not in content and 'Sector de prueba' not in content


@pytest.mark.parametrize('id', [0,-1,999999])
def test_missing_or_invalid_activation(api_client, id):
    assert report(api_client, id).status_code == (404 if id == 999999 else 422)


def test_timezone_and_extra_options_validated(api_client, activation, pdf_strings):
    assert report(api_client, activation['id'], timezone='Bad/Zone').status_code == 422
    assert report(api_client, activation['id'], include_all='true').status_code == 422
    assert report(api_client, activation['id'], timezone='UTC').status_code == 200
    assert '01/01/2020 12:00:00 +0000' in ' '.join(pdf_strings)


def test_only_two_queries_for_complete_history(api_client, activation, db_session, operation_payload):
    for index in range(60):
        db_session.add(ActivationIntervention(activation_id=activation['id'], responsible_id=operation_payload['responsible_id'], occurred_at=datetime(2020,1,1,tzinfo=timezone.utc), content=f'Intervención {index}'))
    db_session.commit()
    statements = []
    def count(*args):
        # The fixture uses nested transactions; SAVEPOINT is not a data query.
        if args[2].lstrip().upper().startswith('SELECT '): statements.append(args[2])
    bind = db_session.get_bind(); event.listen(bind, 'before_cursor_execute', count)
    try: assert report(api_client, activation['id']).status_code == 200
    finally: event.remove(bind, 'before_cursor_execute', count)
    # Authentication reads are separate from the unchanged two-query report.
    auth_queries = [sql for sql in statements if 'security_roles' in sql or 'security_config' in sql]
    assert len(auth_queries) == 2
    assert len(statements) - len(auth_queries) == 2


def test_failure_is_controlled_and_temporary_file_closed(api_client, monkeypatch):
    from tempfile import SpooledTemporaryFile
    from ticketyn.api import activation_reports
    files = []
    def temporary(**kwargs):
        file = SpooledTemporaryFile(**kwargs); files.append(file); return file
    def failed(*args): raise RuntimeError('Contenido confidencial que no debe salir')
    monkeypatch.setattr(activation_reports, 'SpooledTemporaryFile', temporary)
    monkeypatch.setattr(activation_reports, 'activation_pdf', failed)
    response = report(api_client, 1)
    assert response.status_code == 500
    assert response.json()['detail'] == 'No se pudo generar el reporte de la activación.'
    assert 'confidencial' not in response.text
    assert files[0].closed


@pytest.mark.parametrize('notes', [None, '', 'Configuración verificada: CPE ñ & <equipo> "principal".',
    'Primera línea: enlace óptico\nSegunda línea: VLAN 200 & gestión\n\nNuevo párrafo con áéíóú.'])
def test_activation_notes_are_exact_and_separate_from_log(api_client, operation_payload, pdf_strings, monkeypatch, notes):
    from ticketyn.api import activation_reports
    captured = []
    original = activation_reports.paragraph
    def capture(value, **kwargs):
        captured.append(value)
        return original(value, **kwargs)
    monkeypatch.setattr(activation_reports, 'paragraph', capture)
    response = api_client.post('/api/activations', json={**operation_payload, 'activation_notes': notes})
    assert response.status_code == 201
    item = response.json()
    before = api_client.get(f"/api/activations/{item['id']}").json()
    pdf_strings.clear()
    response = report(api_client, item['id'])
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    assert content.index('Equipo de distribución') < content.index('Notas internas de activación') < content.index('Bitácora de activación')
    assert (notes or 'Sin notas registradas') in captured
    for line in (notes or 'Sin notas registradas').splitlines():
        if line:
            assert line in content
    assert 'Sin intervenciones registradas.' in content
    assert api_client.get(f"/api/activations/{item['id']}").json() == before


def test_long_activation_notes_continue_across_pages(api_client, operation_payload, pdf_strings, monkeypatch):
    from reportlab.pdfgen.textobject import PDFTextObject
    first_note_pages = []
    original_text = PDFTextObject._textOut
    def capture_page(self, text, *args, **kwargs):
        if 'NOTA-000' in text:
            first_note_pages.append(self._canvas.getPageNumber())
        return original_text(self, text, *args, **kwargs)
    monkeypatch.setattr(PDFTextObject, '_textOut', capture_page)
    lines = [f'NOTA-{index:03}: Verificación óptica, potencia y conectividad del servicio & CPE <NOC>.' for index in range(110)]
    notes = '\n\n'.join(lines)
    assert len(notes) <= 10000
    item = api_client.post('/api/activations', json={**operation_payload, 'activation_notes': notes}).json()
    pdf_strings.clear()
    response = report(api_client, item['id'])
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    for line in lines:
        assert line in content
    assert content.index('NOTA-000') < content.index('NOTA-109') < content.index('Bitácora de activación')
    assert any('Página 2 /' in value for value in pdf_strings)
    assert first_note_pages and first_note_pages[0] == 1


@pytest.mark.parametrize('recorded, device, port', [(True, 'EQUIPO HISTÓRICO', 'PUERTO HISTÓRICO'),
    (True, 'EQUIPO HISTÓRICO', None), (True, None, None), (False, None, None)])
def test_notes_keep_distribution_snapshots(api_client, activation, db_session, pdf_strings, recorded, device, port):
    item = db_session.get(Activation, activation['id'])
    item.activation_notes = 'Notas históricas originales.'
    item.distribution_recorded = recorded
    item.distribution_device_name = device
    item.distribution_port_name = port
    db_session.commit()
    before = api_client.get(f"/api/activations/{item.id}").json()
    pdf_strings.clear()
    assert report(api_client, item.id).status_code == 200
    content = ' '.join(pdf_strings)
    assert 'Notas históricas originales.' in content
    assert (device or ('No asignado' if recorded else 'No registrado')) in content
    assert (port or ('No asignado' if recorded else 'No registrado')) in content
    assert api_client.get(f"/api/activations/{item.id}").json() == before
