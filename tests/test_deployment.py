"""Exercise the real Alembic CLI against a new database in the test cluster."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text

from ticketyn.db.base import Base


def test_alembic_cli_from_empty_database(postgres_engine, tmp_path):
    # This engine belongs exclusively to the disposable cluster in conftest.
    # Never read .env or a caller's DATABASE_URL to select the target.
    assert not postgres_engine.url.host
    assert Path(postgres_engine.url.query['host']).is_absolute()
    assert Path(postgres_engine.url.query['host']).name == 'socket'
    database = f'ticketyn_cli_{uuid4().hex}'
    database_url = postgres_engine.url.set(database=database)
    root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        'DATABASE_URL': database_url.render_as_string(hide_password=False),
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    environment.pop('PYTHONPATH', None)
    engine = None
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text(f'CREATE DATABASE "{database}"'))
        try:
            engine = create_engine(database_url)
            assert inspect(engine).get_table_names() == []
            def alembic(*args):
                # Outside the checkout: no implicit .env or source import shortcut.
                result = subprocess.run(
                    [sys.executable, '-m', 'alembic', '-c', str(root / 'alembic.ini'), *args],
                    cwd=tmp_path, env=environment, capture_output=True, text=True,
                    timeout=60,
                )
                assert result.returncode == 0, result.stderr
                return result.stdout
            alembic('upgrade', 'head')
            assert '0005_e2e_update_probe (head)' in alembic('current')
            inspector = inspect(engine)
            assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {'alembic_version'}
            probe = next(item for item in inspector.get_columns('tickets') if item['name'] == '_ticketyn_e2e_update_probe')
            assert probe['nullable'] and probe['default'] is None
            assert '_ticketyn_e2e_update_probe' not in Base.metadata.tables['tickets'].c
            for table, column, target in [('circuits', 'node_id', 'nodes'), ('tickets', 'responsible_id', 'responsibles')]:
                assert next(item for item in inspector.get_columns(table) if item['name'] == column)['nullable']
                assert any(item['constrained_columns'] == [column] and item['referred_table'] == target for item in inspector.get_foreign_keys(table))
            with engine.connect() as connection:
                assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0005_e2e_update_probe'
                for table in Base.metadata.tables:
                    assert connection.scalar(text(f'SELECT count(*) FROM "{table}"')) == 0
        finally:
            if engine is not None:
                engine.dispose()
            admin.execute(text(f'DROP DATABASE "{database}"'))
