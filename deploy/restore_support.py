"""Validation/credential helpers for restore.sh; stdlib except active Alembic head."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tomllib
from datetime import datetime
from urllib.parse import urlsplit, unquote

MEMBERS = ('database.dump', 'ticketyn.env', 'metadata.txt', 'MANIFEST.txt', 'SHA256SUMS')
KEYS = {'backup_format', 'created_at_utc', 'completed_dump_at_utc', 'ticketyn_version',
        'expected_git_tag', 'release_name', 'source_release_path', 'pyproject_sha256',
        'database', 'dump_format', 'pg_dump_version', 'server_version', 'encoding',
        'owner', 'alembic_revision'}


class RestoreError(Exception):
    pass


def fail(message):
    raise RestoreError(message)


def config(path):
    text = Path(path).read_text(encoding='utf-8')
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1 or not re.fullmatch(
            r'DATABASE_URL=postgresql\+psycopg://ticketyn:[^@\s]+@127\.0\.0\.1:5432/ticketyn', lines[0]):
        fail('Configuración DATABASE_URL inválida; contenido omitido.')
    url = urlsplit(lines[0].split('=', 1)[1])
    if (url.username, url.hostname, url.port, url.path, url.query, url.fragment) != (
            'ticketyn', '127.0.0.1', 5432, '/ticketyn', '', ''):
        fail('URL PostgreSQL incompatible.')
    raw = url.password
    if raw is None or re.search(r'%(?![0-9a-fA-F]{2})', raw):
        fail('Codificación de contraseña inválida.')
    password = unquote(raw, errors='strict')
    if not password or any(ord(char) < 32 or ord(char) == 127 for char in password):
        fail('Contraseña incompatible con el flujo seguro de psql.')
    return password


def metadata(path):
    result = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if not sep or key in result or key not in KEYS or not value or any(ord(c) < 32 for c in value):
            fail('Metadata inválida o duplicada.')
        result[key] = value
    if result.keys() != KEYS:
        fail('Metadata incompleta.')
    version = result['ticketyn_version']
    if not re.fullmatch(r'\d+\.\d+\.\d+[a-zA-Z0-9.+-]*', version):
        fail('Versión inválida.')
    expected = {'backup_format': 'ticketyn-backup-v1', 'database': 'ticketyn',
                'owner': 'ticketyn', 'encoding': 'UTF8', 'dump_format': 'PostgreSQL custom',
                'expected_git_tag': 'v' + version, 'release_name': version}
    if any(result[key] != value for key, value in expected.items()):
        fail('Metadata incompatible con el formato oficial.')
    if not re.fullmatch('[a-f0-9]{64}', result['pyproject_sha256']) or not re.fullmatch(
            '[A-Za-z0-9_]+', result['alembic_revision']):
        fail('Hash/revisión Alembic inválidos.')
    dates = [datetime.strptime(result[key], '%Y-%m-%dT%H:%M:%SZ') for key in
             ('created_at_utc', 'completed_dump_at_utc')]
    if dates[1] < dates[0]:
        fail('Fechas de metadata incoherentes.')
    source = Path(result['source_release_path'])
    if not source.is_absolute() or '..' in source.parts or source.name != version:
        fail('Ruta informativa de release inválida.')
    if not re.fullmatch(r'pg_dump \(PostgreSQL\) \d+[^\r\n]*', result['pg_dump_version']) or not re.match(
            r'^\d+\.', result['server_version']):
        fail('Versión PostgreSQL inválida.')
    return result


def validate(archive, destination):
    """No extractall: validate all headers first; stream only fixed regular members."""
    source = Path(os.path.abspath(archive))
    for parent in (source, *source.parents):
        if parent.is_symlink():
            fail('Symlink inesperado en la ruta del backup.')
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            fail('El backup debe ser un archivo regular sin hardlinks.')
        with tarfile.open(fileobj=stream, mode='r:') as archive_file:
            entries = []
            for entry in archive_file:
                entries.append(entry)
                if len(entries) > 5:
                    fail('TAR: demasiados componentes.')
            if len(entries) != 5 or {item.name for item in entries} != set(MEMBERS):
                fail('TAR: componentes adicionales, duplicados, ausentes o rutas inesperadas.')
            if any(not item.isreg() or item.linkname or item.pax_headers or item.issparse() for item in entries):
                fail('TAR: tipo, enlace o extensión no permitidos.')
            if any(item.size <= 0 or (item.name != 'database.dump' and item.size > 65536) for item in entries):
                fail('TAR: tamaño de componente inválido.')
            # Reject hidden concatenated archives/data after the end-of-archive marker.
            end = max(item.offset_data + ((item.size + 511) // 512) * 512 for item in entries)
            stream.seek(end)
            while padding := stream.read(1024 * 1024):
                if padding.strip(b'\0'):
                    fail('TAR: datos inesperados después de los componentes.')
            dest = Path(destination)
            dest.mkdir(mode=0o700)
            for item in entries:
                with archive_file.extractfile(item) as incoming, open(dest/item.name, 'xb') as outgoing:
                    os.chmod(dest/item.name, 0o600)
                    while block := incoming.read(1024 * 1024):
                        outgoing.write(block)
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                fail('El backup cambió durante la lectura.')
    sums = (dest/'SHA256SUMS').read_text(encoding='ascii').splitlines()
    expected = {}
    for line in sums:
        match = re.fullmatch(r'([a-f0-9]{64})  (database.dump|ticketyn.env|metadata.txt|MANIFEST.txt)', line)
        if not match or match[2] in expected:
            fail('SHA256SUMS inválido.')
        expected[match[2]] = match[1]
    if set(expected) != set(MEMBERS[:-1]):
        fail('SHA256SUMS incompleto.')
    for name, digest in expected.items():
        with open(dest/name, 'rb') as component:
            if hashlib.file_digest(component, 'sha256').hexdigest() != digest:
                fail('Hash SHA-256 incorrecto: ' + name)
    config(dest/'ticketyn.env')
    metadata(dest/'metadata.txt')


def compatibility(content, release, head, server_number, client_version):
    data = metadata(Path(content)/'metadata.txt')
    project = Path(release)/'pyproject.toml'
    # Legacy releases retain pyproject identity; updated releases carry SemVer identity.
    import importlib.util
    spec = importlib.util.spec_from_file_location('release_identity', Path(__file__).with_name('release_identity.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    version = module.identity(release)
    if data['ticketyn_version'] != version or data['release_name'] != Path(release).name:
        fail('Versión/release incompatible.')
    if hashlib.sha256(project.read_bytes()).hexdigest() != data['pyproject_sha256']:
        fail('La metadata del release activo no coincide exactamente.')
    if data['alembic_revision'] != head:
        fail('Revisión Alembic incompatible.')
    major = int(server_number) // 10000
    dump_major = int(re.search(r'\) (\d+)', data['pg_dump_version'])[1])
    client_major = int(re.search(r'\) (\d+)', client_version)[1])
    if major != int(data['server_version'].split('.')[0]) or dump_major != major or client_major != major:
        fail('Se requiere la misma versión mayor de PostgreSQL y herramientas cliente.')


def head(release):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(Path(release)/'alembic.ini'))
    cfg.set_main_option('script_location', str(Path(release)/'alembic'))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1 or not re.fullmatch('[A-Za-z0-9_]+', heads[0]):
        fail('HEAD Alembic ambiguo.')
    print(heads[0])


def password(path):
    secret = config(path)
    # psql \password generates SCRAM client-side; stdin only, detached from TTY.
    command = ['runuser', '-u', 'postgres', '--', 'setsid', '--wait', 'psql', '-X',
               '-h', '/var/run/postgresql', '-p', '5432', '-U', 'postgres',
               '--no-password', '--set=ON_ERROR_STOP=1', '-q', '-c', r'\password ticketyn', 'postgres']
    env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/nonexistent',
           'PGPASSFILE': '/dev/null', 'PGOPTIONS': '-c password_encryption=scram-sha-256 '
           '-c log_statement=none -c log_min_duration_statement=-1 -c log_min_duration_sample=-1 '
           '-c log_transaction_sample_rate=0 -c log_min_error_statement=panic'}
    subprocess.run(command, input=secret + '\n' + secret + '\n', text=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def http_valid(path, kind):
    data = json.loads(Path(path).read_text())
    if (kind == 'health' and data != {'status': 'ok'}) or (kind == 'api' and not isinstance(data, list)):
        fail('Respuesta HTTP inesperada.')


def port(path):
    text = Path(path).read_text()
    ports = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if 'listen' in line:
            match = re.fullmatch(r'listen (\d+);', line)
            if not match or not 1 <= int(match[1]) <= 65535:
                fail('No se puede determinar con seguridad el puerto HTTP de Ticketyn.')
            ports.append(match[1])
    if len(ports) != 1:
        fail('Se requiere un único listen IPv4 del sitio Ticketyn instalado.')
    print(ports[0])



# Files below are under root-only restore-state; no source/eval of their contents.
PROGRESS_KEYS = {'phase', 'operation', 'staging_database', 'previous_database',
                 'original_oid', 'staging_oid', 'safety_backup'}
STATE_REQUIRED = {'progress.txt', 'previous.env', 'source-metadata.txt', 'RECUPERACION.txt'}
STATE_ALLOWED = STATE_REQUIRED | {'diagnostic.log', 'state-format', 'completion.json', 'finalize-intent.json'}


def private_path(path, directory=False):
    path = Path(path)
    info = path.lstat()
    # Main requires root. Test helpers can validate isolated files owned by their EUID.
    uid, gid = (0, 0) if os.geteuid() == 0 else (os.geteuid(), os.getegid())
    if (info.st_uid, info.st_gid) != (uid, gid) or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
        fail('Propietario/permisos del estado privado inesperados.')
    if (directory and not stat.S_ISDIR(info.st_mode)) or (
            not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
        fail('Tipo/enlace del estado privado inesperado.')
    return info


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def progress(state):
    private_path(state, True)
    files = {path.name for path in Path(state).iterdir()}
    if not STATE_REQUIRED <= files or not files <= STATE_ALLOWED:
        fail('Estado incompleto o con archivos inesperados.')
    for name in files:
        private_path(Path(state)/name)
    values = {}
    for line in (Path(state)/'progress.txt').read_text().splitlines():
        key, sep, value = line.partition('=')
        if not sep or key in values or key not in PROGRESS_KEYS:
            fail('Progress inválido/duplicado.')
        values[key] = value
    if values.keys() != PROGRESS_KEYS or values['phase'] != 'completado':
        fail('La restauración no está completada correctamente.')
    token = values['operation']
    if not re.fullmatch('[a-f0-9]{32}', token) or (
            values['staging_database'], values['previous_database']) != (
            'ticketyn_restore_' + token, 'ticketyn_previous_' + token):
        fail('Identidad/nombres de operación inconsistentes.')
    for key in ('original_oid', 'staging_oid'):
        oid = values[key]
        if key == 'original_oid' and not oid:
            continue
        if not re.fullmatch('[1-9][0-9]{0,9}', oid) or int(oid) > 4294967295:
            fail('OID de operación inválido.')
    if values['original_oid'] == values['staging_oid']:
        fail('DB anterior y activa tienen el mismo OID.')
    if bool(values['original_oid']) != bool(values['safety_backup']):
        fail('Backup previo/DB original inconsistentes.')
    return values


def completion_data(state, configuration, release, cluster):
    if not re.fullmatch('[1-9][0-9]{0,19}', cluster):
        fail('Identidad de clúster inválida.')
    values = progress(state)
    return {'format': 'ticketyn-restore-completion-v1', 'operation': values['operation'],
            'cluster_id': cluster, 'release': str(Path(release).resolve()),
            'pyproject_sha256': digest(Path(release)/'pyproject.toml'),
            'configuration_sha256': digest(configuration),
            'state_hashes': {name: digest(Path(state)/name) for name in sorted(STATE_REQUIRED)}}


def exclusive_json(path, value):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '-' + os.urandom(8).hex())
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        rename_exclusive(temporary, path)  # atomic, exclusive, always one link
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def completion(state, configuration, release, cluster):
    if (Path(state)/'state-format').read_text() != 'ticketyn-restore-state-v2\n':
        fail('Formato de estado nuevo inválido.')
    exclusive_json(Path(state)/'completion.json', completion_data(state, configuration, release, cluster))


def finalize_snapshot(state, configuration, release, cluster, safety_dir, output):
    values = progress(state)
    info = metadata(Path(state)/'source-metadata.txt')
    expected = completion_data(state, configuration, release, cluster)
    marker = Path(state)/'state-format'
    receipt = Path(state)/'completion.json'
    if marker.exists():
        if marker.read_text() != 'ticketyn-restore-state-v2\n' or not receipt.exists():
            fail('Falta comprobante de finalización exitosa.')
    if receipt.exists() and json.loads(receipt.read_text()) != expected:
        fail('El estado, configuración, release o clúster fueron modificados.')
    # Legacy state: cross-check the independently recorded recovery document.
    recovery = (Path(state)/'RECUPERACION.txt').read_text()
    for line in (f"Operación: {values['operation']}", f"DB original OID: {values['original_oid']}",
                 f"DB original conservada tras cutover: {values['previous_database']} (conexiones deshabilitadas)",
                 f"DB preparada: {values['staging_database']}"):
        if recovery.splitlines().count(line) != 1:
            fail('Documento de recuperación inconsistente.')
    backup = values['safety_backup']
    backup_hash = ''
    if backup:
        path = Path(backup)
        if path.parent != Path(safety_dir) or path.suffix != '.tar':
            fail('Ruta del backup de seguridad inválida.')
        private_path(path.parent, True)
        private_path(path)
        backup_hash = digest(path)
        if recovery.splitlines().count('Backup de seguridad: ' + backup) != 1:
            fail('Backup de seguridad distinto al registrado.')
    snapshot = {'format': 'ticketyn-finalize-intent-v1', **values,
                'metadata': info, 'completion': expected, 'safety_backup_sha256': backup_hash,
                'legacy': not receipt.exists()}
    snapshot['state_fingerprint'] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    intent = Path(state)/'finalize-intent.json'
    if intent.exists():
        recorded = json.loads(intent.read_text())
        if set(recorded) != {'snapshot', 'confirmed_at_utc'} or recorded['snapshot'] != snapshot:
            fail('Intención de finalización no coincide con el estado validado.')
        datetime.strptime(recorded['confirmed_at_utc'], '%Y-%m-%dT%H:%M:%SZ')
    # Fixed, validated strings only. Shell reads lines, never evaluates them.
    Path(output).write_text('\n'.join([values['operation'], values['previous_database'],
                                     values['original_oid'], values['staging_oid'], backup]) + '\n')
    Path(output + '.json').write_text(json.dumps(snapshot, sort_keys=True))


def finalize_intent(state, snapshot_file):
    path = Path(state)/'finalize-intent.json'
    snapshot = json.loads(Path(snapshot_file).read_text())
    if not path.exists():
        exclusive_json(path, {'snapshot': snapshot, 'confirmed_at_utc': datetime.now(
            __import__('datetime').timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')})
    elif json.loads(path.read_text())['snapshot'] != snapshot:
        fail('Intención existente distinta; no se reemplaza.')


def rename_exclusive(source, destination):
    # Debian/Ubuntu Linux: atomic rename with RENAME_NOREPLACE (no destination overwrite).
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        fail('El sistema no soporta rename exclusivo; cierre rechazado.')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result != 0:
        raise OSError(ctypes.get_errno(), 'No se pudo archivar el estado de forma exclusiva.')


def final_record(snapshot, recorded):
    return {'format': 'ticketyn-restore-finalized-v1', 'operation': snapshot['operation'],
            'active_database': 'ticketyn', 'active_oid': snapshot['staging_oid'],
            'deleted_previous_database': snapshot['previous_database'] if snapshot['original_oid'] else '',
            'deleted_previous_oid': snapshot['original_oid'], 'cluster_id': snapshot['completion']['cluster_id'],
            'release': snapshot['completion']['release'], 'alembic_revision': snapshot['metadata']['alembic_revision'],
            'safety_backup': snapshot['safety_backup'], 'safety_backup_sha256': snapshot['safety_backup_sha256'],
            'confirmed_at_utc': recorded['confirmed_at_utc'], 'state_fingerprint': snapshot['state_fingerprint']}


def finalize_history_validate(state, snapshot_file, history):
    history = Path(history)
    if not history.exists() and not history.is_symlink():
        return
    private_path(history, True)
    snapshot = json.loads(Path(snapshot_file).read_text())
    token = snapshot['operation']
    pending = history/(token + '.pending')
    if pending.exists() or pending.is_symlink():
        fail('Existe un archivo de estado pendiente; requiere revisión manual.')
    target = history/(token + '.json')
    if target.exists() or target.is_symlink():
        private_path(target)
        intent = Path(state)/'finalize-intent.json'
        if not intent.exists():
            fail('Registro final preexistente sin intención de esta operación.')
        private_path(intent)
        if json.loads(target.read_text()) != final_record(snapshot, json.loads(intent.read_text())):
            fail('Registro final existente distinto; no se reemplaza.')


def finalize_archive(state, snapshot_file, history):
    state = Path(state); history = Path(history)
    private_path(state, True)
    snapshot = json.loads(Path(snapshot_file).read_text())
    intent = state/'finalize-intent.json'
    private_path(intent)
    recorded = json.loads(intent.read_text())
    if recorded['snapshot'] != snapshot:
        fail('Estado/intención cambiaron antes de archivar.')
    if not history.exists():
        history.mkdir(mode=0o700)
        sync_directory(history.parent)
    private_path(history, True)
    token = snapshot['operation']
    record = final_record(snapshot, recorded)
    target = history/(token + '.json')
    if target.exists() or target.is_symlink():
        private_path(target)
        if json.loads(target.read_text()) != record:
            fail('Registro final existente distinto; no se reemplaza.')
    else:
        exclusive_json(target, record)
    pending = history/(token + '.pending')
    files = list(state.iterdir())
    if {path.name for path in files} - STATE_ALLOWED:
        fail('No se archiva un estado con archivos desconocidos.')
    for path in files:
        private_path(path)
    rename_exclusive(state, pending)
    sync_directory(history); sync_directory(state.parent)
    # No recursive delete; only the verified files of our renamed private directory.
    for path in files:
        (pending/path.name).unlink()
    pending.rmdir()
    sync_directory(history)
    print(str(target))


if __name__ == '__main__':
    try:
        operations = {'validate': validate, 'compatibility': compatibility, 'head': head,
                      'password': password, 'http-valid': http_valid, 'port': port,
                      'completion': completion, 'finalize-snapshot': finalize_snapshot,
                      'finalize-intent': finalize_intent, 'finalize-archive': finalize_archive,
                      'finalize-history-validate': finalize_history_validate}
        operations[sys.argv[1]](*sys.argv[2:])
    except RestoreError as error:
        print('Error: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except (ValueError, OSError, KeyError, UnicodeError, tarfile.TarError, subprocess.CalledProcessError):
        # Exception messages may contain URL/password or untrusted archive names.
        print('Error: validación/operación de restore rechazada (' + sys.argv[1] + '); contenido sensible omitido.', file=sys.stderr)
        sys.exit(1)
