"""Real Alembic roundtrip in a disposable DB; the application never maps the probe."""
import pytest
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Text, create_engine, inspect, text
from sqlalchemy.orm import Session

from ticketyn.core.config import get_settings
from ticketyn.db.base import Base
from ticketyn.db.session import get_session

ROOT = Path(__file__).resolve().parents[1]
HEAD = '0007_e2e_recovery_probe'
PREVIOUS = '0005_e2e_update_probe'


def cli(url, action, revision):
    # Explicit URL of the disposable cluster; process isolation prevents settings cache reuse.
    environment = {**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False)}
    result = subprocess.run([sys.executable, '-B', '-m', 'alembic', '-c', str(ROOT/'alembic.ini'), action, revision],
                            cwd=ROOT, env=environment, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def snapshot(connection, column):
    # Every existing domain row, including timestamps, numbering and historical catalogs.
    columns = [column] if isinstance(column, str) else list(column)
    tables = sorted(set(inspect(connection).get_table_names()) & set(Base.metadata.tables))
    rows = {name: connection.execute(text(
        f'SELECT to_jsonb(t) - CAST(:columns AS text[]) FROM "{name}" t ORDER BY id'), {'columns': columns}).scalars().all()
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
    (PREVIOUS, '0006_e2e_postmigration_probe', '_ticketyn_e2e_postmigration_probe'),
    ('0006_e2e_postmigration_probe', HEAD, '_ticketyn_e2e_recovery_probe'),
    (PREVIOUS, HEAD, ('_ticketyn_e2e_postmigration_probe', '_ticketyn_e2e_recovery_probe')),
])
def test_probe_preserves_data_and_backend_and_roundtrip(postgres_engine, monkeypatch, previous, head, column):
    added_columns = [column] if isinstance(column, str) else list(column)
    name = 'e2e_update_'+uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE '+name))
    url = postgres_engine.url.set(database=name)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', previous)
        # Sembrar SQL del esquema histórico: el backend actual requiere 0009.
        # No hacer que código nuevo funcione artificialmente contra una DB antigua.
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO customers(customer_code,name) VALUES ('E2E','Cliente ficticio')"))
            connection.execute(text("INSERT INTO nodes(name) VALUES ('Nodo ficticio')"))
            connection.execute(text("INSERT INTO responsibles(name) VALUES ('Asignado ficticio')"))
            connection.execute(text("INSERT INTO circuits(customer_id,circuit_code,description,node_id) VALUES (1,'E2E-C','Enlace ficticio',1)"))
            for table in ('sectors', 'departments', 'incident_types'):
                connection.execute(text(f"INSERT INTO {table}(name) VALUES ('Ficticio')"))
            for number, status, end in [(1, 'OPEN', None), (2, 'CLOSED', '2026-10-01T11:00:00Z')]:
                connection.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,responsible_id,start_at,end_at,status) VALUES (:number,:reference,'Histórico ñ','Datos conservados',1,1,1,1,1,1,'2026-10-01T10:00:00Z',:end,:status)"),
                                   {'number': number, 'reference': f'E2E-{number}', 'end': end, 'status': status})
            existing = {item['name'] for item in inspect(connection).get_columns('tickets')}
            for prior in ('_ticketyn_e2e_update_probe', '_ticketyn_e2e_postmigration_probe'):
                if prior in existing:
                    connection.execute(text('UPDATE tickets SET '+prior+'=:value WHERE id=1'), {'value': 'Dato previo de '+prior})
            before = snapshot(connection, column)
        cli(url, 'upgrade', head)
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == head
            assert snapshot(connection, column) == before
            columns = {c['name']: c for c in inspect(connection).get_columns('tickets')}
            for added_column in added_columns:
                assert isinstance(columns[added_column]['type'], Text)
                assert columns[added_column]['nullable'] and columns[added_column]['default'] is None
                assert added_column not in Base.metadata.tables['tickets'].c
                assert connection.execute(text('SELECT '+added_column+' FROM tickets ORDER BY id')).scalars().all() == [None, None]
            if head == HEAD:
                assert {'_ticketyn_e2e_update_probe', '_ticketyn_e2e_postmigration_probe', '_ticketyn_e2e_recovery_probe'} <= set(columns)
        cli(url, 'downgrade', previous)
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == previous
            assert snapshot(connection, column) == before
        cli(url, 'upgrade', 'head')
        monkeypatch.setenv('DATABASE_URL', url.render_as_string(hide_password=False))
        get_settings.cache_clear()
        from ticketyn.main import create_app
        app = create_app()
        def session():
            with Session(engine) as db:
                yield db
        app.dependency_overrides[get_session] = session
        with TestClient(app) as client:
            for number in (1, 2):
                response = client.get(f'/api/tickets/{number}')
                assert response.status_code == 200
                assert response.json()['description'] == 'Datos conservados'
                assert response.json()['resolution'] is None
                assert all(field not in response.json() for field in added_columns)
            assert client.get('/health').json() == {'status': 'ok'}
            assert client.patch('/api/tickets/1', json={'title': 'Editado tras migración'}).status_code == 200
    finally:
        get_settings.cache_clear()
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE '+name))


def test_candidate_release_and_real_migration_lineage(tmp_path):
    spec = importlib.util.spec_from_file_location('update_validator', ROOT/'deploy/update_support.py')
    updater = importlib.util.module_from_spec(spec); spec.loader.exec_module(updater)
    assert updater.tag_version('v0.3.0') == '0.3.0'
    updater.forward('0.1.6', '0.3.0')
    # Applied migration bytes must still match the actual official source tag.
    tracked = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'v0.1.6', 'alembic'], cwd=ROOT).decode().splitlines()
    for name in tracked:
        assert (ROOT/name).read_bytes() == subprocess.check_output(['git', 'show', f'v0.1.6:{name}'], cwd=ROOT)
    assert updater.ri.project_version(ROOT) == '0.3.0'
    previous = tmp_path/'previous'; previous.mkdir()
    shutil.copytree(ROOT/'alembic', previous/'alembic', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT/'alembic.ini', previous/'alembic.ini')
    # The source release predates the additive follow-up migration.
    (previous/'alembic/versions/0008_ticket_updates.py').unlink()
    (previous/'alembic/versions/0009_ticket_resolution.py').unlink()
    (previous/'alembic/versions/0010_ticket_escalations.py').unlink()
    (previous/'alembic/versions/0011_department_positions.py').unlink()
    (previous/'alembic/versions/0012_catalog_name_uniqueness.py').unlink()
    archive = tmp_path/'candidate.tar'
    # The candidate retains every applied revision and adds follow-up/resolution.
    names = set(subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().strip('\0').split('\0'))
    with tarfile.open(archive, 'w') as output:
        for name in sorted(names):
            if updater.selected(name) and ((ROOT/name).exists() or (ROOT/name).is_symlink()):
                output.add(ROOT/name, arcname=name, recursive=False)
    candidate = tmp_path/'candidate'
    updater.extract_release(archive, candidate)
    assert updater.ri.project_version(candidate) == '0.3.0'
    assert updater.migration_plan(previous, candidate, HEAD) == '0012_catalog_name_uniqueness'
    # Also demonstrate the exact stable production path v0.2.0 -> v0.3.0.
    stable = tmp_path/'stable020'; stable.mkdir()
    shutil.copytree(ROOT/'alembic', stable/'alembic', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT/'alembic.ini', stable/'alembic.ini')
    for name in ('0010_ticket_escalations.py', '0011_department_positions.py', '0012_catalog_name_uniqueness.py'):
        (stable/'alembic/versions'/name).unlink()
    for name in subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'v0.2.0', 'alembic'], cwd=ROOT).decode().splitlines():
        assert (ROOT/name).read_bytes() == subprocess.check_output(['git', 'show', f'v0.2.0:{name}'], cwd=ROOT)
    updater.forward('0.2.0', '0.3.0')
    assert updater.migration_plan(stable, candidate, '0009_ticket_resolution') == '0012_catalog_name_uniqueness'

    assert (candidate/'alembic/versions/0008_ticket_updates.py').is_file()
    assert (candidate/'alembic/versions/0009_ticket_resolution.py').is_file()
    assert (candidate/'alembic/versions/0010_ticket_escalations.py').is_file()
    assert json.loads((ROOT/'frontend/package.json').read_text())['version'] == '0.3.0'
    lock = json.loads((ROOT/'frontend/package-lock.json').read_text())
    assert lock['version'] == lock['packages']['']['version'] == '0.3.0'
    assert (candidate/'frontend/dist/index.html').is_file()
    installation = subprocess.run(['bash', '-c', 'source "$1/install.sh"; SOURCE="$2"; check_project; validate_release_source "$SOURCE"; project_version "$SOURCE"', 'release-check', str(ROOT), str(candidate)], capture_output=True, text=True)
    assert installation.returncode == 0, installation.stderr
    assert installation.stdout.strip() == '0.3.0'

    assert (candidate/'update.sh').read_bytes() == (ROOT/'update.sh').read_bytes()
    assert (candidate/'deploy/update_support.py').read_bytes() == (ROOT/'deploy/update_support.py').read_bytes()
