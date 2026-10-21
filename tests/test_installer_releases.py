"""Stable release acquisition with simulated GitHub; never installs or uses network."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_release', ROOT / 'deploy/install_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def metadata(tag='v1.2.3', **overrides):
    return {'tag_name': tag, 'draft': False, 'prerelease': False,
            'published_at': '2026-01-02T03:04:05Z',
            'tarball_url': f'{release.API}/tarball/{tag}', **overrides}


def archive(number='1.2.3', *, extra=(), prefix='AngelAqRod-ticketyn-abc1234'):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as tar:
        entries = [('pyproject.toml', f'[project]\nname = "ticketyn"\nversion = "{number}"\n'.encode()),
                   ('src/ticketyn/main.py', b'# application fixture\n'),
                   ('frontend/dist/index.html', b'<script src="/assets/app.js"></script>'),
                   ('frontend/dist/assets/app.js', b'/* compiled fixture */')]
        for name, content in entries:
            item = tarfile.TarInfo(f'{prefix}/{name}')
            item.size = len(content)
            tar.addfile(item, io.BytesIO(content))
        for item, content in extra:
            tar.addfile(item, io.BytesIO(content) if content is not None else None)
    return output.getvalue()


class Response(io.BytesIO):
    def __init__(self, content, headers=None, status=200):
        super().__init__(content)
        self.status = status
        self.headers = {'Content-Length': str(len(content))} if headers is None else headers


class GitHub:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request.full_url)
        assert timeout == 30
        assert request.get_header('User-agent') == 'Ticketyn-installer'
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def github(data=None, source=None):
    return GitHub(Response(json.dumps(metadata() if data is None else data).encode()),
                  Response(archive() if source is None else source))


@pytest.mark.parametrize('tag', ['v0.6.2', 'v0.10.0', 'v1.0.0', 'v12.100.3'])
def test_uses_github_latest_published_release_and_exact_tag(tmp_path, tag):
    data = metadata(tag, target_commitish='development/v99', assets=[{'name': 'unrelated.zip'}])
    remote = github(data, archive(tag[1:]))
    destination = tmp_path / 'source'
    assert release.download_release(destination, opener=remote) == tag
    assert remote.requests == [f'{release.API}/releases/latest', f'{release.API}/tarball/{tag}']
    assert (destination / 'frontend/dist/assets/app.js').is_file()
    assert (destination / 'pyproject.toml').is_file()
    assert not (tmp_path / 'release.tar.gz.part').exists()


@pytest.mark.parametrize('overrides', [
    {'draft': True}, {'prerelease': True}, {'draft': None}, {'prerelease': 'false'},
    {'tag_name': 'v1.2.3-rc.1'}, {'tag_name': 'v01.2.3'}, {'tag_name': 'master'},
    {'tag_name': 'v1.2.3;touch /tmp/unwanted'}, {'tag_name': None},
    {'published_at': None}, {'published_at': 'invalid'}, {'published_at': '2026-01-01'},
    {'tarball_url': 'https://evil.example/source.tar.gz'},
    {'tarball_url': f'{release.API}/tarball/master'},
    {'tarball_url': None},
])
def test_rejects_unpublished_prerelease_or_invalid_metadata_without_fallback(tmp_path, overrides):
    remote = github(metadata(**overrides))
    with pytest.raises(release.ReleaseError):
        release.download_release(tmp_path / 'source', opener=remote)
    assert remote.requests == [f'{release.API}/releases/latest']
    assert not (tmp_path / 'source').exists()


@pytest.mark.parametrize('body', [b'not JSON', b'<html>bad gateway</html>', b'[]', b'null', b'{}', b'\xff',
                                  b'[' * 2000 + b'0' + b']' * 2000])
def test_invalid_json_or_shape_stops(tmp_path, body):
    remote = GitHub(Response(body))
    with pytest.raises(release.ReleaseError):
        release.download_release(tmp_path / 'source', opener=remote)
    assert len(remote.requests) == 1


@pytest.mark.parametrize('status, headers, message', [
    (404, {}, 'No hay una release estable'), (500, {}, 'HTTP 500'),
    (403, {}, 'HTTP 403'), (429, {}, 'Límite de consultas'),
    (403, {'X-RateLimit-Remaining': '0'}, 'Límite de consultas'),
    (403, {'Retry-After': '60'}, 'Límite de consultas'),
])
def test_github_http_errors_stop_without_using_another_version(tmp_path, status, headers, message):
    remote = GitHub(HTTPError(f'{release.API}/releases/latest', status, 'error', headers, None))
    with pytest.raises(release.ReleaseError, match=message):
        release.download_release(tmp_path / 'source', opener=remote)
    assert len(remote.requests) == 1


@pytest.mark.parametrize('failure', [URLError('offline'), TimeoutError(), OSError('connection interrupted')])
def test_network_failure_stops(tmp_path, failure):
    remote = GitHub(failure)
    with pytest.raises(release.ReleaseError, match='conexión HTTPS'):
        release.download_release(tmp_path / 'source', opener=remote)
    assert len(remote.requests) == 1


def test_missing_tag_resource_is_not_replaced_by_branch_or_other_archive(tmp_path):
    remote = GitHub(Response(json.dumps(metadata()).encode()),
                    HTTPError(f'{release.API}/tarball/v1.2.3', 404, 'not found', {}, None))
    with pytest.raises(release.ReleaseError, match='tag o recurso'):
        release.download_release(tmp_path / 'source', opener=remote)
    assert len(remote.requests) == 2
    assert not (tmp_path / 'source').exists()


def test_incomplete_transfer_never_reaches_extraction(tmp_path):
    content = archive()
    remote = GitHub(Response(json.dumps(metadata()).encode()),
                    Response(content[:-20], {'Content-Length': str(len(content))}))
    with pytest.raises(release.ReleaseError, match='incompleta'):
        release.download_release(tmp_path / 'source', opener=remote)
    assert not (tmp_path / 'source').exists()
    assert not (tmp_path / 'release.tar.gz').exists()


@pytest.mark.parametrize('content', [b'not a gzip archive', archive()[:-8]])
def test_corrupt_or_truncated_gzip_is_rejected_even_without_content_length(tmp_path, content):
    remote = GitHub(Response(json.dumps(metadata()).encode()), Response(content, {}))
    with pytest.raises(release.ReleaseError, match='incompleto, corrupto'):
        release.download_release(tmp_path / 'source', opener=remote)


def test_archive_version_must_match_selected_tag(tmp_path):
    with pytest.raises(release.ReleaseError, match='no coinciden'):
        release.download_release(tmp_path / 'source', opener=github(source=archive('9.8.7')))


@pytest.mark.parametrize('kind', ['traversal', 'absolute', 'symlink', 'hardlink', 'fifo', 'duplicate', 'second-root'])
def test_unsafe_archive_entries_never_escape_staging(tmp_path, kind):
    name = 'AngelAqRod-ticketyn-abc1234/src/ticketyn/extra.py'
    content = b'x'
    if kind == 'traversal': name = 'AngelAqRod-ticketyn-abc1234/../escaped'
    if kind == 'absolute': name = '/escaped'
    if kind == 'duplicate': name = 'AngelAqRod-ticketyn-abc1234/pyproject.toml'
    if kind == 'second-root': name = 'other/src/file'
    item = tarfile.TarInfo(name)
    if kind in ('symlink', 'hardlink', 'fifo'):
        item.type = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE, 'fifo': tarfile.FIFOTYPE}[kind]
        item.linkname = '/etc/passwd'
        content = None
    else:
        item.size = len(content)
    with pytest.raises(release.ReleaseError):
        release.download_release(tmp_path / 'source', opener=github(source=archive(extra=[(item, content)])))
    assert not (tmp_path / 'escaped').exists()


def test_downloaded_installer_and_bootstrap_are_never_executed(tmp_path):
    script = b'#!/bin/sh\ntouch SHOULD_NEVER_EXECUTE\n'
    item = tarfile.TarInfo('AngelAqRod-ticketyn-abc1234/install.sh')
    item.size = len(script); item.mode = 0o755
    bootstrap = tarfile.TarInfo('AngelAqRod-ticketyn-abc1234/bootstrap-superadmin.sh')
    bootstrap.size = len(script); bootstrap.mode = 0o755
    release.download_release(tmp_path / 'source', opener=github(source=archive(extra=[(item, script), (bootstrap, script)])))
    assert (tmp_path / 'source/install.sh').read_bytes() == script
    assert (tmp_path / 'source/bootstrap-superadmin.sh').read_bytes() == script
    assert (tmp_path / 'source/bootstrap-superadmin.sh').stat().st_mode & 0o111
    assert not (tmp_path / 'source/SHOULD_NEVER_EXECUTE').exists()


def test_resume_only_downloads_explicit_persisted_tag(tmp_path):
    remote = github()
    assert release.download_release(tmp_path / 'source', 'v1.2.3', opener=remote) == 'v1.2.3'
    assert remote.requests[0] == f'{release.API}/releases/tags/v1.2.3'
    assert '/latest' not in ''.join(remote.requests)


def test_resume_rejects_a_different_release(tmp_path):
    with pytest.raises(release.ReleaseError, match='no coincide'):
        release.download_release(tmp_path / 'source', 'v4.5.6', opener=github())


@pytest.mark.parametrize('url', [
    'http://api.github.com/repos/AngelAqRod/ticketyn/tarball/v1.2.3',
    'https://evil.example/archive', 'https://codeload.github.com/other/repo/tar.gz/v1.2.3',
    'https://api.github.com@evil.example/repos/AngelAqRod/ticketyn/',
])
def test_redirect_does_not_downgrade_tls_or_leave_official_repository(url):
    request = Request(f'{release.API}/tarball/v1.2.3')
    with pytest.raises(release.ReleaseError):
        release.OfficialRedirect().redirect_request(request, None, 302, 'Found', {}, url)


def test_official_codeload_https_redirect_is_allowed():
    target = 'https://codeload.github.com/AngelAqRod/ticketyn/legacy.tar.gz/refs/tags/v1.2.3'
    result = release.OfficialRedirect().redirect_request(Request(f'{release.API}/tarball/v1.2.3'), None, 302, 'Found', {}, target)
    assert result.full_url == target


@pytest.mark.parametrize('limit_name', ['MAX_JSON', 'MAX_ARCHIVE', 'MAX_EXPANDED', 'MAX_MEMBERS'])
def test_resource_bounds(tmp_path, monkeypatch, limit_name):
    monkeypatch.setattr(release, limit_name, 1)
    with pytest.raises(release.ReleaseError):
        release.download_release(tmp_path / 'source', opener=github())


@pytest.mark.parametrize('headers', [{'Content-Length': 'unknown'}, {'Content-Length': '-1'},
                                   {'Content-Length': '999999999999'}])
def test_invalid_or_excessive_response_size_is_rejected(tmp_path, headers):
    remote = GitHub(Response(json.dumps(metadata()).encode(), headers))
    with pytest.raises(release.ReleaseError, match='Tamaño de respuesta'):
        release.download_release(tmp_path / 'source', opener=remote)


def test_stream_without_announced_length_is_still_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'MAX_JSON', 10)
    remote = GitHub(Response(json.dumps(metadata()).encode(), {}))
    with pytest.raises(release.ReleaseError, match='tamaño o tiempo'):
        release.download_release(tmp_path / 'source', opener=remote)


def test_overall_download_deadline(tmp_path, monkeypatch):
    clock = iter([0, 121])
    monkeypatch.setattr(release.time, 'monotonic', lambda: next(clock))
    with pytest.raises(release.ReleaseError, match='tamaño o tiempo'):
        release.download_release(tmp_path / 'source', opener=github())


def test_existing_destination_is_preserved(tmp_path):
    destination = tmp_path / 'source'
    destination.mkdir()
    (destination / 'existing').write_text('preserve')
    remote = github()
    with pytest.raises(release.ReleaseError, match='no se sobrescribe'):
        release.download_release(destination, opener=remote)
    assert (destination / 'existing').read_text() == 'preserve'
    assert remote.requests == []


def shell(script):
    return subprocess.run(['bash', '-c', 'source "$1"\n' + script, 'test', str(ROOT / 'install.sh')],
                          capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize('resume', [False, True])
def test_shell_uses_trusted_helper_and_announces_selected_version(tmp_path, resume):
    helper = tmp_path / 'trusted/deploy/install_release.py'
    helper.parent.mkdir(parents=True)
    trace = tmp_path / 'arguments'
    helper.write_text(f'import sys\nfrom pathlib import Path\nPath({str(trace)!r}).write_text(repr(sys.argv[1:]))\nprint("v1.2.3")\n')
    work = tmp_path / 'work'; work.mkdir()
    state = tmp_path / 'state'
    if resume:
        state.mkdir()
        for key, value in {'version': '1.2.3', 'format': '1', 'status': 'failed'}.items():
            (state / key).write_text(value)
    result = shell(f'''INSTALLER_SOURCE="{helper.parents[1]}"; WORK="{work}"; INSTALL_STATE="{state}"
protected_path() {{ :; }}
fetch_install_source
printf 'SOURCE=%s\n' "$SOURCE"
''')
    assert result.returncode == 0, result.stderr
    assert 'Release seleccionada para instalar: v1.2.3' in result.stdout
    assert f'SOURCE={work}/source' in result.stdout
    assert ('--resume-tag' in trace.read_text()) == resume
    assert ('Recuperación explícita' in result.stdout) == resume


def test_installer_stops_if_download_fails_instead_of_using_local_checkout(tmp_path):
    helper = tmp_path / 'trusted/deploy/install_release.py'
    helper.parent.mkdir(parents=True)
    helper.write_text('raise SystemExit(1)\n')
    result = shell(f'''INSTALLER_SOURCE="{helper.parents[1]}"; WORK="{tmp_path}"; INSTALL_STATE="{tmp_path}/absent"
fetch_install_source
echo SHOULD_NOT_INSTALL
''')
    assert result.returncode != 0
    assert 'checkout local ni otra versión' in result.stderr
    assert 'SHOULD_NOT_INSTALL' not in result.stdout


@pytest.mark.parametrize('values, message', [
    ({'format': '1', 'status': 'complete', 'version': '1.2.3'}, 'utiliza el updater'),
    ({'format': '2', 'status': 'failed', 'version': '1.2.3'}, 'Formato de recuperación'),
    ({'format': '1', 'status': 'unexpected', 'version': '1.2.3'}, 'Estado de recuperación'),
    ({'format': '1', 'status': 'failed', 'version': '../master'}, 'Versión de recuperación'),
])
def test_invalid_or_completed_recovery_state_stops_before_download(tmp_path, values, message):
    state = tmp_path / 'state'; state.mkdir()
    for key, value in values.items():
        (state / key).write_text(value)
    result = shell(f'''INSTALLER_SOURCE="{tmp_path}/no-helper"; WORK="{tmp_path}"; INSTALL_STATE="{state}"
protected_path() {{ :; }}
fetch_install_source
echo SHOULD_NOT_INSTALL
''')
    assert result.returncode != 0
    assert message in result.stderr
    assert 'install_release.py' not in result.stderr
    assert 'SHOULD_NOT_INSTALL' not in result.stdout


def test_missing_frontend_download_is_rejected_by_existing_validation(tmp_path):
    release.download_release(tmp_path / 'source', opener=github())
    (tmp_path / 'source/frontend/dist/index.html').unlink()
    result = shell(f'SOURCE="{tmp_path}/source"; check_project; echo SHOULD_NOT_INSTALL')
    assert result.returncode != 0
    assert 'frontend/dist/index.html' in result.stderr
    assert 'SHOULD_NOT_INSTALL' not in result.stdout


def test_downloaded_source_passes_existing_validation_and_deterministic_copy(tmp_path):
    # Representative distribution, not executable installation: all operations
    # below are confined to tmp_path; no venv, services, apt or DB are invoked.
    files = [
        'requirements.lock', 'LICENSE', 'README.md', 'alembic.ini', 'update.sh', 'backup.sh',
        'deploy/update_support.py', 'deploy/restore_support.py', 'deploy/release_identity.py',
        'deploy/install_updater.py', 'deploy/systemd/ticketyn.service', 'deploy/nginx/ticketyn.conf',
        'alembic/env.py', 'alembic/versions/0001_initial_catalogs.py',
        'alembic/versions/0002_remove_services.py', 'alembic/versions/0003_ticket_domain.py',
        'alembic/versions/0004_nodes_responsibles.py',
    ]
    extra = []
    for name in files:
        item = tarfile.TarInfo(f'AngelAqRod-ticketyn-abc1234/{name}')
        content = b'# distribution fixture\n'; item.size = len(content)
        extra.append((item, content))
    source = tmp_path / 'source'
    release.download_release(source, opener=github(source=archive(extra=extra)))
    copied = tmp_path / 'releases/1.2.3'; copied.mkdir(parents=True)
    result = shell(f'''SOURCE="{source}"; RELEASE="{copied}"
check_project
validate_release_source "$SOURCE"
[[ $(project_version "$SOURCE") == 1.2.3 ]]
SOURCE_HASH=$(release_tar | sha256sum | cut -d ' ' -f1)
copy_release
SOURCE="$RELEASE"
[[ $(release_tar | sha256sum | cut -d ' ' -f1) == "$SOURCE_HASH" ]]
''')
    assert result.returncode == 0, result.stderr
    assert (copied / 'frontend/dist/assets/app.js').read_bytes() == b'/* compiled fixture */'
    assert not (copied / 'update.sh').exists()  # original release copy whitelist


def test_main_acquires_and_validates_source_before_existing_install_flow():
    text = (ROOT / 'install.sh').read_text().split('main() {', 1)[1]
    steps = ['fetch_install_source\n', 'check_project\n', 'validate_release_source "$SOURCE"',
             'VERSION=$(project_version "$SOURCE")', 'confirm_install\n', 'init_state\n',
             'install_dependencies\n', 'prepare_database\n', 'prepare_release\n',
             'install_admin_updater\n', 'configure_services\n', 'final_checks\n']
    positions = [text.index(step) for step in steps]
    assert positions == sorted(positions)
    assert text.index('trap cleanup EXIT') < text.index('fetch_install_source\n')
    assert 'bootstrap-superadmin' not in text
