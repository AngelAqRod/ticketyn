"""Conservative production updater. Tests inject paths/commands, never host services."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ri = load('release_identity')
rs = load('restore_support')
ORIGIN = 'https://github.com/AngelAqRod/ticketyn.git'
FILES = ('pyproject.toml', 'requirements.lock', 'LICENSE', 'README.md', 'alembic.ini')
TREES = ('src', 'alembic', 'deploy', 'frontend/dist')
MAINTENANCE = ('backup.sh', 'restore.sh', 'update.sh', 'deploy/restore_support.py', 'deploy/release_identity.py', 'deploy/update_support.py')
PHASES = ('preparing', 'backup', 'prepared', 'stopping', 'migrating', 'migrated', 'activating', 'starting', 'checking', 'complete')
SAFE_RETRY = ('preparing', 'backup', 'prepared', 'stopping')


class UpdateError(Exception):
    pass


def fail(message):
    raise UpdateError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def secure(path, directory=False, private=False):
    path = Path(path)
    if any(parent.is_symlink() for parent in path.parents):
        fail('Symlink inesperado en ruta: '+str(path))
    info = path.lstat()
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or info.st_uid != os.geteuid() or info.st_gid != os.getegid()
            or info.st_mode & 0o022 or (not directory and info.st_nlink != 1)
            or (private and stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600))):
        fail('Propietario, permisos o tipo inseguros: '+str(path))
    return info


def stamp(path):
    info = Path(path).lstat()
    return [info.st_dev, info.st_ino]


def write_json(path, value, exclusive=False):
    path = Path(path)
    temporary = path.parent/('.write-'+secrets.token_hex(16))
    try:
        with open(temporary, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        if exclusive:
            rs.rename_exclusive(temporary, path)
        else:
            secure(path, private=True)
            os.replace(temporary, path)
        rs.sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def exchange(left, right):
    import ctypes
    library = ctypes.CDLL(None, use_errno=True)
    rename = library.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(left), -100, os.fsencode(right), 2):
        raise OSError(ctypes.get_errno(), 'No se pudo intercambiar current atómicamente.')


def switch_current(current, target, previous, expected_inode, temporary):
    if not current.is_symlink() or stamp(current) != expected_inode or current.resolve() != previous:
        fail('current cambió antes de activación.')
    os.symlink(target, temporary)  # exclusive; never unlink an unexpected destination
    new_inode = stamp(temporary)
    exchange(temporary, current)
    if not temporary.is_symlink() or stamp(temporary) != expected_inode or temporary.resolve() != previous:
        # Exchange preserves the unexpected object instead of overwriting/deleting it.
        if current.is_symlink() and stamp(current) == new_inode:
            exchange(temporary, current)
            if temporary.is_symlink() and stamp(temporary) == new_inode:
                temporary.unlink()
        fail('current cambió concurrentemente; objeto original conservado.')
    temporary.unlink()  # only the verified old symlink; both releases remain
    rs.sync_directory(current.parent)


def tag_version(tag):
    if not isinstance(tag, str) or not tag.startswith('v'):
        fail('Se requiere un tag explícito vX.Y.Z.')
    try:
        ri.semver(tag[1:])
    except ValueError as error:
        fail(str(error))
    return tag[1:]


def forward(source, target):
    if ri.compare(target, source) <= 0:
        fail('Solo se permiten forward upgrades: misma versión y downgrade rechazados.')
    if ri.semver(source)[0][0] != ri.semver(target)[0][0]:
        fail('Cambio de versión mayor no soportado por esta primera implementación.')


def selected(name):
    return name in FILES or any(name == t or name.startswith(t+'/') for t in TREES) or name in ('install.sh', 'backup.sh', 'restore.sh', 'update.sh')


def extract_release(archive, destination):
    """Positive allowlist; never extractall. All selected entries must be ordinary."""
    seen = set()
    with tarfile.open(archive) as source:
        for member in source:
            name = member.name.rstrip('/')
            if name.startswith('/') or '..' in name.split('/') or '\\' in name or '\x00' in name:
                fail('Ruta insegura en release.')
            if not selected(name):
                continue
            parts = name.split('/')
            sensitive = any(p == '.git' or p.startswith('.env') or p in ('node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') or p.endswith(('.egg-info', '.pyc')) for p in parts)
            if sensitive or re.search(r'(?i)(\.key|\.pem|\.p12|\.pfx|\.dump|\.sql|\.sql\.gz|\.bak|\.backup|\.pgdump)$', name) or any(p in ('id_rsa', 'id_ed25519', 'backups') for p in parts):
                fail('Contenido sensible/no permitido: '+name)
            if name in seen or not (member.isfile() or member.isdir()) or member.issparse():
                fail('Tipo/enlace/entrada duplicada no permitida: '+name)
            seen.add(name)
            target = Path(destination)/name
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with source.extractfile(member) as stream, open(target, 'xb') as output:
                    shutil.copyfileobj(stream, output)
                target.chmod(0o700 if member.mode & 0o111 else 0o600)
                if (b'PRIVATE KEY' + b'-----') in target.read_bytes():
                    fail('Posible clave privada en '+name)
    for name in FILES+MAINTENANCE+('frontend/dist/index.html', 'src/ticketyn/main.py', 'alembic/env.py', 'deploy/systemd/ticketyn.service', 'deploy/nginx/ticketyn.conf'):
        if not (Path(destination)/name).is_file():
            fail('Falta contenido requerido: '+name)
    assets(Path(destination))


def assets(release):
    paths = re.findall(r'/assets/[^"<>\s]+', (release/'frontend/dist/index.html').read_text())
    if not paths:
        fail('Frontend sin assets compilados.')
    for path in paths:
        if '..' in path or not (release/'frontend/dist'/path.lstrip('/')).is_file():
            fail('Asset frontend ausente o inválido.')
    return paths


def migration_plan(old, new, current):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    def scripts(path):
        cfg = Config(str(Path(path)/'alembic.ini'))
        cfg.set_main_option('script_location', str(Path(path)/'alembic'))
        return ScriptDirectory.from_config(cfg)
    previous, target = scripts(old), scripts(new)
    if previous.get_heads() != [current] or len(target.get_heads()) != 1:
        fail('Alembic actual/HEAD ambiguo o incompatible.')
    # Immutable baseline, including env.py: do not silently reinterpret applied revisions.
    for path in (Path(old)/'alembic').rglob('*.py'):
        counterpart = Path(new)/path.relative_to(old)
        if not counterpart.is_file() or digest(path) != digest(counterpart):
            fail('Una migración/env.py aplicada fue modificada; requiere revisión manual.')
    head = target.get_heads()[0]
    revisions = list(target.walk_revisions())
    if any(r.branch_labels or r.dependencies or isinstance(r.down_revision, tuple) for r in revisions):
        fail('Solo se soporta una cadena Alembic lineal sin ramas/dependencias.')
    ancestry = {r.revision for r in revisions}
    if current not in ancestry or len(target.get_bases()) != 1:
        fail('La revisión origen no pertenece a la cadena destino.')
    return head


class Updater:
    def __init__(self, tag, base='/opt/ticketyn', config='/etc/ticketyn', backups='/var/backups/ticketyn', lock='/run/ticketyn-install.lock'):
        self.tag, self.version = tag, tag_version(tag)
        self.base, self.config, self.backups, self.lock_path = map(Path, (base, config, backups, lock))
        self.current = self.base/'current'; self.releases = self.base/'releases'
        self.env = self.config/'ticketyn.env'; self.state = self.config/'update-state'
        self.unit = Path('/etc/systemd/system/ticketyn.service')
        self.site = Path('/etc/nginx/sites-available/ticketyn')
        self.link = Path('/etc/nginx/sites-enabled/ticketyn')
        self.data = None; self.work = None; self.lock_fd = None; self.authorized = False
        self.scripts = Path(__file__).resolve().parent.parent

    def run(self, args, **kwargs):
        # No inherited Git/Pip credential/config/trace variables. No secrets in argv.
        environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': str(self.work or '/nonexistent'), 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0', 'PIP_CONFIG_FILE': '/dev/null', 'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        try:
            result = subprocess.run([str(a) for a in args], check=True, capture_output=True, text=not kwargs.pop('binary', False), env=environment, pass_fds=(self.lock_fd,) if self.lock_fd is not None else (), **kwargs).stdout
        except subprocess.CalledProcessError:
            if str(args[0]) == 'curl':
                raise  # Expected transient failures are retried silently.
            fail('Falló '+Path(args[0]).name+'; salida omitida para proteger credenciales. Revisar fase de update-state.')
        return result.strip() if isinstance(result, str) else result

    def pg(self, sql, database='postgres'):
        return self.run(['runuser', '-u', 'postgres', '--', 'env', '-i', 'PATH=/usr/bin:/bin', 'HOME=/nonexistent', 'PGPASSFILE=/dev/null', 'PGAPPNAME=ticketyn-update', 'psql', '--host=/var/run/postgresql', '--port=5432', '--username=postgres', '--no-password', '--dbname='+database, '-XAt', '--set=ON_ERROR_STOP=1', '-c', sql])

    def db_revision(self):
        value = self.pg('SELECT version_num FROM public.alembic_version', 'ticketyn')
        if not re.fullmatch('[A-Za-z0-9_]+', value):
            fail('DB con revisión Alembic inválida/múltiple.')
        return value

    def head(self, release):
        return self.run([release/'.venv/bin/python', '-I', '-B', Path(__file__).with_name('restore_support.py'), 'head', release], cwd='/')

    def lock(self):
        secure(self.lock_path.parent, directory=True)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        secure(self.lock_path, private=True)
        if stamp(self.lock_path) != [os.fstat(fd).st_dev, os.fstat(fd).st_ino]:
            os.close(fd); fail('Lock cambió durante apertura.')
        self.lock_fd = fd
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('Install/update/restore en ejecución.')

    def preflight(self):
        for path in (self.base, self.releases, self.config, self.backups):
            secure(path, directory=True)
        secure(self.backups, directory=True, private=True)
        secure(self.env, private=True); rs.config(self.env)
        installed = self.config/'install-state'
        secure(installed, directory=True, private=True)
        for name, value in [('format', '1'), ('status', 'complete')]:
            secure(installed/name, private=True)
            if (installed/name).read_text().strip() != value:
                fail('No existe una instalación administrada completada.')
        if (self.config/'restore-state').exists() or (self.config/'restore-state').is_symlink():
            fail('restore-state pendiente: finalizar/revisar restore antes de actualizar.')
        if not self.current.is_symlink() or self.current.lstat().st_uid != os.geteuid():
            fail('current debe ser el symlink administrado por root.')
        self.old = self.current.resolve(strict=True)
        if self.old.parent != self.releases or self.old.is_symlink():
            fail('current apunta fuera de releases.')
        secure(self.old, directory=True); secure(self.old/'pyproject.toml')
        self.source_version = ri.identity(self.old)
        self.target = self.releases/self.version
        secure(self.unit); secure(self.site)
        unit = self.unit.read_text()
        for required in ('User=ticketyn', 'Group=ticketyn', 'EnvironmentFile=/etc/ticketyn/ticketyn.env', '--host 127.0.0.1 --port 8000', '/opt/ticketyn/current/.venv/bin/uvicorn'):
            if required not in unit:
                fail('Unidad systemd ajena/incompatible.')
        if not self.link.is_symlink() or self.link.resolve() != self.site or 'root /opt/ticketyn/current/frontend/dist;' not in self.site.read_text():
            fail('Nginx no utiliza la estructura administrada; no se reconfigura.')
        # Existing helper outputs port; use subprocess for its CLI.
        self.port = self.run(['python3', '-I', '-B', Path(__file__).with_name('restore_support.py'), 'port', self.site])
        self.run(['nginx', '-t']); self.run(['systemctl', 'is-active', '--quiet', 'nginx'])
        self.revision = self.db_revision()
        if self.pg("SELECT pg_get_userbyid(datdba)||':'||pg_encoding_to_char(encoding) FROM pg_database WHERE datname='ticketyn'") != 'ticketyn:UTF8':
            fail('DB ticketyn con propietario/encoding inesperado.')
        self.db_oid = self.pg("SELECT oid FROM pg_database WHERE datname='ticketyn'")
        self.cluster = self.pg('SELECT system_identifier FROM pg_control_system()')
        database_size = int(self.pg("SELECT pg_database_size('ticketyn')"))
        if shutil.disk_usage(self.backups).free < 2*database_size + 256*1024**2:
            fail('Espacio insuficiente para el backup obligatorio (reserva conservadora).')
        self.env_hash = digest(self.env)
        if shutil.disk_usage(self.releases).free < max(1024**3, self.tree_size(self.old)*3):
            fail('Espacio insuficiente: se requiere al menos 1 GiB y 3 veces el release actual.')
        self.read_state()
        if self.data:
            self.validate_resume()
        else:
            forward(self.source_version, self.version)
            if self.target.exists() or self.target.is_symlink():
                fail('Release destino preexistente: no se modifica.')
            if self.revision != self.head(self.old):
                fail('DB no coincide con HEAD de la release activa.')
            self.run(['systemctl', 'is-enabled', '--quiet', 'ticketyn'])
            self.healthy(self.old)

    @staticmethod
    def tree_size(path):
        return sum(p.lstat().st_size for p in path.rglob('*') if p.is_file())

    def read_state(self):
        if not self.state.exists() and not self.state.is_symlink():
            return
        secure(self.state, directory=True, private=True)
        secure(self.state/'state.json', private=True)
        data = json.loads((self.state/'state.json').read_text())
        if data.get('format') != 'ticketyn-update-v1' or not re.fullmatch('[a-f0-9]{32}', data.get('operation', '')) or data.get('phase') not in PHASES or data.get('tag') != self.tag:
            fail('Estado update inválido/otra operación pendiente; revisión manual requerida.')
        self.data = data

    def validate_resume(self):
        d = self.data
        for key, expected in [('target', str(self.target)), ('env_hash', self.env_hash), ('db_oid', self.db_oid), ('cluster', self.cluster), ('origin', ORIGIN)]:
            if d.get(key) != expected:
                fail('Identidad de actualización cambió: '+key)
        if d['phase'] == 'complete':
            if self.old != self.target or self.revision != d['target_head'] or stamp(self.target) != d['target_inode']:
                fail('Estado completado inconsistente.')
            self.verify_target()
            self.healthy(self.target)
            return
        if d['phase'] not in SAFE_RETRY:
            fail('Actualización interrumpida después del límite de migración/activación. Ticketyn debe permanecer detenido. Conservar releases, backup y update-state; recuperar manualmente una DB compatible antes de reactivar código. No se ejecuta downgrade.')
        if stamp(self.current) != d['current_inode'] or str(self.old) != d['previous'] or stamp(self.old) != d['previous_inode'] or self.revision != d['source_head'] or self.source_version != d['source_version']:
            fail('No se puede demostrar un reintento seguro anterior a migración.')
        if self.target.exists() or self.target.is_symlink():
            secure(self.target, directory=True, private=True)
            if stamp(self.target) != d.get('target_inode'):
                fail('Destino no demostrablemente propio.')
        forward(self.source_version, self.version)

    def record(self, phase, **fields):
        self.data.update(fields, phase=phase, updated_at=datetime.now(timezone.utc).isoformat())
        write_json(self.state/'state.json', self.data)
        print('Fase: '+phase, flush=True)

    def begin(self):
        self.authorized = True
        if self.data:
            if self.data['phase'] == 'stopping':
                # Only old pointer, original DB OID/schema and unchanged config proven.
                self.run(['systemctl', 'enable', 'ticketyn']); self.run(['systemctl', 'start', 'ticketyn']); self.healthy(self.old)
            return
        self.data = {'format': 'ticketyn-update-v1', 'operation': secrets.token_hex(16), 'tag': self.tag, 'origin': ORIGIN, 'source_version': self.source_version, 'target_version': self.version, 'previous': str(self.old), 'target': str(self.target), 'previous_inode': stamp(self.old), 'current_inode': stamp(self.current), 'source_head': self.revision, 'env_hash': self.env_hash, 'db_oid': self.db_oid, 'cluster': self.cluster, 'backup': '', 'phase': 'preparing', 'result': 'pending'}
        initial = self.config/('.update-state-'+self.data['operation'])
        initial.mkdir(mode=0o700)
        write_json(initial/'state.json', self.data, exclusive=True)
        rs.rename_exclusive(initial, self.state)
        rs.sync_directory(self.config)

    def git(self, *args):
        return self.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.allow=never', '-c', 'protocol.https.allow=always', *args])

    def fetch(self):
        ref = 'refs/tags/'+self.tag
        advertised = self.git('ls-remote', '--refs', '--tags', ORIGIN, ref).splitlines()
        if len(advertised) != 1 or not re.fullmatch('[a-f0-9]{40,64}\t'+re.escape(ref), advertised[0]):
            fail('Tag inexistente o ambiguo en repositorio oficial.')
        oid = advertised[0].split('\t')[0]
        repo = self.work/'git'
        self.git('init', '--quiet', repo)
        self.git('-C', repo, 'fetch', '--quiet', '--no-tags', ORIGIN, ref+':'+ref)
        if self.git('-C', repo, 'rev-parse', '--verify', ref) != oid:
            fail('Tag cambió durante obtención.')
        commit = self.git('-C', repo, 'rev-parse', '--verify', ref+'^{commit}')
        if self.git('-C', repo, 'cat-file', '-t', ref) == 'tag':
            text = self.git('-C', repo, 'cat-file', '-p', ref)
            if not text.startswith('object '+commit+'\ntype commit\ntag '+self.tag+'\n'):
                fail('Tag anotado ambiguo/no directo a commit.')
        if self.data.get('commit') and (self.data['commit'] != commit or self.data['tag_oid'] != oid):
            fail('El tag registrado fue modificado; no se reintenta.')
        archive = self.work/'source.tar'
        self.git('-C', repo, 'archive', '--format=tar', '--output='+str(archive), commit)
        source = self.work/'source'; source.mkdir(mode=0o700)
        extract_release(archive, source)
        package = ri.project_version(source)
        # Uniform contract for all tags: package core equals tag core. The manifest
        # retains full SemVer identity; arbitrary SemVer prereleases aren't PEP440.
        if package != '.'.join(map(str, ri.semver(self.version)[0])):
            fail('project.version no coincide con el núcleo de versión del tag.')
        hashes = {str(p.relative_to(source)): digest(p) for p in source.rglob('*') if p.is_file()}
        self.record('preparing', commit=commit, tag_oid=oid, package_version=package, release_hashes=hashes)
        return source

    def prepare(self, source):
        if not self.target.exists():
            # Record source inode before exclusive rename: kill between rename and
            # next record remains identifiable. No venv relocation/shebang damage.
            self.record('preparing', target_inode=stamp(source))
            rs.rename_exclusive(source, self.target)
            rs.sync_directory(self.releases)
        else:
            # Resume only immutable content previously installed from this exact tag.
            for path in source.rglob('*'):
                other = self.target/path.relative_to(source)
                if path.is_file() and (not other.is_file() or other.is_symlink() or digest(path) != digest(other)):
                    fail('Contenido destino cambió; revisión manual requerida.')
        marker = self.target/'.ticketyn-release.json'
        expected = {'format': 'ticketyn-release-v1', 'version': self.version, 'tag': self.tag, 'commit': self.data['commit'], 'package_version': self.data['package_version'], 'pyproject_sha256': digest(self.target/'pyproject.toml'), 'operation': self.data['operation']}
        if marker.exists():
            secure(marker)
            if json.loads(marker.read_text()) != expected:
                fail('Manifiesto destino modificado.')
        else:
            write_json(marker, expected, exclusive=True)
        venv = self.target/'.venv'
        if venv.is_symlink():
            fail('venv inesperado.')
        self.run(['python3', '-B', '-m', 'venv', venv])
        pip = venv/'bin/pip'; python = venv/'bin/python'
        self.run([pip, 'install', '--no-cache-dir', '--no-deps', '-r', self.target/'requirements.lock'])
        build = self.work/'package-build'
        shutil.copytree(self.target, build, ignore=shutil.ignore_patterns('.venv', '.ticketyn-release.json'))
        self.run([pip, 'install', '--no-cache-dir', '--no-deps', build])
        self.run([pip, 'check'])
        self.run([python, '-I', '-B', Path(__file__), 'verify-python', self.target, self.env], cwd='/')
        self.data['target_head'] = self.run([python, '-I', '-B', Path(__file__), 'plan', self.old, self.target, self.revision], cwd=self.target)
        if not re.fullmatch('[A-Za-z0-9_]+', self.data['target_head']):
            fail('HEAD destino inválido.')
        self.verify_target()
        self.run(['sync', '-f', self.target])
        self.record('backup', target_head=self.data['target_head'])

    def backup(self):
        # A retry creates another backup, never silently reuses a stale snapshot.
        result = self.run([self.scripts/'backup.sh'])
        paths = [line.removeprefix('✓ Backup completo y verificado: ') for line in result.splitlines() if line.startswith('✓ Backup completo y verificado: ')]
        if len(paths) != 1:
            fail('No se pudo identificar backup previo.')
        backup = Path(paths[0])
        if backup.parent != self.backups or backup.suffix != '.tar':
            fail('Backup fuera del destino administrado.')
        secure(backup, private=True)
        content = self.work/'backup'
        rs.validate(backup, content)
        self.run(['pg_restore', '--file=/dev/null', content/'database.dump'])
        metadata = rs.metadata(content/'metadata.txt')
        if metadata['ticketyn_version'] != self.source_version or metadata['alembic_revision'] != self.revision or metadata['pyproject_sha256'] != digest(self.old/'pyproject.toml') or digest(content/'ticketyn.env') != self.env_hash:
            fail('Backup no corresponde al estado validado.')
        self.record('prepared', backup=str(backup), backup_sha256=digest(backup))

    def verify_target(self):
        secure(self.target, directory=True)
        if stamp(self.target) != self.data.get('target_inode'):
            fail('Identidad del directorio destino cambió.')
        for name, expected in self.data.get('release_hashes', {}).items():
            if not selected(name) or '..' in name.split('/'):
                fail('Ruta del estado destino inválida.')
            path = self.target/name
            secure(path)
            if digest(path) != expected:
                fail('Integridad destino cambió: '+name)
        if ri.identity(self.target) != self.version:
            fail('Identidad destino cambió.')
        marker = json.loads((self.target/'.ticketyn-release.json').read_text())
        if marker['commit'] != self.data['commit'] or marker.get('operation') != self.data['operation']:
            fail('Manifiesto destino no corresponde a la operación.')

    def revalidate(self):
        secure(self.env, private=True)
        if digest(self.env) != self.data['env_hash'] or self.current.resolve() != self.old or stamp(self.current) != self.data['current_inode'] or stamp(self.old) != self.data['previous_inode'] or self.db_revision() != self.data['source_head'] or self.pg("SELECT oid FROM pg_database WHERE datname='ticketyn'") != self.data['db_oid']:
            fail('La instalación cambió después del preflight.')

    def activate(self):
        self.revalidate()
        self.verify_target()
        backup = Path(self.data['backup'])
        secure(backup, private=True)
        if digest(backup) != self.data['backup_sha256']:
            fail('El backup previo cambió; no se migra.')
        self.record('stopping'); self.run(['systemctl', 'disable', 'ticketyn']); self.run(['systemctl', 'stop', 'ticketyn'])
        self.record('migrating')  # durable BEFORE possible DDL, including interruption
        if self.data['target_head'] != self.data['source_head']:
            self.run([self.target/'.venv/bin/python', '-I', '-B', Path(__file__), 'migrate', self.target, self.env], cwd=self.target)
        if self.db_revision() != self.data['target_head']:
            fail('Alembic no alcanzó HEAD destino.')
        self.record('migrated')
        # No writable release, no foreign links. venv contains expected Python links.
        for root, dirs, files in os.walk(self.target, followlinks=False):
            Path(root).chmod(0o755)
            for name in files:
                path = Path(root)/name
                if not path.is_symlink():
                    path.chmod(0o755 if path.stat().st_mode & 0o111 or root.endswith('/bin') else 0o644)
        self.record('activating')
        if not self.current.is_symlink() or self.current.resolve() != self.old:
            fail('current cambió; no se reemplaza.')
        temporary = self.base/('.current-'+self.data['operation'])
        switch_current(self.current, self.target, self.old, self.data['current_inode'], temporary)
        self.record('starting'); self.run(['systemctl', 'start', 'ticketyn'])
        self.record('checking'); self.healthy(self.target)
        self.run(['systemctl', 'enable', 'ticketyn'])
        self.record('complete', result='success')
        self.archive_state()

    def healthy(self, release):
        self.run(['systemctl', 'is-active', '--quiet', 'ticketyn'])
        self.run(['systemctl', 'is-active', '--quiet', 'nginx'])
        import time
        for path, kind in [('/health', 'health'), ('/api/customers', 'api'), ('/', 'frontend')]+[(p, 'asset') for p in assets(release)]:
            for attempt in range(30):
                try:
                    # curl stderr captured: expected transient 502/connect failures silent.
                    response = self.run(['curl', '-fsS', '--max-time', '3', 'http://127.0.0.1:'+self.port+path], binary=True)
                    if isinstance(response, str):
                        response = response.encode()
                    if kind == 'health' and json.loads(response) != {'status': 'ok'}:
                        raise ValueError()
                    if kind == 'api' and not isinstance(json.loads(response), list):
                        raise ValueError()
                    if kind == 'frontend' and response != (release/'frontend/dist/index.html').read_bytes():
                        raise ValueError()
                    if kind == 'asset' and response != (release/'frontend/dist'/path.lstrip('/')).read_bytes():
                        raise ValueError()
                    break
                except (subprocess.CalledProcessError, ValueError):
                    if attempt == 29:
                        fail(path+' no respondió válidamente después de 30 intentos; revisar Ticketyn/Nginx.')
                    time.sleep(1)
        self.check_socket()
        if self.current.resolve() != release:
            fail('current no coincide con la release verificada.')

    def check_socket(self):
        sockets = self.run(['ss', '-H', '-ltn', 'sport = :8000']).splitlines()
        if not sockets or [line.split()[3] for line in sockets] != ['127.0.0.1:8000']:
            fail('Uvicorn debe escuchar únicamente en LOCAL 127.0.0.1:8000.')

    def archive_state(self):
        history = self.config/'update-history'
        if not history.exists():
            history.mkdir(mode=0o700)
        secure(history, directory=True, private=True)
        # Entire state contains metadata only; preserve durable diagnostic history.
        rs.rename_exclusive(self.state, history/self.data['operation'])
        rs.sync_directory(self.config); rs.sync_directory(history)

    def failure(self):
        if not self.data or not self.authorized:
            return
        phase = self.data['phase']
        try:
            self.record(phase, result='interrupted_or_failed')
            if phase not in SAFE_RETRY and phase != 'complete':
                self.run(['systemctl', 'disable', 'ticketyn'])
                self.run(['systemctl', 'stop', 'ticketyn'])
                print('Ticketyn detenido: no se realiza rollback de esquema ni de current. Conservar backup y ambas releases; revisar update-state y recuperar manualmente una DB compatible.', file=sys.stderr)
            elif phase == 'stopping':
                self.revalidate(); self.run(['systemctl', 'enable', 'ticketyn']); self.run(['systemctl', 'start', 'ticketyn'])
            print('Estado conservado: '+str(self.state)+'; fase '+phase+'.', file=sys.stderr)
        except Exception:
            print('No se pudo completar diagnóstico/detención. Revisar servicio y update-state manualmente.', file=sys.stderr)

    def execute(self):
        self.lock()
        self.work = Path(tempfile.mkdtemp(prefix='ticketyn-update-')); self.work.chmod(0o700)
        try:
            self.preflight()
            if self.data and self.data['phase'] == 'complete':
                self.archive_state(); return
            self.begin()
            # Publication must remain on the releases filesystem (no EXDEV from /tmp).
            shutil.rmtree(self.work)
            self.work = Path(tempfile.mkdtemp(prefix='.ticketyn-update-', dir=self.releases))
            self.work.chmod(0o700)
            self.record(self.data['phase'], workspace=str(self.work), workspace_inode=stamp(self.work))
            source = self.fetch(); self.prepare(source); self.backup(); self.activate()
            print('✓ Ticketyn actualizado a '+self.tag+'. Backup previo conservado; releases anteriores conservadas.')
        except BaseException:
            self.failure(); raise
        finally:
            shutil.rmtree(self.work)  # only mkdtemp-owned ephemeral workspace, no releases/backups
            if self.lock_fd is not None:
                os.close(self.lock_fd)


def auxiliary(args):
    if args[0] == 'plan':
        print(migration_plan(*args[1:])); return
    if args[0] in ('migrate', 'verify-python'):
        release, configuration = map(Path, args[1:])
        rs.config(configuration)
        os.environ['DATABASE_URL'] = next(line.split('=', 1)[1] for line in configuration.read_text().splitlines() if line.startswith('DATABASE_URL='))
        if args[0] == 'migrate':
            from alembic.config import Config
            from alembic import command
            cfg = Config(str(release/'alembic.ini'))
            cfg.set_main_option('script_location', str(release/'alembic'))
            command.upgrade(cfg, 'head')
        else:
            import importlib.metadata
            import ticketyn
            from ticketyn.main import app
            if not app or importlib.metadata.version('ticketyn') != ri.project_version(release):
                fail('Paquete instalado/import incoherente.')
            for line in (release/'requirements.lock').read_text().splitlines():
                if line and not line.startswith('#'):
                    match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s]+)', line)
                    if not match or importlib.metadata.version(match[1]) != match[2]:
                        fail('Dependencias instaladas no coinciden con lock.')
        return
    fail('Operación interna inválida.')


if __name__ == '__main__':
    try:
        if sys.argv[1:2] and sys.argv[1] in ('plan', 'migrate', 'verify-python'):
            auxiliary(sys.argv[1:])
        else:
            if os.geteuid() != 0 or len(sys.argv) != 2:
                fail('Se requiere root y un tag explícito.')
            os.umask(0o077)
            def interrupted(signum, frame):
                raise UpdateError('Interrumpido por señal '+str(signum)+'.')
            signal.signal(signal.SIGINT, interrupted); signal.signal(signal.SIGTERM, interrupted)
            Updater(sys.argv[1]).execute()
    except (Exception, KeyboardInterrupt):
        # Never print CalledProcessError, arguments/env or third-party traceback:
        # migrations/imports may contain secrets in their diagnostic messages.
        error = sys.exc_info()[1]
        print('Error: '+(str(error) if isinstance(error, UpdateError) else 'Falló una comprobación/comando; instalación no declarada exitosa. Revisar fase registrada y servicios.'), file=sys.stderr)
        sys.exit(1)
