from uuid import uuid4
from sqlalchemy import create_engine, inspect, text
from test_e2e_update_migration import cli, snapshot


def test_0014_to_0015_preserves_existing_circuits_and_fms(postgres_engine):
    database = 'service_types_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(postgres_engine.url.set(database=database))
    try:
        cli(engine.url, 'upgrade', '0014_circuit_operations')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('ST','Histórico')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description,active,initial_capacity,initial_capacity_unit) VALUES (1,'ST-1','Enlace',false,250,'Mbps')"))
            db.execute(text("INSERT INTO responsibles(name) VALUES ('Operador histórico')"))
            for table in ('sectors', 'departments', 'incident_types'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Ejemplo')"))
            db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,status) VALUES (1,'ST-1','Histórico','Conservar',1,1,1,1,1,'2020-01-01T12:00:00Z','OPEN')"))
            db.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference) VALUES (1,1,'2020-01-01T12:00:00Z',1,'ACT-000001')"))
            db.execute(text("INSERT INTO activation_interventions(activation_id,responsible_id,occurred_at,content) VALUES (1,1,'2019-01-01T12:00:00Z','Datos técnicos')"))
            db.execute(text("INSERT INTO capacity_changes(circuit_id,responsible_id,effective_at,operation_type,new_capacity,new_unit) VALUES (1,1,'2020-01-01T13:00:00Z','INCREASE',500,'Mbps')"))
            db.execute(text("INSERT INTO circuit_lifecycle_operations(circuit_id,responsible_id,effective_at,operation_type,reason_id) VALUES (1,1,'2020-01-01T14:00:00Z','DEACTIVATE',1)"))
            before = snapshot(db, [])
        cli(engine.url, 'upgrade', '0015_circuit_service_types')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0015_circuit_service_types'
            after = snapshot(db, ['service_type_id'])
            assert {name: rows for name,rows in after[0].items() if name != 'service_types'} == before[0]
            assert after[0]['service_types'] == []
            for old, new in zip(before[1:], after[1:]):
                assert set(old) <= set(new)
            assert db.scalar(text('SELECT service_type_id FROM circuits')) is None
            column = next(c for c in inspect(db).get_columns('circuits') if c['name'] == 'service_type_id')
            assert column['nullable']
            fk = next(fk for fk in inspect(db).get_foreign_keys('circuits') if fk['constrained_columns'] == ['service_type_id'])
            assert fk['referred_table'] == 'service_types' and fk['options'].get('ondelete') != 'CASCADE'
        cli(engine.url, 'downgrade', '0014_circuit_operations')
        with engine.connect() as db:
            assert snapshot(db, []) == before
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
