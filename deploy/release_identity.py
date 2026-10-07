"""Release identity, distinct from Python distribution version for SemVer tags."""
import hashlib
import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path

PATTERN = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'


def secure_ancestors(path):
    """Root/user-controlled chain; only the system sticky /tmp boundary is allowed.

    Tests may use private directories below /tmp. A non-sticky writable parent,
    including one below /tmp, is never trusted.
    """
    root = Path('/').stat()  # also supports mapped-root test namespaces
    for parent in Path(path).absolute().parents:
        info = parent.lstat()
        sticky_tmp = (parent == Path('/tmp') and info.st_uid == root.st_uid
                      and stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (root.st_uid, os.geteuid())
                or info.st_gid not in (root.st_gid, os.getegid())
                or (info.st_mode & 0o022 and not sticky_tmp)):
            raise ValueError('Ancestro inseguro: '+str(parent))


def read_regular(path):
    """No-follow descriptor read with identity checks on both sides."""
    secure_ancestors(path)
    before = Path(path).lstat()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        actual = os.fstat(stream.fileno())
        if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1
                or (actual.st_dev, actual.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError('Archivo sustituido/inseguro: '+str(path))
        data = stream.read()
        after = Path(path).lstat()
        if (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('Archivo cambió durante lectura: '+str(path))
        return data


NGINX_LAYOUTS = {'managed': 'ticketyn', 'legacy-conf': 'ticketyn.conf'}


def nginx_paths(root, layout):
    if layout not in NGINX_LAYOUTS:
        raise ValueError('Layout Nginx desconocido.')
    root = Path(root)
    return root/'sites-available'/NGINX_LAYOUTS[layout], root/'sites-enabled'/NGINX_LAYOUTS[layout]


def nginx_layout(root='/etc/nginx', expected=None):
    """Exactly one complete pair, never repair/rename or accept dangling aliases."""
    root = Path(root)
    if not root.is_absolute(): raise ValueError('Raíz Nginx no absoluta.')
    for directory in (root, root/'sites-available', root/'sites-enabled'):
        secure_ancestors(directory)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (os.geteuid(), os.getegid())
                or info.st_mode & 0o022):
            raise ValueError('Directorio Nginx inseguro: '+str(directory))
    present = []
    for layout in NGINX_LAYOUTS:
        site, link = nginx_paths(root, layout)
        exists = [path.exists() or path.is_symlink() for path in (site, link)]
        if any(exists): present.append((layout, site, link, all(exists)))
    if len(present) != 1 or not present[0][3]:
        raise ValueError('Layout Nginx ausente, incompleto o ambiguo; debe existir exactamente un par Ticketyn.')
    layout, site, link, _ = present[0]
    if expected is not None and layout != expected:
        raise ValueError('Layout Nginx distinto de la evidencia administrada.')
    info = site.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or (info.st_uid, info.st_gid) != (os.geteuid(), os.getegid()) or info.st_mode & 0o022):
        raise ValueError('Site Nginx inseguro: '+str(site))
    info = link.lstat()
    if (not stat.S_ISLNK(info.st_mode) or (info.st_uid, info.st_gid) != (os.geteuid(), os.getegid())):
        raise ValueError('Enlace Nginx inseguro: '+str(link))
    target = Path(os.readlink(link))
    target = target if target.is_absolute() else link.parent/target
    if Path(os.path.normpath(target)) != site or link.resolve(strict=True) != site:
        raise ValueError('Enlace enabled no corresponde directamente al site seleccionado.')
    return {'layout': layout, 'site': site, 'link': link}


def nginx_loaded(text, root, selection):
    """Effective on-disk nginx -T dump, not a claim about worker memory."""
    markers = re.findall(r'^# configuration file (.+):$', text, re.M)
    selected = {str(selection['site']), str(selection['link'])}
    alternatives = {str(path) for layout in NGINX_LAYOUTS for path in nginx_paths(root, layout)}-selected
    if sum(markers.count(path) for path in selected) != 1 or any(path in markers for path in alternatives):
        raise ValueError('Nginx no carga inequívocamente el layout Ticketyn seleccionado.')


def semver(value):
    match = re.fullmatch(PATTERN, value)
    if not match:
        raise ValueError('Versión SemVer inválida (build metadata no admitida).')
    pre = match[4].split('.') if match[4] else []
    if any(p.isdigit() and len(p) > 1 and p.startswith('0') for p in pre):
        raise ValueError('Identificador prerelease numérico con cero inicial.')
    return tuple(map(int, match.group(1, 2, 3))), pre


def compare(left, right):
    a, ap = semver(left); b, bp = semver(right)
    if a != b:
        return (a > b) - (a < b)
    if not ap or not bp:
        return (not ap) - (not bp)
    for x, y in zip(ap, bp):
        if x == y:
            continue
        if x.isdigit() and y.isdigit():
            return (int(x) > int(y)) - (int(x) < int(y))
        if x.isdigit() != y.isdigit():
            return -1 if x.isdigit() else 1
        return (x > y) - (x < y)
    return (len(ap) > len(bp)) - (len(ap) < len(bp))


def project_version(release):
    return tomllib.loads((Path(release)/'pyproject.toml').read_text())['project']['version']


def identity(release):
    release = Path(release)
    package = project_version(release)
    marker = release/'.ticketyn-release.json'
    if not marker.exists() and not marker.is_symlink():
        if release.name != package:
            raise ValueError('Release y pyproject incoherentes.')
        semver(package)
        return package
    info = marker.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022 or (info.st_uid, info.st_gid) != (os.geteuid(), os.getegid()):
        raise ValueError('Manifiesto de release inseguro.')
    data = json.loads(marker.read_text())
    version = data['version']
    semver(version)
    if (data['format'] != 'ticketyn-release-v1' or release.name != version
            or data['tag'] != 'v'+version or data['package_version'] != package
            or package != '.'.join(map(str, semver(version)[0]))
            or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', data['commit'])
            or data['pyproject_sha256'] != hashlib.sha256((release/'pyproject.toml').read_bytes()).hexdigest()):
        raise ValueError('Identidad de release inválida.')
    return version


if __name__ == '__main__':
    try:
        print(identity(sys.argv[1]))
    except (ValueError, KeyError, OSError, TypeError):
        sys.exit('Error: identidad de release inválida; contenido omitido.')
