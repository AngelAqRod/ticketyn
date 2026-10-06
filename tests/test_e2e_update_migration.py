"""Real Alembic roundtrip in a disposable DB; the application never maps the probe."""
import pytest
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from ticketyn.core.config import get_settings
from ticketyn.db.base import Base
from ticketyn.db.session import get_session

ROOT = Path(__file__).resolve().parents[1]
HEAD = '0006_e2e_postmigration_probe'
PREVIOUS = '0005_e2e_update_probe'


def cli(url, action, revision):
    # Explicit URL of the disposable cluster; process isolation prevents settings cache reuse.
    environment = {**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False)}
    result = subprocess.run([sys.executable, '-B', '-m', 'alembic', '-c', str(ROOT/'alembic.ini'), action, revision],
                            cwd=ROOT, env=environment, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def snapshot(connection, column):
    # Every existing domain row, including timestamps, numbering and historical catalogs.
    tables = sorted(Base.metadata.tables)
    rows = {name: connection.execute(text(
        f'SELECT to_jsonb(t) - :column FROM "{name}" t ORDER BY id'), {'column': column}).scalars().all()
            for name in tables}
    constraints = connection.execute(text("SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
        "FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY conrelid, conname")).all()
    sequences = connection.execute(text("SELECT sequencename, sequenceowner, data_type, start_value, min_value, "
        "max_value, increment_by, cycle, cache_size, last_value FROM pg_sequences "
        "WHERE schemaname='public' ORDER BY sequencename")).all()
    indexes = connection.execute(text("SELECT tablename, indexname, indexdef FROM pg_indexes "
        "WHERE schemaname='public' ORDER BY tablename,indexname")).all()
    return rows, constraints, sequences, indexes


@pytest.mark.parametrize("previous, head, column", [
    ('0004_nodes_responsibles', '0005_e2e_update_probe', '_ticketyn_e2e_update_probe'),
    (PREVIOUS, HEAD, '_ticketyn_e2e_postmigration_probe'),
])
def test_probe_preserves_data_and_backend_and_roundtrip(postgres_engine, monkeypatch, previous, head, column):
    name = 'e2e_update_'+uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE '+name))
    url = postgres_engine.url.set(database=name)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', previous)
        monkeypatch.setenv('DATABASE_URL', url.render_as_string(hide_password=False))
        get_settings.cache_clear()
        # The app uses an explicit test Session; never the default/dev engine.
        from ticketyn.main import create_app
        app = create_app()
        def session():
            with Session(engine) as db:
                yield db
        app.dependency_overrides[get_session] = session
        with TestClient(app) as client:
            def post(path, value):
                response = client.post('/api/'+path, json=value)
                assert response.status_code == 201, response.text
                return response.json()
            customer = post('customers', {'customer_code': 'E2E', 'name': 'Cliente ficticio'})
            node = post('nodes', {'name': 'Nodo ficticio'})
            responsible = post('responsibles', {'name': 'Asignado ficticio'})
            circuit = post('circuits', {'customer_id': customer['id'], 'circuit_code': 'E2E-C', 'description': 'Circuito ficticio', 'node_id': node['id']})
            ids = {field+'_id': post(path, {'name': 'Catálogo ficticio'})['id']
                   for field, path in [('sector', 'sectors'), ('department', 'departments'), ('incident_type', 'incident-types')]}
            payload = {**ids, 'customer_id': customer['id'], 'circuit_id': circuit['id'], 'responsible_id': responsible['id'],
                       'title': 'Incidencia histórica ñ', 'description': 'Dato previo conservado', 'start_at': '2026-10-01T10:00:00+00:00'}
            opened = post('tickets', payload)
            closed = post('tickets', {**payload, 'status': 'CLOSED', 'end_at': '2026-10-01T11:00:00+00:00'})
            with engine.connect() as connection:
                before = snapshot(connection, column)
                assert connection.scalar(text('SELECT version_num FROM alembic_version')) == previous
            cli(url, 'upgrade', head)
            with engine.connect() as connection:
                assert connection.scalar(text('SELECT version_num FROM alembic_version')) == head
                assert snapshot(connection, column) == before
                columns = {c['name']: c for c in inspect(connection).get_columns('tickets')}
                assert columns[column]['nullable'] is True and columns[column]['default'] is None
                assert column not in Base.metadata.tables['tickets'].c
                assert connection.execute(text('SELECT '+column+' FROM tickets ORDER BY id')).scalars().all() == [None, None]
            for ticket in (opened, closed):
                response = client.get('/api/tickets/'+str(ticket['id']))
                assert response.status_code == 200 and response.json() == ticket
                assert column not in response.json()
            assert client.get('/health').status_code == 503
            updated = client.patch('/api/tickets/'+str(opened['id']), json={'title': 'Editado tras migración'})
            assert updated.status_code == 200
            added = post('tickets', {**payload, 'title': 'Creado tras migración'})
            with engine.begin() as connection:
                assert connection.scalar(text('SELECT '+column+' FROM tickets WHERE id=:id'), {'id': added['id']}) is None
                connection.execute(text('UPDATE tickets SET '+column+'=NULL WHERE id=:id'), {'id': added['id']})
                before_downgrade = snapshot(connection, column)
            cli(url, 'downgrade', previous)
            with engine.connect() as connection:
                assert connection.scalar(text('SELECT version_num FROM alembic_version')) == previous
                assert column not in {c['name'] for c in inspect(connection).get_columns('tickets')}
                assert snapshot(connection, column) == before_downgrade
            # Reapply the actual migration after the tested downgrade; no automatic updater rollback.
            cli(url, 'upgrade', head)
            assert client.get('/api/tickets/'+str(added['id'])).status_code == 200
    finally:
        get_settings.cache_clear()
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE '+name))


def test_candidate_release_and_real_migration_lineage(tmp_path):
    spec = importlib.util.spec_from_file_location('update_validator', ROOT/'deploy/update_support.py')
    updater = importlib.util.module_from_spec(spec); spec.loader.exec_module(updater)
    assert updater.tag_version('v0.1.3-test.1') == '0.1.3-test.1'
    updater.forward('0.1.2-test.1', '0.1.3-test.1')
    assert updater.ri.project_version(ROOT) == '0.1.3'
    previous = tmp_path/'previous'; previous.mkdir()
    shutil.copytree(ROOT/'alembic', previous/'alembic', ignore=shutil.ignore_patterns('0006_e2e_postmigration_probe.py', '__pycache__', '*.pyc'))
    shutil.copy2(ROOT/'alembic.ini', previous/'alembic.ini')
    archive = tmp_path/'candidate.tar'
    # Include tracked working files plus the new (not yet committed) migration.
    names = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().strip('\0').split('\0'))
    names.add('alembic/versions/0006_e2e_postmigration_probe.py')
    with tarfile.open(archive, 'w') as output:
        for name in sorted(names):
            if updater.selected(name):
                output.add(ROOT/name, arcname=name, recursive=False)
    candidate = tmp_path/'candidate'
    updater.extract_release(archive, candidate)
    assert updater.ri.project_version(candidate) == '0.1.3'
    assert updater.migration_plan(previous, candidate, PREVIOUS) == HEAD
    assert (candidate/'frontend/dist/index.html').is_file()
