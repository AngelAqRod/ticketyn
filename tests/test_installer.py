"""Installer functions in subprocesses; no apt/users/services or production paths."""
from pathlib import Path
import os
import subprocess

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / 'install.sh'


def shell(script, stdin=''):
    return subprocess.run(['bash', '-c', 'source "$1"\n' + script, 'test', str(INSTALLER)],
                          input=stdin, text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize('value, valid', [('80', True), ('', False), ('00080', True), ('65535', True), ('0', False), ('65536', False), ('-1', False), ('abc', False), ('80;touch /etc/test', False), ('1.5', False)])
def test_port_validation(value, valid):
    result = shell(f'valid_port "{value}"')
    assert (result.returncode == 0) == valid


@pytest.mark.parametrize('stdin, expected', [('\n', 80), ('bogus\n0\n65536\n8080\n', 8080), ('8000\n5432\n8090\n', 8090)])
def test_port_prompt(stdin, expected):
    result = shell('listening_port() { return 1; }; nginx_port_configured() { return 1; }; choose_port; echo "PORT=$HTTP_PORT"', stdin)
    assert result.returncode == 0
    assert f'PORT={expected}' in result.stdout


def test_conflict_offers_another_port():
    result = shell('listening_port() { [[ $1 == 80 ]]; }; nginx_port_configured() { return 1; }; choose_port; echo "PORT=$HTTP_PORT"', '\n8080\n')
    assert 'ocupado' in result.stdout and 'PORT=8080' in result.stdout


def test_cancel_before_changes():
    result = shell('listening_port() { return 0; }; choose_port; echo SHOULD_NOT_RUN', '80\nC\n')
    assert result.returncode == 0 and 'SHOULD_NOT_RUN' not in result.stdout


@pytest.mark.parametrize('answer', ['\n', 'S\n', 's\n', 'Y\n', 'y\n', 'invalid\ns\n'])
def test_confirmation_defaults_to_yes(answer):
    result = shell('HTTP_PORT=80; confirm_install; echo CONFIRMED', answer)
    assert result.returncode == 0 and 'CONFIRMED' in result.stdout


def test_confirmation_no_cancels():
    result = shell('HTTP_PORT=80; confirm_install; echo SHOULD_NOT_RUN', 'n\n')
    assert result.returncode == 0 and 'SHOULD_NOT_RUN' not in result.stdout


@pytest.mark.parametrize('content, supported', [('ID=debian\nVERSION_ID="12"', True), ('ID=debian\nVERSION_ID="13"', True), ('ID=ubuntu\nVERSION_ID="24.04"', True), ('ID=ubuntu\nVERSION_ID="22.04"', False), ('ID=arch\nVERSION_ID="rolling"', False)])
def test_supported_os(tmp_path, content, supported):
    release = tmp_path/'os-release'
    release.write_text(content)
    result = shell(f'check_os "{release}"')
    assert (result.returncode == 0) == supported


@pytest.mark.parametrize('config, port, conflict', [('server { listen 80; }', 80, True), ('server { listen [::]:8080; }', 8080, True), ('server { listen\n 127.0.0.1:8080; }', 8080, True), ('# listen 80;\nserver { listen 8080; }', 80, False), ('server { listen 8080; }', 80, False)])
def test_nginx_port_detection(config, port, conflict):
    result = shell(f'nginx_config_uses_port {port}', config)
    assert (result.returncode == 0) == conflict


@pytest.mark.parametrize('local, peer, valid', [('127.0.0.1:8000', '0.0.0.0:*', True), ('0.0.0.0:8000', '0.0.0.0:*', False), ('[::]:8000', '[::]:*', False)])
def test_socket_check_uses_local_address(local, peer, valid):
    result = shell(f'ss() {{ echo "LISTEN 0 128 {local} {peer}"; }}; check_backend_socket')
    assert (result.returncode == 0) == valid


def test_non_root_stops_immediately():
    if os.geteuid() == 0:
        pytest.skip('Run this test as a non-root user, as required by PostgreSQL tests.')
    result = subprocess.run([str(INSTALLER)], capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert 'como root' in result.stderr
    assert 'Puerto HTTP' not in result.stdout


def test_missing_frontend_stops_before_changes(tmp_path):
    result = shell(f'SOURCE="{tmp_path}"; check_project')
    assert result.returncode != 0 and 'frontend/dist/index.html' in result.stderr


def test_version_from_metadata(tmp_path):
    (tmp_path/'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    assert shell(f'project_version "{tmp_path}"').stdout == '0.1.0'
    (tmp_path/'pyproject.toml').write_text('[project]\nversion = "../../etc"\n')
    assert shell(f'project_version "{tmp_path}"').returncode != 0


def test_release_copy_whitelist_preserves_dist_excludes_secrets(tmp_path):
    source, release = tmp_path/'source', tmp_path/'release'
    source.mkdir(); release.mkdir()
    for name in ['src/ticketyn', 'alembic/versions', 'deploy/systemd', 'frontend/dist/assets', 'frontend/node_modules', '.git', 'src/ticketyn/__pycache__']:
        (source/name).mkdir(parents=True)
    for name in ['alembic.ini', 'pyproject.toml', 'requirements.lock', 'LICENSE', 'README.md', 'frontend/dist/index.html', 'src/ticketyn/main.py']:
        (source/name).write_text('test')
    for name in ['.env', 'src/ticketyn/__pycache__/main.pyc', 'frontend/node_modules/test.js', '.git/config']:
        (source/name).write_text('must not copy')
    result = shell(f'SOURCE="{source}"; RELEASE="{release}"; SOURCE_HASH=$(release_tar | sha256sum | cut -c 1-64); copy_release')
    assert result.returncode == 0, result.stderr
    assert (release/'frontend/dist/index.html').exists()
    assert (release/'src/ticketyn/main.py').exists()
    assert not (release/'.git').exists()
    assert not (release/'frontend/node_modules').exists()
    assert not list(release.rglob('.env'))
    assert not list(release.rglob('*.pyc'))


def test_tag_must_match_project_version(tmp_path):
    (tmp_path/'.git').mkdir()
    (tmp_path/'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    result = shell(f'git() {{ case "$3" in rev-parse) echo HEAD;; tag) echo v0.2.0;; esac; }}; project_version "{tmp_path}"')
    assert result.returncode != 0 and 'no coincide' in result.stderr


def test_invalid_existing_nginx_configuration_aborts():
    result = shell('nginx() { return 1; }; nginx_port_configured 80; echo SHOULD_NOT_RUN')
    assert result.returncode != 0 and 'no es válida' in result.stderr
    assert 'SHOULD_NOT_RUN' not in result.stdout


def test_nginx_implicit_port_80():
    result = shell('nginx_config_uses_port 80', 'server { listen 127.0.0.1; }')
    assert result.returncode == 0


def test_password_pipe_uses_scram_without_terminal(postgres_engine):
    # Disposable test cluster only. No real system roles/services are touched.
    import shutil
    from uuid import uuid4
    from sqlalchemy import text
    if not shutil.which('setsid') or not shutil.which('psql'):
        pytest.skip('setsid/psql required for password-pipe integration test')
    role = f'installer_test_{uuid4().hex}'
    password = 'synthetic-test-password-not-a-production-secret'
    environment = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    environment['PGOPTIONS'] = '-c password_encryption=scram-sha-256'
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text(f'CREATE ROLE "{role}" LOGIN'))
        try:
            result = subprocess.run([
                'setsid', '--wait', 'psql', '-X', '-h', postgres_engine.url.query['host'],
                '-p', postgres_engine.url.query['port'], '-U', postgres_engine.url.username,
                '--set', 'ON_ERROR_STOP=1', '-q', '-c', f'\\password {role}', 'postgres',
            ], input=f'{password}\n{password}\n', text=True, capture_output=True,
                env=environment, timeout=10)
            assert result.returncode == 0, result.stderr
            assert password not in result.stdout + result.stderr
            stored = connection.scalar(text('SELECT rolpassword FROM pg_authid WHERE rolname=:role'), {'role': role})
            assert stored.startswith('SCRAM-SHA-256$')
        finally:
            connection.execute(text(f'DROP ROLE "{role}"'))


@pytest.mark.parametrize('kind', ['file', 'directory', 'broken_symlink'])
def test_existing_artifacts_are_never_overwritten(tmp_path, kind):
    target = tmp_path/'existing'
    if kind == 'file':
        target.write_text('preserve')
    elif kind == 'directory':
        target.mkdir()
    else:
        target.symlink_to(tmp_path/'missing')
    result = shell(f'require_absent "{target}" "Ya existe; se conserva"; echo SHOULD_NOT_RUN')
    assert result.returncode != 0 and 'SHOULD_NOT_RUN' not in result.stdout
    assert target.exists() or target.is_symlink()
    if kind == 'file':
        assert target.read_text() == 'preserve'


def test_build_asset_discovery(tmp_path):
    page = tmp_path/'index.html'
    page.write_text('<script src="/assets/app-abc.js"></script>\n<link href="/assets/style-def.css">')
    result = shell(f'frontend_assets "{page}"')
    assert result.returncode == 0
    assert result.stdout.splitlines() == ['/assets/app-abc.js', '/assets/style-def.css']


# Ownership is the only OS property mocked here: tests run as a non-root user.
# Actual mode checks, inode/hash checks and all writes stay inside tmp_path.
def state_setup(tmp_path):
    return f'''
chown() {{ :; }}
protected_path() {{
    [[ ! -L $1 && $(stat -c %a "$1") == "$2" ]] || fail "Estado inseguro: $1";
}}
INSTALL_STATE="{tmp_path}/state"
ENV_FILE="{tmp_path}/ticketyn.env"
POLICY_FILE="{tmp_path}/policy-rc.d"
INSTALL_LOCK="{tmp_path}/install.lock"
VERSION=0.1.0; SOURCE_HASH={'a' * 64}; HTTP_PORT=8080
NEW_NGINX=1; DEFAULT_ABSENT=1; RECOVERING=0
init_state
'''


def fake_database(tmp_path, exit_code):
    """Real setsid --fork --wait; fake psql/runuser/createdb, never system PG."""
    import shutil
    fake = tmp_path / 'bin'
    fake.mkdir()
    executables = {
        'runuser': '#!/bin/sh\nwhile [ "$1" != -- ]; do shift; done\nshift\nexec "$@"\n',
        'setsid': f'#!/bin/sh\nexec "{shutil.which("setsid")}" --fork "$@"\n',
        'psql': f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{tmp_path}/psql-args"\nread first\nread second\n[ "$first" = "$second" ] || exit 9\nexit {exit_code}\n',
        'createdb': f'#!/bin/sh\nprintf "%s\\n" "$*" > "{tmp_path}/createdb-args"\n',
    }
    for name, content in executables.items():
        path = fake/name
        path.write_text(content)
        path.chmod(0o755)
    return f'''
PATH="{fake}:$PATH"
systemctl() {{ :; }}
ss() {{ echo 'LISTEN 0 128 127.0.0.1:5432 0.0.0.0:*'; }}
locale() {{ echo C.utf8; }}
psql_admin() {{
    printf '%s\\n' "$*" >> "{tmp_path}/sql-args"
    case "$*" in
        *'count(*)'*) echo 0;;
        *'pg_encoding_to_char'*) echo "ticketyn-install:$INSTALL_TOKEN:ticketyn:UTF8";;
        *) echo 1;;
    esac
}}
'''


@pytest.mark.parametrize('exit_code', [0, 7])
def test_psql_exit_status_and_no_continuation_after_password_failure(tmp_path, exit_code):
    result = shell(state_setup(tmp_path) + fake_database(tmp_path, exit_code)
                   + '\nprepare_database\necho DATABASE_READY')
    assert (result.returncode == 0) == (exit_code == 0), result.stderr
    assert (tmp_path/'createdb-args').exists() == (exit_code == 0)
    assert (tmp_path/'state/password_ready').exists() == (exit_code == 0)
    assert ('DATABASE_READY' in result.stdout) == (exit_code == 0)
    password = (tmp_path/'ticketyn.env').read_text().split(':', 2)[2].split('@')[0]
    assert len(password) == 64
    assert password not in result.stdout + result.stderr
    assert password not in (tmp_path/'psql-args').read_text()
    assert password not in (tmp_path/'sql-args').read_text()
    assert all(password not in item.read_text() for item in (tmp_path/'state').iterdir())
    assert (tmp_path/'ticketyn.env').stat().st_mode & 0o777 == 0o600
    if exit_code == 0:
        args = (tmp_path/'createdb-args').read_text()
        assert '--encoding=UTF8' in args and '--template=template0' in args


def test_unknown_role_is_not_changed(tmp_path):
    mocks = fake_database(tmp_path, 0) + '''
psql_admin() {
    case "$*" in *'count(*)'*) echo 1;; *'shobj_description'*) echo foreign;; *) echo 1;; esac
}
'''
    result = shell(state_setup(tmp_path) + mocks + '\nprepare_database')
    assert result.returncode != 0 and 'no pertenece' in result.stderr
    assert not (tmp_path/'psql-args').exists()
    assert not (tmp_path/'createdb-args').exists()


def test_unknown_database_is_not_migrated_or_recreated(tmp_path):
    mocks = fake_database(tmp_path, 0) + '''
state_put password_ready 1
psql_admin() {
    case "$*" in
        *'count(*)'*) echo 1;;
        *'pg_encoding_to_char'*) echo foreign;;
        *'shobj_description'*) echo "ticketyn-install:$INSTALL_TOKEN";;
        *) echo 1;;
    esac
}
'''
    result = shell(state_setup(tmp_path) + mocks + '\nprepare_database\necho MIGRATE')
    assert result.returncode != 0 and 'no tiene identidad' in result.stderr
    assert 'MIGRATE' not in result.stdout
    assert not (tmp_path/'createdb-args').exists()


def test_owned_credentials_are_reused_without_rotating_password(tmp_path):
    result = shell(state_setup(tmp_path) + '''
ensure_credentials
before=$DB_PASSWORD
ensure_credentials
[[ $DB_PASSWORD == "$before" ]]
''')
    assert result.returncode == 0, result.stderr


def test_protected_state_roundtrip_and_completed_install_refused(tmp_path):
    result = shell(state_setup(tmp_path) + '''
phase servicios
state_put release_ready 1
load_state
[[ $RECOVERING == 1 && $RELEASE_READY == 1 && $PHASE == servicios && $HTTP_PORT == 8080 ]]
state_put status complete
load_state
echo SHOULD_NOT_RUN
''')
    assert result.returncode != 0 and 'ya está instalado' in result.stderr
    assert 'SHOULD_NOT_RUN' not in result.stdout
    assert (tmp_path/'state').stat().st_mode & 0o777 == 0o700
    assert all(item.stat().st_mode & 0o777 == 0o600 for item in (tmp_path/'state').iterdir())


@pytest.mark.parametrize('change', ['VERSION=0.2.0', f'SOURCE_HASH={"b" * 64}', 'chmod 0777 "$INSTALL_STATE"'])
def test_recovery_rejects_changed_version_source_or_insecure_state(tmp_path, change):
    result = shell(state_setup(tmp_path) + change + '\nload_state\necho SHOULD_NOT_RUN')
    assert result.returncode != 0 and 'SHOULD_NOT_RUN' not in result.stdout


def test_state_symlink_is_rejected(tmp_path):
    target = tmp_path/'outside'
    target.mkdir(mode=0o700)
    (tmp_path/'state').symlink_to(target)
    result = shell(f'INSTALL_STATE="{tmp_path}/state"; load_state')
    assert result.returncode != 0 and 'seguro' in result.stderr


@pytest.mark.parametrize('kind', ['file', 'directory', 'symlink'])
def test_atomic_current_publication_refuses_unexpected_destination(tmp_path, kind):
    destination = tmp_path/'current'
    if kind == 'file':
        destination.write_text('foreign')
    elif kind == 'directory':
        destination.mkdir()
    else:
        destination.symlink_to('foreign')
    result = shell(state_setup(tmp_path) + f'create_owned_link current release "{destination}"')
    assert result.returncode != 0
    if kind == 'file':
        assert destination.read_text() == 'foreign'
    elif kind == 'directory':
        assert list(destination.iterdir()) == []
    else:
        assert destination.readlink() == Path('foreign')


def test_current_publication_identity_survives_recovery(tmp_path):
    result = shell(state_setup(tmp_path) + f'''
create_owned_link current release "{tmp_path}/current"
load_state
require_owned current "{tmp_path}/current"
''')
    assert result.returncode == 0, result.stderr
    assert (tmp_path/'current').readlink() == Path('release')


def test_publish_file_does_not_overwrite_destination_that_appeared(tmp_path):
    prepared, destination = tmp_path/'prepared', tmp_path/'unit'
    prepared.write_text('ours'); destination.write_text('administrator')
    result = shell(state_setup(tmp_path) + f'publish_file unit "{prepared}" "{destination}"')
    assert result.returncode != 0
    assert destination.read_text() == 'administrator'


def test_recovery_rejects_replaced_or_modified_artifact(tmp_path):
    artifact = tmp_path/'unit'
    artifact.write_text('ours')
    result = shell(state_setup(tmp_path) + f'''
record_owned unit "{artifact}"
printf changed > "{artifact}"
RECOVERING=1
allow_owned_or_absent unit "{artifact}"
''')
    assert result.returncode != 0 and 'no reconocido' in result.stderr
    assert artifact.read_text() == 'changed'


def test_abandoned_owned_policy_recovered_but_administrator_policy_preserved(tmp_path):
    result = shell(state_setup(tmp_path) + '''
policy_content > "$POLICY_FILE"
record_owned policy "$POLICY_FILE"
load_state
recover_policy
[[ ! -e $POLICY_FILE ]]
printf administrator > "$POLICY_FILE"
recover_policy
''')
    assert result.returncode != 0
    assert (tmp_path/'policy-rc.d').read_text() == 'administrator'


def test_preexisting_policy_without_ownership_marker_is_untouched(tmp_path):
    result = shell(state_setup(tmp_path) + '''
printf administrator > "$POLICY_FILE"
recover_policy
''')
    assert result.returncode == 0
    assert (tmp_path/'policy-rc.d').read_text() == 'administrator'


@pytest.mark.parametrize('lock_present, expected', [(False, 0), (True, 101)])
def test_policy_after_sigkill_or_reboot_does_not_block_without_lock(tmp_path, lock_present, expected):
    fake = tmp_path/'bin'; fake.mkdir()
    executable = fake/'flock'
    executable.write_text(f'#!/bin/sh\nexit {101 if lock_present else 0}\n')
    executable.chmod(0o755)
    result = shell(state_setup(tmp_path) + '''policy_content > "$POLICY_FILE"\n'''
                   + f'PATH="{fake}:$PATH" sh "$POLICY_FILE"')
    assert result.returncode == expected


@pytest.mark.parametrize('sig', ['SIGINT', 'SIGTERM', 'SIGKILL'])
def test_interruption_preserves_recoverable_state_and_policy(tmp_path, sig):
    import signal
    script = state_setup(tmp_path) + '''
STATE_ACTIVE=1; OWN_POLICY=1
WORK=$(mktemp -d "$INSTALL_STATE/../work.XXXXXXXX")
policy_content > "$POLICY_FILE"
record_owned policy "$POLICY_FILE"
phase paquetes
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'READY\\n'
read -r answer
'''
    process = subprocess.Popen(['bash', '-c', 'source "$1"\n' + script, 'test', str(INSTALLER)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline() == 'READY\n'
        process.send_signal(getattr(signal, sig))
        process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill(); process.communicate(timeout=5)
    assert (tmp_path/'state/phase').read_text().strip() == 'paquetes'
    if sig == 'SIGKILL':
        assert (tmp_path/'policy-rc.d').exists()
        # No init_state again: use the persisted state from the interrupted process.
        setup = state_setup(tmp_path).split('init_state')[0]
        result = shell(setup + 'load_state\nrecover_policy')
        assert result.returncode == 0, result.stderr
    else:
        assert (tmp_path/'state/status').read_text().strip() == 'failed'
    assert not (tmp_path/'policy-rc.d').exists()


@pytest.mark.parametrize('config, code', [
    ('server { listen "8080"; }', 0),
    ('server { listen example.internal:8080; }', 2),
    ('server { listen $unknown; }', 2),
    ('server { listen nonsense; }', 2),
    ('# comment; listen 8080;\nserver { listen 9090; }', 1),
    ('server { listen unix:/tmp/nginx.sock; }', 1),
])
def test_conservative_nginx_listen_parser(config, code):
    result = shell('nginx_config_uses_port 8080', config)
    assert result.returncode == code


def test_unknown_nginx_listen_aborts_preflight(tmp_path):
    result = shell('nginx() { echo "server { listen unknown; }"; }; nginx_port_configured 80; echo SHOULD_NOT_RUN')
    assert result.returncode != 0 and 'no interpretable' in result.stderr
    assert 'SHOULD_NOT_RUN' not in result.stdout


def test_nginx_ipv4_only_works_without_ipv6():
    result = shell(f'HTTP_PORT=8080; render_nginx "{INSTALLER.parent}/deploy/nginx/ticketyn.conf"')
    assert result.returncode == 0
    assert 'listen 8080;' in result.stdout and 'listen [::]' not in result.stdout
    assert 'proxy_pass http://127.0.0.1:8000;' in result.stdout


@pytest.mark.parametrize('preexisting, changed', [(False, False), (True, False), (False, True)])
def test_packaged_default_protection(tmp_path, preexisting, changed):
    import hashlib
    default = tmp_path/'default.conf'; link = tmp_path/'default'
    original = b'packaged default'
    checksum = hashlib.md5(original).hexdigest()
    default.write_bytes(b'admin edit' if changed else original)
    link.symlink_to(default)
    result = shell(state_setup(tmp_path) + f'''
NEW_NGINX=1; DEFAULT_ABSENT={0 if preexisting else 1}
NGINX_DEFAULT_LINK="{link}"; NGINX_DEFAULT_FILE="{default}"
dpkg-query() {{ echo '/etc/nginx/sites-available/default {checksum}'; }}
capture_packaged_default
remove_new_packaged_default
''')
    assert link.is_symlink() == (preexisting or changed)
    assert default.exists()
    assert (result.returncode == 0) == (not changed or preexisting)


@pytest.mark.parametrize('name', ['.env', '.git', 'secret.key', 'secret.pem', 'backup.dump', 'backup.sql', 'secret.p12', 'secret.pfx', 'id_ed25519', 'data.bak'])
def test_release_aborts_on_sensitive_nested_content(tmp_path, name):
    for tree in ['src', 'alembic', 'deploy', 'frontend/dist']:
        (tmp_path/tree).mkdir(parents=True)
    (tmp_path/'src'/name).write_text('do not copy')
    result = shell(f'validate_release_source "{tmp_path}"')
    assert result.returncode != 0 and str(tmp_path/'src'/name) in result.stderr


def test_release_aborts_on_private_key_content_or_escaping_symlink(tmp_path):
    for tree in ['src', 'alembic', 'deploy', 'frontend/dist']:
        (tmp_path/tree).mkdir(parents=True)
    key = tmp_path/'src/disguised.txt'
    key.write_text('-----BEGIN OPENSSH PRIVATE KEY-----')
    assert shell(f'validate_release_source "{tmp_path}"').returncode != 0
    key.unlink(); key.symlink_to('/etc/passwd')
    result = shell(f'validate_release_source "{tmp_path}"')
    assert result.returncode != 0 and 'Symlink' in result.stderr


def test_git_error_is_not_treated_as_head_without_tag(tmp_path):
    (tmp_path/'.git').mkdir()
    (tmp_path/'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    result = shell(f'git() {{ return 128; }}; project_version "{tmp_path}"')
    assert result.returncode != 0 and 'HEAD' in result.stderr


@pytest.mark.parametrize('tag, dirty', [('', False), ('v0.1.0', False), ('', True)])
def test_git_tag_and_worktree_file_supported(tmp_path, tag, dirty):
    (tmp_path/'.git').write_text('gitdir: fictional-test-worktree')
    (tmp_path/'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    result = shell(f'''
git() {{ case "$3" in rev-parse) echo HEAD;; tag) printf '%s' '{tag}';; status) printf '%s' '{' M README.md' if dirty else ''}';; esac; }}
project_version "{tmp_path}"
''')
    assert result.returncode == 0 and result.stdout == '0.1.0'
    assert ('árbol Git modificado' in result.stderr) == dirty
    assert ('sin tag exacto' in result.stderr) == (not tag)


def test_owned_partial_release_can_resume_after_pip_failure(tmp_path):
    source, release = tmp_path/'source', tmp_path/'releases/0.1.0'
    for tree in ['src/ticketyn', 'alembic', 'deploy/systemd', 'frontend/dist']:
        (source/tree).mkdir(parents=True)
    for name in ['alembic.ini', 'pyproject.toml', 'requirements.lock', 'LICENSE', 'README.md', 'src/ticketyn/main.py', 'frontend/dist/index.html']:
        (source/name).write_text('fixture')
    runtime = tmp_path/'python-runtime'
    runtime.write_text('''#!/bin/sh
case "$*" in
    *'pip install'*) [ "${FAIL_PIP:-0}" = 0 ] || exit 9;;
esac
exit 0
''')
    runtime.chmod(0o755)
    mocks = f'''
SOURCE="{source}"
RELEASE="{release}"
RELEASES_DIR="{release.parent}"
CURRENT_FILE="{tmp_path}/current"
SOURCE_HASH=$(release_tar | sha256sum | cut -d ' ' -f1)
state_put source "$SOURCE_HASH"
python3() {{
    mkdir -p "$RELEASE/.venv/bin"
    cp "{runtime}" "$RELEASE/.venv/bin/python"
}}
chown() {{ :; }}
ensure_credentials() {{ :; }}
verify_database_head() {{ echo VERIFIED >> "{tmp_path}/migration-checks"; }}
'''
    first = shell(state_setup(tmp_path) + mocks + '''
STATE_ACTIVE=1; trap cleanup EXIT
phase release
export FAIL_PIP=1
prepare_release
''')
    assert first.returncode != 0
    assert release.exists() and not (tmp_path/'current').exists()
    assert (tmp_path/'state/status').read_text().strip() == 'failed'
    setup = state_setup(tmp_path).split('init_state')[0]
    resumed = shell(setup + mocks + '''
load_state
export FAIL_PIP=0
prepare_release
''')
    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path/'current').readlink() == release
    assert (tmp_path/'state/release_ready').read_text().strip() == '1'
    assert (release/'frontend/dist/index.html').read_text() == 'fixture'
    # Prepared/published release is not recopied or pip-installed on a late retry.
    ready = shell(setup + mocks + 'load_state\nexport FAIL_PIP=1\nprepare_release')
    assert ready.returncode == 0, ready.stderr
    assert len((tmp_path/'migration-checks').read_text().splitlines()) == 2


@pytest.mark.parametrize('failure', ['nginx', 'systemd', 'final'])
def test_late_failure_can_resume_owned_deployment_without_rollback(tmp_path, failure):
    release = tmp_path/'release'
    (release/'deploy/systemd').mkdir(parents=True)
    (release/'deploy/nginx').mkdir()
    (release/'deploy/systemd/ticketyn.service').write_text('[Service]\nUser=ticketyn\n')
    (release/'deploy/nginx/ticketyn.conf').write_text('server { listen 80; listen [::]:80; }\n')
    mocks = f'''
RELEASE="{release}"
UNIT_FILE="{tmp_path}/unit.service"
NGINX_SITE="{tmp_path}/site.conf"
NGINX_LINK="{tmp_path}/enabled"
CURRENT_FILE="{tmp_path}/current"
remove_new_packaged_default() {{ :; }}
nginx_port_configured() {{ return 1; }}
listening_port() {{ return 1; }}
nginx() {{ [[ $FAILURE != nginx ]]; }}
systemctl() {{ [[ $FAILURE != systemd ]]; }}
final_checks() {{ [[ $FAILURE != final ]]; }}
'''
    first = shell(state_setup(tmp_path) + mocks + f'''
create_owned_link current "$RELEASE" "$CURRENT_FILE"
state_put release_ready 1
STATE_ACTIVE=1; trap cleanup EXIT
phase servicios
FAILURE={failure}
configure_services
phase comprobaciones
final_checks
''')
    assert first.returncode != 0
    assert (tmp_path/'current').readlink() == release
    assert (tmp_path/'state/status').read_text().strip() == 'failed'
    setup = state_setup(tmp_path).split('init_state')[0]
    resumed = shell(setup + mocks + '''
load_state
FAILURE=none
configure_services
final_checks
state_put status complete
''')
    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path/'current').readlink() == release
    assert (tmp_path/'state/status').read_text().strip() == 'complete'


def test_policy_fails_open_on_lock_inspection_error(tmp_path):
    fake = tmp_path/'bin'; fake.mkdir()
    executable = fake/'flock'
    executable.write_text('#!/bin/sh\nexit 73\n'); executable.chmod(0o755)
    result = shell(state_setup(tmp_path) + 'policy_content > "$POLICY_FILE"\n'
                   + f'PATH="{fake}:$PATH" sh "$POLICY_FILE"')
    assert result.returncode == 0


def test_apt_failure_cleans_own_policy_and_retains_phase(tmp_path):
    result = shell(state_setup(tmp_path) + '''
STATE_ACTIVE=1; trap cleanup EXIT
phase paquetes
apt-get() { return 9; }
install_dependencies
echo SHOULD_NOT_RUN
''')
    assert result.returncode != 0
    assert not (tmp_path/'policy-rc.d').exists()
    assert (tmp_path/'state/status').read_text().strip() == 'failed'
    assert (tmp_path/'state/phase').read_text().strip() == 'paquetes'
    assert 'SHOULD_NOT_RUN' not in result.stdout


def test_changed_default_symlink_is_not_unlinked(tmp_path):
    import hashlib
    default = tmp_path/'default.conf'; link = tmp_path/'default'; replacement = tmp_path/'replacement'
    default.write_text('packaged'); link.symlink_to(default); replacement.symlink_to(default)
    checksum = hashlib.md5(default.read_bytes()).hexdigest()
    # First checksum call replaces link inode; immediate revalidation must detect it.
    result = shell(state_setup(tmp_path) + f'''
NEW_NGINX=1; DEFAULT_ABSENT=1
NGINX_DEFAULT_LINK="{link}"; NGINX_DEFAULT_FILE="{default}"
dpkg-query() {{ echo '/etc/nginx/sites-available/default {checksum}'; }}
record_owned default "$NGINX_DEFAULT_LINK"
md5sum() {{
    if [[ -L "{replacement}" ]]; then mv -Tf "{replacement}" "{link}"; fi
    command md5sum "$@"
}}
remove_new_packaged_default
''')
    assert result.returncode != 0 and link.is_symlink()
    assert default.exists()


def test_nginx_recovery_ignores_only_verified_own_site(tmp_path):
    config = tmp_path/'site.conf'
    config.write_text('server { listen 8080; }\n')
    result = shell(state_setup(tmp_path) + f'''
NGINX_SITE="{config}"
record_owned nginx "$NGINX_SITE"
RECOVERING=1
nginx() {{ printf '%s\\n' '# configuration file /etc/nginx/sites-enabled/ticketyn:' 'server {{ listen 8080; }}' '# configuration file /etc/nginx/sites-enabled/other:' 'server {{ listen 9090; }}'; }}
if nginx_port_configured 8080; then exit 9; fi
nginx_port_configured 9090
''')
    assert result.returncode == 0, result.stderr


def test_real_policy_unlocks_after_sigkill_even_with_running_child(tmp_path):
    import signal
    script = state_setup(tmp_path) + '''
exec 9>>"$INSTALL_LOCK"
flock -n 9
policy_content > "$POLICY_FILE"
sleep 30 9>&- >/dev/null 2>&1 &
printf '%s\\n' "$!"
wait
'''
    process = subprocess.Popen(['bash', '-c', 'source "$1"\n' + script, 'test', str(INSTALLER)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child = None
    try:
        child = int(process.stdout.readline())
        process.kill(); process.communicate(timeout=5)
        result = subprocess.run(['sh', str(tmp_path/'policy-rc.d')], capture_output=True, timeout=5)
        assert result.returncode == 0
    finally:
        if process.poll() is None:
            process.kill(); process.communicate(timeout=5)
        if child:
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_real_git_matching_tag_dirty_worktree_and_missing_tag(tmp_path):
    # Real Git repository entirely in pytest's temporary directory.
    def git(*arguments):
        return subprocess.run(['git', '-C', str(tmp_path), *arguments], check=True, capture_output=True)
    git('init', '-q')
    git('config', 'user.name', 'Installer Test')
    git('config', 'user.email', 'installer@example.invalid')
    (tmp_path/'pyproject.toml').write_text('[project]\nversion = "0.1.0"\n')
    git('add', 'pyproject.toml'); git('commit', '-qm', 'test fixture')
    without_tag = shell(f'project_version "{tmp_path}"')
    assert without_tag.returncode == 0 and 'sin tag exacto' in without_tag.stderr
    git('tag', 'v0.1.0')
    matching = shell(f'project_version "{tmp_path}"')
    assert matching.returncode == 0 and matching.stderr == ''
    worktree = tmp_path/'linked-worktree'
    git('worktree', 'add', '-q', '--detach', str(worktree), 'HEAD')
    assert (worktree/'.git').is_file()
    linked = shell(f'project_version "{worktree}"')
    assert linked.returncode == 0 and linked.stdout == '0.1.0'
    (tmp_path/'untracked.txt').write_text('local edit')
    dirty = shell(f'project_version "{tmp_path}"')
    assert dirty.returncode == 0 and 'árbol Git modificado' in dirty.stderr
    git('tag', 'v0.2.0')
    mismatch = shell(f'project_version "{tmp_path}"')
    assert mismatch.returncode != 0 and 'no coincide' in mismatch.stderr


def test_default_recreated_by_administrator_after_failure_is_preserved(tmp_path):
    import hashlib
    default = tmp_path/'default.conf'; link = tmp_path/'default'
    default.write_text('packaged')
    checksum = hashlib.md5(default.read_bytes()).hexdigest()
    result = shell(state_setup(tmp_path) + f'''
NGINX_DEFAULT_LINK="{link}"; NGINX_DEFAULT_FILE="{default}"
dpkg-query() {{ echo '/etc/nginx/sites-available/default {checksum}'; }}
ln -s "$NGINX_DEFAULT_FILE" "$NGINX_DEFAULT_LINK"
capture_packaged_default
remove_new_packaged_default
ln -s "$NGINX_DEFAULT_FILE" "$NGINX_DEFAULT_LINK"
load_state
remove_new_packaged_default
''')
    assert result.returncode != 0 and link.is_symlink()
    assert default.exists()


def test_default_without_marker_after_interrupted_apt_requires_manual_review(tmp_path):
    default = tmp_path/'default.conf'; link = tmp_path/'default'
    default.write_text('packaged'); link.symlink_to(default)
    result = shell(state_setup(tmp_path) + f'''
NGINX_DEFAULT_LINK="{link}"; NGINX_DEFAULT_FILE="{default}"
load_state
capture_packaged_default
''')
    assert result.returncode != 0 and 'sin prueba' in result.stderr
    assert link.is_symlink() and default.exists()
