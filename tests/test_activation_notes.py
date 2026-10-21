"""Activation notes are optional data, not interventions or operational edits."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text

from test_e2e_update_migration import cli
from test_fms import create, operation_payload  # noqa: F401 -- shared fixture
from ticketyn.models.fms import Activation


@pytest.mark.parametrize('extra,expected', [
    ({}, None),
    ({'activation_notes': None}, None),
    ({'activation_notes': ''}, None),
    ({'activation_notes': ' \t\r\n '}, None),
    ({'activation_notes': '  IP pública: 192.0.2.1\nNAT configurado\r\nPuerto deshabilitado  '},
     '  IP pública: 192.0.2.1\nNAT configurado\r\nPuerto deshabilitado  '),
    ({'activation_notes': 'x' * 10000}, 'x' * 10000),
])
def test_create_and_query_notes(api_client, operation_payload, db_session, extra, expected):
    row = create(api_client, '/api/activations', {**operation_payload, **extra})
    assert row['activation_notes'] == expected
    assert db_session.scalar(select(Activation.activation_notes).where(Activation.id == row['id'])) == expected
    assert api_client.get(f"/api/activations/{row['id']}").json()['activation_notes'] == expected
    assert api_client.get('/api/activations').json()[0]['activation_notes'] == expected
    assert api_client.get(f"/api/activations/{row['id']}/interventions").json() == []


@pytest.mark.parametrize('notes', ['x' * 10001, ' ' * 10001, 123, ['not text']])
def test_invalid_creation_does_not_consume_number(api_client, operation_payload, db_session, notes):
    before = api_client.get('/api/settings/activation-number').json()
    response = api_client.post('/api/activations', json={**operation_payload, 'activation_notes': notes})
    assert response.status_code == 422
    assert api_client.get('/api/activations').json() == []
    assert api_client.get('/api/settings/activation-number').json() == before


def test_notes_are_immutable_and_corrections_use_interventions(api_client, operation_payload):
    cid = operation_payload['circuit_id']
    service = create(api_client, '/api/service-types', {'name': 'Servicio histórico'})
    model = create(api_client, '/api/cpe-models', {'name': 'CPE histórico'})
    assert api_client.patch(f'/api/circuits/{cid}', json={
        'service_type_id': service['id'], 'cpe_model_id': model['id'],
        'initial_capacity': '100', 'initial_capacity_unit': 'Mbps',
    }).status_code == 200
    row = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': 'Original'})
    path = f"/api/activations/{row['id']}"
    circuit_before = api_client.get(f'/api/circuits/{cid}').json()
    numbering = api_client.get('/api/settings/activation-number').json()
    for notes in ('Intento de editar', None, ''):
        assert api_client.patch(path + '/notes', json={'activation_notes': notes}).status_code == 403
        assert api_client.patch(path, json={'activation_notes': notes}).status_code == 403
    assert api_client.get(path).json() == row
    assert api_client.get(path + '/interventions').json() == []
    correction = create(api_client, path + '/interventions', {
        'responsible_id': operation_payload['responsible_id'],
        'occurred_at': operation_payload['effective_at'], 'content': 'Corrección documentada en bitácora',
    })
    assert api_client.get(path + '/interventions').json() == [correction]
    assert api_client.get(path).json() == row
    assert api_client.get(f'/api/circuits/{cid}').json() == circuit_before
    assert api_client.get('/api/settings/activation-number').json() == numbering
    assert '/api/activations/{id}/notes' not in api_client.get('/openapi.json').json()['paths']


@pytest.mark.parametrize('path,extra', [
    ('/api/capacity-changes', {'operation_type': 'INCREASE', 'new_capacity': '10', 'new_unit': 'Mbps'}),
    ('/api/circuit-lifecycle', {'operation_type': 'REACTIVATE'}),
])
def test_notes_not_accepted_by_other_operations(api_client, operation_payload, path, extra):
    assert api_client.post(path, json={**operation_payload, **extra, 'activation_notes': 'Solo activaciones'}).status_code == 422
    row = create(api_client, path, {**operation_payload, **extra})
    assert 'activation_notes' not in row


def test_migration_preserves_existing_activation(postgres_engine):
    database = 'activation_notes_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(postgres_engine.url.set(database=database))
    try:
        cli(engine.url, 'upgrade', '0024_default_change_types_upper')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'C','Cliente')"))
            db.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Operador')"))
            db.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description) VALUES(1,1,'C-1','Conservar')"))
            db.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference,service_type_name,initial_capacity,initial_capacity_unit,cpe_activation) VALUES(1,1,'2020-01-01T00:00:00Z',1,'ACT-1','Servicio original',100,'Mbps','CPE original')"))
            db.execute(text("INSERT INTO activation_interventions(activation_id,responsible_id,occurred_at,content) VALUES(1,1,'2020-01-01T00:00:00Z','Original')"))
            snapshots = {table: db.execute(text(f'SELECT to_jsonb(t) FROM {table} t')).scalars().all()
                         for table in ('activations', 'activation_interventions', 'circuits', 'activation_number_config')}
        cli(engine.url, 'upgrade', '0025_activation_notes')
        cli(engine.url, 'upgrade', '0025_activation_notes')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0025_activation_notes'
            after = db.scalar(text('SELECT to_jsonb(a) FROM activations a'))
            assert after.pop('activation_notes') is None
            assert after == snapshots['activations'][0]
            for table in ('activation_interventions', 'circuits', 'activation_number_config'):
                assert db.execute(text(f'SELECT to_jsonb(t) FROM {table} t')).scalars().all() == snapshots[table]
            column = next(c for c in inspect(engine).get_columns('activations') if c['name'] == 'activation_notes')
            assert column['nullable'] and str(column['type']) == 'TEXT'
        cli(engine.url, 'downgrade', '0024_default_change_types_upper')
        cli(engine.url, 'upgrade', '0025_activation_notes')
        with engine.begin() as db:
            db.execute(text("UPDATE activations SET activation_notes='Conservar notas'"))
        # Match the existing safeguards against losing operational text on downgrade.
        from pathlib import Path
        import os
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-B', '-m', 'alembic', 'downgrade', '0024_default_change_types_upper'],
                                cwd=Path(__file__).resolve().parents[1],
                                env={**os.environ, 'DATABASE_URL': engine.url.render_as_string(hide_password=False)},
                                capture_output=True, text=True, timeout=30)
        assert result.returncode != 0 and 'Downgrade inseguro' in result.stderr
        with engine.connect() as db:
            assert db.scalar(text('SELECT activation_notes FROM activations')) == 'Conservar notas'
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
