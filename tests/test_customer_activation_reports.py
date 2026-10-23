"""Positive projection and confidentiality for the client activation certificate."""
from dataclasses import fields
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect, select, text

from ticketyn.api.customer_activation_reports import CustomerActivationReport, customer_activation_report
from ticketyn.models import Circuit, Responsible, Node, Sector
from ticketyn.models.fms import Activation, ActivationIntervention
from ticketyn.models.security import SecurityRole
from test_fms import operation_payload
from test_ticket_exports import pdf_strings
from test_e2e_update_migration import cli


def certificate(client, id):
    return client.get(f'/api/activations/{id}/reports/customer/pdf')


def create(client, payload):
    response = client.post('/api/activations', json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize('internal,public', [(None, None), ('PRIVATE_INTERNAL_ONLY', None),
    (None, 'Entrega: IP 203.0.113.10'), ('PRIVATE_INTERNAL', 'VLAN 200 & <entrega>\n\nPuerto cliente: ether1')])
def test_notes_create_consult_and_separate_pdfs(api_client, operation_payload, pdf_strings, internal, public):
    item = create(api_client, {**operation_payload, 'activation_notes': internal, 'customer_activation_notes': public})
    assert item['activation_notes'] == internal and item['customer_activation_notes'] == public
    assert api_client.get(f"/api/activations/{item['id']}").json() == item
    assert api_client.get('/api/activations').json()[0]['customer_activation_notes'] == public
    pdf_strings.clear()
    response = certificate(api_client, item['id'])
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert f"ticketyn-activacion-{item['id']}-cliente.pdf" in response.headers['content-disposition']
    content = ' '.join(pdf_strings)
    assert 'Constancia de activación de servicio' in content
    if internal: assert internal not in content
    for line in (public or 'Sin información de entrega registrada.').splitlines():
        if line: assert line in content
    assert 'Notas internas' not in content
    pdf_strings.clear()
    assert api_client.get(f"/api/activations/{item['id']}/reports/pdf").status_code == 200
    content = ' '.join(pdf_strings)
    assert 'Notas internas de activación' in content and 'Información para el cliente' in content
    if internal: assert internal in content
    for line in (public or 'Sin notas para cliente registradas').splitlines():
        if line: assert line in content
    assert api_client.get(f"/api/activations/{item['id']}").json() == item
    # Initial activation fields remain immutable: no new editing endpoint.
    assert api_client.patch(f"/api/activations/{item['id']}", json={'customer_activation_notes': None}).status_code in (403, 405)


@pytest.mark.parametrize('notes, expected', [('', None), ('  \n ', None), ('  A & <B>\n\nC  ', '  A & <B>\n\nC  ')])
def test_public_notes_empty_normalization_without_touching_internal(api_client, operation_payload, notes, expected):
    item = create(api_client, {**operation_payload, 'activation_notes': 'Original interno', 'customer_activation_notes': notes})
    assert item['activation_notes'] == 'Original interno'
    assert item['customer_activation_notes'] == expected


@pytest.mark.parametrize('notes', ['x' * 10001, ' ' * 10001, 12, ['texto']])
def test_invalid_public_notes(api_client, operation_payload, notes):
    assert api_client.post('/api/activations', json={**operation_payload, 'customer_activation_notes': notes}).status_code == 422


def test_projection_and_public_pdf_exclude_all_internal_sources(api_client, operation_payload, db_session, pdf_strings, monkeypatch):
    from ticketyn.api import activation_reports
    from reportlab.pdfgen.canvas import Canvas
    private = ['PRIVATE_NOTES_SENTINEL', 'PRIVATE_DESCRIPTION_SENTINEL', 'PRIVATE_NODE_SENTINEL',
        'PRIVATE_SECTOR_SENTINEL', 'PRIVATE_PERSON_SENTINEL', 'PRIVATE_DEVICE_SENTINEL',
        'PRIVATE_PORT_SENTINEL', 'PRIVATE_LOG_SENTINEL', 'PRIVATE_CURRENT_SERVICE', '2001:db8:ffff::a1']
    circuit = db_session.get(Circuit, operation_payload['circuit_id'])
    circuit.description = private[1]; circuit.cpe_management_ip = private[-1]
    db_session.get(Node, circuit.node_id).name = private[2]
    db_session.get(Sector, circuit.sector_id).name = private[3]
    db_session.get(Responsible, operation_payload['responsible_id']).name = private[4]
    db_session.commit()
    item = create(api_client, {**operation_payload, 'activation_notes': private[0],
        'customer_activation_notes': 'IP pública: 203.0.113.10\nPuerto cliente: LAN-1'})
    activation = db_session.get(Activation, item['id'])
    activation.distribution_recorded = True
    activation.distribution_device_name = private[5]; activation.distribution_port_name = private[6]
    activation.service_type_name = 'SERVICIO HISTÓRICO AUTORIZADO'
    activation.initial_capacity = 500; activation.initial_capacity_unit = 'Mbps'
    from ticketyn.models import ServiceType
    live_type = ServiceType(name=private[8]); db_session.add(live_type); db_session.flush()
    circuit.service_type_id = live_type.id
    circuit.initial_capacity = 99; circuit.initial_capacity_unit = 'Gbps'
    db_session.add(ActivationIntervention(activation_id=item['id'], responsible_id=operation_payload['responsible_id'],
        occurred_at=activation.effective_at, content=private[7]))
    db_session.commit()
    statements = []
    def capture(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith('SELECT '): statements.append(statement)
    bind = db_session.get_bind(); event.listen(bind, 'before_cursor_execute', capture)
    try: projection = customer_activation_report(db_session, item['id'])
    finally: event.remove(bind, 'before_cursor_execute', capture)
    assert {f.name for f in fields(projection)} == {'reference', 'customer_name', 'circuit_code', 'service_type_name',
        'effective_at', 'initial_capacity', 'initial_capacity_unit', 'customer_activation_notes'}
    assert len(statements) == 1
    for column in ['activations.activation_notes', 'distribution_device_name', 'cpe_management_ip', 'responsible_id', 'circuits.description']:
        assert column not in statements[0]
    def forbidden(*args): raise AssertionError('The internal renderer must never generate a client PDF')
    monkeypatch.setattr(activation_reports, 'activation_pdf', forbidden)
    metadata = []
    for method in ['setTitle', 'setAuthor', 'setSubject', 'setKeywords', 'setCreator']:
        original = getattr(Canvas, method)
        def capture_metadata(self, value, _original=original):
            metadata.append(str(value)); return _original(self, value)
        monkeypatch.setattr(Canvas, method, capture_metadata)
    pdf_strings.clear()
    response = certificate(api_client, item['id'])
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    assert 'SERVICIO HISTÓRICO AUTORIZADO' in content and '203.0.113.10' in content and 'LAN-1' in content
    assert '500 Mbps' in content and '99 Gbps' not in content
    Path('/tmp/ticketyn-client-activation-privacy.pdf').write_bytes(response.content)
    for marker in private:
        assert marker not in content and marker not in ' '.join(metadata)
        assert marker.encode() not in response.content


def test_public_long_notes_are_complete_and_start_on_first_page(api_client, operation_payload, pdf_strings, monkeypatch):
    from reportlab.pdfgen.textobject import PDFTextObject
    pages = []
    original = PDFTextObject._textOut
    def capture(self, value, *args, **kwargs):
        if 'PUBLIC-000' in value: pages.append(self._canvas.getPageNumber())
        return original(self, value, *args, **kwargs)
    monkeypatch.setattr(PDFTextObject, '_textOut', capture)
    lines = [f'PUBLIC-{i:03}: Parámetros autorizados & VLAN <200> para cliente.' for i in range(120)]
    notes = '\n\n'.join(lines)
    item = create(api_client, {**operation_payload, 'customer_activation_notes': notes})
    pdf_strings.clear()
    assert certificate(api_client, item['id']).status_code == 200
    content = ' '.join(pdf_strings)
    for line in lines: assert line in content
    assert pages[0] == 1
    assert any('Página 2 /' in value for value in pdf_strings)


@pytest.mark.parametrize('role', ['SUPERADMIN', 'ADMIN', 'OPERATOR', 'AUDITOR', 'CUSTOM'])
def test_certificate_requires_authentication_and_export_permission(api_client, operation_payload, db_session, role):
    item = create(api_client, operation_payload)
    if role == 'CUSTOM':
        selected = SecurityRole(name='Sin exportación'); db_session.add(selected); db_session.flush()
    else: selected = db_session.scalar(select(SecurityRole).where(SecurityRole.code == role))
    person = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    person.security_role_id = selected.id; db_session.commit()
    assert certificate(api_client, item['id']).status_code == (403 if role == 'CUSTOM' else 200)
    api_client.headers.pop('Authorization')
    assert certificate(api_client, item['id']).status_code == 401


def test_missing_invalid_and_failed_public_pdf_are_controlled(api_client, monkeypatch, operation_payload):
    from ticketyn.api import customer_activation_reports
    assert certificate(api_client, 999999).status_code == 404
    assert api_client.get('/api/activations/1/reports/customer/pdf?timezone=Invalid/Zone').status_code == 422
    item = create(api_client, operation_payload)
    def failed(*args): raise RuntimeError('PRIVATE_EXCEPTION_SENTINEL')
    monkeypatch.setattr(customer_activation_reports, 'customer_activation_pdf', failed)
    response = certificate(api_client, item['id'])
    assert response.status_code == 500 and 'PRIVATE_EXCEPTION_SENTINEL' not in response.text


def test_0036_migration_preserves_internal_notes_and_does_not_backfill(postgres_engine):
    name = 'customer_notes_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0035_cpe_management_ip')
        with engine.begin() as c:
            c.execute(text("INSERT INTO customers(name,customer_code) VALUES ('Histórico','HIST')"))
            c.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'HIST-C','Descripción privada')"))
            c.execute(text("INSERT INTO responsibles(name) VALUES ('Responsable histórico')"))
            c.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference,activation_notes) VALUES (1,1,'2020-01-01T00:00:00Z',1,'ACT-HIST','NOTAS INTERNAS ANTIGUAS')"))
            before = c.scalar(text('SELECT to_jsonb(a) FROM activations a'))
        cli(engine.url, 'upgrade', '0036_customer_activation_notes')
        with engine.begin() as c:
            row = c.scalar(text('SELECT to_jsonb(a) FROM activations a'))
            assert row.pop('customer_activation_notes') is None
            assert row.pop('customer_name_snapshot') is None
            assert row.pop('circuit_code_snapshot') is None
            assert row == before
            column = next(col for col in inspect(c).get_columns('activations') if col['name'] == 'customer_activation_notes')
            assert str(column['type']) == 'TEXT' and column['nullable'] and column['default'] is None
            c.execute(text("UPDATE activations SET customer_activation_notes='Información pública autorizada'"))
        with pytest.raises(AssertionError, match='Downgrade inseguro'):
            cli(engine.url, 'downgrade', '0035_cpe_management_ip')
        with engine.begin() as c: c.execute(text('UPDATE activations SET customer_activation_notes=NULL'))
        cli(engine.url, 'downgrade', '0035_cpe_management_ip')
        with engine.connect() as c: assert c.scalar(text('SELECT to_jsonb(a) FROM activations a')) == before
        cli(engine.url, 'upgrade', '0036_customer_activation_notes')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + name))


def test_certificate_identity_and_service_are_historical_not_live(api_client, operation_payload, db_session, pdf_strings):
    from ticketyn.models import Customer
    item = create(api_client, {**operation_payload, 'customer_activation_notes': 'Entrega original'})
    projection = customer_activation_report(db_session, item['id'])
    circuit = db_session.get(Circuit, item['circuit_id'])
    db_session.get(Customer, circuit.customer_id).name = 'PRIVATE_CURRENT_CUSTOMER'
    circuit.circuit_code = 'PRIVATE_CURRENT_CODE'
    db_session.commit()
    assert customer_activation_report(db_session, item['id']) == projection
    pdf_strings.clear()
    assert certificate(api_client, item['id']).status_code == 200
    content = ' '.join(pdf_strings)
    assert projection.customer_name in content and projection.circuit_code in content
    assert 'PRIVATE_CURRENT_CUSTOMER' not in content and 'PRIVATE_CURRENT_CODE' not in content


def test_historical_activation_never_falls_back_to_current_identity(api_client, operation_payload, db_session, pdf_strings):
    item = create(api_client, {**operation_payload, 'activation_notes': 'PRIVATE_OLD_INTERNAL'})
    historical = db_session.get(Activation, item['id'])
    historical.customer_name_snapshot = None; historical.circuit_code_snapshot = None
    db_session.commit()
    pdf_strings.clear()
    assert certificate(api_client, item['id']).status_code == 200
    content = ' '.join(pdf_strings)
    assert 'No registrado' in content and 'Sin información de entrega registrada.' in content
    for hidden in ['Cliente de prueba', 'MANUAL-CIRCUIT', 'PRIVATE_OLD_INTERNAL']:
        assert hidden not in content


@pytest.mark.parametrize('field', ['customer_name_snapshot', 'circuit_code_snapshot'])
def test_identity_snapshots_cannot_be_injected_by_client(api_client, operation_payload, field):
    assert api_client.post('/api/activations', json={**operation_payload, field: 'IDENTIDAD INVENTADA'}).status_code == 422
