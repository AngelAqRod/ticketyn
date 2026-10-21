"""Fetch public stable release sources for install.sh; never run downloaded code."""
import argparse
from datetime import datetime
import gzip
import http.client
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import sys
import tarfile
import time
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import zlib

API = 'https://api.github.com/repos/AngelAqRod/ticketyn'
TAG = re.compile(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
MAX_JSON = 1024 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_MEMBERS = 50000
FILES = {'pyproject.toml', 'requirements.lock', 'alembic.ini', 'LICENSE', 'README.md',
         'install.sh', 'update.sh', 'backup.sh', 'restore.sh', 'bootstrap-superadmin.sh'}
TREES = ('src', 'alembic', 'deploy', 'frontend/dist')


class ReleaseError(RuntimeError):
    pass


def stable_tag(value):
    if not isinstance(value, str) or len(value) > 64 or TAG.fullmatch(value) is None:
        raise ReleaseError('El tag de la release no es una versión estable vX.Y.Z válida de Ticketyn.')
    return value


def check_url(url):
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.port in (None, 443)
                 and not parsed.username and not parsed.password and not parsed.fragment
                 and ((parsed.hostname == 'api.github.com' and parsed.path.startswith('/repos/AngelAqRod/ticketyn/'))
                      or (parsed.hostname == 'codeload.github.com' and parsed.path.startswith('/AngelAqRod/ticketyn/'))))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ReleaseError('URL de descarga o redirección ajena al repositorio HTTPS oficial.')


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def stream_url(url, limit, opener):
    check_url(url)
    request = Request(url, headers={'Accept': 'application/vnd.github+json',
                                    'User-Agent': 'Ticketyn-installer', 'Cache-Control': 'no-cache'})
    started = time.monotonic()
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                raise ReleaseError(f'GitHub respondió HTTP {response.status}; no se selecciona otra versión.')
            length = response.headers.get('Content-Length')
            if length is not None and (not length.isdecimal() or int(length) > limit):
                raise ReleaseError('Tamaño de respuesta de GitHub inválido o excesivo.')
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > limit or time.monotonic() - started > 120:
                    raise ReleaseError('La descarga excedió el tamaño o tiempo permitido.')
                yield chunk
            if length is not None and total != int(length):
                raise ReleaseError('Descarga incompleta: no coincide con el tamaño anunciado por GitHub.')
    except HTTPError as error:
        if error.code == 429 or (error.code == 403 and
                (error.headers.get('X-RateLimit-Remaining') == '0' or error.headers.get('Retry-After'))):
            raise ReleaseError('Límite de consultas de GitHub alcanzado; espera antes de volver a ejecutar.') from None
        if error.code == 404 and url.endswith('/releases/latest'):
            raise ReleaseError('No hay una release estable pública disponible, o el repositorio no es accesible.') from None
        if error.code == 404:
            raise ReleaseError('El tag o recurso de descarga seleccionado no existe en GitHub.') from None
        raise ReleaseError(f'GitHub respondió HTTP {error.code}; no se selecciona otra versión.') from None
    except (URLError, OSError, TimeoutError, http.client.HTTPException):
        raise ReleaseError('No se pudo completar la conexión HTTPS o la descarga de GitHub; revisa red y certificados.') from None


def release_metadata(data, expected_tag=None):
    if not isinstance(data, dict):
        raise ReleaseError('Los metadatos de release de GitHub no son válidos.')
    if data.get('draft') is not False or data.get('prerelease') is not False:
        raise ReleaseError('La release recibida es borrador, prerelease o carece de estado estable verificable.')
    tag = stable_tag(data.get('tag_name'))
    if expected_tag is not None and tag != expected_tag:
        raise ReleaseError('El tag recibido no coincide con la instalación parcial que se quiere recuperar.')
    try:
        published = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00'))
        if published.tzinfo is None:
            raise ValueError
    except (KeyError, ValueError, AttributeError, TypeError):
        raise ReleaseError('La release no tiene una fecha de publicación válida.') from None
    url = data.get('tarball_url')
    if url != f'{API}/tarball/{tag}':
        raise ReleaseError('La release no ofrece el archivo fuente oficial asociado al tag seleccionado.')
    return tag, url


def extract_source(archive, destination):
    # Consume gzip to EOF, checking its CRC/trailer and expansion bound before
    # tarfile parses any extended headers. Never use extractall or restore owners.
    expanded = 0
    with gzip.open(archive, 'rb') as stream:
        while chunk := stream.read(65536):
            expanded += len(chunk)
            if expanded > MAX_EXPANDED:
                raise ReleaseError('El archivo fuente expandido supera el límite permitido.')
    destination.mkdir(mode=0o700)
    prefix, seen = None, set()
    with tarfile.open(archive, 'r:gz') as source:
        for count, member in enumerate(source, 1):
            if count > MAX_MEMBERS:
                raise ReleaseError('El archivo fuente contiene demasiadas entradas.')
            raw = member.name.rstrip('/')
            parts = raw.split('/')
            if (not raw or raw.startswith('/') or '\\' in raw
                    or any(part in ('', '.', '..') for part in parts)
                    or any(ord(char) < 32 or ord(char) == 127 for char in raw)):
                raise ReleaseError('Ruta insegura en el archivo fuente.')
            if prefix is None:
                prefix = parts[0]
            if parts[0] != prefix:
                raise ReleaseError('El archivo no tiene la raíz única de un archivo fuente de GitHub.')
            name = '/'.join(parts[1:])
            if not name or not (name in FILES or any(name == tree or name.startswith(tree + '/') for tree in TREES)):
                continue
            if name in seen or member.issparse() or not (member.isfile() or member.isdir()):
                raise ReleaseError('Entrada duplicada, enlace o tipo no permitido en el archivo fuente.')
            seen.add(name)
            target = destination / PurePosixPath(name)
            if member.isdir():
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                with source.extractfile(member) as stream, target.open('xb') as output:
                    shutil.copyfileobj(stream, output)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def download_release(destination, resume_tag=None, *, opener=None):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ReleaseError('El directorio de descarga ya existe; no se sobrescribe.')
    if resume_tag is not None:
        stable_tag(resume_tag)
    opener = opener or build_opener(OfficialRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    endpoint = f'{API}/releases/tags/{resume_tag}' if resume_tag else f'{API}/releases/latest'
    try:
        data = json.loads(b''.join(stream_url(endpoint, MAX_JSON, opener)))
    except (ValueError, UnicodeError, RecursionError):
        raise ReleaseError('GitHub devolvió una respuesta JSON inválida; no se selecciona otra versión.') from None
    tag, url = release_metadata(data, resume_tag)
    archive = destination.parent / 'release.tar.gz'
    partial = destination.parent / 'release.tar.gz.part'
    with partial.open('xb') as output:
        for chunk in stream_url(url, MAX_ARCHIVE, opener):
            output.write(chunk)
    partial.replace(archive)
    try:
        extract_source(archive, destination)
        with (destination / 'pyproject.toml').open('rb') as stream:
            project = tomllib.load(stream)['project']
        if project.get('name') != 'ticketyn' or project.get('version') != tag[1:]:
            raise ReleaseError('El tag de GitHub y project.version de Ticketyn no coinciden.')
    except (OSError, EOFError, ValueError, KeyError, TypeError, AttributeError, tarfile.TarError, zlib.error):
        raise ReleaseError('Archivo fuente incompleto, corrupto o sin pyproject.toml compatible; no se instala.') from None
    return tag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--resume-tag', help='Solo recuperación explícita de la versión persistida por install.sh')
    args = parser.parse_args()
    try:
        print(download_release(args.destination, args.resume_tag))
    except (ReleaseError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
