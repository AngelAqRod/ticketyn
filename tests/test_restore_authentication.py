"""Authentication compatibility tests for restore.sh and restore_support.py.

All tests use isolated test environments, mocks, and temporary directories.
Never touches real databases or system services.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest
from test_restore import (
    ROOT, SCRIPT, SUPPORT, SECRET, support, package, shell,
    environment, installation, safety_script, configure, components, MAJOR,
)

AUTH_HEAD = '0032_responsible_selectable'


def security_source(release, version='0.7.0'):
    (release / 'pyproject.toml').write_text(f'[project]\nversion = "{version}"\n')
    for name in [
        'src/ticketyn/main.py',
        'src/ticketyn/api/auth.py',
        'src/ticketyn/security/bootstrap.py',
        'bootstrap-superadmin.sh',
        'alembic/versions/0030_security_foundation.py',
        'alembic/versions/0031_role_permissions.py',
        'alembic/versions/0032_responsible_selectable.py',
    ]:
        target = release / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (release / 'bootstrap-superadmin.sh').chmod(0o755)
    return release


def setup_authenticated_release(i, version='0.7.0'):
    new_release = i['app'] / 'releases' / version
    if i['release'].exists() and i['release'] != new_release:
        i['release'].rename(new_release)
        i['release'] = new_release
        (i['app'] / 'current').unlink(missing_ok=True)
        (i['app'] / 'current').symlink_to(new_release)
    release = i['release']
    release.mkdir(parents=True, exist_ok=True)
    security_source(release, version)
    binary = release / '.venv/bin/python'
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(f'#!/bin/sh\necho {AUTH_HEAD}\n')
    binary.chmod(0o755)

    # Prepare backup components matching AUTH_HEAD and version
    parts = components(i)
    meta = dict(line.split('=', 1) for line in parts['metadata.txt'].decode().splitlines())
    meta['alembic_revision'] = AUTH_HEAD
    meta['ticketyn_version'] = version
    meta['release_name'] = version
    meta['expected_git_tag'] = f'v{version}'
    meta['source_release_path'] = f'/opt/ticketyn/releases/{version}'
    meta['pyproject_sha256'] = hashlib.sha256((release / 'pyproject.toml').read_bytes()).hexdigest()
    parts['metadata.txt'] = ''.join(f'{k}={v}\n' for k, v in meta.items()).encode()
    parts['ticketyn.env'] = i['env'].read_bytes()
    i['archive'] = package(i, parts)
    return release


def auth_configure(i, status='401'):
    base = configure(i)
    # Override restore_pg to return AUTH_HEAD and HTTP_STATUS
    return base + f'''
HTTP_STATUS={shlex.quote(str(status))}
restore_pg() {{
    if [[ $1 == pg_restore ]]; then
        cat >/dev/null
        [[ ${{DUMP_FAIL:-0}} == 0 ]] || {{ echo '{SECRET}' >&2; return 8; }}
    elif [[ "$*" == *'SELECT version_num'* ]]; then echo {AUTH_HEAD}
    else echo 0; fi
}}
'''


def test_auth_mode_detects_authenticated_and_legacy_releases(environment):
    i = environment
    # Legacy release (from environment fixture)
    assert support.auth_mode(i['release']) is None  # prints to stdout
    assert support.authentication(i['release']) == 'legacy'

    # Authenticated release
    setup_authenticated_release(i)
    assert support.authentication(i['release']) == 'required'

    # CLI invoker
    result_auth = subprocess.run(
        ['python3', '-I', str(SUPPORT), 'auth-mode', str(i['release'])],
        capture_output=True, text=True, check=True,
    )
    assert result_auth.stdout.strip() == 'required'


@pytest.mark.parametrize('missing', [
    'bootstrap-superadmin.sh',
    'src/ticketyn/security/bootstrap.py',
    'src/ticketyn/api/auth.py',
    'alembic/versions/0032_responsible_selectable.py',
])
def test_auth_mode_rejects_incomplete_security_capabilities(environment, missing):
    i = environment
    setup_authenticated_release(i)
    (i['release'] / missing).unlink()

    with pytest.raises(support.RestoreError):
        support.authentication(i['release'])

    result = subprocess.run(
        ['python3', '-I', str(SUPPORT), 'auth-mode', str(i['release'])],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert any(term in result.stderr for term in ('incompatible', 'incompleta', 'Faltan', 'bootstrap-superadmin.sh'))


def test_http_valid_unit_logic(tmp_path):
    health_ok = tmp_path / 'health_ok.json'
    health_ok.write_text('{"status": "ok"}')
    support.http_valid(health_ok, 'health')
    support.http_valid(health_ok, 'health', 'required')

    health_bad = tmp_path / 'health_bad.json'
    health_bad.write_text('{"status": "error"}')
    with pytest.raises(support.RestoreError, match='health'):
        support.http_valid(health_bad, 'health')

    # API in required mode
    status_401 = tmp_path / 'status_401.txt'
    status_401.write_text('401\n')
    support.http_valid(status_401, 'api', 'required')

    for bad_code in ['200', '403', '500', '502', '404', '']:
        status_bad = tmp_path / f'status_{bad_code}.txt'
        status_bad.write_text(bad_code)
        with pytest.raises(support.RestoreError, match='401'):
            support.http_valid(status_bad, 'api', 'required')

    # API in legacy mode
    api_list = tmp_path / 'api_list.json'
    api_list.write_text('[]')
    support.http_valid(api_list, 'api', 'legacy')

    api_dict = tmp_path / 'api_dict.json'
    api_dict.write_text('{"detail": "error"}')
    with pytest.raises(support.RestoreError, match='API'):
        support.http_valid(api_dict, 'api', 'legacy')


def test_authenticated_restore_success_flow(environment):
    i = environment
    safety_script(i)
    setup_authenticated_release(i)

    code = auth_configure(i, status='401') + '''
REPLACE=1
restore_validate
restore_begin
restore_run
'''
    result = shell(code)
    assert result.returncode == 0, result.stderr
    assert '✓ Ticketyn restaurado y verificado.' in result.stdout
    assert SECRET not in result.stdout + result.stderr

    state = i['config'] / 'restore-state'
    progress = dict(line.split('=', 1) for line in (state / 'progress.txt').read_text().splitlines())
    assert progress['phase'] == 'completado'
    assert (state / 'completion.json').exists()


@pytest.mark.parametrize('status', ['200', '403', '500', '502'])
def test_authenticated_restore_rejects_non_401_status(environment, status):
    i = environment
    safety_script(i)
    setup_authenticated_release(i)

    code = auth_configure(i, status=status) + '''
REPLACE=1
restore_validate
restore_begin
restore_run
'''
    result = shell(code)
    assert result.returncode != 0
    assert '/api/customers no respondió correctamente mediante Nginx tras 30 intentos' in result.stderr
    assert '✓ Ticketyn restaurado y verificado' not in result.stdout

    # State preserved, Ticketyn stopped to prevent external writes
    state = i['config'] / 'restore-state'
    assert state.exists()
    assert (state / 'RECUPERACION.txt').exists()
    assert i['active'].read_text().strip() == '0'
    assert SECRET not in result.stdout + result.stderr


def test_authenticated_restore_rejects_health_failure(environment):
    i = environment
    safety_script(i)
    setup_authenticated_release(i)

    code = auth_configure(i, status='401') + '''
REPLACE=1
restore_validate
restore_begin
curl() {
    local kind=api
    [[ "$*" == *'/health'* ]] && kind=health
    if [[ $kind == health ]]; then echo '{"status":"degraded"}'; else echo 401; fi
}
restore_run
'''
    result = shell(code)
    assert result.returncode != 0
    assert '/health no respondió correctamente mediante Nginx tras 30 intentos' in result.stderr
    assert '✓ Ticketyn restaurado y verificado' not in result.stdout


def test_authenticated_restore_rejects_service_inaccessible(environment):
    i = environment
    safety_script(i)
    setup_authenticated_release(i)

    code = auth_configure(i) + '''
REPLACE=1
HTTP_FAIL=1
restore_validate
restore_begin
restore_run
'''
    result = shell(code)
    assert result.returncode != 0
    assert 'no respondió correctamente mediante Nginx tras 30 intentos' in result.stderr


def test_restore_validate_aborts_early_on_incomplete_security(environment):
    i = environment
    safety_script(i)
    setup_authenticated_release(i)
    # Remove bootstrap-superadmin.sh
    (i['release'] / 'bootstrap-superadmin.sh').unlink()

    code = auth_configure(i) + '''
REPLACE=1
restore_validate
'''
    result = shell(code)
    assert result.returncode != 0
    assert 'No se pudo determinar el modo de autenticación' in result.stderr
    # Must not have created restore-state or touched systemctl
    assert not (i['config'] / 'restore-state').exists()
    assert 'systemctl stop' not in i['calls'].read_text()


def test_legacy_restore_flow_accepts_200_and_rejects_401(environment):
    i = environment
    safety_script(i)
    # environment is already a legacy release (v0.1.0)

    # 1. Accepting 200 with list
    code_ok = configure(i) + '''
REPLACE=1
restore_validate
restore_begin
restore_run
'''
    result_ok = shell(code_ok)
    assert result_ok.returncode == 0, result_ok.stderr
    assert '✓ Ticketyn restaurado y verificado.' in result_ok.stdout

    # Clean up state for second test
    shutil.rmtree(i['config'] / 'restore-state', ignore_errors=True)
    if not i['work'].exists():
        i['work'].mkdir(mode=0o700)

    # 2. Rejecting 401 on legacy release
    code_fail = configure(i) + '''
REPLACE=1
restore_validate
restore_begin
curl() {
    local kind=api
    [[ "$*" == *'/health'* ]] && kind=health
    if [[ $kind == health ]]; then echo '{"status":"ok"}'; else return 22; fi
}
restore_run
'''
    result_fail = shell(code_fail)
    assert result_fail.returncode != 0
    assert '/api/customers no respondió correctamente' in result_fail.stderr


def test_authenticated_restore_finalize_success_and_failure(environment):
    i = environment
    safety_script(i)
    setup_authenticated_release(i)

    # First, complete an authenticated restore
    code_restore = auth_configure(i, status='401') + '''
REPLACE=1
restore_validate
restore_begin
restore_run
'''
    res_restore = shell(code_restore)
    assert res_restore.returncode == 0, res_restore.stderr

    state = i['config'] / 'restore-state'
    progress = dict(line.split('=', 1) for line in (state / 'progress.txt').read_text().splitlines())
    i['token'] = progress['operation']
    i['previous'] = progress['previous_database']
    i['state'] = state

    db = json.loads(i['db'].read_text())
    i['db'].write_text(json.dumps(db))
    i['properties'] = i['root'] / 'db-properties.json'
    i['properties'].write_text('{}')
    i['fake'].write_text('''import json, pathlib, re, sys
path=pathlib.Path(sys.argv[1]); trace=pathlib.Path(sys.argv[2]); props=json.loads(pathlib.Path(sys.argv[3]).read_text()); args=sys.argv[4:]
sql=sys.stdin.read() if '--file=-' in args else args[args.index('-c')+1]
db=json.loads(path.read_text())
if sql.startswith('SELECT oid FROM '): print(db.get(re.search("datname='([^']+)'",sql)[1],''))
elif sql.startswith('SELECT oid::text||'):
    name=re.search("datname='([^']+)'",sql)[1]
    if name in db:
        extra=props.get(name, {})
        allow=extra.get('allow', 'true' if name=='ticketyn' else 'false')
        print(db[name]+':'+extra.get('owner','ticketyn')+':UTF8:'+allow)
elif "system_identifier" in sql: print(props.get('cluster','987654321'))
elif "current_setting('server_version_num')" in sql: print(''' + str(MAJOR * 10000 + 6) + ''')
elif sql.startswith('SELECT count(*) FROM pg_stat_activity'): print(props.get('sessions',0))
elif sql.startswith('SELECT count(*) FROM pg_database WHERE oid='):
    print(sum(oid==re.search(r'oid=(\\d+)',sql)[1] for oid in db.values()))
elif sql.startswith('SELECT format('):
    name=re.search("datname='([^']+)'",sql)[1]; oid=re.search(r'AND oid=(\\d+)',sql)[1]
    with trace.open('a') as out: out.write(sql+'\\n')
    if db.get(name)==oid: db.pop(name)
    path.write_text(json.dumps(db))
else: raise SystemExit('Unexpected mock query: ' + sql)
''')

    finalize_base = auth_configure(i, status='401') + f'''
restore_sql() {{
    command python3 "{i['fake']}" "{i['db']}" "{i['calls']}" "{i['properties']}" "$@"
}}
restore_lock() {{ :; }}
'''
    # 1. Finalize failure when /api/customers does not return 401
    if not i['work'].exists():
        i['work'].mkdir(mode=0o700)
    code_finalize_fail = finalize_base + '''
HTTP_STATUS=200
restore_finalize
'''
    result_fail = shell(code_finalize_fail, stdin='FINALIZAR RESTAURACION\n')
    assert result_fail.returncode != 0
    assert '/api/customers no respondió correctamente' in result_fail.stderr
    # DB was NOT dropped because HTTP checks in finalize-validate failed
    assert 'DROP DATABASE' not in i['calls'].read_text()

    # 2. Finalize success with valid 401 and 200
    if not i['work'].exists():
        i['work'].mkdir(mode=0o700)
    code_finalize_ok = finalize_base + '''
HTTP_STATUS=401
restore_finalize
'''
    result_ok = shell(code_finalize_ok, stdin='FINALIZAR RESTAURACION\n')
    assert result_ok.returncode == 0, result_ok.stderr
    assert '✓ Restauración finalizada.' in result_ok.stdout
    assert not state.exists()
