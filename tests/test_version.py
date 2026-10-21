"""Version resolution and HTTP contract; no DB, SMTP, installation or migration."""
from importlib.metadata import PathDistribution
from pathlib import Path
import subprocess
import sys
import tomllib

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ticketyn.core import version


def source_tree(root, project='[project]\nname = "ticketyn"\nversion = "1.2.3"\n'):
    module = root / 'src/ticketyn/core/version.py'
    module.parent.mkdir(parents=True)
    module.write_text('# source fixture\n')
    if project is not None:
        (root / 'pyproject.toml').write_text(project)
    return module


def installed_tree(site, number, *, record=True):
    module = site / 'ticketyn/core/version.py'
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text('# installed fixture\n')
    info = site / f'ticketyn-{number}.dist-info'
    info.mkdir()
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: ticketyn\nVersion: {number}\n')
    if record:
        (info / 'RECORD').write_text('ticketyn/core/version.py,,\n')
    return module, PathDistribution(info)


def test_checkout_uses_official_project_version_instead_of_installed_metadata(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    with (root / 'pyproject.toml').open('rb') as stream:
        expected = tomllib.load(stream)['project']['version']

    def unexpected(**kwargs):
        pytest.fail('A source checkout must not read installed distribution metadata')

    monkeypatch.setattr(version, 'distributions', unexpected)
    assert version.get_version() == expected


def test_source_resolution_does_not_use_cwd(monkeypatch, tmp_path):
    module = source_tree(tmp_path / 'release')
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'pyproject.toml').write_text('[project]\nname="ticketyn"\nversion="9.8.7"')
    monkeypatch.chdir(other)
    monkeypatch.setattr(version, '_MODULE_PATH', module.resolve())
    assert version.get_version() == '1.2.3'


def test_switching_current_does_not_relabel_loaded_source(monkeypatch, tmp_path):
    old = source_tree(tmp_path / 'releases/old')
    source_tree(tmp_path / 'releases/new', '[project]\nname="ticketyn"\nversion="4.5.6"')
    current = tmp_path / 'current'
    current.symlink_to(old.parents[3], target_is_directory=True)
    monkeypatch.setattr(version, '_MODULE_PATH', (current / 'src/ticketyn/core/version.py').resolve())
    current.unlink()
    current.symlink_to(tmp_path / 'releases/new', target_is_directory=True)
    monkeypatch.chdir(current)
    assert version.get_version() == '1.2.3'


@pytest.mark.parametrize('project', [
    None, '[project', '[project]\nname="other"\nversion="1.2.3"',
    '[project]\nname="ticketyn"', '[project]\nname="ticketyn"\nversion=123',
    '[project]\nname="ticketyn"\nversion="invalid"',
    '[project]\nname="ticketyn"\nversion="1.2.3\\n"',
])
def test_invalid_or_missing_source_metadata_does_not_fall_back(monkeypatch, tmp_path, project):
    module = source_tree(tmp_path / 'source', project)
    monkeypatch.setattr(version, '_MODULE_PATH', module.resolve())
    monkeypatch.setattr(version, 'distributions', lambda **kwargs: pytest.fail('No fallback from invalid source'))
    with pytest.raises(RuntimeError):
        version.get_version()


@pytest.mark.parametrize('number', ['1.2.3', '1.2.3rc1', '1.2.3.dev1', '1.2.3+local.2'])
def test_installed_package_uses_owned_metadata_without_pyproject(monkeypatch, tmp_path, number):
    module, distribution = installed_tree(tmp_path / 'release/.venv/lib/python3/site-packages', number)
    monkeypatch.setattr(version, '_MODULE_PATH', module.resolve())
    monkeypatch.setattr(version, 'distributions', lambda **kwargs: [distribution])
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="ticketyn"\nversion="9.8.7"')
    assert version.get_version() == number


def test_installed_package_ignores_metadata_from_another_release(monkeypatch, tmp_path):
    _, stale = installed_tree(tmp_path / 'old/site-packages', '9.8.7')
    module, actual = installed_tree(tmp_path / 'current/site-packages', '1.2.3')
    monkeypatch.setattr(version, '_MODULE_PATH', module.resolve())
    monkeypatch.setattr(version, 'distributions', lambda **kwargs: [stale, actual])
    assert version.get_version() == '1.2.3'


def test_isolated_python_loads_installed_release_without_source_toml(tmp_path):
    stale_site = tmp_path / 'old/site-packages'
    actual_site = tmp_path / 'releases/candidate/.venv/lib/python3/site-packages'
    installed_tree(stale_site, '9.8.7')
    module, _ = installed_tree(actual_site, '1.2.3')
    module.write_text(Path(version.__file__).read_text())
    (actual_site / 'ticketyn/__init__.py').write_text('')
    (actual_site / 'ticketyn/core/__init__.py').write_text('')
    # This unrelated working-directory TOML and the older metadata come first;
    # neither is the source of the installed module's version.
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="ticketyn"\nversion="8.7.6"')
    result = subprocess.run([
        sys.executable, '-I', '-B', '-c',
        'import sys; sys.path[:0] = sys.argv[1:]; '
        'from ticketyn.core.version import get_version; print(get_version())',
        str(stale_site), str(actual_site),
    ], cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '1.2.3'


@pytest.mark.parametrize('kind', ['absent', 'foreign', 'unrecorded', 'invalid', 'ambiguous'])
def test_unproven_or_invalid_installed_version_fails_safely(monkeypatch, tmp_path, kind):
    module, actual = installed_tree(tmp_path / 'site-packages', '1.2.3', record=kind != 'unrecorded')
    candidates = [actual]
    if kind == 'absent':
        candidates = []
    elif kind == 'foreign':
        _, foreign = installed_tree(tmp_path / 'other/site-packages', '9.8.7')
        candidates = [foreign]
    elif kind == 'invalid':
        (tmp_path / 'site-packages/ticketyn-1.2.3.dist-info/METADATA').write_text('Name: ticketyn\nVersion: invalid\n')
    elif kind == 'ambiguous':
        _, another = installed_tree(tmp_path / 'site-packages', '9.8.7')
        candidates.append(another)
    monkeypatch.setattr(version, '_MODULE_PATH', module.resolve())
    monkeypatch.setattr(version, 'distributions', lambda **kwargs: candidates)
    with pytest.raises(RuntimeError):
        version.get_version()


def test_http_version_contract_matches_project_and_does_not_cache():
    # Isolate the real router's contract; authentication remains in the real app.
    from ticketyn.api.health import router
    app = FastAPI(version=version.get_version())
    app.include_router(router)
    with TestClient(app) as client:
        result = client.get('/api/system/version')
    assert result.status_code == 200
    assert result.json() == {'version': version.get_version()}
    assert result.headers['cache-control'] == 'no-store'


def test_real_app_uses_central_version_and_keeps_endpoint_authenticated(monkeypatch):
    from ticketyn.core.config import get_settings
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
    get_settings.cache_clear()
    try:
        from ticketyn.main import create_app
        app = create_app(start_notifications=False, start_audit_retention=False)
        assert app.version == version.get_version()
        assert app.openapi()['info']['version'] == app.version
        with TestClient(app) as client:
            result = client.get('/api/system/version')
        assert result.status_code == 401
        assert result.headers['cache-control'] == 'no-store'
    finally:
        get_settings.cache_clear()
