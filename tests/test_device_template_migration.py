"""Actual Alembic roundtrip in a separate database of the disposable cluster."""
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, inspect, text
from test_e2e_update_migration import cli


def test_template_migration_preserves_topology_and_guards_downgrade(postgres_engine):
    name = 'template_migration_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0038_port_classification')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO nodes(name) VALUES ('Nodo existente')"))
            connection.execute(text("INSERT INTO distribution_devices(node_id,name) VALUES (1,'Equipo existente')"))
            connection.execute(text("INSERT INTO distribution_ports(distribution_device_id,name) VALUES (1,'Legado1')"))
            connection.execute(text("INSERT INTO customers(name,customer_code) VALUES ('Histórico','HIST')"))
            connection.execute(text("INSERT INTO responsibles(name) VALUES ('Responsable histórico')"))
            connection.execute(text("INSERT INTO circuits(customer_id,circuit_code,description,node_id,distribution_device_id,distribution_port_id) VALUES (1,'OLD','Sin cambios',1,1,1)"))
            connection.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference,activation_notes) VALUES (1,1,'2020-01-01T00:00:00Z',1,'ACT-OLD','Notas originales')"))
            before = {table: connection.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all()
                      for table in ('distribution_devices', 'distribution_ports', 'circuits', 'activations', 'responsibles')}
        cli(engine.url, 'upgrade', '0039_device_templates')
        with engine.begin() as connection:
            for table, data in before.items():
                assert connection.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all() == data
            assert connection.scalar(text("SELECT count(*) FROM security_permissions WHERE code LIKE 'catalogs.distribution_device_templates.%'")) == 4
            assert 'distribution_device_template_groups' in inspect(connection).get_table_names()
        cli(engine.url, 'downgrade', '0038_port_classification')
        cli(engine.url, 'upgrade', '0039_device_templates')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO distribution_device_templates(name) VALUES ('Modelo conservado')"))
        with pytest.raises(AssertionError, match='Downgrade inseguro'):
            cli(engine.url, 'downgrade', '0038_port_classification')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM distribution_device_templates')) == 1
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + name))
