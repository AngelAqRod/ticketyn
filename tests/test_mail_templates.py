"""Templates and ephemeral real-data preview; no SMTP or FMS writes."""
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, inspect, text
from ticketyn.models import Activation, Circuit, Customer
from ticketyn.models.mail_notifications import MailEventConfig
from ticketyn.notifications.fields import ACTIVATION_EVENT, ACTIVATION_FIELDS
from test_fms import create, operation_payload  # noqa: F401
from test_mail_notifications import no_smtp_or_dns  # noqa: F401
from test_e2e_update_migration import cli

EVENT = '/api/mail-notifications/events/' + ACTIVATION_EVENT
EMPTY = {'version': 1, 'subject': [], 'body': []}


def plain_result(preview):
    assert preview['html_body'].startswith('<!doctype html>')
    return {key: preview[key] for key in ('subject', 'body')}


def dynamic(identifier, **kwargs):
    return {'type': 'field', 'field_id': identifier, **kwargs}


def sample():
    return {'version': 1, 'subject': [{'type': 'text', 'text': 'Activación | '}, dynamic('activation.reference'), {'type': 'text', 'text': ' | '}, dynamic('customer.name')], 'body': [
        {'type': 'introduction', 'text': 'Estimados,\nRegistro técnico.'},
        dynamic('activation.activation_notes', label_mode='DEFAULT', custom_label=None),
        dynamic('circuit.current_capacity', label_mode='CUSTOM', custom_label='Capacidad vigente'),
        {'type': 'signature', 'text': 'Saludos,\nNOC'}]}


def test_template_roundtrip_independent_config(api_client, db_session):
    assert api_client.get(EVENT + '/template').json() == EMPTY
    assert api_client.patch(EVENT, json={'mode': 'MANUAL', 'to': ['noc@example.com']}).status_code == 200
    before = api_client.get(EVENT).json()
    template = sample()
    assert api_client.patch(EVENT + '/template', json=template).json() == template
    assert api_client.get(EVENT + '/template').json() == template
    assert api_client.get(EVENT).json() == before
    assert db_session.get(MailEventConfig, ACTIVATION_EVENT).template == template
    template['subject'].reverse(); template['body'].reverse()
    assert api_client.patch(EVENT + '/template', json=template).json() == template
    assert api_client.get(EVENT + '/template').json() == template
    assert api_client.patch(EVENT + '/template', json=EMPTY).status_code == 200
    assert api_client.get(EVENT + '/template').json() == EMPTY
    assert api_client.get('/api/mail-notifications/events/unknown/template').status_code == 404


@pytest.mark.parametrize('template', [
    {'subject': [{'type': 'html', 'text': 'bad'}]},
    {'body': [dynamic('activation.__dict__')]},
    {'subject': [dynamic('customer.password')]},
    {'subject': [{'type': 'text', 'text': 'X\r\nBcc: leak@example.com'}]},
    {'subject': [{'type': 'text', 'text': 'X\x00bad'}]},
    {'body': [dynamic('customer.name', label_mode='CUSTOM', custom_label=' ')]},
    {'body': [dynamic('customer.name', label_mode='CUSTOM', custom_label='X\nY')]},
    {'body': [dynamic('customer.name', label_mode='DEFAULT', custom_label='Other')]},
    {'body': [{'type': 'signature', 'text': 'X' * 10001}]},
    {'subject': [{'type': 'text', 'text': 'X'}] * 51},
    {'version': 2}, {'body': None}, {'body': [], 'expression': 'exec(...)'},
])
def test_reject_invalid_templates(api_client, template):
    assert api_client.patch(EVENT + '/template', json=template).status_code == 422
    assert api_client.post(EVENT + '/preview', json={'activation_id': 1, 'template': template}).status_code == 422
    assert api_client.get(EVENT + '/template').json() == EMPTY


def test_real_preview_unsaved_historical_current_multiline(api_client, operation_payload, db_session):
    circuit = db_session.get(Circuit, operation_payload['circuit_id'])
    circuit.initial_capacity = 100; circuit.initial_capacity_unit = 'Mbps'
    db_session.commit()
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': 'IP pública\nNAT configurado\n  Puerto especial'})
    original = api_client.get('/api/activations/' + str(activation['id'])).json()
    circuit = db_session.get(Circuit, operation_payload['circuit_id'])
    circuit.initial_capacity = 200
    customer = db_session.get(Customer, circuit.customer_id); customer.name = 'Cliente actual'
    row = db_session.get(Activation, activation['id']); row.service_type_name = 'Servicio histórico'; row.cpe_activation = 'Equipo histórico'; row.node_id = None
    db_session.commit()
    # Latest effective capacity, not a future change, defines current capacity.
    create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': 'INCREASE', 'previous_capacity': '200', 'previous_unit': 'Mbps', 'new_capacity': '300', 'new_unit': 'Mbps'})
    create(api_client, '/api/capacity-changes', {**operation_payload, 'effective_at': '2099-01-01T12:00:00-06:00', 'operation_type': 'INCREASE', 'previous_capacity': '300', 'previous_unit': 'Mbps', 'new_capacity': '400', 'new_unit': 'Mbps'})
    before = api_client.get('/api/activations/' + str(activation['id'])).json()
    template = sample()
    template['body'] += [dynamic('activation.initial_capacity'), dynamic('circuit.initial_capacity'), dynamic('activation.effective_at'), dynamic('activation.service_type'), dynamic('activation.cpe'), dynamic('activation.node')]
    response = api_client.post(EVENT + '/preview', json={'activation_id': activation['id'], 'template': template})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['subject'] == f"Activación | {activation['reference']} | Cliente actual"
    assert 'CORRELATIVO:' not in result['subject']
    assert 'NOTAS DE ACTIVACIÓN:\n' + original['activation_notes'] in result['body']
    assert 'Capacidad vigente: 300 Mbps' in result['body']
    assert 'CAPACIDAD INICIAL: 100 Mbps' in result['body'] and 'CAPACIDAD INICIAL: 200 Mbps' in result['body']
    assert 'FECHA EFECTIVA DE ACTIVACIÓN: 01/01/2020 12:00:00' in result['body']
    assert 'Servicio histórico' in result['body'] and 'Equipo histórico' in result['body']
    assert 'NODO:' not in result['body']
    assert result['body'].startswith('Estimados,\nRegistro técnico.\n\n')
    assert api_client.get(EVENT + '/template').json() == EMPTY
    assert api_client.get('/api/activations/' + str(activation['id'])).json() == before
    assert api_client.get(f"/api/activations/{activation['id']}/interventions").json() == []
    # Registry is the sole source of allowed attributes. Resolve every field.
    all_fields = {'subject': [], 'body': [dynamic(field.id) for field in ACTIVATION_FIELDS]}
    assert api_client.post(EVENT + '/preview', json={'activation_id': activation['id'], 'template': all_fields}).status_code == 200
    tables = set(inspect(db_session.connection()).get_table_names())
    assert not {'mail_messages', 'mail_jobs', 'mail_delivery_work'} & tables


def test_preview_orders_subject_and_labels_without_changing_saved_template(api_client, operation_payload):
    activation = create(api_client, '/api/activations', operation_payload)
    saved = sample()
    assert api_client.patch(EVENT + '/template', json=saved).status_code == 200
    draft = {'subject': [dynamic('circuit.code'), {'type': 'text', 'text': ' / '}, dynamic('activation.reference')],
             'body': [dynamic('activation.reference', label_mode='CUSTOM', custom_label='Referencia local'),
                      dynamic('activation.reference', label_mode='DEFAULT')]}
    response = api_client.post(EVENT + '/preview', json={'activation_id': activation['id'], 'template': draft})
    assert response.status_code == 200
    result = response.json()
    assert result['subject'] == activation['circuit']['circuit_code'] + ' / ' + activation['reference']
    assert result['body'] == f"Referencia local: {activation['reference']}\nCORRELATIVO: {activation['reference']}"
    assert api_client.get(EVENT + '/template').json() == saved


@pytest.mark.parametrize('label_mode', [None, 'DEFAULT', 'CUSTOM'])
def test_all_registered_labels_unicode_and_existing_templates(api_client, operation_payload, db_session, label_mode):
    circuit_id = operation_payload['circuit_id']
    customer_id = db_session.get(Circuit, circuit_id).customer_id
    service = create(api_client, '/api/service-types', {'name': 'Servicio MiXto ñ'})
    cpe = create(api_client, '/api/cpe-models', {'name': 'Cpe MiXto ñ'})
    assert api_client.patch(f'/api/customers/{customer_id}', json={'name': 'Cliente Ñandú ágil'}).status_code == 200
    assert api_client.patch(f'/api/circuits/{circuit_id}', json={
        'description': 'Descripción MiXta ñ', 'initial_capacity': '100',
        'initial_capacity_unit': 'Mbps', 'service_type_id': service['id'], 'cpe_model_id': cpe['id'],
    }).status_code == 200
    notes = 'Ip pública ñandú\nPuerto MiXto: core A'
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': notes})
    blocks, labels = [], []
    for index, field in enumerate(ACTIVATION_FIELDS):
        block = dynamic(field.id)
        if label_mode is not None:
            block['label_mode'] = label_mode
        if label_mode == 'CUSTOM':
            label = f'Etiqueta MiXta {index} · áéíóú Ñandú'
            block['custom_label'] = label
        else:
            label = field.label.upper()
        blocks.append(block)
        labels.append(label)
    introduction, signature = 'Estimados,\nInicio MiXto ñ', 'Saludos,\nNoc ágil'
    template = {'version': 1,
                'subject': [{'type': 'text', 'text': 'Aviso MiXto |'}, dynamic('customer.name')],
                'body': [{'type': 'introduction', 'text': introduction}, *blocks,
                         {'type': 'signature', 'text': signature}]}
    response = api_client.patch(EVENT + '/template', json=template)
    assert response.status_code == 200, response.text
    if label_mode is None:
        # Existing JSON templates can omit label_mode; reads/rendering must not
        # rewrite them just to change presentation.
        db_session.get(MailEventConfig, ACTIVATION_EVENT).template = template
        db_session.commit()
    stored = db_session.get(MailEventConfig, ACTIVATION_EVENT).template
    loaded = api_client.get(EVENT + '/template').json()
    response = api_client.post(EVENT + '/preview', json={'activation_id': activation['id'], 'template': loaded})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['subject'] == 'Aviso MiXto | Cliente Ñandú ágil'
    assert result['body'].startswith(introduction + '\n\n')
    assert result['body'].endswith('\n\n' + signature)
    cursor = 0
    for field, label in zip(ACTIVATION_FIELDS, labels):
        marker = label + (':\n' if field.id == 'activation.activation_notes' else ': ')
        position = result['body'].find(marker, cursor)
        assert position >= cursor, field.id
        cursor = position + len(marker)
        if field.id == 'activation.activation_notes':
            assert marker + notes in result['body']
    for value in ('Cliente Ñandú ágil', 'Servicio MiXto ñ', 'Cpe MiXto ñ', 'Descripción MiXta ñ', '100 Mbps'):
        assert value in result['body']
    if label_mode != 'CUSTOM':
        assert 'DESCRIPCIÓN DEL CIRCUITO: Descripción MiXta ñ' in result['body']
        assert 'CÓDIGO DE CIRCUITO:' in result['body']
        assert 'NOTAS DE ACTIVACIÓN:\n' + notes in result['body']
    assert db_session.get(MailEventConfig, ACTIVATION_EVENT).template == stored
    assert [field['label'] for field in api_client.get(EVENT + '/fields').json()] == [field.label for field in ACTIVATION_FIELDS]
    assert api_client.get(f"/api/activations/{activation['id']}").json() == activation


def test_missing_values_headers_order_and_limits(api_client, operation_payload):
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': 'Dato\r\nBcc: ejemplo\nOtro'})
    template = {'subject': [dynamic('activation.activation_notes')], 'body': [dynamic('circuit.current_capacity'), dynamic('activation.service_type')]}
    request = {'activation_id': activation['id'], 'template': template}
    result = api_client.post(EVENT + '/preview', json=request).json()
    assert result['subject'] == 'Dato Bcc: ejemplo Otro'
    assert result['body'] == ''
    template['body'].reverse()
    assert api_client.post(EVENT + '/preview', json=request).json()['body'] == ''
    template['subject'] = [{'type': 'text', 'text': 'á' * 600}]
    assert api_client.post(EVENT + '/preview', json=request).status_code == 422
    request['template'] = EMPTY
    assert plain_result(api_client.post(EVENT + '/preview', json=request).json()) == {'subject': '', 'body': ''}
    request['activation_id'] = 2147483647
    assert api_client.post(EVENT + '/preview', json=request).status_code == 404
    assert api_client.post('/api/mail-notifications/events/unknown/preview', json=request).status_code == 404


def test_real_template_migration(postgres_engine):
    database = 'mail_templates_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(postgres_engine.url.set(database=database))
    try:
        cli(engine.url, 'upgrade', '0026_mail_configuration')
        with engine.begin() as db:
            db.execute(text("UPDATE mail_event_config SET mode='MANUAL', to_recipients='[\"noc@example.com\"]'::jsonb"))
            db.execute(text("UPDATE mail_transport_config SET host='smtp.example.com', smtp_password_encrypted='opaque-encrypted-value'"))
            event = db.scalar(text('SELECT to_jsonb(e) FROM mail_event_config e'))
            smtp = db.scalar(text('SELECT to_jsonb(s) FROM mail_transport_config s'))
        cli(engine.url, 'upgrade', '0027_mail_templates')
        with engine.connect() as db:
            assert db.scalar(text('SELECT template FROM mail_event_config')) is None
            assert db.scalar(text("SELECT to_jsonb(e) - 'template' FROM mail_event_config e")) == event
            assert db.scalar(text('SELECT to_jsonb(s) FROM mail_transport_config s')) == smtp
        cli(engine.url, 'downgrade', '0026_mail_configuration')
        assert 'template' not in {column['name'] for column in inspect(engine).get_columns('mail_event_config')}
        cli(engine.url, 'upgrade', '0027_mail_templates')
        with engine.begin() as db:
            db.execute(text('UPDATE mail_event_config SET template=CAST(:template AS jsonb)'), {'template': __import__('json').dumps(sample())})
        with pytest.raises(AssertionError, match='plantillas configuradas'):
            cli(engine.url, 'downgrade', '0026_mail_configuration')
        with engine.begin() as db:
            assert db.scalar(text('SELECT template FROM mail_event_config')) == sample()
            db.execute(text('UPDATE mail_event_config SET template=NULL'))
        cli(engine.url, 'downgrade', '0026_mail_configuration')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))

@pytest.mark.parametrize(('elements', 'expected'), [
    (['texto 1', 'ACT-000005', '16/10/2026 18:56:00'], 'texto 1 ACT-000005 16/10/2026 18:56:00'),
    (['texto 1', '|', 'ACT-000005', '|', 'fecha'], 'texto 1 | ACT-000005 | fecha'),
    (['texto 1 | ', ' ACT-000005 ', ' | fecha'], 'texto 1 | ACT-000005 | fecha'),
    ([' texto  1 ', '', '  ', 'ACT-000005', '', ' / ', 'fecha '], 'texto 1 ACT-000005 / fecha'),
    (['', ' ', ''], ''),
    (['uno', '-', 'dos'], 'uno - dos'),
])
def test_subject_spacing(elements, expected):
    from ticketyn.notifications.templates import join_subject_elements
    assert join_subject_elements(elements) == expected


def test_empty_elements_persist_and_preview_without_placeholder_or_writes(api_client, operation_payload, db_session):
    activation = create(api_client, '/api/activations', operation_payload)
    template = {'version': 1, 'subject': [
        {'type': 'text', 'text': ''}, {'type': 'text', 'text': 'texto 1'},
        dynamic('activation.service_type'), dynamic('activation.reference'),
        {'type': 'text', 'text': ' '}, dynamic('activation.effective_at')],
        'body': [{'type': 'introduction', 'text': ''}, dynamic('activation.service_type'),
                 {'type': 'signature', 'text': ''}]}
    assert api_client.patch(EVENT + '/template', json=template).status_code == 200
    stored = api_client.get(EVENT + '/template').json()
    before = api_client.get(f"/api/activations/{activation['id']}").json()
    response = api_client.post(EVENT + '/preview', json={'activation_id': activation['id'], 'template': template})
    assert response.status_code == 200
    assert plain_result(response.json()) == {'subject': f"texto 1 {activation['reference']} 01/01/2020 12:00:00", 'body': ''}
    assert api_client.get(EVENT + '/template').json() == stored
    assert api_client.get(f"/api/activations/{activation['id']}").json() == before
    assert api_client.get(f"/api/activations/{activation['id']}/interventions").json() == []

@pytest.mark.parametrize(('middle', 'separator'), [
    ([], '\n'),
    ([{'type': 'introduction', 'text': ''}], '\n'),
    ([{'type': 'introduction', 'text': '\n\n'}], '\n\n'),
    ([{'type': 'introduction', 'text': 'Observación\n\nintencional'}], '\n\nObservación\n\nintencional\n\n'),
])
def test_compact_body_preserves_sections_order_and_explicit_breaks(api_client, operation_payload, middle, separator):
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': 'Línea uno\n\n  Línea tres'})
    template = {'version': 1, 'subject': [{'type': 'text', 'text': 'Asunto intacto'}], 'body': [
        {'type': 'introduction', 'text': 'Estimados,\nAviso'},
        dynamic('activation.reference'), *middle, dynamic('activation.activation_notes'),
        {'type': 'signature', 'text': 'Saludos,\nNOC'}]}
    assert api_client.patch(EVENT + '/template', json=template).status_code == 200
    stored = api_client.get(EVENT + '/template').json()
    before = api_client.get(f"/api/activations/{activation['id']}").json()
    result = api_client.post(EVENT + '/preview', json={'activation_id': activation['id'], 'template': stored})
    assert result.status_code == 200
    assert plain_result(result.json()) == {'subject': 'Asunto intacto', 'body': (
        f"Estimados,\nAviso\n\nCORRELATIVO: {activation['reference']}" + separator +
        'NOTAS DE ACTIVACIÓN:\nLínea uno\n\n  Línea tres\n\nSaludos,\nNOC')}
    assert api_client.get(EVENT + '/template').json() == stored
    assert api_client.get(f"/api/activations/{activation['id']}").json() == before
