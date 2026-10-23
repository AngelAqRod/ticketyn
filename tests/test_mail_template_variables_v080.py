"""Pruebas exhaustivas para variables de plantillas de correo Ticketyn v0.8.0.

Cubre los 14 requisitos de prueba del alcance:
1. Variables antiguas que siguen funcionando.
2. Equipo y puerto registrados.
3. Equipo asignado sin puerto.
4. Activación sin distribución («No asignado»).
5. Activación histórica anterior a v0.8.0 («No registrado»).
6. IPv4 e IPv6 de gestión CPE (normalizadas y estado actual).
7. Circuito sin IP («No asignada»).
8. Activación con notas.
9. Activación sin notas («Sin notas registradas»).
10. Variables en asunto y cuerpo.
11. Variables disponibles en el selector de UI (catálogo API).
12. Vista previa frente a renderizado real del worker.
13. Ausencia de filtración de datos de gestión y control de acceso.
14. Plantillas previamente guardadas.
"""
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import text
from ticketyn.models import Activation, Circuit, Customer
from ticketyn.models.mail_notifications import MailEventConfig
from ticketyn.notifications.fields import ACTIVATION_EVENT, ACTIVATION_FIELDS
from ticketyn.notifications.templates import render_template
from ticketyn.schemas.mail_templates import MailTemplate
from test_fms import create, operation_payload  # noqa: F401
from test_mail_notifications import no_smtp_or_dns  # noqa: F401

EVENT_BASE = '/api/mail-notifications/events/' + ACTIVATION_EVENT


def dynamic(field_id, **kwargs):
    return {'type': 'field', 'field_id': field_id, **kwargs}


@pytest.fixture
def distribution_setup(api_client, ticket_payload, numbered_port):
    node_id = ticket_payload['node_id']
    dev_res = api_client.post('/api/distribution-devices', json={
        'node_id': node_id,
        'name': 'OLT-HUAWEI-01',
    })
    assert dev_res.status_code == 201, dev_res.text
    dev = dev_res.json()

    port = numbered_port(dev['id'], prefix='gpon-', numbering_format='X/Y/Z', positions=(0, 1))
    return {'node_id': node_id, 'device': dev, 'port': port}


# 1. Variables antiguas que siguen funcionando
def test_1_legacy_variables_continue_working(api_client, operation_payload, db_session):
    circuit = db_session.get(Circuit, operation_payload['circuit_id'])
    circuit.initial_capacity = Decimal('100')
    circuit.initial_capacity_unit = 'Mbps'
    db_session.commit()

    activation = create(api_client, '/api/activations', {
        **operation_payload,
        'activation_notes': 'Nota existente',
    })

    legacy_ids = [
        'activation.reference', 'activation.effective_at', 'activation.created_at',
        'activation.sector', 'activation.node', 'activation.responsible',
        'activation.initial_capacity', 'circuit.code', 'circuit.description',
        'customer.name', 'customer.code',
    ]
    template = {
        'version': 1,
        'subject': [dynamic('activation.reference'), {'type': 'text', 'text': ' | '}, dynamic('customer.name')],
        'body': [dynamic(fid) for fid in legacy_ids],
    }
    response = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template})
    assert response.status_code == 200, response.text
    result = response.json()
    assert activation['reference'] in result['subject']
    assert 'CORRELATIVO: ' + activation['reference'] in result['body']
    assert 'CAPACIDAD INICIAL: 100 Mbps' in result['body']
    assert 'CLIENTE: ' in result['body']


# 2. Equipo y puerto registrados
def test_2_distribution_device_and_port_registered(api_client, operation_payload, distribution_setup):
    cid = operation_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={
        'distribution_device_id': distribution_setup['device']['id'],
        'distribution_port_id': distribution_setup['port']['id'],
    })
    activation = create(api_client, '/api/activations', operation_payload)

    template = {
        'version': 1,
        'subject': [dynamic('activation.distribution_device'), {'type': 'text', 'text': ' / '}, dynamic('activation.distribution_port')],
        'body': [dynamic('activation.distribution_device'), dynamic('activation.distribution_port')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == 'OLT-HUAWEI-01 / gpon-0/1/1'
    assert 'EQUIPO DE DISTRIBUCIÓN: OLT-HUAWEI-01' in res['body']
    assert 'PUERTO DE DISTRIBUCIÓN: gpon-0/1/1' in res['body']


# 3. Equipo asignado sin puerto
def test_3_distribution_device_assigned_without_port(api_client, operation_payload, distribution_setup):
    cid = operation_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={
        'distribution_device_id': distribution_setup['device']['id'],
        'distribution_port_id': None,
    })
    activation = create(api_client, '/api/activations', operation_payload)

    template = {
        'version': 1,
        'subject': [dynamic('activation.distribution_device'), {'type': 'text', 'text': ' / '}, dynamic('activation.distribution_port')],
        'body': [dynamic('activation.distribution_device'), dynamic('activation.distribution_port')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == 'OLT-HUAWEI-01 / No asignado'
    assert 'EQUIPO DE DISTRIBUCIÓN: OLT-HUAWEI-01' in res['body']
    assert 'PUERTO DE DISTRIBUCIÓN: No asignado' in res['body']


# 4. Activación sin distribución («No asignado»)
def test_4_activation_without_distribution(api_client, operation_payload):
    cid = operation_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={
        'distribution_device_id': None,
        'distribution_port_id': None,
    })
    activation = create(api_client, '/api/activations', operation_payload)

    template = {
        'version': 1,
        'subject': [dynamic('activation.distribution_device'), {'type': 'text', 'text': ' / '}, dynamic('activation.distribution_port')],
        'body': [dynamic('activation.distribution_device'), dynamic('activation.distribution_port')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == 'No asignado / No asignado'
    assert 'EQUIPO DE DISTRIBUCIÓN: No asignado' in res['body']
    assert 'PUERTO DE DISTRIBUCIÓN: No asignado' in res['body']


# 5. Activación histórica anterior a v0.8.0 («No registrado»)
def test_5_historical_activation_prior_to_v080(api_client, operation_payload, distribution_setup, db_session):
    cid = operation_payload['circuit_id']
    rid = operation_payload['responsible_id']

    # Insertar registro legacy previo a v0.8.0 (distribution_recorded = false)
    db_session.execute(text("""
        INSERT INTO activations (
            circuit_id, responsible_id, effective_at, activation_number, reference,
            distribution_recorded, distribution_device_name, distribution_port_name
        ) VALUES (
            :cid, :rid, '2020-01-01T00:00:00Z', 88881, 'ACT-HIST-LEGACY',
            false, NULL, NULL
        )
    """), {'cid': cid, 'rid': rid})
    db_session.commit()

    legacy_act = db_session.scalar(text("SELECT id FROM activations WHERE reference = 'ACT-HIST-LEGACY'"))

    # Modificar el circuito actual a un equipo nuevo
    api_client.patch(f'/api/circuits/{cid}', json={
        'distribution_device_id': distribution_setup['device']['id'],
        'distribution_port_id': distribution_setup['port']['id'],
    })

    template = {
        'version': 1,
        'subject': [dynamic('activation.distribution_device'), {'type': 'text', 'text': ' | '}, dynamic('activation.distribution_port')],
        'body': [dynamic('activation.distribution_device'), dynamic('activation.distribution_port')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': legacy_act, 'template': template}).json()
    # No debe reflejar 'OLT-HUAWEI-01' ni 'gpon-0/1/1', sino 'No registrado'
    assert res['subject'] == 'No registrado | No registrado'
    assert 'EQUIPO DE DISTRIBUCIÓN: No registrado' in res['body']
    assert 'PUERTO DE DISTRIBUCIÓN: No registrado' in res['body']


# 6. IPv4 e IPv6 de gestión CPE normalizadas
def test_6_cpe_management_ip_ipv4_and_ipv6_normalized(api_client, operation_payload):
    cid = operation_payload['circuit_id']

    # IPv4 con espacios se limpia y normaliza
    res_patch = api_client.patch(f'/api/circuits/{cid}', json={'cpe_management_ip': ' 192.168.10.25 '})
    assert res_patch.status_code == 200, res_patch.text
    activation = create(api_client, '/api/activations', operation_payload)

    template = {
        'version': 1,
        'subject': [dynamic('circuit.cpe_management_ip')],
        'body': [dynamic('circuit.cpe_management_ip')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == '192.168.10.25'
    assert 'IP DE GESTIÓN CPE: 192.168.10.25' in res['body']

    # IPv6 se normaliza a RFC 5952 y refleja el estado actual del circuito
    res_patch_v6 = api_client.patch(f'/api/circuits/{cid}', json={'cpe_management_ip': '2001:0db8:0000:0000:0000:0000:0000:0001'})
    assert res_patch_v6.status_code == 200, res_patch_v6.text
    res2 = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res2['subject'] == '2001:db8::1'
    assert 'IP DE GESTIÓN CPE: 2001:db8::1' in res2['body']


# 7. Circuito sin IP («No asignada»)
def test_7_circuit_without_cpe_ip(api_client, operation_payload):
    cid = operation_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={'cpe_management_ip': None})
    activation = create(api_client, '/api/activations', operation_payload)

    template = {
        'version': 1,
        'subject': [dynamic('circuit.cpe_management_ip')],
        'body': [dynamic('circuit.cpe_management_ip')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == 'No asignada'
    assert 'IP DE GESTIÓN CPE: No asignada' in res['body']


# 8. Activación con notas
def test_8_activation_with_notes(api_client, operation_payload):
    notes = 'Línea de configuración 1\nLínea 2: VLAN 100'
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': notes})

    template = {
        'version': 1,
        'subject': [dynamic('activation.activation_notes')],
        'body': [dynamic('activation.activation_notes')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == 'Línea de configuración 1 Línea 2: VLAN 100'
    assert 'NOTAS DE ACTIVACIÓN:\n' + notes in res['body']
    assert '<table' in res['html_body'] and 'NOTAS DE ACTIVACIÓN:' in res['html_body']


# 9. Activación sin notas («Sin notas registradas»)
def test_9_activation_without_notes(api_client, operation_payload):
    activation = create(api_client, '/api/activations', operation_payload)

    template = {
        'version': 1,
        'subject': [dynamic('activation.activation_notes')],
        'body': [dynamic('activation.activation_notes')],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == 'Sin notas registradas'
    assert 'NOTAS DE ACTIVACIÓN:\nSin notas registradas' in res['body']
    assert 'Sin notas registradas' in res['html_body']


# 10. Variables en asunto y cuerpo
def test_10_variables_in_subject_and_body(api_client, operation_payload, distribution_setup):
    cid = operation_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={
        'distribution_device_id': distribution_setup['device']['id'],
        'distribution_port_id': distribution_setup['port']['id'],
        'cpe_management_ip': '10.0.0.1',
    })
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': 'Rack A'})

    template = {
        'version': 1,
        'subject': [
            {'type': 'text', 'text': 'NOC | '},
            dynamic('activation.distribution_device'),
            {'type': 'text', 'text': ' / '},
            dynamic('activation.distribution_port'),
            {'type': 'text', 'text': ' | CPE: '},
            dynamic('circuit.cpe_management_ip'),
        ],
        'body': [
            {'type': 'introduction', 'text': 'Resumen operativo.'},
            dynamic('activation.distribution_device'),
            dynamic('activation.distribution_port'),
            dynamic('circuit.cpe_management_ip'),
            dynamic('activation.activation_notes'),
            {'type': 'signature', 'text': 'Equipo NOC'},
        ],
    }
    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()
    assert res['subject'] == 'NOC | OLT-HUAWEI-01 / gpon-0/1/1 | CPE: 10.0.0.1'
    assert 'EQUIPO DE DISTRIBUCIÓN: OLT-HUAWEI-01' in res['body']
    assert 'PUERTO DE DISTRIBUCIÓN: gpon-0/1/1' in res['body']
    assert 'IP DE GESTIÓN CPE: 10.0.0.1' in res['body']
    assert 'NOTAS DE ACTIVACIÓN:\nRack A' in res['body']
    assert res['body'].startswith('Resumen operativo.\n\n')
    assert res['body'].endswith('\n\nEquipo NOC')


# 11. Variables disponibles en el selector de UI
def test_11_variables_available_in_ui_field_selector(api_client):
    res = api_client.get(EVENT_BASE + '/fields')
    assert res.status_code == 200
    fields_by_id = {f['id']: f for f in res.json()}

    # Equipo de distribución
    assert 'activation.distribution_device' in fields_by_id
    dev_field = fields_by_id['activation.distribution_device']
    assert dev_field['group'] == 'Activación FMS'
    assert dev_field['label'] == 'Equipo de distribución'
    assert dev_field['temporality'] == 'HISTORICAL'
    assert dev_field['format'] == 'text'

    # Puerto de distribución
    assert 'activation.distribution_port' in fields_by_id
    port_field = fields_by_id['activation.distribution_port']
    assert port_field['group'] == 'Activación FMS'
    assert port_field['label'] == 'Puerto de distribución'
    assert port_field['temporality'] == 'HISTORICAL'

    # IP de gestión CPE
    assert 'circuit.cpe_management_ip' in fields_by_id
    ip_field = fields_by_id['circuit.cpe_management_ip']
    assert ip_field['group'] == 'Circuito'
    assert ip_field['label'] == 'IP de gestión CPE'
    assert ip_field['temporality'] == 'CURRENT'

    # Notas de activación
    assert 'activation.activation_notes' in fields_by_id
    notes_field = fields_by_id['activation.activation_notes']
    assert notes_field['group'] == 'Activación FMS'
    assert notes_field['label'] == 'Notas de activación'
    assert notes_field['temporality'] == 'HISTORICAL'


# 12. Vista previa frente a envío real
def test_12_preview_matches_worker_rendering(api_client, operation_payload, distribution_setup, db_session):
    cid = operation_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={
        'distribution_device_id': distribution_setup['device']['id'],
        'distribution_port_id': distribution_setup['port']['id'],
        'cpe_management_ip': '172.16.0.5',
    })
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': 'Bitácora'})

    template = {
        'version': 1,
        'subject': [dynamic('activation.reference'), {'type': 'text', 'text': ' - '}, dynamic('activation.distribution_device')],
        'body': [
            dynamic('activation.distribution_device'),
            dynamic('activation.distribution_port'),
            dynamic('circuit.cpe_management_ip'),
            dynamic('activation.activation_notes'),
        ],
    }
    # 1. Vista previa vía endpoint
    preview_res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': template}).json()

    # 2. Renderizado idéntico del worker/motor interno
    db_act = db_session.get(Activation, activation['id'])
    worker_res = render_template(db_session, ACTIVATION_EVENT, MailTemplate.model_validate(template), db_act)

    assert preview_res['subject'] == worker_res.subject
    assert preview_res['body'] == worker_res.body
    assert preview_res['html_body'] == worker_res.html_body


# 13. Ausencia de filtración de datos de gestión en contextos no autorizados
def test_13_no_management_leakage_and_unauthorized_access_denied(api_client):
    # La configuración técnica interna cpe_configuration no debe aparecer en los campos
    fields = api_client.get(EVENT_BASE + '/fields').json()
    for f in fields:
        assert 'cpe_configuration' not in f['id']
        for p in f['source_paths']:
            assert 'cpe_configuration' not in p

    # Intento de inyectar atributos arbitrarios o internos debe fallar con 422
    injected_template = {
        'version': 1,
        'subject': [],
        'body': [dynamic('circuit.cpe_configuration')],
    }
    assert api_client.patch(EVENT_BASE + '/template', json=injected_template).status_code == 422
    assert api_client.post(EVENT_BASE + '/preview', json={'activation_id': 1, 'template': injected_template}).status_code == 422

    # Intentos de acceso sin autenticación o con credencial no autorizada se rechazan (401/403)
    assert api_client.get(EVENT_BASE + '/fields', headers={'Authorization': ''}).status_code in (401, 403)
    assert api_client.get(EVENT_BASE + '/template', headers={'Authorization': 'Bearer token-invalido'}).status_code in (401, 403)
    assert api_client.post(EVENT_BASE + '/preview', json={'activation_id': 1, 'template': {'version': 1, 'subject': [], 'body': []}}, headers={'Authorization': 'Bearer token-invalido'}).status_code in (401, 403)


# 14. Plantillas previamente guardadas
def test_14_previously_saved_templates_remain_compatible(api_client, operation_payload, db_session):
    activation = create(api_client, '/api/activations', operation_payload)

    # Simular plantilla guardada previamente en v0.7.0 (solo campos anteriores)
    saved_v070 = {
        'version': 1,
        'subject': [{'type': 'text', 'text': 'Aviso de activación | '}, dynamic('activation.reference')],
        'body': [
            {'type': 'introduction', 'text': 'Estimados colaboradores,\nSe ha registrado una nueva activación.'},
            dynamic('activation.reference'),
            dynamic('customer.name'),
            dynamic('circuit.code'),
            {'type': 'signature', 'text': 'Atentamente,\nNOC'},
        ],
    }
    # Guardar en base de datos
    assert api_client.patch(EVENT_BASE + '/template', json=saved_v070).status_code == 200

    # Consultar y renderizar sin necesidad de migraciones ni mutaciones
    loaded = api_client.get(EVENT_BASE + '/template').json()
    assert loaded == MailTemplate.model_validate(saved_v070).model_dump()

    res = api_client.post(EVENT_BASE + '/preview', json={'activation_id': activation['id'], 'template': loaded}).json()
    assert res['subject'] == f"Aviso de activación | {activation['reference']}"
    assert f"CORRELATIVO: {activation['reference']}" in res['body']
    assert 'CLIENTE: ' in res['body']
    assert 'CÓDIGO DE CIRCUITO: ' in res['body']
