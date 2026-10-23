"""All migration work runs only in databases created in the disposable test cluster."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from test_e2e_update_migration import cli


def test_upgrade_preserves_names_links_and_fms_and_detects_historical_duplicates(postgres_engine):
    name = 'nomenclature_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0036_customer_activation_notes')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO customers(name,customer_code) VALUES ('Old','C')"))
            connection.execute(text("INSERT INTO responsibles(name) VALUES ('Old')"))
            connection.execute(text("INSERT INTO nodes(name) VALUES ('N')"))
            connection.execute(text("INSERT INTO distribution_devices(node_id,name) VALUES (1,'D')"))
            connection.execute(text("INSERT INTO distribution_ports(distribution_device_id,name,active) VALUES (1,'Sfp+1',false)"))
            connection.execute(text("INSERT INTO circuits(customer_id,node_id,circuit_code,description,distribution_device_id,distribution_port_id) VALUES (1,1,'C','Old',1,1)"))
            connection.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference,activation_notes,distribution_recorded,distribution_device_name,distribution_port_name) VALUES (1,1,'2020-01-01T00:00:00Z',1,'A','Original',true,'Historical device','Historical snapshot')"))
            before = {table: connection.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all() for table in ('circuits', 'activations', 'distribution_ports')}
            # Simulate an old installation with a missing uniqueness index.
            connection.execute(text('DROP INDEX uq_distribution_ports_name_normalized'))
            connection.execute(text("INSERT INTO distribution_ports(distribution_device_id,name) VALUES (1,'sFP+1')"))
        with pytest.raises(AssertionError, match='Existen puertos equivalentes históricos'):
            cli(engine.url, 'upgrade', '0037_port_nomenclatures')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0036_customer_activation_notes'
            assert 'port_nomenclatures' not in inspect(connection).get_table_names()
            assert connection.scalar(text('SELECT count(*) FROM distribution_ports')) == 2
        # The fixture owns these disposable rows; operational migrations never repair them.
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM distribution_ports WHERE id=2'))
            connection.execute(text('CREATE UNIQUE INDEX uq_distribution_ports_name_normalized ON distribution_ports (distribution_device_id, lower(btrim(regexp_replace(name, \'[[:space:]]+\', \' \', \'g\')) COLLATE "C.utf8"))'))
        cli(engine.url, 'upgrade', '0038_port_classification')
        with engine.connect() as connection:
            for table, rows in before.items():
                after = connection.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all()
                if table == 'distribution_ports':
                    for row in after:
                        for key in ('nomenclature_id', 'numbering_format', 'number_components'):
                            assert row.pop(key) is None
                assert after == rows
            assert connection.scalar(text('SELECT count(*) FROM port_nomenclatures')) == 0
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("INSERT INTO distribution_ports(distribution_device_id,name) VALUES (1,'SFP+1')"))
        cli(engine.url, 'downgrade', '0036_customer_activation_notes')
        with engine.connect() as connection:
            assert connection.execute(text('SELECT to_jsonb(t) FROM distribution_ports t ORDER BY id')).scalars().all() == before['distribution_ports']
        cli(engine.url, 'upgrade', '0038_port_classification')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + name))
