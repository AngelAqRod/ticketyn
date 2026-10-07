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
