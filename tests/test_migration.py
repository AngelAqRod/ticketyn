from io import StringIO
from pathlib import Path
import runpy
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_mock_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from ticketyn.db.base import Base
from ticketyn import models  # noqa: F401


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
    Base.metadata.create_all(engine, checkfirst=False)

    def normalize(statements):
        return {" ".join(statement.split()) for statement in statements if statement.strip()}

    initial_statements = [
        statement for statement in output.getvalue().split(";")
        if not statement.strip().startswith("CREATE TABLE services")
    ]
    assert normalize(initial_statements) == normalize(model_statements)
    assert set(Base.metadata.tables) == {"customers", "circuits", "sectors"}


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
            retained = {table: table_structure(table) for table in Base.metadata.tables}
            connection.execute(text("INSERT INTO services (name) VALUES ('Dato histórico')"))

            with Operations.context(context):
                removal["upgrade"]()
            assert set(inspect(connection).get_table_names(schema=schema)) == set(Base.metadata.tables)
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
