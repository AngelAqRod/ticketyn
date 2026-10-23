"""Installer/bootstrap boundary: temporary files, fake services and ephemeral PG only."""
import importlib.util
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, inspect, select as sql_select, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_security', ROOT / 'deploy/install_security.py')
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


def shell(script, *, terminal=False):
    args = ['bash', '-c', 'source "$1"\n' + script, 'test', str(ROOT / 'install.sh')]
    if not terminal:
        return subprocess.run(args, capture_output=True, text=True, timeout=30)
    master, slave = pty.openpty()
    try:
        return subprocess.run(args, stdin=slave, capture_output=True, text=True, timeout=30)
    finally:
        os.close(slave); os.close(master)


@pytest.fixture
def auth_source(tmp_path):
    source = tmp_path / 'source'
    for name in ['src/ticketyn/main.py', 'src/ticketyn/api/auth.py', 'src/ticketyn/security/bootstrap.py',
                 'bootstrap-superadmin.sh', 'alembic/versions/0030_security_foundation.py',
                 'alembic/versions/0031_role_permissions.py', 'alembic/versions/0032_responsible_selectable.py']:
        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    return source


def test_detects_actual_authentication_even_before_version_bump(auth_source):
    assert security.capability(auth_source) == 'required'
    result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'deploy/install_security.py'), str(auth_source)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout == 'required\n'


def test_legacy_release_does_not_depend_on_version_number(tmp_path):
    (tmp_path / 'src/ticketyn').mkdir(parents=True)
    (tmp_path / 'alembic/versions').mkdir(parents=True)
    # HEAD now contains v0.7 authentication; pin this historical fixture explicitly.
    legacy = subprocess.check_output(['git', 'show', 'v0.6.2:src/ticketyn/main.py'], cwd=ROOT)
    (tmp_path / 'src/ticketyn/main.py').write_bytes(legacy)
    (tmp_path / 'alembic/versions/0029.py').write_text("revision='0029_mail_requests'\ndown_revision=None\n")
    assert security.capability(tmp_path) == 'legacy'


@pytest.mark.parametrize('missing', ['bootstrap-superadmin.sh', 'src/ticketyn/security/bootstrap.py',
                                   'src/ticketyn/api/auth.py', 'alembic/versions/0032_responsible_selectable.py'])
def test_partial_security_package_never_falls_back_to_legacy(auth_source, missing):
    (auth_source / missing).unlink()
    with pytest.raises((security.CapabilityError, OSError)):
        security.capability(auth_source)


@pytest.mark.parametrize('change', ['no-wiring', 'no-auth-router', 'no-check', 'wrong-schema', 'not-executable'])
def test_checks_capabilities_beyond_file_names(auth_source, change):
    if change == 'no-wiring':
        file = auth_source / 'src/ticketyn/main.py'
        file.write_text(file.read_text().replace('install_security(app, security_session_factory)', 'pass'))
    if change == 'no-check':
        file = auth_source / 'src/ticketyn/security/bootstrap.py'
        file.write_text(file.read_text().replace("'--check'", "'--other'"))
    if change == 'no-auth-router':
        file = auth_source / 'src/ticketyn/main.py'
        file.write_text(file.read_text().replace('app.include_router(auth_router)', 'pass'))
    if change == 'wrong-schema':
        file = auth_source / 'alembic/versions/0031_role_permissions.py'
        file.write_text(file.read_text().replace("down_revision = '0030_security_foundation'", "down_revision = '0029_mail_requests'"))
    if change == 'not-executable':
        (auth_source / 'bootstrap-superadmin.sh').chmod(0o644)
    with pytest.raises(security.CapabilityError):
        security.capability(auth_source)


@pytest.mark.parametrize('with_bootstrap', [False, True])
def test_release_copy_includes_bootstrap_without_changing_legacy_identity(auth_source, tmp_path, with_bootstrap):
    if not with_bootstrap:
        (auth_source / 'bootstrap-superadmin.sh').unlink()
    for name in ['deploy', 'frontend/dist']:
        (auth_source / name).mkdir(parents=True)
    for name in ['alembic.ini', 'pyproject.toml', 'requirements.lock', 'LICENSE', 'README.md']:
        (auth_source / name).write_text('fixture')
    candidate = tmp_path / 'candidate'; candidate.mkdir()
    result = shell(f'''SOURCE="{auth_source}"; RELEASE="{candidate}"
SOURCE_HASH=$(release_tar | sha256sum | cut -d ' ' -f1)
copy_release
if [[ -f "$SOURCE/bootstrap-superadmin.sh" ]]; then
    cmp "$SOURCE/bootstrap-superadmin.sh" "$RELEASE/bootstrap-superadmin.sh"
    [[ -x "$RELEASE/bootstrap-superadmin.sh" ]]
else
    old_hash=$(tar -C "$SOURCE" --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \\
        --exclude='__pycache__' --exclude='*.pyc' --exclude='.env*' --exclude='*.egg-info' \\
        --exclude='.git' --exclude='node_modules' --exclude='.pytest_cache' --exclude='.mypy_cache' --exclude='.ruff_cache' \\
        -cf - src alembic alembic.ini pyproject.toml requirements.lock LICENSE README.md deploy frontend/dist | sha256sum | cut -d ' ' -f1)
    [[ "$old_hash" == "$SOURCE_HASH" ]]
fi
''')
    assert result.returncode == 0, result.stderr
    assert (candidate / 'bootstrap-superadmin.sh').exists() == with_bootstrap


@pytest.fixture
def simulated_install(tmp_path):
    candidate = tmp_path / 'release'
    (candidate / '.venv/bin').mkdir(parents=True)
    (candidate / '.venv/bin/python').write_text('# fixture interpreter\n')
    (candidate / '.venv/bin/python').chmod(0o755)
    code = tmp_path / 'check-code'; code.write_text('3')
    trace = tmp_path / 'bootstrap-calls'
    bootstrap = candidate / 'bootstrap-superadmin.sh'
    bootstrap.write_text(f'''#!/bin/bash
printf '%s\\n' "$*" >> "{trace}"
if [[ "$*" == *--check* ]]; then exit "$(cat "{code}")"; fi
[[ ${{CREATION_CODE:-0}} == 0 ]] || exit "$CREATION_CODE"
[[ ${{FORGET_CREATE:-0}} != 1 ]] || exit 0
printf '0' > "{code}"
''')
    bootstrap.chmod(0o755)
    setup = f'''AUTH_MODE=required; ADMIN_READY=0; RELEASE_READY=1
RELEASE="{candidate}"; ENV_FILE="{tmp_path}/private.env"
'''
    return setup, candidate, code, trace


def test_new_authenticated_install_initializes_and_checks_before_services(simulated_install):
    setup, candidate, code, trace = simulated_install
    result = shell(setup + 'initialize_administration\n[[ $ADMIN_READY == 1 ]]\necho SERVICES_ALLOWED', terminal=True)
    assert result.returncode == 0, result.stderr
    assert 'Instalación técnica completada' in result.stdout
    assert 'Inicialización administrativa completada' in result.stdout
    calls = trace.read_text().splitlines()
    assert len(calls) == 3
    assert calls[0].endswith('--check') and not calls[1].endswith('--check') and calls[2].endswith('--check')
    assert all(line.startswith('--config ') for line in calls)
    assert 'SERVICES_ALLOWED' in result.stdout


def test_existing_superadmin_never_prompts_or_changes_credentials(simulated_install):
    setup, candidate, code, trace = simulated_install
    code.write_text('0')
    result = shell(setup + 'initialize_administration\n[[ $ADMIN_READY == 1 ]]')
    assert result.returncode == 0, result.stderr
    assert len(trace.read_text().splitlines()) == 2
    assert all(line.endswith('--check') for line in trace.read_text().splitlines())


@pytest.mark.parametrize('code', [1, 2, 130])
def test_invalid_database_or_inconsistent_state_stops_without_starting_services(simulated_install, code):
    setup, candidate, state, trace = simulated_install
    state.write_text(str(code))
    result = shell(setup + 'initialize_administration\necho SERVICES_ALLOWED')
    assert result.returncode != 0
    assert 'Inicialización administrativa pendiente' in result.stderr
    assert 'SERVICES_ALLOWED' not in result.stdout
    assert len(trace.read_text().splitlines()) == 1


@pytest.mark.parametrize('code', [1, 130])
def test_failed_or_interrupted_creation_cannot_announce_ready(simulated_install, code):
    setup, candidate, state, trace = simulated_install
    result = shell(setup + f'export CREATION_CODE={code}\ninitialize_administration\necho SERVICES_ALLOWED', terminal=True)
    assert result.returncode != 0
    assert 'falló o fue interrumpido' in result.stderr
    assert 'SERVICES_ALLOWED' not in result.stdout
    assert state.read_text() == '3'


def test_bootstrap_exit_zero_requires_independent_confirmation(simulated_install):
    setup, candidate, state, trace = simulated_install
    result = shell(setup + 'export FORGET_CREATE=1\ninitialize_administration\necho SERVICES_ALLOWED', terminal=True)
    assert result.returncode != 0 and 'no confirmó un Superadministrador válido' in result.stderr
    assert 'SERVICES_ALLOWED' not in result.stdout


def test_missing_bootstrap_and_missing_terminal_are_actionable(simulated_install):
    setup, candidate, state, trace = simulated_install
    result = shell(setup + 'initialize_administration')
    assert result.returncode != 0 and 'terminal interactiva' in result.stderr
    assert str(candidate / 'bootstrap-superadmin.sh') in result.stderr
    (candidate / 'bootstrap-superadmin.sh').unlink()
    result = shell(setup + 'initialize_administration')
    assert result.returncode != 0 and 'falta el intérprete o el bootstrap' in result.stderr
    assert 'Inicialización administrativa pendiente' in result.stderr


def test_migrations_must_be_verified_before_bootstrap(simulated_install):
    setup, candidate, state, trace = simulated_install
    result = shell(setup + 'RELEASE_READY=0\ninitialize_administration\necho SERVICES_ALLOWED')
    assert result.returncode != 0 and 'migraciones' in result.stderr
    assert not trace.exists()
    assert 'SERVICES_ALLOWED' not in result.stdout


def test_legacy_install_skips_bootstrap(simulated_install):
    setup, candidate, state, trace = simulated_install
    result = shell(setup + 'AUTH_MODE=legacy\ninitialize_administration')
    assert result.returncode == 0 and 'no incorpora autenticación' in result.stdout
    assert not trace.exists()


def test_reexecution_preserves_state_and_checks_existing_admin(simulated_install, tmp_path):
    from test_installer import state_setup
    setup, candidate, code, trace = simulated_install
    first = shell(state_setup(tmp_path) + setup + '''
state_put release_ready 1
phase bootstrap
STATE_ACTIVE=1; trap cleanup EXIT
export CREATION_CODE=1
initialize_administration
''', terminal=True)
    assert first.returncode != 0
    assert (tmp_path / 'state/status').read_text().strip() == 'failed'
    assert (tmp_path / 'state/phase').read_text().strip() == 'bootstrap'
    assert candidate.is_dir()
    # Simulate completion by the documented local bootstrap, then resume.
    code.write_text('0')
    before = trace.read_text().splitlines()
    result = shell(state_setup(tmp_path).split('init_state')[0] + setup + '''
load_state
initialize_administration
[[ $ADMIN_READY == 1 && $RECOVERING == 1 ]]
''')
    assert result.returncode == 0, result.stderr
    assert all(line.endswith('--check') for line in trace.read_text().splitlines()[len(before):])


def test_service_start_failure_preserves_administrator_and_can_resume(simulated_install, tmp_path):
    from test_installer import state_setup
    setup, candidate, code, trace = simulated_install
    code.write_text('0')
    preserved = candidate / 'previously-prepared'; preserved.write_text('preserve')
    first = shell(state_setup(tmp_path) + setup + '''
state_put release_ready 1
STATE_ACTIVE=1; trap cleanup EXIT
phase bootstrap
initialize_administration
phase servicios
configure_services() { return 9; }
configure_services
show_success
''')
    assert first.returncode != 0
    assert 'se instaló correctamente' not in first.stdout
    assert (tmp_path / 'state/phase').read_text().strip() == 'servicios'
    resumed = shell(state_setup(tmp_path).split('init_state')[0] + setup + '''
load_state
initialize_administration
configure_services() { echo SERVICES_READY; }
configure_services
''')
    assert resumed.returncode == 0, resumed.stderr
    assert 'SERVICES_READY' in resumed.stdout
    assert all(line.endswith('--check') for line in trace.read_text().splitlines())
    assert preserved.read_text() == 'preserve'


@pytest.mark.parametrize('mode, ready, pending', [('legacy', 0, False), ('required', 1, False), ('required', 0, True)])
def test_failure_diagnostics_only_request_missing_initialization(simulated_install, tmp_path, mode, ready, pending):
    from test_installer import state_setup
    setup, candidate, code, trace = simulated_install
    result = shell(state_setup(tmp_path) + setup + f'''
AUTH_MODE={mode}; ADMIN_READY={ready}
STATE_ACTIVE=1; trap cleanup EXIT
phase bootstrap
false
''')
    assert result.returncode != 0
    assert ('Inicialización administrativa pendiente' in result.stderr) == pending


@pytest.mark.parametrize('mode, ready, expected', [('required', 1, True), ('required', 0, False), ('legacy', 0, True)])
def test_success_messages_distinguish_administrative_initialization(mode, ready, expected):
    result = shell(f'''AUTH_MODE={mode}; ADMIN_READY={ready}; HTTP_PORT=8080
ip() {{ :; }}
hostname() {{ :; }}
show_success
''')
    assert (result.returncode == 0) == expected
    if not expected:
        assert 'se instaló correctamente' not in result.stdout
    elif mode == 'required':
        assert 'Autenticación habilitada' in result.stdout
        assert 'no incorpora autenticación' not in result.stdout
    else:
        assert 'no incorpora autenticación' in result.stdout


@pytest.mark.parametrize('status, valid', [('401', True), ('200', False), ('403', False), ('500', False), ('000', False)])
def test_authenticated_health_expects_401_without_creating_a_session(tmp_path, status, valid):
    candidate = tmp_path / 'release'; dist = candidate / 'frontend/dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<script src="/assets/app.js"></script>')
    (dist / 'assets/app.js').write_text('fixture')
    work = tmp_path / 'work'; work.mkdir()
    current = tmp_path / 'current'; current.symlink_to(candidate)
    trace = tmp_path / 'requests'; checks = tmp_path / 'admin-checks'
    result = shell(f'''AUTH_MODE=required; ADMIN_READY=1; HTTP_PORT=8080
RELEASE="{candidate}"; WORK="{work}"; CURRENT_FILE="{current}"
systemctl() {{ :; }}
ss() {{ echo 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*'; }}
run_bootstrap() {{ [[ "$*" == --check ]]; echo CHECK >> "{checks}"; }}
curl() {{
    local url="${{@: -1}}"
    printf '%s\\n' "$*" >> "{trace}"
    case "$url" in
        */health) printf '%s' '{{"status":"ok"}}' ;;
        */api/customers) printf '%s' '{status}' ;;
        */assets/app.js) cat "$RELEASE/frontend/dist/assets/app.js" ;;
        */) cat "$RELEASE/frontend/dist/index.html" ;;
        *) return 99 ;;
    esac
}}
final_checks
echo VERIFIED
''')
    assert (result.returncode == 0) == valid, result.stderr
    assert ('VERIFIED' in result.stdout) == valid
    requests = trace.read_text()
    assert '/api/auth/login' not in requests and 'Authorization' not in requests
    assert '-o /dev/null -w %{http_code}' in requests
    assert not (work / 'customers.json').exists()
    assert checks.exists() == valid


def test_main_bootstrap_is_after_migrations_and_before_starting_services():
    main = (ROOT / 'install.sh').read_text().split('main() {', 1)[1]
    steps = ['validate_release_source "$SOURCE"', 'detect_authentication\n', 'prepare_release\n',
             'initialize_administration\n', 'install_admin_updater\n', 'configure_services\n', 'final_checks\n',
             'state_put phase completa; state_put status complete']
    assert [main.index(step) for step in steps] == sorted(main.index(step) for step in steps)


@pytest.fixture
def blank_database(postgres_engine):
    name = 'installer_bootstrap_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text(f'CREATE DATABASE {name}'))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text(f'DROP DATABASE {name}'))


@pytest.fixture
def real_candidate(tmp_path, blank_database):
    candidate = tmp_path / 'candidate'
    (candidate / '.venv/bin').mkdir(parents=True)
    (candidate / 'src/ticketyn').mkdir(parents=True)
    (candidate / 'src/ticketyn/main.py').write_text('# selects candidate interpreter\n')
    shutil.copy2(ROOT / 'bootstrap-superadmin.sh', candidate)
    for name, executable in [('python', sys.executable), ('alembic', str(ROOT / '.venv/bin/alembic'))]:
        file = candidate / '.venv/bin' / name
        file.write_text('#!/bin/sh\nexec ' + shlex.quote(executable) + ' "$@"\n')
        file.chmod(0o755)
    (candidate / 'alembic.ini').write_text(f'[alembic]\nscript_location = {ROOT}/alembic\n')
    config = tmp_path / 'private.env'
    config.write_text('DATABASE_URL=' + blank_database.url.render_as_string(hide_password=False) + '\n')
    config.chmod(0o600)
    setup = f'AUTH_MODE=required; RELEASE="{candidate}"; ENV_FILE="{config}"\n'
    return candidate, config, setup


def interactive_shell(script, responses):
    master, slave = pty.openpty()
    process = subprocess.Popen(['bash', '-c', 'source "$1"\n' + script, 'test', str(ROOT / 'install.sh')],
                               stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = bytearray(); position = 0; responses = list(responses)
    pipes = [process.stdout, process.stderr]
    deadline = time.monotonic() + 40
    try:
        while pipes:
            if time.monotonic() > deadline:
                raise AssertionError('Timed out waiting for isolated bootstrap prompts')
            readable, _, _ = select.select(pipes, [], [], .1)
            for pipe in readable:
                chunk = os.read(pipe.fileno(), 65536)
                if not chunk:
                    pipes.remove(pipe)
                else:
                    output.extend(chunk)
            if responses and responses[0][0].encode() in output[position:]:
                prompt, value = responses.pop(0)
                position = len(output)
                os.write(master, value.encode() + b'\n')
        return process.wait(timeout=5), output.decode()
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)
        process.stdout.close(); process.stderr.close()
        os.close(slave); os.close(master)


def test_real_migrations_bootstrap_and_reexecution_on_disposable_postgresql(real_candidate, blank_database):
    from ticketyn.models import Responsible
    from ticketyn.security.passwords import verify_password
    candidate, config, setup = real_candidate
    # Actual existing migration path, bound exclusively to the ephemeral DB.
    result = shell(setup + 'verify_database_head')
    assert result.returncode == 0, result.stderr
    with blank_database.connect() as connection:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        expected_head = ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini'))).get_current_head()
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == expected_head
    secret = 'SyntheticInstallerPassword!'  # exclusively an ephemeral test value
    code, output = interactive_shell(setup + 'RELEASE_READY=1\ninitialize_administration\n[[ $ADMIN_READY == 1 ]]', [
        ('Nombre de usuario (login): ', 'installer-admin'),
        ('Nombre completo para el catálogo de responsables', 'Installer Admin'),
        ('Contraseña del superadministrador: ', secret), ('Confirmar contraseña: ', secret),
    ])
    assert code == 0, output
    assert secret not in output and '$argon2' not in output
    with Session(blank_database) as session:
        admin = session.scalar(sql_select(Responsible).where(Responsible.username == 'installer-admin'))
        assert admin.access_granted and not admin.operational_selectable and admin.password_change_required
        assert verify_password(admin.password_hash, secret)
        identity, hashed = admin.id, admin.password_hash
    repeated = shell(setup + 'RELEASE_READY=1\ninitialize_administration\n[[ $ADMIN_READY == 1 ]]')
    assert repeated.returncode == 0, repeated.stderr
    with Session(blank_database) as session:
        assert session.scalar(sql_select(func.count()).select_from(Responsible)) == 1
        assert session.get(Responsible, identity).password_hash == hashed


def test_real_unprepared_database_is_not_initialized(real_candidate, blank_database):
    candidate, config, setup = real_candidate
    result = shell(setup + 'RELEASE_READY=1\ninitialize_administration\necho SERVICES_ALLOWED')
    assert result.returncode != 0
    assert 'Inicialización administrativa pendiente' in result.stderr
    assert 'SERVICES_ALLOWED' not in result.stdout
    assert inspect(blank_database).get_table_names() == []


def test_corrupt_existing_password_cannot_satisfy_initialization(real_candidate, blank_database):
    from ticketyn.models import Responsible
    from ticketyn.models.security import SecurityRole
    candidate, config, setup = real_candidate
    result = shell(setup + 'verify_database_head')
    assert result.returncode == 0, result.stderr
    with Session(blank_database) as session:
        role = session.scalar(sql_select(SecurityRole).where(SecurityRole.code == 'SUPERADMIN'))
        account = Responsible(name='Corrupt fixture', username='corrupt-admin', active=True,
                              access_granted=True, security_role_id=role.id, password_hash='invalid-test-hash')
        session.add(account); session.commit(); identity = account.id
    result = shell(setup + 'RELEASE_READY=1\ninitialize_administration\necho SERVICES_ALLOWED')
    assert result.returncode != 0
    assert 'SERVICES_ALLOWED' not in result.stdout
    with Session(blank_database) as session:
        assert session.get(Responsible, identity).password_hash == 'invalid-test-hash'


def test_real_mismatched_passwords_preserve_database(real_candidate, blank_database):
    from ticketyn.models import Responsible
    candidate, config, setup = real_candidate
    result = shell(setup + 'verify_database_head')
    assert result.returncode == 0, result.stderr
    code, output = interactive_shell(setup + 'RELEASE_READY=1\ninitialize_administration\necho SERVICES_ALLOWED', [
        ('Nombre de usuario (login): ', 'mismatch-admin'),
        ('Nombre completo para el catálogo de responsables', 'Mismatch Admin'),
        ('Contraseña del superadministrador: ', 'synthetic-first-value'),
        ('Confirmar contraseña: ', 'synthetic-second-value'),
    ])
    assert code != 0 and 'Las contraseñas no coinciden' in output
    assert 'SERVICES_ALLOWED' not in output
    assert 'synthetic-first-value' not in output and 'synthetic-second-value' not in output
    with Session(blank_database) as session:
        assert session.scalar(sql_select(func.count()).select_from(Responsible)) == 0


def test_bootstrap_configuration_errors_never_echo_credentials(tmp_path, capsys):
    from ticketyn.security.bootstrap import main
    config = tmp_path / 'private.env'
    secret = 'SYNTHETIC'
    config.write_text(f'DATABASE_URL=postgresql://a:{secret}@b/c\n')
    config.chmod(0o600)
    assert main(['--config', str(config), '--check']) == 2
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
