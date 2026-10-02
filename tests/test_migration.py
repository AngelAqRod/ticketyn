from io import StringIO
from pathlib import Path
import runpy

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_mock_engine

from ticketyn.db.base import Base
from ticketyn import models  # noqa: F401


def test_initial_migration_matches_models():
    """Comparar DDL PostgreSQL sin ejecutar la migración ni abrir conexiones."""
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

    assert normalize(output.getvalue().split(";")) == normalize(model_statements)
