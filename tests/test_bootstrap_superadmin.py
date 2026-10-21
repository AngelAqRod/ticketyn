"""Automated tests for Ticketyn v0.7.0 superadmin bootstrap infrastructure.

Covers all 10 required scenarios from specification Section 6:
  1. Ausencia de superadmin: permite inicialización.
  2. Superadmin válido existente: no realiza cambios.
  3. Segunda ejecución: no duplica registros (idempotencia).
  4. Responsable histórico con otro rol: no altera sus permisos ni contraseñas.
  5. Usuario duplicado: rechaza la operación de forma segura.
  6. Contraseñas no coincidentes: no crea registros.
  7. Error de base de datos: no deja datos parciales (rollback transaccional).
  8. Nuevo superadmin: activo, rol correcto, hash válido y operational_selectable = false.
  9. Estados administrativos inconsistentes: no aplica reparaciones automáticas.
 10. Ejecución concurrente: evita inicializaciones duplicadas por condición de carrera.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import subprocess
import sys
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from ticketyn.models import Responsible
from ticketyn.models.security import SecurityConfig, SecurityRole, SecurityAudit
from ticketyn.security.bootstrap import (
    SuperadminStatus,
    inspect_superadmin_status,
    create_superadmin,
    interactive_bootstrap,
    check_status_cli,
    main as bootstrap_main,
    settings_from_file,
)
from ticketyn.security.passwords import hash_password, verify_password
from ticketyn.security.service import principal, seed_foundation


@pytest.fixture
def disposable_db(postgres_engine):
    """Creates a fresh, isolated database per test to ensure pristine security state."""
    db_name = f'bs_test_{uuid4().hex}'
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.execute(text(f'CREATE DATABASE {db_name}'))

    engine = create_engine(postgres_engine.url.set(database=db_name), pool_pre_ping=True)
    from ticketyn.db.base import Base
    from ticketyn import models  # noqa: F401
    Base.metadata.create_all(engine)

    try:
        yield engine
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.execute(text(f'DROP DATABASE {db_name}'))


@pytest.fixture
def env_config(tmp_path, disposable_db):
    """Generates a private 0600 environment file pointing to the disposable DB."""
    cfg = tmp_path / 'ticketyn_test.env'
    cfg.write_text(f'DATABASE_URL={disposable_db.url.render_as_string(hide_password=False)}\n')
    cfg.chmod(0o600)
    return str(cfg)


# ==============================================================================
# Test 1: Ausencia de superadmin: permite inicialización
# ==============================================================================
def test_01_absence_of_superadmin_allows_initialization(disposable_db):
    with Session(disposable_db) as session:
        seed_foundation(session)
        report = inspect_superadmin_status(session)
        assert report.status == SuperadminStatus.NONE_EXIST
        assert len(report.valid_superadmins) == 0

        admin, created = create_superadmin(
            session,
            username='admin_initial',
            password='InitialPassword123!',
            responsible_name='Admin Inicial',
            source='CLI test',
        )
        session.commit()
        assert created is True
        assert admin.id is not None
        assert admin.username == 'admin_initial'

        p = principal(session, admin.id)
        assert p is not None
        assert p.role == 'SUPERADMIN'


# ==============================================================================
# Test 2: Superadmin válido existente: no realiza cambios
# ==============================================================================
def test_02_valid_existing_superadmin_makes_no_changes(disposable_db, capsys):
    with Session(disposable_db) as session:
        seed_foundation(session)
        admin1, _ = create_superadmin(
            session,
            username='existing_super',
            password='FirstPassword123!',
            responsible_name='Super Existente',
        )
        session.commit()
        admin1_id = admin1.id
        admin1_hash = admin1.password_hash
        admin1_revision = admin1.access_revision

    # Running interactive bootstrap when already satisfied
    with Session(disposable_db) as session:
        code = interactive_bootstrap(session)
        session.commit()
        assert code == 0

    with Session(disposable_db) as session:
        report = inspect_superadmin_status(session)
        assert report.status == SuperadminStatus.VALID_EXISTS
        assert len(report.valid_superadmins) == 1

        admin = session.get(Responsible, admin1_id)
        assert admin.password_hash == admin1_hash
        assert admin.access_revision == admin1_revision
        assert admin.username == 'existing_super'

    captured = capsys.readouterr()
    assert 'INICIALIZACIÓN ADMINISTRATIVA: Ya satisfecha' in captured.out


# ==============================================================================
# Test 3: Segunda ejecución: no duplica registros (idempotencia)
# ==============================================================================
def test_03_second_execution_does_not_duplicate_records(env_config, disposable_db, monkeypatch):
    # First execution via main
    monkeypatch.setattr('ticketyn.security.bootstrap.getpass.getpass', lambda *_: 'SafePassword123!')
    code1 = bootstrap_main(['--config', env_config, '--username', 'super1', '--name', 'Super Uno'])
    assert code1 == 0

    with Session(disposable_db) as session:
        count1 = session.scalar(select(func.count(Responsible.id)))
        assert count1 == 1

    # Second execution via main (no username passed, already exists)
    code2 = bootstrap_main(['--config', env_config])
    assert code2 == 0

    with Session(disposable_db) as session:
        count2 = session.scalar(select(func.count(Responsible.id)))
        assert count2 == 1  # No duplicate created!


# ==============================================================================
# Test 4: Responsable histórico con otro rol: no altera sus permisos
# ==============================================================================
def test_04_historical_responsible_with_other_role_is_not_altered(disposable_db):
    with Session(disposable_db) as session:
        seed_foundation(session)
        operator_role = session.scalar(select(SecurityRole).where(SecurityRole.code == 'OPERATOR'))

        # Historical operator
        hist_op = Responsible(
            name='Operador Historico',
            username='op_historico',
            password_hash=hash_password('OperatorSecret123!'),
            security_role_id=operator_role.id,
            active=True,
            access_granted=True,
            operational_selectable=True,
        )
        # Historical uncredentialed responsible
        hist_clean = Responsible(
            name='Tecnico Historico',
            active=True,
            access_granted=False,
            operational_selectable=True,
        )
        session.add_all([hist_op, hist_clean])
        session.commit()
        hist_op_id = hist_op.id
        hist_clean_id = hist_clean.id
        hist_op_hash = hist_op.password_hash

    # Now run bootstrap
    with Session(disposable_db) as session:
        admin, created = create_superadmin(
            session,
            username='brand_new_admin',
            password='NewAdminPassword123!',
            responsible_name='Super Nuevo',
        )
        session.commit()
        assert created is True

    # Verify historical responsibles remain completely untouched
    with Session(disposable_db) as session:
        op = session.get(Responsible, hist_op_id)
        assert op.name == 'Operador Historico'
        assert op.username == 'op_historico'
        assert op.password_hash == hist_op_hash
        assert session.get(SecurityRole, op.security_role_id).code == 'OPERATOR'
        assert op.operational_selectable is True
        assert op.active is True
        assert op.access_granted is True

        clean = session.get(Responsible, hist_clean_id)
        assert clean.name == 'Tecnico Historico'
        assert clean.username is None
        assert clean.password_hash is None
        assert clean.security_role_id is None
        assert clean.access_granted is False
        assert clean.operational_selectable is True


# ==============================================================================
# Test 5: Usuario duplicado: rechaza la operación de forma segura
# ==============================================================================
def test_05_duplicate_username_is_safely_rejected(disposable_db):
    with Session(disposable_db) as session:
        seed_foundation(session)
        existing = Responsible(
            name='Usuario Existente',
            username='carlos',
            active=True,
            operational_selectable=True,
        )
        session.add(existing)
        session.commit()

    with Session(disposable_db) as session:
        with pytest.raises(ValueError, match='ya está reservado o en uso'):
            create_superadmin(
                session,
                username='carlos',  # Same username
                password='Password123!',
                responsible_name='Super Admin',
            )
        session.rollback()

    # Case-insensitive collation test
    with Session(disposable_db) as session:
        with pytest.raises(ValueError, match='ya está reservado o en uso'):
            create_superadmin(
                session,
                username='CARLOS',  # Uppercase collision
                password='Password123!',
                responsible_name='Super Admin 2',
            )
        session.rollback()

        # Ensure no superadmin was created
        report = inspect_superadmin_status(session)
        assert report.status == SuperadminStatus.NONE_EXIST


# ==============================================================================
# Test 6: Contraseñas no coincidentes: no crea registros
# ==============================================================================
def test_06_mismatched_passwords_creates_no_records(disposable_db, monkeypatch, capsys):
    with Session(disposable_db) as session:
        seed_foundation(session)

    # Mock mismatched passwords
    inputs = ['PasswordAAA123!', 'PasswordBBB123!']
    monkeypatch.setattr('ticketyn.security.bootstrap.getpass.getpass', lambda *_: inputs.pop(0))

    with Session(disposable_db) as session:
        code = interactive_bootstrap(session, pre_username='admin_test', pre_name='Admin Test')
        session.commit()
        assert code == 1

    captured = capsys.readouterr()
    assert 'Las contraseñas no coinciden' in captured.err

    with Session(disposable_db) as session:
        count = session.scalar(select(func.count(Responsible.id)))
        assert count == 0


# ==============================================================================
# Test 7: Error de base de datos: no deja datos parciales
# ==============================================================================
def test_07_database_error_leaves_no_partial_data(disposable_db):
    with Session(disposable_db) as session:
        seed_foundation(session)

    with Session(disposable_db) as session:
        with patch('ticketyn.security.bootstrap.audit', side_effect=RuntimeError('Simulated audit failure')):
            with pytest.raises(RuntimeError):
                create_superadmin(
                    session,
                    username='partial_admin',
                    password='Password123!',
                    responsible_name='Partial Admin',
                )
            session.rollback()

    # Verify no records or half-created accounts exist
    with Session(disposable_db) as session:
        report = inspect_superadmin_status(session)
        assert report.status == SuperadminStatus.NONE_EXIST
        assert session.scalar(select(func.count(Responsible.id))) == 0


# ==============================================================================
# Test 8: Nuevo superadmin: activo, rol correcto, hash válido y operational_selectable = false
# ==============================================================================
def test_08_new_superadmin_attributes_and_auth(disposable_db):
    raw_password = 'CorrectHorseBatteryStaple99!'
    with Session(disposable_db) as session:
        seed_foundation(session)
        admin, created = create_superadmin(
            session,
            username='sec_admin',
            password=raw_password,
            responsible_name='Seguridad Principal',
        )
        session.commit()
        admin_id = admin.id

    with Session(disposable_db) as session:
        admin = session.get(Responsible, admin_id)
        assert admin is not None
        assert admin.active is True
        assert admin.access_granted is True
        assert admin.operational_selectable is False
        assert admin.password_change_required is True
        assert session.get(SecurityRole, admin.security_role_id).code == 'SUPERADMIN'
        assert admin.username == 'sec_admin'
        assert admin.name == 'Seguridad Principal'

        # Verify Argon2id hash validity
        assert verify_password(admin.password_hash, raw_password) is True
        assert verify_password(admin.password_hash, 'WrongPassword!') is False

        # Verify principal authentication capability
        p = principal(session, admin_id)
        assert p is not None
        assert p.username == 'sec_admin'
        assert p.role == 'SUPERADMIN'
        assert 'accounts.manage' in p.permissions
        assert 'roles.manage' in p.permissions


# ==============================================================================
# Test 9: Estados administrativos inconsistentes: no aplica reparaciones automáticas
# ==============================================================================
def test_09_inconsistent_administrative_state_does_not_auto_repair(disposable_db, capsys):
    with Session(disposable_db) as session:
        seed_foundation(session)
        role = session.scalar(select(SecurityRole).where(SecurityRole.code == 'SUPERADMIN'))

        # Inconsistent record: superadmin role but inactive and without password/username
        corrupt = Responsible(
            name='Corrupt Admin',
            security_role_id=role.id,
            active=False,
            access_granted=False,
            password_hash=None,
            username=None,
            operational_selectable=False,
        )
        session.add(corrupt)
        session.commit()
        corrupt_id = corrupt.id

    with Session(disposable_db) as session:
        report = inspect_superadmin_status(session)
        assert report.status == SuperadminStatus.INCONSISTENT
        assert len(report.inconsistent_records) == 1
        assert len(report.valid_superadmins) == 0

        # Run interactive bootstrap
        code = interactive_bootstrap(session)
        session.commit()
        assert code == 1

    captured = capsys.readouterr()
    assert 'ERROR: ESTADO ADMINISTRATIVO INCONSISTENTE DETECTADO' in captured.err
    assert 'No se aplicaron modificaciones automáticas' in captured.err

    # Verify the corrupt record was NOT automatically modified or repaired
    with Session(disposable_db) as session:
        rec = session.get(Responsible, corrupt_id)
        assert rec.active is False
        assert rec.access_granted is False
        assert rec.password_hash is None
        assert rec.username is None


# ==============================================================================
# Test 10: Ejecución concurrente: evita inicializaciones duplicadas
# ==============================================================================
def test_10_concurrent_execution_prevents_duplicate_initializations(disposable_db):
    with Session(disposable_db) as session:
        seed_foundation(session)

    results = []

    def run_bootstrap_task(worker_id):
        # Each thread uses its own distinct Session
        with Session(disposable_db) as session:
            try:
                admin, created = create_superadmin(
                    session,
                    username=f'admin_worker_{worker_id}',
                    password='ConcurrentPassword123!',
                    responsible_name=f'Admin Worker {worker_id}',
                    source=f'thread-{worker_id}',
                )
                session.commit()
                return (worker_id, True, admin.id, created)
            except Exception as e:
                session.rollback()
                return (worker_id, False, str(e), False)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_bootstrap_task, i) for i in range(4)]
        results = [f.result() for f in futures]

    # Verify that all threads succeeded cleanly
    assert all(r[1] is True for r in results)

    # Exactly one thread created the superadmin, the others detected it was satisfied
    created_count = sum(1 for r in results if r[3] is True)
    assert created_count == 1

    # Verify DB has exactly ONE superadmin
    with Session(disposable_db) as session:
        report = inspect_superadmin_status(session)
        assert report.status == SuperadminStatus.VALID_EXISTS
        assert len(report.valid_superadmins) == 1
        count = session.scalar(select(func.count(Responsible.id)))
        assert count == 1


# ==============================================================================
# Test 11: End-to-end integration via bootstrap-superadmin.sh
# ==============================================================================
def test_11_shell_script_end_to_end(env_config, disposable_db):
    script_path = Path(__file__).resolve().parents[1] / 'bootstrap-superadmin.sh'
    assert script_path.is_file()

    # 1. Run --check when none exists -> exit code 3
    proc_check_none = subprocess.run(
        [str(script_path), '--config', env_config, '--check'],
        capture_output=True,
        text=True,
    )
    assert proc_check_none.returncode == 3
    assert 'No existe un superadministrador' in proc_check_none.stdout

    # 2. Run interactive creation providing input via stdin
    input_data = "admin_sh\nSuper Bash\nShSecretPassword123!\nShSecretPassword123!\n"
    proc_create = subprocess.run(
        [str(script_path), '--config', env_config],
        input=input_data,
        capture_output=True,
        text=True,
    )
    assert proc_create.returncode == 0
    assert 'SUPERADMINISTRADOR INICIAL CREADO EXITOSAMENTE' in proc_create.stdout
    assert 'admin_sh' in proc_create.stdout

    # 3. Run --check now -> exit code 0
    proc_check_ok = subprocess.run(
        [str(script_path), '--config', env_config, '--check'],
        capture_output=True,
        text=True,
    )
    assert proc_check_ok.returncode == 0
    assert 'Superadministrador válido y operativo presente' in proc_check_ok.stdout

    # 4. Run script again -> exit code 0 (already satisfied)
    proc_repeat = subprocess.run(
        [str(script_path), '--config', env_config],
        capture_output=True,
        text=True,
    )
    assert proc_repeat.returncode == 0
    assert 'INICIALIZACIÓN ADMINISTRATIVA: Ya satisfecha' in proc_repeat.stdout
