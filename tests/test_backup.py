"""Backup helpers use temporary paths/mocks; never the production installation."""
import hashlib
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tarfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'backup.sh'
SECRET = 'synthetic-backup-secret-not-a-real-password'


def shell(code):
    return subprocess.run(['bash', '-c', 'source "$1"\n' + code, 'test', str(SCRIPT)],
                          capture_output=True, text=True, timeout=15)


@pytest.fixture
def installation(tmp_path):
    config = tmp_path/'etc/ticketyn'
    config.mkdir(parents=True, mode=0o700)
    env = config/'ticketyn.env'
    env.write_text(f'DATABASE_URL=postgresql+psycopg://ticketyn:{SECRET}@127.0.0.1:5432/ticketyn\n')
    env.chmod(0o600)
    app = tmp_path/'opt/ticketyn'
    release = app/'releases/0.1.0'
    release.mkdir(parents=True)
    (release/'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    (app/'current').symlink_to(release)
    backups = tmp_path/'backups/ticketyn'
    backups.mkdir(parents=True, mode=0o700)
    return dict(config=config, env=env, app=app, release=release, backups=backups,
                trace=tmp_path/'postgres-arguments', root=tmp_path)


def setup(i):
    variables = dict(CONFIG_DIR=i['config'], CONFIG_FILE=i['env'], APP_ROOT=i['app'],
                     RELEASES_DIR=i['app']/'releases', CURRENT_FILE=i['app']/'current', BACKUP_DIR=i['backups'])
    lines = [f'{key}={shlex.quote(str(value))}' for key, value in variables.items()]
    return '\n'.join(lines) + '''
umask 077
WORK=''; WORK_ID=''; FINAL_PATH=''
# Only owner/group is virtualized; actual modes, file types, hashes and inodes are checked.
stat() {
    if [[ $1 == -c && $2 == %u:%g ]]; then echo 0:0
    else command stat "$@"; fi
}
chown() { :; }
trap backup_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
'''


def mocks(i):
    return f'''
backup_postgres() {{
    printf '%s\\n' "$*" >> "{i['trace']}"
    case "$1" in
        psql)
            printf '%s\\n' 'server_version=17.6' 'encoding=UTF8' 'owner=ticketyn' 'alembic_revision=0004_nodes_responsibles' ;;
        pg_dump)
            if [[ ${{DUMP_FAIL:-0}} == 1 ]]; then
                printf '%s\\n' '{SECRET}' >&2
                printf 'partial dump'
                return 17
            fi
            printf 'synthetic-custom-dump' ;;
        *) return 99 ;;
    esac
}}
env() {{
    if [[ "$*" == *'pg_restore'* ]]; then return "${{RESTORE_FAIL:-0}}"
    elif [[ "$*" == *'pg_dump --version'* ]]; then echo 'pg_dump (PostgreSQL) 17.6'
    else command env "$@"; fi
}}
'''


RUN = 'backup_preflight\nbackup_prepare\nbackup_dump\nbackup_metadata\nbackup_publish\n'


def assert_integrity(archive, dest):
    with tarfile.open(archive) as package:
        assert package.getnames() == ['database.dump', 'ticketyn.env', 'metadata.txt', 'MANIFEST.txt', 'SHA256SUMS']
        assert all(item.isfile() and item.mode == 0o600 for item in package.getmembers())
        package.extractall(dest, filter='data')
    for line in (dest/'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.sha256((dest/name).read_bytes()).hexdigest() == digest


def test_backup_requires_root():
    if os.geteuid() == 0:
        pytest.skip('The suite normally runs without root.')
    result = subprocess.run([str(SCRIPT)], text=True, capture_output=True, timeout=5)
    assert result.returncode != 0 and 'como root' in result.stderr


def test_successful_backup_manifest_integrity_permissions(installation):
    i = installation
    result = shell(setup(i) + mocks(i) + RUN)
    assert result.returncode == 0, result.stderr
    assert SECRET not in result.stdout + result.stderr
    assert 'DATABASE_URL' not in result.stdout + result.stderr
    assert result.stderr == ''
    archives = list(i['backups'].glob('*.tar'))
    assert len(archives) == 1 and '-v0.1.0-' in archives[0].name
    assert archives[0].stat().st_mode & 0o777 == 0o600
    assert i['backups'].stat().st_mode & 0o777 == 0o700
    assert not list(i['backups'].glob('.ticketyn-backup.*'))
    extracted = i['root']/'inspect'
    assert_integrity(archives[0], extracted)
    assert (extracted/'ticketyn.env').read_text() == i['env'].read_text()
    metadata = (extracted/'metadata.txt').read_text()
    assert 'ticketyn_version=0.1.0' in metadata and 'expected_git_tag=v0.1.0' in metadata
    assert 'alembic_revision=0004_nodes_responsibles' in metadata
    assert str(i['release']) in metadata
    assert 'SHA256SUMS' in (extracted/'MANIFEST.txt').read_text()
    assert SECRET not in metadata + (extracted/'MANIFEST.txt').read_text()
    assert SECRET not in i['trace'].read_text()
    check = subprocess.run(['sha256sum', '--check', '--strict', 'SHA256SUMS'], cwd=extracted, capture_output=True)
    assert check.returncode == 0
    (extracted/'database.dump').write_bytes(b'changed')
    assert subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=extracted, capture_output=True).returncode != 0
    (extracted/'metadata.txt').unlink()
    assert subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=extracted, capture_output=True).returncode != 0


@pytest.mark.parametrize('failure', ['DUMP_FAIL=1', 'RESTORE_FAIL=1'])
def test_dump_failure_or_invalid_dump_never_published(installation, failure):
    i = installation
    result = shell(setup(i) + mocks(i) + failure + '\n' + RUN)
    assert result.returncode != 0
    assert SECRET not in result.stdout + result.stderr
    assert list(i['backups'].iterdir()) == []


@pytest.mark.parametrize('problem', ['missing', 'mode', 'symlink', 'hardlink', 'invalid_url', 'shell_code', 'extra_variable', 'owner'])
def test_missing_or_insecure_config_is_rejected(installation, problem):
    i = installation
    extra = ''
    if problem == 'missing':
        i['env'].unlink()
    elif problem == 'mode':
        i['env'].chmod(0o644)
    elif problem == 'symlink':
        target = i['config']/'actual.env'
        i['env'].rename(target); i['env'].symlink_to(target)
    elif problem == 'hardlink':
        os.link(i['env'], i['config']/'alias.env')
    elif problem == 'invalid_url':
        i['env'].write_text('DATABASE_URL=postgresql+psycopg://other:secret@remote/other\n')
    elif problem == 'shell_code':
        i['env'].write_text(f'DATABASE_URL=$(touch "{i["root"]}/SHOULD_NOT_EXIST")\n')
    elif problem == 'extra_variable':
        with i['env'].open('a') as config:
            config.write('OTHER_SECRET=value\n')
    else:
        extra = 'stat() { if [[ $2 == %u:%g ]]; then echo 1000:1000; else command stat "$@"; fi; }\n'
    result = shell(setup(i) + mocks(i) + extra + RUN)
    assert result.returncode != 0
    assert list(i['backups'].iterdir()) == []
    assert SECRET not in result.stdout + result.stderr
    assert not (i['root']/'SHOULD_NOT_EXIST').exists()


@pytest.mark.parametrize('problem', ['current_missing', 'outside_release', 'release_symlink', 'version_mismatch', 'project_symlink'])
def test_invalid_active_installation_rejected(installation, problem):
    i = installation
    current = i['app']/'current'
    if problem == 'current_missing':
        current.unlink()
    elif problem == 'outside_release':
        current.unlink(); current.symlink_to(i['config'])
    elif problem == 'release_symlink':
        moved = i['app']/'outside'
        i['release'].rename(moved); i['release'].symlink_to(moved)
    elif problem == 'version_mismatch':
        (i['release']/'pyproject.toml').write_text('version = "0.2.0"\n')
    else:
        project = i['release']/'pyproject.toml'
        original = i['root']/'project'
        project.rename(original); project.symlink_to(original)
    result = shell(setup(i) + mocks(i) + RUN)
    assert result.returncode != 0
    assert list(i['backups'].iterdir()) == []


@pytest.mark.parametrize('problem', ['symlink', 'mode', 'file', 'missing'])
def test_backup_directory_policy(installation, problem):
    i = installation
    i['backups'].rmdir()
    if problem == 'symlink':
        i['backups'].symlink_to(i['config'])
    elif problem == 'mode':
        i['backups'].mkdir(mode=0o755)
    elif problem == 'file':
        i['backups'].write_text('preserve')
    result = shell(setup(i) + mocks(i) + RUN)
    assert (result.returncode == 0) == (problem == 'missing'), result.stderr
    if problem == 'missing':
        assert i['backups'].stat().st_mode & 0o777 == 0o700
    elif problem == 'file':
        assert i['backups'].read_text() == 'preserve'
    elif problem == 'symlink':
        assert i['backups'].is_symlink()


def test_collision_during_publication_preserves_existing_backup(installation):
    i = installation
    result = shell(setup(i) + mocks(i) + '''
backup_preflight; backup_prepare; backup_dump; backup_metadata
printf 'administrator backup' > "$FINAL_PATH"
backup_publish
''')
    assert result.returncode != 0
    archives = list(i['backups'].glob('*.tar'))
    assert len(archives) == 1 and archives[0].read_text() == 'administrator backup'
    assert not list(i['backups'].glob('.ticketyn-backup.*'))


@pytest.mark.parametrize('failure', ['tar', 'sync'])
def test_disk_or_archive_failure_publishes_nothing(installation, failure):
    i = installation
    result = shell(setup(i) + mocks(i) + f'''
backup_preflight; backup_prepare; backup_dump; backup_metadata
{failure}() {{ return 28; }}
backup_publish
''')
    assert result.returncode != 0
    assert list(i['backups'].iterdir()) == []


def test_post_publication_sync_failure_removes_only_own_artifact(installation):
    i = installation
    result = shell(setup(i) + mocks(i) + '''
backup_preflight; backup_prepare; backup_dump; backup_metadata
SYNC_COUNT=0
sync() { SYNC_COUNT=$((SYNC_COUNT + 1)); [[ $SYNC_COUNT == 1 ]]; }
backup_publish
''')
    assert result.returncode != 0
    assert list(i['backups'].iterdir()) == []


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM, signal.SIGKILL])
def test_interruption_never_publishes_partial_backup(installation, sig):
    i = installation
    code = setup(i) + mocks(i) + '''
backup_preflight; backup_prepare
printf partial > "$CONTENT/database.dump"
printf 'READY\\n'
read -r answer
'''
    process = subprocess.Popen(['bash', '-c', 'source "$1"\n' + code, 'test', str(SCRIPT)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline() == 'READY\n'
        process.send_signal(sig)
        process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill(); process.communicate(timeout=5)
    assert not list(i['backups'].glob('*.tar'))
    if sig != signal.SIGKILL:
        assert list(i['backups'].iterdir()) == []
    else:
        remaining = list(i['backups'].glob('.ticketyn-backup.*'))
        assert len(remaining) == 1 and remaining[0].stat().st_mode & 0o777 == 0o700


def test_configuration_changed_during_dump_aborts(installation):
    i = installation
    result = shell(setup(i) + mocks(i) + '''
backup_preflight; backup_prepare
original_postgres=$(declare -f backup_postgres)
# Replace pg_dump only; maintain the known metadata responses.
backup_postgres() {
    if [[ $1 == pg_dump ]]; then
        printf 'dump'
        printf '# changed\n' >> "$CONFIG_FILE"
    else
        printf '%s\n' 'server_version=17.6' 'encoding=UTF8' 'owner=ticketyn' 'alembic_revision=0004_nodes_responsibles'
    fi
}
backup_dump
''')
    assert result.returncode != 0 and 'cambió' in result.stderr
    assert list(i['backups'].iterdir()) == []


def test_peer_command_does_not_forward_credentials(tmp_path):
    # The runuser executable is virtualized; inspect actual env -i behavior.
    log = tmp_path/'arguments'
    peer = tmp_path/'peer'
    peer.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" > "{log}"\nenv\n')
    peer.chmod(0o755)
    result = shell(f'''
export DATABASE_URL='DO_NOT_FORWARD_URL' PGPASSWORD='DO_NOT_FORWARD_PASSWORD' PGHOST='remote'
runuser() {{ shift 3; "$@"; }}
backup_postgres "{peer}"
''')
    assert result.returncode == 0, result.stderr
    assert 'DO_NOT_FORWARD' not in result.stdout + result.stderr + log.read_text()
    assert 'remote' not in result.stdout
    assert '--host=/var/run/postgresql --port=5432 --username=postgres --dbname=ticketyn --no-password' in log.read_text()


def test_real_dump_can_be_restored_in_disposable_cluster(installation, postgres_engine):
    """Native tools against test-only DBs; never production paths/credentials."""
    import uuid
    from sqlalchemy import create_engine, text

    name = 'backup_probe_' + uuid.uuid4().hex
    restored = name + '_restored'
    admin = postgres_engine.execution_options(isolation_level='AUTOCOMMIT')
    role_created = False
    engines = []
    try:
        with admin.connect() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='ticketyn'")):
                conn.exec_driver_sql('CREATE ROLE ticketyn')
                role_created = True
            conn.exec_driver_sql(f'CREATE DATABASE {name} OWNER ticketyn TEMPLATE template0 ENCODING \'UTF8\'')
            conn.exec_driver_sql(f'CREATE DATABASE {restored} TEMPLATE template0 ENCODING \'UTF8\'')
        source = create_engine(postgres_engine.url.set(database=name))
        target = create_engine(postgres_engine.url.set(database=restored))
        engines.extend([source, target])
        with source.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE alembic_version (version_num varchar(64))')
            conn.exec_driver_sql("INSERT INTO alembic_version VALUES ('0004_nodes_responsibles')")
            conn.exec_driver_sql('CREATE TABLE probe (id serial PRIMARY KEY, name text)')
            conn.execute(text('INSERT INTO probe(name) VALUES (:name)'), {'name': 'Nodo Ñ · Responsable Á'})
        host = postgres_engine.url.query['host']
        port = postgres_engine.url.query['port']
        user = postgres_engine.url.username
        native = f'''\nbackup_postgres() {{
    env -i PATH=/usr/bin:/bin PGOPTIONS='-c default_transaction_read_only=on' "$1" \\
        --host={shlex.quote(host)} --port={port} --username={shlex.quote(user)} \\
        --dbname={name} --no-password "${{@:2}}"
}}
'''
        result = shell(setup(installation) + native + RUN)
        assert result.returncode == 0, result.stderr
        assert SECRET not in result.stdout + result.stderr
        artifact = next(installation['backups'].glob('*.tar'))
        dump = installation['root']/'restoration.dump'
        with tarfile.open(artifact) as archive:
            dump.write_bytes(archive.extractfile('database.dump').read())
        subprocess.run(['pg_restore', '--host', host, '--port', port, '--username', user,
                        '--dbname', restored, '--no-owner', '--no-privileges', '--exit-on-error',
                        str(dump)], check=True, capture_output=True)
        with target.connect() as conn:
            assert conn.scalar(text('SELECT name FROM probe')) == 'Nodo Ñ · Responsable Á'
            assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0004_nodes_responsibles'
            assert conn.scalar(text("SELECT nextval('probe_id_seq')")) == 2
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS {restored}')
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS {name}')
            if role_created:
                conn.exec_driver_sql('DROP ROLE ticketyn')
