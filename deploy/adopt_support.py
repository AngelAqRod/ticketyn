"""Offline, read-only application validation followed by administrative adoption.

The receipt extends install-state format 1; it is not installer recovery state.
Only administrative files are published. Root is the trust boundary, as in update.
"""
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import importlib.util


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


u = load('update_support')
p = load('install_updater')
VERSION = '0.1.0'
COMMIT = '5d478abc97ffa18bb5293b96dfedc8649e89a013'
REVISION = '0004_nodes_responsibles'


class Adopter(u.Updater):
    def __init__(self, *args, command='/usr/local/sbin/ticketyn-update', **kwargs):
        super().__init__('v0.1.1', *args, **kwargs)
        self.command = Path(command)
        self.installed = self.config/'install-state'

    def git(self, *args, binary=False):
        # Read-only Git: no index refresh, replacement objects, fsmonitor/hooks,
        # global config, external diff, pager or network. Never safe.directory.
        environment = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent',
                       'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
                       'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0',
                       'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_TERMINAL_PROMPT': '0'}
        try:
            result = subprocess.run(['git', '-c', 'core.fsmonitor=false',
                                     '-c', 'core.hooksPath=/dev/null', '-C', str(self.old),
                                     *args], check=True, capture_output=True,
                                    text=not binary, env=environment).stdout
        except subprocess.CalledProcessError:
            u.fail('No se pudo verificar Git offline; salida omitida.')
        return result if binary else result.strip()

    def verify_git(self):
        u.secure(self.old/'.git', directory=True)
        for root, dirs, files in os.walk(self.old/'.git', followlinks=False):
            for name in dirs+files:
                path = Path(root)/name
                u.secure(path, directory=path.is_dir())
        settings = self.git('config', '--no-includes', '--local', '--null', '--list', binary=True)
        for entry in settings.split(b'\0'):
            key = entry.split(b'\n', 1)[0].decode('utf-8').lower()
            if (key.startswith(('include.', 'includeif.', 'filter.', 'diff.', 'fsck.'))
                    or key.startswith('extensions.') or key in ('core.attributesfile', 'core.worktree', 'core.alternaterefscommand')):
                u.fail('Configuración Git externa/filtros no permitidos para adopción.')
        self.verify_objects()
        if self.git('rev-parse', '--show-toplevel') != str(self.old):
            u.fail('La release no es la raíz de su checkout Git.')
        if self.git('rev-parse', 'HEAD') != COMMIT:
            u.fail('Commit no permitido para adopción.')
        # Independently compare literal files: assume-unchanged/skip-worktree or
        # clean filters must not conceal modifications from git status.
        tree = self.git('ls-tree', '-rz', '--full-tree', COMMIT, binary=True)
        # Reject a manipulated index before status can inspect any submodule.
        # ls-files is literal/index-only: no filters or child Git invocations.
        expected_index = []
        for entry in tree.split(b'\0'):
            if entry:
                header, name = entry.split(b'\t', 1)
                mode, kind, oid = header.split()
                expected_index.append(mode+b' '+oid+b' 0\t'+name)
        actual_index = self.git('ls-files', '--stage', '-z', binary=True).split(b'\0')
        if sorted(entry for entry in actual_index if entry) != sorted(expected_index):
            u.fail('Índice Git distinto del baseline permitido.')
        if self.git('status', '--porcelain=v1', '--untracked-files=all', '--ignore-submodules=all'):
            u.fail('Working tree modificado; no se adopta.')
        tracked = {}
        for entry in tree.split(b'\0'):
            if not entry:
                continue
            header, raw_path = entry.split(b'\t', 1)
            mode, kind, oid = header.split()
            name = os.fsdecode(raw_path)
            if mode not in (b'100644', b'100755') or kind != b'blob':
                u.fail('Tipo Git no permitido: '+name)
            path = self.old/name
            u.secure(path)
            expected = self.git('cat-file', 'blob', oid.decode(), binary=True)
            if u.ri.read_regular(path) != expected:
                u.fail('Archivo distinto del commit permitido: '+name)
            tracked[name] = hashlib.sha256(expected).hexdigest()
        for name in u.FILES + ('deploy/systemd/ticketyn.service', 'deploy/nginx/ticketyn.conf',
                               'frontend/dist/index.html', 'src/ticketyn/main.py'):
            if name not in tracked:
                u.fail('Baseline incompleto: '+name)
        self.tracked_bytes = {name: u.ri.read_regular(self.old/name) for name in tracked}
        return tracked

    def verify_objects(self):
        gitdir = self.old/'.git'
        for name in ('objects/info/alternates', 'objects/info/http-alternates', 'shallow', 'info/grafts'):
            if (gitdir/name).exists() or (gitdir/name).is_symlink():
                u.fail('Object store externo/reescritura Git no permitido.')
        if self.git('for-each-ref', '--format=%(refname)', 'refs/replace'):
            u.fail('Replace objects no permitidos.')
        self.git('fsck', '--full', '--strict', '--no-reflogs')
        visited = set()
        def check(oid, kind):
            if oid in visited: return
            if not re.fullmatch('[0-9a-f]{40}', oid): u.fail('OID Git inválido.')
            data = self.git('cat-file', kind, oid, binary=True)
            actual = hashlib.sha1(kind.encode()+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if actual != oid: u.fail('Integridad criptográfica Git inválida: '+oid)
            visited.add(oid)
            if kind == 'commit':
                tree = re.search(rb'^tree ([0-9a-f]{40})$', data, re.M)
                if not tree: u.fail('Commit sin tree válido.')
                check(tree[1].decode(), 'tree')
            elif kind == 'tree':
                offset = 0
                while offset < len(data):
                    end = data.index(b'\0', offset)
                    mode, name = data[offset:end].split(b' ', 1)
                    if name in (b'.', b'..') or b'/' in name: u.fail('Ruta Git inválida.')
                    child = data[end+1:end+21]
                    if len(child) != 20: u.fail('Tree Git truncado.')
                    if mode not in (b'40000', b'100644', b'100755'): u.fail('Tipo Git no permitido.')
                    check(child.hex(), 'tree' if mode == b'40000' else 'blob')
                    offset = end+21
        check(COMMIT, 'commit')

    def validate_runtime(self, tracked):
        """Never execute the release's interpreter, pip, migrations or imports.

        Inspect every cache and venv entry, then compare installed Ticketyn source
        with cryptographically verified Git blobs. Third-party packages are pinned
        by metadata; this is not an attestation of upstream wheel provenance.
        """
        import importlib.metadata
        venv = self.old/'.venv'
        u.secure(venv, directory=True)
        cfg = venv/'pyvenv.cfg'
        u.secure(cfg)
        options = {}
        for line in u.ri.read_regular(cfg).decode().splitlines():
            if not line.strip(): continue
            key, separator, value = line.partition('=')
            if not separator or key.strip() in options: u.fail('pyvenv.cfg ambiguo.')
            options[key.strip()] = value.strip()
        if (set(options)-{'home', 'include-system-site-packages', 'version', 'executable', 'command', 'prompt'}
                or options.get('home') != '/usr/bin'
                or options.get('include-system-site-packages') != 'false'
                or not re.fullmatch(r'3\.(?:1[1-9]|[2-9][0-9])\.[0-9]+', options.get('version', ''))):
            u.fail('pyvenv.cfg no corresponde a un entorno aislado del sistema.')
        if 'executable' in options:
            executable = Path(options['executable'])
            if (executable.parent != Path('/usr/bin')
                    or not re.fullmatch(r'python3(?:\.[0-9]+)?', executable.name)):
                u.fail('Ejecutable externo en pyvenv.cfg.')
        for root, dirs, files in os.walk(self.old, followlinks=False):
            for name in dirs+files:
                path = Path(root)/name
                if path.is_symlink():
                    u.ri.secure_ancestors(path)
                    link = path.lstat()
                    if (link.st_uid, link.st_gid) != (os.geteuid(), os.getegid()):
                        u.fail('Symlink no perteneciente a root.')
                    target = path.resolve(strict=True)
                    internal = target.is_relative_to(venv)
                    interpreter = (path.parent == venv/'bin' and name.startswith('python')
                                   and target.parent == Path('/usr/bin')
                                   and re.fullmatch(r'python3(?:\.[0-9]+)?', target.name))
                    if not internal and not interpreter: u.fail('Destino de symlink no permitido: '+str(path))
                    u.ri.secure_ancestors(target)
                    info = target.stat()
                    if (not (u.stat.S_ISREG(info.st_mode) or u.stat.S_ISDIR(info.st_mode))
                            or (path.parent == venv/'bin' and (not u.stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111))
                            or info.st_uid != (os.geteuid() if internal else Path('/').stat().st_uid)
                            or info.st_gid != (os.getegid() if internal else Path('/').stat().st_gid)
                            or info.st_mode & 0o022):
                        u.fail('Destino de symlink inseguro: '+str(path))
                else:
                    u.secure(path, directory=path.is_dir())
        sites = list((venv/'lib').glob('python*/site-packages'))
        if len(sites) != 1: u.fail('site-packages ambiguo/ausente.')
        site = sites[0]
        for path in site.rglob('*'):
            if path.name in ('sitecustomize.py', 'usercustomize.py'):
                u.fail('Personalización Python no permitida.')
            if path.suffix == '.pth':
                for line in u.ri.read_regular(path).decode().splitlines():
                    standard = "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; enabled = os.environ.get(var, 'local') == 'local'; enabled and __import__('_distutils_hack').add_shim();"
                    if (line.strip() and not line.startswith('#')
                            and not (path.name == 'distutils-precedence.pth' and line.strip() == standard)):
                        u.fail('Archivo .pth ejecutable/externo no permitido.')
        installed = {str(path.relative_to(site/'ticketyn')): path
                     for path in (site/'ticketyn').rglob('*.py')}
        expected = {name.removeprefix('src/ticketyn/'): value for name, value in tracked.items()
                    if name.startswith('src/ticketyn/') and name.endswith('.py')}
        if installed.keys() != expected.keys(): u.fail('Código Ticketyn instalado incompleto/extra.')
        for name, path in installed.items():
            if u.digest(path) != expected[name]: u.fail('Código Ticketyn instalado distinto del baseline.')
        # Cached Ticketyn bytecode can override source during normal imports.
        # Validate without executing it. Cross-interpreter caches fail closed.
        import importlib.util
        import marshal
        import types
        for path in (site/'ticketyn').rglob('*.pyc'):
            source = (path.parent.parent/(path.name.split('.')[0]+'.py')
                      if path.parent.name == '__pycache__' else path.with_suffix('.py'))
            relative = str(source.relative_to(site/'ticketyn'))
            if relative not in expected: u.fail('Bytecode Ticketyn sin fuente verificada.')
            data = u.ri.read_regular(path)
            if len(data) < 16 or len(data) > 10_000_000 or data[:4] != importlib.util.MAGIC_NUMBER:
                u.fail('Bytecode Ticketyn no verificable con Python del sistema.')
            try:
                cached = marshal.loads(data[16:])
                optimize = 2 if '.opt-2.' in path.name else 1 if '.opt-1.' in path.name else 0
                reference = compile(u.ri.read_regular(source), str(source), 'exec', optimize=optimize)
                if not isinstance(cached, types.CodeType) or cached != reference:
                    u.fail('Bytecode Ticketyn distinto del baseline.')
            except (ValueError, EOFError, TypeError):
                u.fail('Bytecode Ticketyn inválido.')
        versions = {}
        for dist in importlib.metadata.distributions(path=[str(site)]):
            name = re.sub('[-_.]+', '-', dist.metadata['Name']).lower()
            if name in versions: u.fail('Distribución Python duplicada.')
            versions[name] = dist.version
        if versions.get('ticketyn') != VERSION: u.fail('Versión instalada de Ticketyn incorrecta.')
        for line in (self.old/'requirements.lock').read_text().splitlines():
            if not line or line.startswith('#'): continue
            name, version = line.split('==')
            if versions.get(re.sub('[-_.]+', '-', name).lower()) != version:
                u.fail('Dependencia instalada distinta del lock: '+name)

    def head(self, release):
        import ast
        parents = {}
        for path in (release/'alembic/versions').glob('*.py'):
            values = {}
            for node in ast.parse(u.ri.read_regular(path)).body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id in ('revision', 'down_revision'):
                            values[target.id] = ast.literal_eval(node.value)
            revision, parent = values['revision'], values['down_revision']
            if revision in parents or not isinstance(revision, str) or (parent is not None and not isinstance(parent, str)):
                u.fail('Cadena Alembic ambigua.')
            parents[revision] = parent
        heads = set(parents)-set(parents.values())
        if len(heads) != 1 or any(parent is not None and parent not in parents for parent in parents.values()):
            u.fail('Cadena Alembic incompleta.')
        return heads.pop()

    def pg(self, sql, database='postgres'):
        if not sql.startswith('SELECT '): u.fail('Solo consultas read-only de adopción.')
        return self.run(['runuser', '-u', 'postgres', '--', 'env', '-i', 'PATH=/usr/bin:/bin',
                         'HOME=/nonexistent', 'PGPASSFILE=/dev/null',
                         'PGOPTIONS=-c default_transaction_read_only=on -c search_path=pg_catalog',
                         'psql', '--host=/var/run/postgresql', '--port=5432', '--username=postgres',
                         '--no-password', '--dbname='+database, '-XAt', '--set=ON_ERROR_STOP=1', '-c', sql])

    def db_revision(self):
        # Catalog-only check before ever evaluating public.alembic_version.
        shape = self.pg("SELECT c.relkind||':'||pg_catalog.pg_get_userbyid(c.relowner)||':'||a.atttypid::text||':'||c.relrowsecurity::text FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid WHERE n.nspname='public' AND c.relname='alembic_version' AND a.attname='version_num' AND a.attnum>0 AND NOT a.attisdropped", 'ticketyn')
        if shape not in ('r:ticketyn:1043:false', 'r:ticketyn:25:false'):
            u.fail('Objeto Alembic no es tabla ordinaria esperada, sin RLS.')
        return super().db_revision()

    def authenticate(self):
        # libpq reads a private anonymous memory FD: no password in argv, environment,
        # disk or captured output. The descriptor survives only this child process.
        password = u.rs.config(self.env)
        escape = lambda text: text.replace('\\', '\\\\').replace(':', '\\:')
        fd = os.memfd_create('ticketyn-adoption-auth', os.MFD_CLOEXEC)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, ('127.0.0.1:5432:ticketyn:ticketyn:'+escape(password)+'\n').encode())
            os.lseek(fd, 0, os.SEEK_SET)
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/nonexistent',
                   'PGPASSFILE': '/proc/self/fd/'+str(fd),
                   'PGOPTIONS': '-c default_transaction_read_only=on -c search_path=pg_catalog'}
            sql = "SELECT current_database()||':'||current_user||':'||oid::text FROM pg_catalog.pg_database WHERE datname=current_database()"
            try:
                value = subprocess.run(['/usr/bin/psql', '--host=127.0.0.1', '--port=5432',
                                        '--username=ticketyn', '--dbname=ticketyn', '--no-password',
                                        '-XAt', '--set=ON_ERROR_STOP=1', '-c', sql], env=env,
                                       pass_fds=(fd,), capture_output=True, text=True, check=True).stdout.strip()
            except subprocess.CalledProcessError:
                u.fail('Autenticación PostgreSQL fallida; salida omitida.')
            return value
        finally: os.close(fd)

    def validate_loaded_unit(self):
        expected = {'User': 'ticketyn', 'Group': 'ticketyn', 'WorkingDirectory': '/opt/ticketyn/current',
                    'EnvironmentFiles': '/etc/ticketyn/ticketyn.env (ignore_errors=no)',
                    'Environment': 'PYTHONDONTWRITEBYTECODE=1', 'UMask': '0077',
                    'NoNewPrivileges': 'yes', 'PrivateTmp': 'yes', 'ProtectSystem': 'full',
                    'ProtectHome': 'yes', 'Type': 'simple', 'LoadState': 'loaded',
                    'DynamicUser': 'no', 'RootDirectory': '', 'RootImage': '',
                    'ExecStartPre': '', 'ExecStartPost': '', 'ExecStop': '', 'ExecStopPost': ''}
        for name, value in expected.items():
            if self.run(['systemctl', 'show', 'ticketyn', '--property='+name, '--value']) != value:
                u.fail('Propiedad systemd cargada inesperada: '+name)
        start = self.run(['systemctl', 'show', 'ticketyn', '--property=ExecStart', '--value'])
        path = '/opt/ticketyn/current/.venv/bin/uvicorn'
        argv = path+' ticketyn.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1'
        if (not start.startswith('{ path='+path+' ; argv[]='+argv+' ; ')
                or start.count('{ path=') != 1 or 'ignore_errors=no' not in start):
            u.fail('ExecStart cargado inesperado.')

    @staticmethod
    def directives(text):
        return '\n'.join(value for line in text.splitlines()
                         if (value := line.split('#', 1)[0].strip()))

    def validate(self):
        for path in (self.base, self.releases, self.config):
            u.secure(path, directory=True)
        u.secure(self.backups, directory=True, private=True)
        for name in ('install-state', 'update-state', 'restore-state'):
            path = self.config/name
            if path.exists() or path.is_symlink():
                u.fail(name+' existente: no se adopta ni repara una operación previa.')
        if (not self.current.is_symlink()
                or (self.current.lstat().st_uid, self.current.lstat().st_gid) != (os.geteuid(), os.getegid())):
            u.fail('current no es un symlink seguro de root.')
        self.old = self.current.resolve(strict=True)
        if self.old != self.releases/VERSION or self.old.parent != self.releases:
            u.fail('current no apunta al baseline permitido dentro de releases.')
        u.secure(self.old, directory=True)
        # First baseline supports self-contained checkouts only, not external
        # worktree metadata that could be writable outside the validated tree.
        u.secure(self.old/'.git', directory=True)
        # Validate ownership/types of Git configuration and the venv BEFORE
        # invoking either. A service-writable .git/config must not run filters
        # as root before being rejected by the final snapshot.
        snapshot = u.release_snapshot(self.old)
        if u.ri.identity(self.old) != VERSION or u.ri.project_version(self.old) != VERSION:
            u.fail('project.version no corresponde al baseline permitido.')
        tracked = self.verify_git()
        self.validate_runtime(tracked)
        u.secure(self.env, private=True); u.rs.config(self.env)
        for path in (self.unit.parent, self.site.parent):
            u.secure(path, directory=True)
        u.secure(self.unit); u.secure(self.site)
        if (not self.link.is_symlink()
                or (self.link.lstat().st_uid, self.link.lstat().st_gid) != (os.geteuid(), os.getegid())
                or self.link.resolve(strict=True) != self.site):
            u.fail('Sitio Nginx habilitado inesperado/inseguro.')
        u.secure(self.link.parent, directory=True)
        # Exact baseline directives, ignoring comments/whitespace only. HTTP
        # port may differ, and the matching IPv6 listen is optional.
        unit = self.tracked_bytes['deploy/systemd/ticketyn.service'].decode()
        site = self.tracked_bytes['deploy/nginx/ticketyn.conf'].decode()
        if self.directives(self.unit.read_text()) != self.directives(unit):
            u.fail('Unidad systemd no corresponde al baseline permitido.')
        if self.run(['systemctl', 'show', 'ticketyn', '--property=FragmentPath', '--value']) != str(self.unit):
            u.fail('systemd utiliza otra unidad.')
        if self.run(['systemctl', 'show', 'ticketyn', '--property=DropInPaths', '--value']):
            u.fail('Drop-ins systemd no permitidos para adopción.')
        self.validate_loaded_unit()
        self.port = self.run(['python3', '-I', '-B', Path(__file__).with_name('restore_support.py'), 'port', self.site])
        def without_listen(text):
            return '\n'.join(line for line in self.directives(text).splitlines()
                             if not line.startswith('listen '))
        if without_listen(self.site.read_text()) != without_listen(site):
            u.fail('Configuración Nginx no corresponde al baseline permitido.')
        self.run(['nginx', '-t'])
        # Verify effective configuration on disk; workers are observed via HTTP.
        # No reload or claim of byte-for-byte in-memory equivalence. An extra server
        # on this port is ambiguous and could intercept health/API requests.
        loaded = self.run(['nginx', '-T'])
        if loaded.count('# configuration file '+str(self.site)+':') + loaded.count('# configuration file '+str(self.link)+':') != 1:
            u.fail('Nginx no carga inequívocamente el sitio validado.')
        listens = re.findall(r'^\s*listen\s+([^;]+);', loaded, re.M)
        for value in listens:
            if not re.fullmatch(r'(?:[0-9.]+:|\[[0-9A-Fa-f:]+\]:)?[0-9]+(?:\s+[A-Za-z0-9_=]+)*', value.strip()):
                u.fail('Escucha Nginx no interpretable con seguridad; no se adopta.')
        expected = [self.port]
        if 'listen [::]:'+self.port+';' in self.directives(self.site.read_text()):
            expected.append('[::]:'+self.port)
        relevant = [value.strip() for value in listens if re.search(r'(?:^|:)'+re.escape(self.port)+r'(?:\s|$)', value.strip())]
        if sorted(relevant) != sorted(expected):
            u.fail('Nginx contiene escuchas ambiguas para el puerto de Ticketyn.')
        self.run(['systemctl', 'is-enabled', '--quiet', 'ticketyn'])
        self.run(['systemctl', 'is-active', '--quiet', 'ticketyn'])
        self.run(['systemctl', 'is-active', '--quiet', 'nginx'])
        revision = self.db_revision()
        if revision != REVISION or self.head(self.old) != REVISION:
            u.fail('Alembic no corresponde al baseline; no se ejecutan migraciones.')
        if self.pg("SELECT pg_get_userbyid(datdba)||':'||pg_encoding_to_char(encoding) FROM pg_database WHERE datname='ticketyn'") != 'ticketyn:UTF8':
            u.fail('Propietario/encoding PostgreSQL inesperado.')
        oid = self.pg("SELECT oid FROM pg_database WHERE datname='ticketyn'")
        cluster = self.pg('SELECT system_identifier FROM pg_control_system()')
        if not re.fullmatch(r'[1-9][0-9]*', oid) or not re.fullmatch(r'[1-9][0-9]*', cluster):
            u.fail('OID/cluster PostgreSQL inválidos.')
        authenticated = self.authenticate()
        if authenticated != 'ticketyn:ticketyn:'+oid:
            u.fail('DATABASE_URL no autentica la misma DB como ticketyn.')
        self.healthy(self.old)
        if u.release_snapshot(self.old) != snapshot:
            u.fail('La release cambió durante la validación.')
        return {'format': 'ticketyn-adoption-v1', 'origin': 'adopted', 'version': VERSION,
                'release': str(self.old), 'commit': COMMIT, 'revision': revision,
                'db_oid': oid, 'cluster': cluster, 'owner': 'ticketyn', 'encoding': 'UTF8',
                'current_inode': u.stamp(self.current),
                'release_inode': u.stamp(self.old), 'release_snapshot': snapshot,
                'tracked_files': tracked, 'env_sha256': u.digest(self.env),
                'unit_sha256': u.digest(self.unit), 'nginx_sha256': u.digest(self.site),
                'env_inode': u.stamp(self.env), 'unit_inode': u.stamp(self.unit),
                'nginx_inode': u.stamp(self.site),
                'nginx_link_inode': u.stamp(self.link), 'port': self.port}

    def execute(self):
        staging = None
        self.lock()
        try:
            evidence = self.validate()
            # Existing provisioner validates/atomically publishes its own bundle.
            # Failure here cannot publish a completed managed installation.
            bundle = p.install(self.scripts, self.base, self.command)
            if self.validate() != evidence:
                u.fail('La instalación cambió durante la adopción; no se publica estado.')
            p.validate_publication(self.base, self.command, bundle)
            evidence.update(operation='adopt-'+secrets.token_hex(16),
                            created_at=datetime.now(timezone.utc).isoformat(),
                            updater_bundle=str(bundle))
            staging = Path(tempfile.mkdtemp(prefix='.adoption-', dir=self.config))
            for name, value in [('format', '1\n'), ('status', 'complete\n'), ('origin', 'adopted\n')]:
                with open(staging/name, 'xb', opener=lambda path, flags: os.open(path, flags | os.O_NOFOLLOW, 0o600)) as stream:
                    stream.write(value.encode())
                    stream.flush()
                    os.fsync(stream.fileno())
            u.write_json(staging/'adoption.json', evidence, exclusive=True)
            with open(staging/'adoption.sha256', 'x', opener=lambda path, flags: os.open(path, flags | os.O_NOFOLLOW, 0o600)) as stream:
                stream.write(u.digest(staging/'adoption.json')+'\n')
                stream.flush(); os.fsync(stream.fileno())
            u.validate_adoption(staging, self.base)
            u.rs.sync_directory(staging)
            # Full state appears atomically, never an incomplete install-state.
            u.rs.rename_exclusive(staging, self.installed)
            staging = None
            u.rs.sync_directory(self.config)
            print('✓ Instalación adoptada. ticketyn-update disponible; DB, release, current y servicios sin cambios.')
        finally:
            if staging is not None and staging.exists():
                shutil.rmtree(staging)  # Only our private, unpublished mkdtemp.
            if self.lock_fd is not None:
                os.close(self.lock_fd); self.lock_fd = None


def main():
    if os.geteuid() != 0 or os.getegid() != 0 or sys.argv[1:]:
        u.fail('La adopción requiere root y no acepta argumentos ni --force.')
    os.umask(0o077)
    def interrupted(signum, frame):
        raise InterruptedError('Adopción interrumpida; si install-state ya existe, revisar antes de reintentar. No eliminarlo.')
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    Adopter().execute()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Never echo exception subprocess output or configuration contents.
        message = str(error) if isinstance(error, (u.UpdateError, InterruptedError)) else 'Validación/publicación fallida; revisar permisos y evidencia. No se modifica DB ni servicios.'
        print('Error: '+message, file=sys.stderr)
        sys.exit(1)
