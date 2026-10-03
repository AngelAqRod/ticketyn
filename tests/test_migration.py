from io import StringIO
import hashlib
from pathlib import Path
import runpy
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_mock_engine, inspect, text, MetaData
from sqlalchemy.exc import IntegrityError

from ticketyn.db.base import Base
from ticketyn import models  # noqa: F401

def normalized_ddl(statements):
    result = set()
    for statement in statements:
        value = ' '.join(statement.split())
        if not value:
            continue
        if value.startswith('CREATE TABLE '):
            start = value.index('(')
            body = value[start + 1:-1]
            parts, current, depth = [], '', 0
            for character in body:
                if character == ',' and depth == 0:
                    parts.append(current.strip()); current = ''; continue
                depth += (character == '(') - (character == ')')
                current += character
            parts.append(current.strip())
            value = value[:start] + '(' + ', '.join(sorted(parts)) + ')'
        result.add(value)
    return result


def historical_metadata():
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        if table.name not in {'nodes', 'responsibles'}:
            table.to_metadata(metadata)
    for table_name, field in [('circuits', 'node_id'), ('tickets', 'responsible_id')]:
        table = metadata.tables[table_name]
        for constraint in list(table.constraints):
            if field in constraint.columns:
                table.constraints.remove(constraint)
        for index in list(table.indexes):
            if field in index.columns:
                table.indexes.remove(index)
        for foreign_key in list(table.c[field].foreign_keys):
            table.foreign_keys.discard(foreign_key)
        table._columns.remove(table.c[field])
    return metadata


INITIAL_TABLES = {"customers", "circuits", "sectors"}


def test_applied_migrations_are_unchanged():
    versions = Path(__file__).resolve().parents[1] / "alembic/versions"
    expected = {
        "0003_ticket_domain.py": "c21135545cb6e23afbf75d2413ff733d3f2c2591a0652a51f2049a1d5d6eba89",
        "0001_initial_catalogs.py": "ee2a7351ba4028f4b7a49661bb700574e04a571246f9d1795c1c097829bcc648",
        "0002_remove_services.py": "bc1ceae086cc1be911a2ccee190af1cd544e9e4f76f954c1f615e33ae6a817ec",
    }
    for filename, digest in expected.items():
        assert hashlib.sha256((versions / filename).read_bytes()).hexdigest() == digest

def test_retained_initial_tables_match_models():
    """Comparar las tablas conservadas de 0001 con los modelos actuales."""
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0001_initial_catalogs.py"
    )
    revision = runpy.run_path(str(revision_path))
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        revision["upgrade"]()

    model_statements = []

    def collect(statement, *args, **kwargs):
        model_statements.append(str(statement.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql+psycopg://", collect)
    legacy = historical_metadata()
    legacy.create_all(
        engine, tables=[legacy.tables[name] for name in INITIAL_TABLES], checkfirst=False
    )

    def normalize(statements):
        return normalized_ddl(statements)

    initial_statements = [
        statement for statement in output.getvalue().split(";")
        if not statement.strip().startswith("CREATE TABLE services")
    ]
    assert normalize(initial_statements) == normalize(model_statements)
    assert INITIAL_TABLES <= set(Base.metadata.tables)


def test_remove_services_migration_roundtrip(postgres_engine):
    """Ejecutar 0001/0002 y revertir 0002 solo en el PostgreSQL temporal."""
    versions = Path(__file__).resolve().parents[1] / "alembic/versions"
    initial = runpy.run_path(str(versions / "0001_initial_catalogs.py"))
    removal = runpy.run_path(str(versions / "0002_remove_services.py"))
    assert initial["down_revision"] is None
    assert removal["down_revision"] == initial["revision"]
    assert removal["revision"] == "0002_remove_services"

    schema = f"migration_test_{uuid4().hex}"
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            # Separado de las tablas usadas por las pruebas ORM/API.
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            context = MigrationContext.configure(connection)

            def table_structure(table):
                inspector = inspect(connection)
                columns = [
                    {**column, "type": repr(column["type"])}
                    for column in inspector.get_columns(table, schema=schema)
                ]
                return {
                    "columns": columns,
                    "primary_key": inspector.get_pk_constraint(table, schema=schema),
                    "unique": inspector.get_unique_constraints(table, schema=schema),
                    "indexes": inspector.get_indexes(table, schema=schema),
                    "foreign_keys": inspector.get_foreign_keys(table, schema=schema),
                }

            with Operations.context(context):
                initial["upgrade"]()
            assert set(inspect(connection).get_table_names(schema=schema)) == {
                "customers", "circuits", "services", "sectors"
            }
            original = table_structure("services")
            retained = {table: table_structure(table) for table in INITIAL_TABLES}
            connection.execute(text("INSERT INTO services (name) VALUES ('Dato histórico')"))

            with Operations.context(context):
                removal["upgrade"]()
            assert set(inspect(connection).get_table_names(schema=schema)) == INITIAL_TABLES
            assert {table: table_structure(table) for table in retained} == retained

            with Operations.context(context):
                removal["downgrade"]()
            assert table_structure("services") == original
            assert {table: table_structure(table) for table in retained} == retained
            assert connection.scalar(text("SELECT count(*) FROM services")) == 0
            restored = connection.execute(text(
                "INSERT INTO services (name) VALUES ('Restaurado') "
                "RETURNING id, name, active, created_at"
            )).one()
            assert restored.id == 1
            assert restored.name == "Restaurado"
            assert restored.active is True
            assert restored.created_at.tzinfo is not None
            with pytest.raises(IntegrityError) as error:
                with connection.begin_nested():
                    connection.execute(text("INSERT INTO services (name) VALUES ('Restaurado')"))
            assert error.value.orig.diag.constraint_name == "uq_services_name"
        finally:
            transaction.rollback()


def test_ticket_migration_matches_models_offline():
    versions = Path(__file__).resolve().parents[1] / "alembic/versions"
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        runpy.run_path(str(versions / "0001_initial_catalogs.py"))["upgrade"]()
        runpy.run_path(str(versions / "0003_ticket_domain.py"))["upgrade"]()
    migration_statements = [
        statement for statement in output.getvalue().split(";")
        if statement.strip() and not statement.strip().startswith("CREATE TABLE services")
    ]
    model_statements = []

    def collect(statement, *args, **kwargs):
        model_statements.append(str(statement.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql+psycopg://", collect)
    historical_metadata().create_all(engine, checkfirst=False)
    normalize = normalized_ddl
    assert normalize(migration_statements) == normalize(model_statements)


def test_ticket_migration_upgrade_and_downgrade(postgres_engine):
    versions = Path(__file__).resolve().parents[1] / "alembic/versions"
    initial = runpy.run_path(str(versions / "0001_initial_catalogs.py"))
    removal = runpy.run_path(str(versions / "0002_remove_services.py"))
    tickets = runpy.run_path(str(versions / "0003_ticket_domain.py"))
    assert tickets["down_revision"] == removal["revision"]
    assert tickets["revision"] == "0003_ticket_domain"
    schema = f"ticket_migration_{uuid4().hex}"

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                initial["upgrade"]()
                removal["upgrade"]()

            def original_structure():
                metadata = []
                inspector = inspect(connection)
                for table in sorted(INITIAL_TABLES):
                    metadata.append((table, [
                        {**column, "type": repr(column["type"])}
                        for column in inspector.get_columns(table, schema=schema)
                    ], inspector.get_pk_constraint(table, schema=schema),
                       inspector.get_unique_constraints(table, schema=schema),
                       inspector.get_foreign_keys(table, schema=schema),
                       inspector.get_indexes(table, schema=schema)))
                return metadata

            before = original_structure()
            connection.execute(text("INSERT INTO customers (customer_code, name) VALUES ('MIGRATION', 'Prueba')"))
            with Operations.context(context):
                tickets["upgrade"]()
            inspector = inspect(connection)
            assert set(inspector.get_table_names(schema=schema)) == set(historical_metadata().tables)
            assert original_structure() == before
            for table in ("departments", "incident_types", "ticket_number_config", "tickets"):
                assert connection.scalar(text(f'SELECT count(*) FROM "{table}"')) == 0
            ticket_columns = {column["name"] for column in inspector.get_columns("tickets", schema=schema)}
            assert "duration" not in ticket_columns and "duration_seconds" not in ticket_columns
            checks = {check["name"] for check in inspector.get_check_constraints("tickets", schema=schema)}
            assert checks == {"ck_tickets_status_values", "ck_tickets_valid_dates", "ck_tickets_positive_ticket_number"}
            assert len(inspector.get_foreign_keys("tickets", schema=schema)) == 5
            with Operations.context(context):
                tickets["downgrade"]()
            assert set(inspect(connection).get_table_names(schema=schema)) == INITIAL_TABLES
            assert original_structure() == before
            assert connection.scalar(text("SELECT customer_code FROM customers")) == "MIGRATION"
        finally:
            transaction.rollback()
