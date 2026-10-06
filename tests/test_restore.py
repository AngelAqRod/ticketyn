"""All paths/services are virtualized; native PG tests use the disposable cluster."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tarfile
import tempfile
import time

import pytest
from test_backup import installation, setup

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'restore.sh'
SUPPORT = ROOT/'deploy/restore_support.py'
SECRET = 'synthetic-backup-secret-not-a-real-password'
HEAD = '0004_nodes_responsibles'
MAJOR = int(subprocess.check_output(['pg_restore', '--version'], text=True).split()[2].split('.')[0])
spec = importlib.util.spec_from_file_location('restore_support', SUPPORT)
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def components(i):
    metadata = {
        'backup_format': 'ticketyn-backup-v1', 'created_at_utc': '2026-10-05T12:00:00Z',
        'completed_dump_at_utc': '2026-10-05T12:01:00Z', 'ticketyn_version': '0.1.0',
        'expected_git_tag': 'v0.1.0', 'release_name': '0.1.0', 'source_release_path': '/opt/ticketyn/releases/0.1.0',
        'pyproject_sha256': hashlib.sha256((i['release']/'pyproject.toml').read_bytes()).hexdigest(),
        'database': 'ticketyn', 'dump_format': 'PostgreSQL custom', 'pg_dump_version': f'pg_dump (PostgreSQL) {MAJOR}.6',
        'server_version': f'{MAJOR}.6', 'encoding': 'UTF8', 'owner': 'ticketyn', 'alembic_revision': HEAD,
    }
    return {'database.dump': b'fake custom dump', 'ticketyn.env': i['env'].read_bytes(),
            'metadata.txt': ''.join(f'{key}={value}\n' for key, value in metadata.items()).encode(),
            'MANIFEST.txt': 'Ticketyn — backup lógico completo\n'.encode()}


def package(i, parts=None, additions=()):
    parts = parts if parts is not None else components(i)
    parts = dict(parts)
    if 'SHA256SUMS' not in parts:
        parts['SHA256SUMS'] = ''.join(f'{hashlib.sha256(value).hexdigest()}  {name}\n'
                                    for name, value in parts.items()).encode()
    path = i['root']/'backup.tar'
    with tarfile.open(path, 'w') as archive:
        for name, value in parts.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(value))
        for member in additions:
            archive.addfile(member, io.BytesIO(b'x') if member.size else None)
    path.chmod(0o600)
    return path


def shell(code, stdin=''):
    return subprocess.run(['bash', '-c', 'source "$1"\nsource "$2"\n' + code,
                           'test', str(ROOT/'backup.sh'), str(SCRIPT)], input=stdin,
                          text=True, capture_output=True, timeout=20)


def validate(i, archive):
    return subprocess.run(['python3', '-I', str(SUPPORT), 'validate', str(archive),
                           str(i['root']/'validated')], text=True, capture_output=True)


@pytest.fixture
def environment(installation):
    i = installation
    i['archive'] = package(i)
    i['unit'] = i['root']/'ticketyn.service'
    i['unit'].write_text((ROOT/'deploy/systemd/ticketyn.service').read_text())
    i['nginx'] = i['root']/'nginx-ticketyn'
    i['nginx'].write_text('server {\n listen 8080;\n}\n')
    i['link'] = i['root']/'enabled-ticketyn'
    i['link'].symlink_to(i['nginx'])
    binary = i['release']/'.venv/bin/python'
    binary.parent.mkdir(parents=True)
    binary.write_text(f'#!/bin/sh\necho {HEAD}\n')
    binary.chmod(0o755)
    i['db'] = i['root']/'db.json'
    i['db'].write_text(json.dumps({'ticketyn': '100'}))
    i['active'] = i['root']/'active'
    i['active'].write_text('1')
    i['calls'] = i['root']/'calls'
    i['calls'].write_text('')
    i['fake'] = i['root']/'fake_pg.py'
    i['fake'].write_text('''import json, pathlib, re, sys
path=pathlib.Path(sys.argv[1]); trace=pathlib.Path(sys.argv[2]); args=sys.argv[3:]
sql=args[args.index('-c')+1]; db=json.loads(path.read_text())
if sql.startswith('SELECT oid '):
    print(db.get(re.search("datname='([^']+)'",sql)[1], ''))
elif "system_identifier" in sql: print(987654321)
elif "current_setting('server_version_num')" in sql: print(''' + str(MAJOR * 10000 + 6) + ''')
elif sql.startswith("SELECT count(*) FROM pg_roles"): print(1)
elif sql.startswith('SELECT pg_get_userbyid'): print('ticketyn:UTF8')
else:
    with trace.open('a') as out: out.write(sql+'\\n')
    if sql.startswith('CREATE DATABASE '): db[sql.split()[2]]='200'
    for old,new in re.findall(r'ALTER DATABASE (\\w+) RENAME TO (\\w+)',sql): db[new]=db.pop(old)
    path.write_text(json.dumps(db))
''')
    work = Path(tempfile.mkdtemp(prefix='ticketyn-restore.'))
    i['work'] = work
    try:
        yield i
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def configure(i):
    return setup(i) + f'''
trap - EXIT
WORK={shlex.quote(str(i['work']))}; WORK_ID=$(backup_identity "$WORK"); CONTENT=$WORK/components
SUPPORT={shlex.quote(str(SUPPORT))}; BACKUP_SCRIPT={shlex.quote(str(i['root']/'backup-helper'))}
UNIT_FILE={shlex.quote(str(i['unit']))}; NGINX_SITE={shlex.quote(str(i['nginx']))}; NGINX_LINK={shlex.quote(str(i['link']))}
STATE={shlex.quote(str(i['config']/'restore-state'))}; SAFETY_DIR={shlex.quote(str(i['backups']))}
ARCHIVE={shlex.quote(str(i['archive']))}; REPLACE=0
MUTATING=0; CUTOVER_ATTEMPTED=0; BLOCK_ATTEMPTED=0; WAS_ACTIVE=0; PHASE=validacion; SAFETY_BACKUP=''; STAGE_OID=''
trap restore_cleanup EXIT
restore_sql() {{ python3 "{i['fake']}" "{i['db']}" "{i['calls']}" "$@"; }}
restore_pg() {{
    if [[ $1 == pg_restore ]]; then
        cat >/dev/null
        [[ ${{DUMP_FAIL:-0}} == 0 ]] || {{ echo '{SECRET}' >&2; return 8; }}
    elif [[ "$*" == *'SELECT version_num'* ]]; then echo {HEAD}
    else echo 0; fi
}}
restore_validate_dump() {{ [[ ${{INVALID_DUMP:-0}} == 0 ]] || restore_fail 'Dump inválido'; }}
systemctl() {{
    printf 'systemctl %s\\n' "$*" >> "{i['calls']}"
    case "$1" in
        is-active) [[ "$*" == *nginx* || $(cat "{i['active']}") == 1 ]] ;;
        stop) [[ ${{STOP_FAIL:-0}} == 0 ]] || return 3; echo 0 > "{i['active']}" ;;
        start) [[ ${{START_FAIL:-0}} == 0 ]] || return 3; echo 1 > "{i['active']}" ;;
        *) return 9 ;;
    esac
}}
python3() {{
    if [[ "$*" == *'password '* ]]; then
        echo password_sync >> "{i['calls']}"
        [[ ${{PASSWORD_FAIL:-0}} == 0 ]] || return 5
    else command python3 "$@"; fi
}}
curl() {{
    local kind=api
    [[ "$*" == *'/health'* ]] && kind=health
    local counter="{i['root']}/curl-$kind" count=0
    [[ ! -f $counter ]] || count=$(cat "$counter")
    count=$((count+1)); echo "$count" > "$counter"
    if [[ ${{HTTP_FAIL:-0}} == 1 || ${{HTTP_FAIL:-0}} == "$kind" || $count -le ${{HTTP_TRANSIENT:-0}} ]]; then echo '{SECRET}: HTTP 502' >&2; return 22; fi
    if [[ $kind == health ]]; then echo '{{"status":"ok"}}'; else echo '[]'; fi
}}
sleep() {{ :; }}
ss() {{ echo 'LISTEN 0 2048 127.0.0.1:8000 0.0.0.0:*'; }}
'''


def safety_script(i, fail=False):
    script = i['root']/'backup-helper'
    output = i['backups']/'safety.tar'
    script.write_text('#!/bin/bash\n' + ('exit 7\n' if fail else
                     f'cp -- {shlex.quote(str(i["archive"]))} {shlex.quote(str(output))}\n'
                     f'printf "✓ Backup completo y verificado: %s\\n" {shlex.quote(str(output))}\n'))
    script.chmod(0o755)


def test_requires_root():
    if os.geteuid() == 0:
        pytest.skip('Non-root assertion requires a non-root test user')
    result = subprocess.run([str(SCRIPT), '/missing'], capture_output=True, text=True)
    assert result.returncode != 0 and 'root' in result.stderr


@pytest.mark.parametrize('args', ['', '--replace', '--other /tmp/backup', 'a b', '--replace a b', '--replace --replace'])
def test_invalid_arguments(args):
    result = shell('restore_args ' + args + '\necho SHOULD_NOT_RUN')
    assert result.returncode != 0 and 'SHOULD_NOT_RUN' not in result.stdout


@pytest.mark.parametrize('kind', ['missing', 'directory', 'symlink', 'hardlink', 'corrupt'])
def test_invalid_archive_file(installation, kind):
    path = installation['root']/'input'
    if kind == 'directory': path.mkdir()
    elif kind == 'symlink': path.symlink_to(package(installation))
    elif kind == 'hardlink': os.link(package(installation), path)
    elif kind == 'corrupt': path.write_bytes(b'not a tar')
    result = validate(installation, path)
    assert result.returncode != 0
    assert SECRET not in result.stdout + result.stderr


@pytest.mark.parametrize('kind', ['missing', 'extra', 'traversal', 'absolute', 'symlink', 'hardlink', 'device', 'duplicate'])
def test_unsafe_tar_headers(installation, kind):
    parts = components(installation)
    extra = []
    if kind == 'missing': parts.pop('metadata.txt')
    elif kind == 'extra': parts['surprise.txt'] = b'no'
    else:
        member = tarfile.TarInfo({'traversal': '../escaped', 'absolute': '/tmp/escaped'}.get(kind, 'database.dump'))
        if kind == 'symlink': member.type = tarfile.SYMTYPE; member.linkname = '/etc/passwd'
        elif kind == 'hardlink': member.type = tarfile.LNKTYPE; member.linkname = 'ticketyn.env'
        elif kind == 'device': member.type = tarfile.CHRTYPE
        else: member.size = 1
        if kind in ('symlink', 'hardlink', 'device'):
            parts.pop('database.dump')
        extra.append(member)
    assert validate(installation, package(installation, parts, extra)).returncode != 0


@pytest.mark.parametrize('kind', ['hash', 'hash_missing', 'config', 'metadata', 'metadata_duplicate'])
def test_invalid_components(installation, kind):
    parts = components(installation)
    if kind == 'hash': parts['SHA256SUMS'] = ''.join(f'{"0"*64 if name == "database.dump" else hashlib.sha256(value).hexdigest()}  {name}\n' for name, value in parts.items()).encode()
    elif kind == 'hash_missing': parts['SHA256SUMS'] = b''
    elif kind == 'config': parts['ticketyn.env'] = b'DATABASE_URL=postgresql://SECRET@remote/db\n'
    elif kind == 'metadata': parts['metadata.txt'] = b'backup_format=unknown\n'
    else: parts['metadata.txt'] += b'database=ticketyn\n'
    result = validate(installation, package(installation, parts))
    assert result.returncode != 0 and SECRET not in result.stdout + result.stderr


def test_official_manifest_hashes_and_private_extraction(installation):
    assert validate(installation, package(installation)).returncode == 0
    dest = installation['root']/'validated'
    assert stat_mode(dest) == 0o700
    assert {p.name for p in dest.iterdir()} == set(support.MEMBERS)
    assert all(stat_mode(p) == 0o600 for p in dest.iterdir())


def stat_mode(path):
    return path.stat().st_mode & 0o777


@pytest.mark.parametrize('kind', ['version', 'alembic', 'project_hash', 'postgres'])
def test_incompatible_backup_aborts_before_changes(environment, kind):
    i = environment
    parts = components(i)
    text = parts['metadata.txt'].decode()
    if kind == 'version':
        text = text.replace('ticketyn_version=0.1.0', 'ticketyn_version=0.2.0').replace('expected_git_tag=v0.1.0', 'expected_git_tag=v0.2.0').replace('release_name=0.1.0', 'release_name=0.2.0').replace('releases/0.1.0', 'releases/0.2.0')
    elif kind == 'alembic': text = text.replace(HEAD, '0003_ticket_domain')
    elif kind == 'postgres': text = text.replace(f'server_version={MAJOR}.6', 'server_version=15.6') if MAJOR != 15 else text.replace('server_version=15.6', 'server_version=16.6')
    else: text = text.replace(hashlib.sha256((i['release']/'pyproject.toml').read_bytes()).hexdigest(), '0'*64)
    parts['metadata.txt'] = text.encode(); package(i, parts)
    result = shell(configure(i) + 'REPLACE=1\nrestore_validate')
    assert result.returncode != 0
    assert not (i['config']/'restore-state').exists()
    assert 'ALTER DATABASE' not in i['calls'].read_text()
    assert not i['work'].exists()


def test_existing_db_requires_replace(environment):
    result = shell(configure(environment) + 'restore_validate')
    assert result.returncode != 0 and '--replace' in result.stderr
    assert json.loads(environment['db'].read_text()) == {'ticketyn': '100'}


@pytest.mark.parametrize('answer', ['\n', 'n\n', 'yes\n', 'REEMPLAZAR\n', '"REEMPLAZAR ticketyn"\n', ''])
def test_enter_or_rejection_does_not_confirm(answer):
    result = shell('REPLACE=1\nrestore_confirm\necho SHOULD_NOT_RUN', answer)
    assert 'Escribe exactamente "REEMPLAZAR ticketyn" para confirmar (Enter cancela): ' in result.stdout
    assert result.returncode != 0 and 'SHOULD_NOT_RUN' not in result.stdout


@pytest.mark.parametrize('failure', [False, True])
def test_safety_backup_is_mandatory(environment, failure):
    i = environment
    if failure: safety_script(i, fail=True)
    result = shell(configure(i) + 'REPLACE=1\nrestore_validate\nrestore_begin\nrestore_run')
    assert result.returncode != 0
    assert json.loads(i['db'].read_text()) == {'ticketyn': '100'}
    assert i['env'].read_bytes() == components(i)['ticketyn.env']
    assert 'systemctl stop' not in i['calls'].read_text()


@pytest.mark.parametrize('replace', [False, True])
def test_successful_flow_and_transient_http(environment, replace):
    i = environment
    if replace: safety_script(i)
    else: i['db'].write_text('{}')
    result = shell(configure(i) + f'REPLACE={int(replace)}\nHTTP_TRANSIENT=2\nrestore_validate\nrestore_confirm\nrestore_begin\nrestore_run', 'REEMPLAZAR ticketyn\n')
    assert result.returncode == 0, result.stderr
    assert SECRET not in result.stdout + result.stderr
    db = json.loads(i['db'].read_text())
    assert db['ticketyn'] == '200'
    assert any(name.startswith('ticketyn_previous_') for name in db) == replace
    assert i['active'].read_text().strip() == '1'
    assert stat_mode(i['env']) == 0o600
    assert 'password_sync' in i['calls'].read_text()
    assert 'phase=completado' in (i['config']/'restore-state/progress.txt').read_text()
    assert not i['work'].exists()


@pytest.mark.parametrize('failure', ['DUMP_FAIL', 'STOP_FAIL', 'START_FAIL', 'PASSWORD_FAIL', 'HTTP_FAIL'])
def test_failures_preserve_recovery_artifacts(environment, failure):
    i = environment; safety_script(i)
    result = shell(configure(i) + f'REPLACE=1\n{failure}=1\nrestore_validate\nrestore_begin\nrestore_run')
    assert result.returncode != 0, result.stdout
    assert SECRET not in result.stdout + result.stderr
    assert (i['backups']/'safety.tar').exists()
    state = i['config']/'restore-state'
    assert stat_mode(state) == 0o700
    assert (state/'previous.env').exists()
    assert SECRET not in (state/'progress.txt').read_text()
    db = json.loads(i['db'].read_text())
    if failure in ('DUMP_FAIL', 'STOP_FAIL'):
        assert db['ticketyn'] == '100'
    else:
        assert db['ticketyn'] == '200'
        assert any(name.startswith('ticketyn_previous_') for name in db)
        assert i['active'].read_text().strip() == '0'
    assert not i['work'].exists()


def test_invalid_dump_aborts_before_service_or_db(environment):
    result = shell(configure(environment) + 'REPLACE=1\nINVALID_DUMP=1\nrestore_validate')
    assert result.returncode != 0
    assert not (environment['config']/'restore-state').exists()


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM])
def test_signals_during_validation_clean_only_temporary_files(environment, sig):
    i = environment
    code = configure(i) + '\necho READY\nread -r wait\n'
    process = subprocess.Popen(['bash', '-c', 'source "$1"\nsource "$2"\n'+code, 'test',
                                str(ROOT/'backup.sh'), str(SCRIPT)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdout.readline().strip() == 'READY'
    process.send_signal(sig)
    out, err = process.communicate(timeout=5)
    assert process.returncode != 0
    assert not i['work'].exists()
    assert json.loads(i['db'].read_text()) == {'ticketyn': '100'}


def test_password_uses_stdin_only_and_real_exit_status(monkeypatch, tmp_path):
    path = tmp_path/'env'
    path.write_text('DATABASE_URL=postgresql+psycopg://ticketyn:secret%21%3A%25@127.0.0.1:5432/ticketyn\n')
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert 'secret' not in ' '.join(command)
        assert 'secret' not in str(kwargs['env'])
        assert kwargs['input'] == 'secret!:%\nsecret!:%\n'
        assert '--wait' in command and kwargs['check'] is True
        raise subprocess.CalledProcessError(8, command)
    monkeypatch.setattr(support.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError): support.password(path)
    assert len(calls) == 1


@pytest.mark.parametrize('replace', [False, True])
def test_native_postgres_restore_and_password_sync(environment, postgres_engine, replace):
    """Real custom dump, data, rename, ownership, Alembic and SCRAM in test cluster."""
    import base64
    import hmac
    from sqlalchemy import create_engine, text

    i = environment
    host = postgres_engine.url.query['host']
    port = postgres_engine.url.query['port']
    user = postgres_engine.url.username
    admin = postgres_engine.execution_options(isolation_level='AUTOCOMMIT')
    source = None
    role_created = False
    names = {'ticketyn'}
    try:
        with admin.connect() as conn:
            assert not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname='ticketyn'"))
            assert not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='ticketyn'"))
            conn.exec_driver_sql('CREATE ROLE ticketyn LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE')
            role_created = True
            conn.exec_driver_sql("COMMENT ON ROLE ticketyn IS 'ticketyn-install:" + 'a'*32 + "'")
            conn.exec_driver_sql("CREATE DATABASE ticketyn OWNER ticketyn TEMPLATE template0 ENCODING 'UTF8'")
        source = create_engine(postgres_engine.url.set(database='ticketyn'))
        from ticketyn.db.base import Base
        with source.begin() as conn:
            conn.exec_driver_sql('SET ROLE ticketyn')
            Base.metadata.create_all(conn)
            conn.exec_driver_sql("INSERT INTO customers(customer_code,name,active) VALUES ('RESTORE-CUSTOMER','Cliente Ñ',false)")
            conn.exec_driver_sql("INSERT INTO nodes(name,active) VALUES ('Nodo Á',false)")
            conn.exec_driver_sql("INSERT INTO responsibles(name,active) VALUES ('Responsable É',false)")
            conn.exec_driver_sql("INSERT INTO circuits(customer_id,node_id,circuit_code,description) VALUES (1,1,'RESTORE-CIRCUIT','Circuito histórico')")
            conn.exec_driver_sql("INSERT INTO sectors(name) VALUES ('Sector prueba')")
            conn.exec_driver_sql("INSERT INTO departments(name) VALUES ('Departamento prueba')")
            conn.exec_driver_sql("INSERT INTO incident_types(name) VALUES ('Tipo prueba')")
            conn.exec_driver_sql("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,responsible_id,start_at,status) VALUES (27,'RESTORE-0027','Incidencia Á','Descripción Ñ',1,1,1,1,1,1,'2026-10-05T12:00:00+00:00','OPEN')")
            conn.exec_driver_sql('CREATE TABLE alembic_version (version_num varchar(64))')
            conn.execute(text('INSERT INTO alembic_version VALUES (:head)'), {'head': HEAD})
            conn.exec_driver_sql('CREATE TABLE probe (id serial PRIMARY KEY, name text)')
            conn.execute(text('INSERT INTO probe(name) VALUES (:name)'), {'name': 'Nodo Ñ — Responsable Á'})
        dump = subprocess.check_output(['pg_dump', '--host', host, '--port', port, '--username', user,
                                        '--dbname', 'ticketyn', '--format=custom', '--compress=6'])
        parts = components(i); parts['database.dump'] = dump
        i['archive'] = package(i, parts)
        source.dispose(); source = None
        if replace:
            # Data written after source backup must survive in retained original DB.
            source = create_engine(postgres_engine.url.set(database='ticketyn'))
            with source.begin() as conn:
                conn.execute(text('INSERT INTO probe(name) VALUES (:name)'), {'name': 'Posterior al backup'})
            source.dispose(); source = None
            safety_script(i)
        else:
            with admin.connect() as conn:
                conn.exec_driver_sql('DROP DATABASE ticketyn')
                conn.exec_driver_sql('DROP ROLE ticketyn')
            role_created = False
        # Only remap cluster socket/user; preserve the real password helper and setsid --wait.
        wrapper = i['root']/'password-helper.py'
        wrapper.write_text(f'''import importlib.util, subprocess, sys
spec=importlib.util.spec_from_file_location('support', {str(SUPPORT)!r})
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
original=subprocess.run
def execute(command, **kwargs):
    if command[0]=='runuser':
        command=command[4:]
        command[command.index('/var/run/postgresql')]={host!r}
        command[command.index('5432')]={port!r}
        command[command.index('postgres', command.index('-U')+1)]={user!r}
    return original(command, **kwargs)
m.subprocess.run=execute
m.password(sys.argv[1])
''')
        native = f'''
restore_pg() {{
    local tool=$1; shift
    env -i PATH=/usr/bin:/bin HOME=/nonexistent PGPASSFILE=/dev/null "$tool" \\
        --host={shlex.quote(host)} --port={port} --username={shlex.quote(user)} --no-password "$@"
}}
restore_sql() {{ restore_pg psql --dbname=postgres -X -At --set=ON_ERROR_STOP=1 "$@"; }}
restore_validate_dump() {{ env -i PATH=/usr/bin:/bin pg_restore --file=/dev/null "$1/database.dump" >/dev/null; }}
python3() {{
    if [[ "$*" == *'password '* ]]; then command python3 "{wrapper}" "$4"
    else command python3 "$@"; fi
}}
'''
        result = shell(configure(i) + native + f'REPLACE={int(replace)}\nrestore_validate\nrestore_begin\nrestore_run')
        assert result.returncode == 0, result.stderr
        assert SECRET not in result.stdout + result.stderr
        with admin.connect() as conn:
            names.update(conn.scalars(text("SELECT datname FROM pg_database WHERE datname LIKE 'ticketyn_restore_%' OR datname LIKE 'ticketyn_previous_%'")))
            verifier = conn.scalar(text("SELECT rolpassword FROM pg_authid WHERE rolname='ticketyn'"))
            assert conn.scalar(text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='ticketyn'")) == 'ticketyn'
        role_created = True
        algorithm, parameters, keys = verifier.split('$')
        iterations, salt = parameters.split(':')
        stored, server = keys.split(':')
        salted = hashlib.pbkdf2_hmac('sha256', SECRET.encode(), base64.b64decode(salt), int(iterations))
        assert algorithm == 'SCRAM-SHA-256'
        assert hashlib.sha256(hmac.digest(salted, b'Client Key', 'sha256')).digest() == base64.b64decode(stored)
        assert hmac.digest(salted, b'Server Key', 'sha256') == base64.b64decode(server)
        source = create_engine(postgres_engine.url.set(database='ticketyn'))
        with source.connect() as conn:
            assert conn.execute(text('SELECT name FROM probe')).scalars().all() == ['Nodo Ñ — Responsable Á']
            assert conn.scalar(text('SELECT version_num FROM alembic_version')) == HEAD
            assert conn.scalar(text("SELECT nextval('probe_id_seq')")) == 2
            assert conn.execute(text('SELECT t.reference,n.name,r.name,c.customer_code FROM tickets t JOIN circuits ci ON ci.id=t.circuit_id JOIN nodes n ON n.id=ci.node_id JOIN responsibles r ON r.id=t.responsible_id JOIN customers c ON c.id=t.customer_id')).one() == ('RESTORE-0027', 'Nodo Á', 'Responsable É', 'RESTORE-CUSTOMER')
            assert conn.scalar(text('SELECT active FROM nodes WHERE id=1')) is False
            assert conn.scalar(text("SELECT nextval('tickets_id_seq')")) == 2
            assert conn.scalar(text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname='probe'")) == 'ticketyn'
        if replace:
            previous = next(name for name in names if name.startswith('ticketyn_previous_'))
            with admin.connect() as conn:
                assert conn.scalar(text('SELECT datallowconn FROM pg_database WHERE datname=:name'), {'name': previous}) is False
                conn.exec_driver_sql(f'ALTER DATABASE {previous} ALLOW_CONNECTIONS true')
            old = create_engine(postgres_engine.url.set(database=previous))
            try:
                with old.connect() as conn:
                    assert conn.scalar(text('SELECT count(*) FROM probe')) == 2
            finally:
                old.dispose()
        assert stat_mode(i['env']) == 0o600
        if replace:
            with admin.connect() as conn:
                conn.exec_driver_sql(f'ALTER DATABASE {previous} ALLOW_CONNECTIONS false')
        i['work'].mkdir(mode=0o700)
        finalize_result = shell(configure(i) + native + '\nrestore_lock() { :; }\nrestore_finalize',
                                'FINALIZAR RESTAURACION\n')
        assert finalize_result.returncode == 0, finalize_result.stderr
        assert SECRET not in finalize_result.stdout + finalize_result.stderr
        assert not (i['config']/'restore-state').exists()
        with admin.connect() as conn:
            assert conn.scalar(text("SELECT 1 FROM pg_database WHERE datname='ticketyn'")) == 1
            if replace:
                assert conn.scalar(text('SELECT count(*) FROM pg_database WHERE datname=:name'), {'name': previous}) == 0
        assert len(list((i['config']/'restore-history').glob('*.json'))) == 1
    finally:
        if source is not None: source.dispose()
        with admin.connect() as conn:
            # Only these named DBs inside the disposable pytest cluster.
            names.update(conn.scalars(text("SELECT datname FROM pg_database WHERE datname LIKE 'ticketyn_restore_%' OR datname LIKE 'ticketyn_previous_%'")))
            for name in names:
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS {name}')
            if role_created or conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='ticketyn'")):
                conn.exec_driver_sql('DROP ROLE ticketyn')


@pytest.mark.parametrize('failure', ['create_db', 'configuration', 'api', 'cutover'])
def test_additional_critical_failures(environment, failure):
    i = environment; safety_script(i)
    fault = ''
    if failure in ('create_db', 'cutover'):
        pattern = '*CREATE\\ DATABASE*' if failure == 'create_db' else '*RENAME\\ TO*'
        fault = f'''
restore_sql() {{
    if [[ "$*" == {pattern} ]]; then return 9; fi
    command python3 "{i['fake']}" "{i['db']}" "{i['calls']}" "$@"
}}
'''
    elif failure == 'configuration':
        fault = '''mv() { if [[ "$*" == *restored.env* ]]; then return 9; else command mv "$@"; fi; }\n'''
    else: fault = 'HTTP_FAIL=api\n'
    result = shell(configure(i) + fault + 'REPLACE=1\nrestore_validate\nrestore_begin\nrestore_run')
    assert result.returncode != 0
    assert SECRET not in result.stdout + result.stderr
    assert (i['backups']/'safety.tar').exists()
    assert (i['config']/'restore-state/previous.env').exists()
    db = json.loads(i['db'].read_text())
    if failure == 'create_db':
        assert db['ticketyn'] == '100'
        assert i['active'].read_text().strip() == '1'
    elif failure == 'cutover':
        assert db['ticketyn'] == '100'
        assert i['active'].read_text().strip() == '0'
    else:
        assert db['ticketyn'] == '200'
        assert any(name.startswith('ticketyn_previous_') for name in db)
        assert i['active'].read_text().strip() == '0'
    if failure == 'api':
        assert (i['root']/'curl-health').exists()
        assert (i['root']/'curl-api').read_text().strip() == '30'


def test_stop_failure_does_not_touch_postgres(environment):
    i = environment; safety_script(i)
    result = shell(configure(i) + 'REPLACE=1\nSTOP_FAIL=1\nrestore_validate\nrestore_begin\nrestore_run')
    assert result.returncode != 0
    assert 'ALTER DATABASE' not in i['calls'].read_text()


def test_concurrent_change_before_mutation_aborts(environment):
    i = environment
    result = shell(configure(i) + 'REPLACE=1\nrestore_validate\nprintf "changed" >> "$CONFIG_FILE"\nrestore_begin')
    assert result.returncode != 0
    assert not (i['config']/'restore-state').exists()
    assert 'systemctl stop' not in i['calls'].read_text()


def test_existing_operation_never_reentered(environment):
    state = environment['config']/'restore-state'; state.mkdir()
    (state/'evidence').write_text('keep')
    result = shell(configure(environment) + 'REPLACE=1\nrestore_validate')
    assert result.returncode != 0
    assert (state/'evidence').read_text() == 'keep'


def test_tar_with_appended_nonzero_content_is_rejected(installation):
    path = package(installation)
    with path.open('ab') as out: out.write(b'additional hidden content')
    assert validate(installation, path).returncode != 0


def test_parent_symlink_in_backup_path_is_rejected(installation):
    path = package(installation)
    link = installation['root']/'linked'; link.symlink_to(installation['root'], target_is_directory=True)
    assert validate(installation, link/path.name).returncode != 0


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM])
def test_signal_after_cutover_stops_service_and_preserves_recovery(environment, sig):
    i = environment; safety_script(i)
    code = configure(i) + '''
REPLACE=1
restore_validate
restore_begin
restore_http_checks() { echo READY; read -r wait; }
restore_run
'''
    process = subprocess.Popen(['bash', '-c', 'source "$1"\nsource "$2"\n'+code,
                                'test', str(ROOT/'backup.sh'), str(SCRIPT)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdout.readline().strip() == 'READY'
    process.send_signal(sig)
    output, error = process.communicate(timeout=5)
    assert process.returncode != 0
    assert SECRET not in output + error
    db = json.loads(i['db'].read_text())
    assert db['ticketyn'] == '200' and any(name.startswith('ticketyn_previous_') for name in db)
    assert (i['config']/'restore-state/previous.env').exists()
    assert (i['backups']/'safety.tar').exists()
    assert i['active'].read_text().strip() == '0'
    assert not i['work'].exists()


@pytest.mark.parametrize('problem', ['missing', 'insecure', 'symlink', 'hardlink'])
def test_live_configuration_must_be_safe(environment, problem):
    i = environment
    if problem == 'missing': i['env'].unlink()
    elif problem == 'insecure': i['env'].chmod(0o644)
    elif problem == 'symlink':
        other = i['env'].with_name('other.env'); i['env'].rename(other); i['env'].symlink_to(other)
    else: os.link(i['env'], i['root']/'another.env')
    result = shell(configure(i) + 'REPLACE=1\nrestore_validate')
    assert result.returncode != 0
    assert not (i['config']/'restore-state').exists()
    assert 'systemctl stop' not in i['calls'].read_text()
    assert SECRET not in result.stdout + result.stderr


def test_real_dump_validator_rejects_invalid_dump_without_db(environment):
    i = environment
    code = setup(i) + f'\nWORK="{i["work"]}"\nrestore_validate_dump "{i["root"]}"'
    (i['root']/'database.dump').write_bytes(b'invalid custom dump')
    result = shell(code)
    assert result.returncode != 0 and 'Dump PostgreSQL inválido' in result.stderr
    assert json.loads(i['db'].read_text()) == {'ticketyn': '100'}


def test_actual_dump_revision_mismatch_prevents_cutover(environment):
    i = environment; safety_script(i)
    result = shell(configure(i) + '''
REPLACE=1
restore_validate
restore_begin
restore_revision() { echo incompatible; }
restore_run
''')
    assert result.returncode != 0
    assert json.loads(i['db'].read_text())['ticketyn'] == '100'
    assert 'RENAME TO' not in i['calls'].read_text()
    assert i['active'].read_text().strip() == '1'


def test_http_200_invalid_json_never_counts_as_success(environment):
    i = environment; safety_script(i)
    result = shell(configure(i) + '''
REPLACE=1
restore_validate
restore_begin
curl() { echo '<html>not Ticketyn</html>'; }
restore_run
''')
    assert result.returncode != 0 and '/health' in result.stderr
    assert i['active'].read_text().strip() == '0'
