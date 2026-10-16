from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import text, select
from test_fms import operation_payload, create
from test_ticket_exports import pdf_strings


def test_catalog_normalized_uniqueness_and_lifecycle(api_client, ticket_payload, db_session):
    model = create(api_client, '/api/cpe-models', {'name': '  MikroTik   CCR  '})
    assert model['name'] == 'MikroTik CCR'
    for name in ['mikrotik ccr', 'MIKROTIK  CCR', '\tMikroTik\tCCR\t']:
        assert api_client.post('/api/cpe-models', json={'name': name}).status_code == 409
    assert api_client.post('/api/cpe-models', json={'name': ' \t '}).status_code == 422
    second = create(api_client, '/api/cpe-models', {'name': 'Cisco'})
    assert api_client.patch(f"/api/cpe-models/{second['id']}", json={'name': 'mikrotik CCR'}).status_code == 409
    assert api_client.patch(f"/api/cpe-models/{model['id']}", json={'name': model['name']}).status_code == 200
    cid = ticket_payload['circuit_id']
    assert api_client.patch(f'/api/circuits/{cid}', json={'cpe_model_id': model['id']}).status_code == 200
    assert api_client.patch(f"/api/cpe-models/{model['id']}", json={'active': False}).status_code == 200
    assert all(x['id'] != model['id'] for x in api_client.get('/api/cpe-models').json())
    assert api_client.patch(f'/api/circuits/{cid}', json={'description': 'Editado', 'cpe_model_id': model['id']}).status_code == 200
    body = {'customer_id':ticket_payload['customer_id'],'circuit_code':'NEW','description':'Nuevo','node_id':ticket_payload['node_id'],'sector_id':ticket_payload['sector_id']}
    assert api_client.post('/api/circuits', json={**body,'cpe_model_id':model['id']}).status_code == 422
    assert api_client.post('/api/circuits', json=body).status_code == 201
    assert api_client.patch(f'/api/circuits/{cid}', json={'cpe_model_id': None}).json()['cpe_model'] is None
    assert api_client.patch(f'/api/circuits/{cid}', json={'cpe_model_id': model['id']}).status_code == 422
    assert api_client.patch(f"/api/cpe-models/{model['id']}", json={'active': True}).status_code == 200
    assert api_client.post('/api/circuits', json={**body,'circuit_code':'NEW2','cpe_model_id':model['id']}).status_code == 201
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("INSERT INTO cpe_models(name) VALUES ('\tMIKROTIK   CCR\t')"))


def test_configuration_preserves_bytes_and_stays_out_of_dtos(api_client, operation_payload, pdf_strings):
    cid = operation_payload['circuit_id']
    config = '  /interface\n\tset name="<script>alert(1)</script>"\r\n  password=PRIVATE_CPE_SENTINEL  \n'
    response = api_client.patch(f'/api/circuits/{cid}/cpe-configuration', json={'configuration': config})
    assert response.status_code == 200 and response.json()['configuration'] == config
    assert response.headers['cache-control'] == 'no-store'
    assert api_client.get(f'/api/circuits/{cid}/cpe-configuration').json()['configuration'] == config
    activation = create(api_client, '/api/activations', operation_payload)
    for path in ['/api/circuits', f'/api/circuits/{cid}', f'/api/circuits/{cid}/operational-detail', '/api/activations', f"/api/activations/{activation['id']}", '/api/fms/reports/activations/details', '/api/activations/export/pdf', '/api/activations/export/xlsx', f"/api/activations/{activation['id']}/reports/pdf", '/api/fms/reports/activations/export/pdf']:
        response = api_client.get(path)
        assert response.status_code == 200, response.text
        assert b'PRIVATE_CPE_SENTINEL' not in response.content
        if 'spreadsheetml' in response.headers['content-type']:
            from openpyxl import load_workbook
            from io import BytesIO
            workbook = load_workbook(BytesIO(response.content))
            assert all('PRIVATE_CPE_SENTINEL' not in str(cell.value) for sheet in workbook for row in sheet for cell in row)
        if 'json' in response.headers['content-type']: assert 'cpe_configuration' not in response.text
    assert 'PRIVATE_CPE_SENTINEL' not in ' '.join(pdf_strings)
    assert api_client.patch(f'/api/circuits/{cid}/cpe-configuration', json={'configuration': ''}).json()['configuration'] == ''
    assert api_client.patch(f'/api/circuits/{cid}/cpe-configuration', json={'configuration': None}).json()['configuration'] is None
    assert api_client.get('/api/circuits/999999/cpe-configuration').status_code == 404
    assert api_client.patch(f'/api/circuits/{cid}/cpe-configuration', json={'configuration': 'x'*500001}).status_code == 422


def test_snapshot_name_and_initial_capacity_survive_mutable_circuit(api_client, operation_payload, pdf_strings):
    service = create(api_client, '/api/service-types', {'name': 'Internet dedicado original'})
    cid = operation_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={'service_type_id': service['id'], 'initial_capacity':'1758.5','initial_capacity_unit':'Mbps'})
    activation = create(api_client, '/api/activations', operation_payload)
    assert activation['service_type_name'] == 'Internet dedicado original'
    assert Decimal(activation['initial_capacity']) == Decimal('1758.5')
    api_client.patch(f"/api/service-types/{service['id']}", json={'name':'NO MOSTRAR SERVICIO ACTUAL'})
    create(api_client, '/api/capacity-changes', {**operation_payload,'operation_type':'INCREASE','previous_capacity':'1758.5','previous_unit':'Mbps','new_capacity':'3','new_unit':'Gbps'})
    api_client.patch(f'/api/circuits/{cid}', json={'initial_capacity':'99','initial_capacity_unit':'Gbps','service_type_id': None})
    current = api_client.get(f"/api/activations/{activation['id']}").json()
    assert current['service_type_name'] == activation['service_type_name']
    assert current['initial_capacity'] == activation['initial_capacity']
    response = api_client.get(f"/api/activations/{activation['id']}/reports/pdf")
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    for value in ['Internet dedicado original','1.759 Gbps','Tipo de servicio histórico','Capacidad inicial histórica','GESTIÓN DE SERVICIOS · OPERACIONES FMS']: assert value in content
    assert '99 Gbps' not in content and 'NO MOSTRAR SERVICIO ACTUAL' not in content
    Path('/tmp/ticketyn-042-activation.pdf').write_bytes(response.content)
    assert api_client.post('/api/activations', json={**operation_payload,'service_type_name':'Inventado'}).status_code == 422


def test_old_or_optional_history_not_replaced(api_client, operation_payload, db_session, pdf_strings):
    activation = create(api_client, '/api/activations', operation_payload)
    assert activation['initial_capacity'] is None and activation['service_type_name'] is None
    service = create(api_client, '/api/service-types', {'name': 'NUEVO SERVICIO ACTUAL'})
    api_client.patch(f"/api/circuits/{operation_payload['circuit_id']}", json={'initial_capacity':'1','initial_capacity_unit':'Gbps','service_type_id':service['id']})
    assert api_client.get(f"/api/activations/{activation['id']}/reports/pdf").status_code == 200
    assert 'NUEVO SERVICIO ACTUAL' not in ' '.join(pdf_strings)
    assert 'Sin registrar' in ' '.join(pdf_strings)
    assert api_client.get('/api/system/version').json() == {'version':'0.5.0'}
    assert api_client.get('/health').json() == {'status':'ok'}


def test_real_migration_preserves_old_data_without_inference(postgres_engine):
    from uuid import uuid4
    from sqlalchemy import create_engine
    from test_e2e_update_migration import cli
    name = 'cpe_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0018_recover_ticket_nodes')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'C','Cliente')"))
            db.execute(text("INSERT INTO service_types(id,name) VALUES(1,'Servicio mutable')"))
            db.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Operador')"))
            db.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description,service_type_id,initial_capacity,initial_capacity_unit) VALUES(1,1,'C-1','Anterior',1,200,'Mbps')"))
            db.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference) VALUES(1,1,'2020-01-01T00:00:00Z',1,'ACT-1')"))
            circuit = db.scalar(text('SELECT to_jsonb(c) FROM circuits c'))
            activation = db.scalar(text('SELECT to_jsonb(a) FROM activations a'))
        cli(engine.url, 'upgrade', '0019_cpe_activation_snapshots')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0019_cpe_activation_snapshots'
            c = db.scalar(text('SELECT to_jsonb(c) FROM circuits c'))
            a = db.scalar(text('SELECT to_jsonb(a) FROM activations a'))
            for field in ('cpe_model_id','cpe_configuration'): assert c.pop(field) is None
            for field in ('service_type_name','initial_capacity','initial_capacity_unit'): assert a.pop(field) is None
            assert c == circuit and a == activation
            assert db.scalar(text('SELECT count(*) FROM cpe_models')) == 0
        cli(engine.url, 'downgrade', '0018_recover_ticket_nodes')
        cli(engine.url, 'upgrade', '0019_cpe_activation_snapshots')
        with engine.begin() as db:
            db.execute(text("UPDATE circuits SET cpe_configuration='Datos a preservar'"))
        import subprocess, sys, os
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable,'-m','alembic','downgrade','0018_recover_ticket_nodes'],cwd=root,env={**os.environ,'DATABASE_URL':engine.url.render_as_string(hide_password=False)},text=True,capture_output=True)
        assert result.returncode != 0 and 'Downgrade inseguro' in result.stderr
        with engine.connect() as db: assert db.scalar(text('SELECT cpe_configuration FROM circuits')) == 'Datos a preservar'
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin: admin.execute(text('DROP DATABASE ' + name))


def test_database_failure_does_not_propagate_configuration(api_client, ticket_payload, monkeypatch, caplog):
    from sqlalchemy.exc import OperationalError
    import ticketyn.api.circuits as circuits
    def fail(*args, **kwargs):
        raise OperationalError('UPDATE circuits', {'configuration':'DO_NOT_LOG_PRIVATE_CONFIG'}, RuntimeError('Unavailable'))
    monkeypatch.setattr(circuits, 'update_item', fail)
    response = api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}/cpe-configuration", json={'configuration':'DO_NOT_LOG_PRIVATE_CONFIG'})
    assert response.status_code == 503
    assert 'DO_NOT_LOG_PRIVATE_CONFIG' not in response.text
    assert 'DO_NOT_LOG_PRIVATE_CONFIG' not in caplog.text


def test_activation_cpe_snapshot_is_immutable(api_client, operation_payload, pdf_strings):
    model = create(api_client, '/api/cpe-models', {'name': 'MikroTik CCR original'})
    cid = operation_payload['circuit_id']
    service = create(api_client, '/api/service-types', {'name': 'Internet dedicado histórico'})
    assert api_client.patch(f'/api/circuits/{cid}', json={'cpe_model_id': model['id'], 'service_type_id': service['id'], 'initial_capacity': '1758.5', 'initial_capacity_unit': 'Mbps'}).status_code == 200
    activation = create(api_client, '/api/activations', operation_payload)
    assert activation['cpe_activation'] == model['name']
    assert api_client.patch(f"/api/cpe-models/{model['id']}", json={'name': 'MODELO RENOMBRADO', 'active': False}).status_code == 200
    # An inactive model already assigned remains valid historical source.
    assert create(api_client, '/api/activations', operation_payload)['cpe_activation'] == 'MODELO RENOMBRADO'
    replacement = create(api_client, '/api/cpe-models', {'name': 'MODELO ACTUAL'})
    assert api_client.patch(f'/api/circuits/{cid}', json={'cpe_model_id': replacement['id']}).status_code == 200
    assert api_client.get(f"/api/activations/{activation['id']}").json()['cpe_activation'] == 'MikroTik CCR original'
    response = api_client.get(f"/api/activations/{activation['id']}/reports/pdf")
    assert response.status_code == 200
    content = ' '.join(pdf_strings)
    assert 'CPE de activación' in content and 'MikroTik CCR original' in content
    assert 'MODELO ACTUAL' not in content and 'MODELO RENOMBRADO' not in content
    Path('/tmp/ticketyn-042-cpe-activation.pdf').write_bytes(response.content)
    assert api_client.post('/api/activations', json={**operation_payload, 'cpe_activation': 'Inventado'}).status_code == 422


def test_missing_cpe_snapshot_has_no_current_fallback(api_client, operation_payload, pdf_strings):
    activation = create(api_client, '/api/activations', operation_payload)
    assert activation['cpe_activation'] is None
    model = create(api_client, '/api/cpe-models', {'name': 'NO USAR MODELO ACTUAL'})
    api_client.patch(f"/api/circuits/{operation_payload['circuit_id']}", json={'cpe_model_id': model['id']})
    assert api_client.get(f"/api/activations/{activation['id']}").json()['cpe_activation'] is None
    assert api_client.get(f"/api/activations/{activation['id']}/reports/pdf").status_code == 200
    content = ' '.join(pdf_strings)
    assert 'CPE de activación' in content and 'Sin registrar' in content
    assert model['name'] not in content


def test_0020_preserves_existing_activation_and_does_not_backfill(postgres_engine):
    from uuid import uuid4
    from sqlalchemy import create_engine
    from test_e2e_update_migration import cli
    name = 'snapshot_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0019_cpe_activation_snapshots')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'C','Cliente')"))
            db.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Operador')"))
            db.execute(text("INSERT INTO cpe_models(id,name) VALUES(1,'CPE actual')"))
            db.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description,cpe_model_id) VALUES(1,1,'C-1','Anterior',1)"))
            db.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference,service_type_name,initial_capacity,initial_capacity_unit) VALUES(1,1,'2020-01-01T00:00:00Z',1,'ACT-1','Servicio original',200,'Mbps')"))
            previous = db.scalar(text('SELECT to_jsonb(a) FROM activations a'))
        cli(engine.url, 'upgrade', '0020_activation_cpe')
        with engine.connect() as db:
            current = db.scalar(text('SELECT to_jsonb(a) FROM activations a'))
            assert current.pop('cpe_activation') is None
            assert current == previous
            assert db.scalar(text('SELECT cpe_model_id FROM circuits')) == 1
        cli(engine.url, 'downgrade', '0019_cpe_activation_snapshots')
        cli(engine.url, 'upgrade', '0020_activation_cpe')
        with engine.begin() as db:
            db.execute(text("UPDATE activations SET cpe_activation='Snapshot a conservar'"))
        import subprocess, sys, os
        result = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', '0019_cpe_activation_snapshots'], env={**os.environ, 'DATABASE_URL': engine.url.render_as_string(hide_password=False)}, capture_output=True, text=True)
        assert result.returncode != 0 and 'Downgrade inseguro' in result.stderr
        with engine.connect() as db:
            assert db.scalar(text('SELECT cpe_activation FROM activations')) == 'Snapshot a conservar'
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + name))
