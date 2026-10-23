"""Upgrade/downgrade only on a fresh database in the ephemeral test cluster."""
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
import pytest

from test_e2e_update_migration import cli


def test_0033_upgrade_downgrade_preserves_existing_data(postgres_engine):
    name = 'distribution_migration_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0032_responsible_selectable')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO customers(name,customer_code) VALUES ('Histórico','HIST')"))
            connection.execute(text("INSERT INTO responsibles(name) VALUES ('Responsable histórico')"))
            connection.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'OLD','Circuito sin nodo')"))
            connection.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference,activation_notes) VALUES (1,1,'2020-01-01T00:00:00Z',1,'ACT-OLD',:notes)"), {'notes': 'Notas originales\nSin inventar distribución'})
            tables = ('customers', 'responsibles', 'circuits', 'activations', 'security_roles', 'security_config',
                      'mail_transport_config', 'mail_event_config')
            existing = set(inspect(connection).get_table_names())
            before = {table: connection.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text')).scalars().all()
                      for table in tables if table in existing}
        cli(engine.url, 'upgrade', '0033_distribution_devices_ports')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0033_distribution_devices_ports'
            for table, rows in before.items():
                after = connection.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text')).scalars().all()
                if table == 'circuits':
                    for row in after:
                        assert row.pop('distribution_device_id') is None
                        assert row.pop('distribution_port_id') is None
                assert after == rows
            assert connection.scalar(text("SELECT count(*) FROM security_permissions WHERE code LIKE 'distribution_%'")) == 14
            assert connection.scalar(text('SELECT count(*) FROM distribution_audit')) == 0
            foreign_keys = {fk['name'] for fk in inspect(connection).get_foreign_keys('circuits')}
            assert {'fk_circuits_distribution_device_node', 'fk_circuits_distribution_port_device'} <= foreign_keys
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO nodes(name) VALUES ('NODO')"))
            connection.execute(text("INSERT INTO distribution_devices(node_id,name) VALUES (1,'CORE')"))
            connection.execute(text("INSERT INTO distribution_ports(distribution_device_id,name) VALUES (1,'sfp+1')"))
            connection.execute(text("INSERT INTO circuits(customer_id,node_id,circuit_code,description,distribution_device_id,distribution_port_id) VALUES (1,1,'NEW','Actual',1,1)"))
            connection.execute(text("INSERT INTO security_role_permissions(role_id,permission_code) SELECT id,'distribution_devices.view' FROM security_roles WHERE code='OPERATOR'"))
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO distribution_devices(node_id,name) VALUES (1,' core ' )"))
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text('UPDATE circuits SET distribution_device_id=NULL WHERE distribution_port_id=1'))
        cli(engine.url, 'downgrade', '0032_responsible_selectable')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0032_responsible_selectable'
            assert not {'distribution_devices', 'distribution_ports', 'distribution_audit'} & set(inspect(connection).get_table_names())
            assert connection.scalar(text("SELECT count(*) FROM security_permissions WHERE code LIKE 'distribution_%'")) == 14
            assert connection.execute(text('SELECT to_jsonb(t) FROM activations t ORDER BY id')).scalars().all() == before['activations']
            assert connection.execute(text('SELECT to_jsonb(t) FROM responsibles t ORDER BY id')).scalars().all() == before['responsibles']
            assert connection.scalar(text('SELECT count(*) FROM circuits')) == 2
        # Revision is repeatable after a clean test-only downgrade.
        cli(engine.url, 'upgrade', '0033_distribution_devices_ports')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + name))
