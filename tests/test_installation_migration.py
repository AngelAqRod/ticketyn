"""Run only in the disposable PostgreSQL fixture, never the configured database."""
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text


def test_installation_upgrade_downgrade(postgres_engine):
    spec = importlib.util.spec_from_file_location('installation_migration', Path(__file__).parents[1] / 'alembic/versions/0042_installation_orders.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        schema = 'installation_migration_' + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA {schema}'))
        connection.execute(text(f'SET LOCAL search_path TO {schema}'))
        for table in ('customers', 'responsibles', 'circuits'):
            connection.execute(text(f'CREATE TABLE {table} (id integer PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE security_permissions (code varchar(100) PRIMARY KEY, description varchar(300) NOT NULL)'))
        try:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert connection.scalar(text('SELECT count(*) FROM security_permissions')) == 8
                tables = inspect(connection).get_table_names(schema=schema)
                assert len([name for name in tables if name.startswith('installation_')]) == 5
                constraints = inspect(connection).get_unique_constraints('installation_requests', schema=schema)
                assert any(c['column_names'] == ['mailbox', 'folder', 'uidvalidity', 'uid'] for c in constraints)
                migration.downgrade()
                assert not any(name.startswith('installation_') for name in inspect(connection).get_table_names(schema=schema))
                # Permission vocabulary survives rollback, matching migration 0031.
                assert connection.scalar(text('SELECT count(*) FROM security_permissions')) == 8
                migration.upgrade()
                assert connection.scalar(text('SELECT count(*) FROM security_permissions')) == 8
                migration.downgrade()
        finally:
            transaction.rollback()


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'alembic/versions' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_order_types_migration_classifies_only_unambiguous_orders(postgres_engine):
    import pytest
    from sqlalchemy.exc import DBAPIError, IntegrityError
    base, types = load('m42', '0042_installation_orders.py'), load('m45', '0045_installation_order_types.py')
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        schema = 'order_types_migration_' + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA {schema}'))
        connection.execute(text(f'SET LOCAL search_path TO {schema}'))
        for table in ('customers', 'responsibles', 'circuits', 'service_types', 'nodes', 'sectors'):
            connection.execute(text(f'CREATE TABLE {table} (id integer PRIMARY KEY)'))
            connection.execute(text(f'INSERT INTO {table} VALUES (1), (2)'))
        connection.execute(text('CREATE TABLE security_permissions (code varchar(100) PRIMARY KEY, description varchar(300) NOT NULL)'))
        try:
            with Operations.context(MigrationContext.configure(connection)):
                base.upgrade()
                for id, ref, circuit in ((1, 'OI-1', 1), (2, 'OI-2', None)):
                    connection.execute(text("INSERT INTO installation_orders (id, reference, customer_id, service, location, requested_at, created_by, circuit_id) VALUES (:i, :r, 1, 'Internet', 'Oficina', now(), 1, :c)"), dict(i=id, r=ref, c=circuit))
                types.upgrade()
                rows = dict(connection.execute(text('SELECT id, order_type FROM installation_orders')).all())
                assert rows == {1: 'NORMAL', 2: None}  # the unlinked legacy order is never classified automatically
                assert connection.scalar(text("SELECT service FROM installation_orders WHERE id = 2")) == 'Internet'  # nothing lost
                with pytest.raises(DBAPIError):  # type is permanent
                    with connection.begin_nested():
                        connection.execute(text("UPDATE installation_orders SET order_type = 'EXTRAORDINARY', circuit_id = NULL, description = 'x', service_type_id = 1, node_id = 1, sector_id = 1 WHERE id = 1"))
                with pytest.raises(IntegrityError):  # NORMAL cannot lose its circuit
                    with connection.begin_nested():
                        connection.execute(text('UPDATE installation_orders SET circuit_id = NULL WHERE id = 1'))
                connection.execute(text("UPDATE installation_orders SET order_type = 'NORMAL', circuit_id = 2 WHERE id = 2"))  # NULL -> NORMAL is the explicit classification
                connection.execute(text("INSERT INTO installation_orders (id, reference, customer_id, requested_at, created_by, order_type, description, service_type_id, node_id, sector_id) VALUES (3, 'OI-3', 1, now(), 1, 'EXTRAORDINARY', 'x', 1, 1, 1)"))
                with pytest.raises(RuntimeError):  # downgrade would have to invent legacy text
                    types.downgrade()
                connection.execute(text('DELETE FROM installation_orders WHERE id = 3'))
                connection.execute(text("UPDATE installation_orders SET service = 'Internet', location = 'Oficina' WHERE service IS NULL"))
                types.downgrade()
                assert 'order_type' not in {c['name'] for c in inspect(connection).get_columns('installation_orders', schema=schema)}
        finally:
            transaction.rollback()
