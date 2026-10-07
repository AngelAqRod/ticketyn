"""Administrative bundle tests: isolated paths, no production services or DB."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_updater', ROOT/'deploy/install_updater.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.fixture
def layout(tmp_path):
    source, base, sbin = tmp_path/'source', tmp_path/'opt', tmp_path/'sbin'
    source.mkdir(); base.mkdir(); sbin.mkdir()
    for name in p.FILES:
        target = source/name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    return source, base, sbin/'ticketyn-update'


def test_complete_bundle_permissions_and_repeatable_install(layout):
    source, base, command = layout
    bundle = p.install(source, base, command)
    assert p.install(source, base, command) == bundle
    assert p.validate_bundle(bundle) == bundle.name
    assert set(json.loads((bundle/'manifest.json').read_text())['files']) == set(p.FILES)
    for name in p.FILES:
        assert (bundle/name).read_bytes() == (ROOT/name).read_bytes()
        info = (bundle/name).stat()
        assert info.st_uid == os.geteuid() and info.st_gid == os.getegid()
        assert not info.st_mode & 0o022
        assert stat.S_IMODE(info.st_mode) == (0o755 if name.endswith('.sh') else 0o644)
    assert stat.S_IMODE(command.stat().st_mode) == 0o755
    assert command.stat().st_uid == os.geteuid()


def test_publish_new_bundle_keeps_previous_and_rejects_tampering(layout):
    source, base, command = layout
    old = p.install(source, base, command)
    (source/'update.sh').write_bytes((source/'update.sh').read_bytes()+b'\n# revision\n')
    new = p.install(source, base, command)
    assert new != old and old.exists()
    assert str(new/'update.sh') in command.read_text()
    (new/'deploy/update_support.py').write_text('changed')
    with pytest.raises(ValueError, match='modificado'):
        p.install(source, base, command)


@pytest.mark.parametrize('kind', ['foreign', 'symlink', 'writable', 'hardlink'])
def test_never_overwrites_unexpected_command(layout, kind):
    source, base, command = layout
    command.write_text('administrator command')
    if kind == 'symlink':
        command.unlink(); command.symlink_to(source/'update.sh')
    elif kind == 'writable':
        command.chmod(0o777)
    elif kind == 'hardlink':
        os.link(command, command.with_name('other'))
    before = command.read_bytes()
    with pytest.raises(ValueError):
        p.install(source, base, command)
    assert command.read_bytes() == before


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'missing'])
def test_unsafe_source_aborts_without_command(layout, kind):
    source, base, command = layout
    file = source/'backup.sh'
    if kind == 'symlink':
        file.unlink(); file.symlink_to(ROOT/'backup.sh')
    elif kind == 'hardlink':
        os.link(file, source/'other')
    else:
        file.unlink()
    with pytest.raises((ValueError, OSError)):
        p.install(source, base, command)
    assert not command.exists()


@pytest.mark.parametrize('args', [['v0.2.0'], ['--recover', 'v0.2.1'], ['--abort']])
def test_launcher_arbitrary_cwd_no_checkout_and_argument_forwarding(layout, tmp_path, args):
    source, base, command = layout
    # Harmless plumbing fixture using the same relative auxiliary resolution;
    # no updater/apt/DB/systemd invocation.
    (source/'update.sh').write_text('''#!/bin/bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 -I -B "$SCRIPT_DIR/deploy/update_support.py" "$@"
''')
    (source/'deploy/update_support.py').write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
    bundle = p.install(source, base, command)
    shutil.rmtree(source)
    cwd = tmp_path/'arbitrary'; cwd.mkdir()
    result = subprocess.run([command, *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == args
    assert not (bundle/'.git').exists()
    assert not (bundle/'frontend').exists()
    (base/'current').symlink_to(tmp_path/'old-release')
    (base/'current').unlink()
    (base/'current').symlink_to(tmp_path/'new-release')
    repeated = subprocess.run([command, *args], cwd=cwd, capture_output=True, text=True)
    assert repeated.returncode == 0 and json.loads(repeated.stdout) == args


def test_real_auxiliaries_resolve_and_backup_uses_bundle(layout):
    source, base, command = layout
    bundle = p.install(source, base, command)
    shutil.rmtree(source)
    # Loading real implementation exercises both sibling module imports. It
    # needs no checkout, CWD or installed app; actual execute() is not invoked.
    spec = importlib.util.spec_from_file_location('bundled_updater', bundle/'deploy/update_support.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.ri.__file__ == str(bundle/'deploy/release_identity.py')
    assert module.rs.__file__ == str(bundle/'deploy/restore_support.py')
    updater = module.Updater('v0.2.0', base=base, config=base/'config', backups=base/'backups', lock=base/'lock')
    assert updater.scripts == bundle
    assert (updater.scripts/'backup.sh').read_bytes() == (ROOT/'backup.sh').read_bytes()
    assert module.Updater('v0.2.1', recover=True).recover is True


def test_race_publishing_command_does_not_overwrite_foreign_file(layout, monkeypatch):
    source, base, command = layout
    original = p.rename_exclusive
    def race(left, right):
        if right == command:
            command.write_text('appeared concurrently')
        original(left, right)
    monkeypatch.setattr(p, 'rename_exclusive', race)
    with pytest.raises(OSError):
        p.install(source, base, command)
    assert command.read_text() == 'appeared concurrently'
    assert not list(command.parent.glob('.ticketyn-update-*'))


def test_failed_preparation_preserves_existing_launcher(layout, monkeypatch):
    source, base, command = layout
    old = p.install(source, base, command)
    previous = command.read_bytes()
    (source/'backup.sh').write_text('new version')
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(p, 'write', fail)
    with pytest.raises(OSError):
        p.install(source, base, command)
    assert command.read_bytes() == previous and old.exists()
    assert not list((base/'admin/updater').glob('.prepare-*'))


def test_cli_requires_root():
    if os.geteuid() == 0:
        pytest.skip('requires non-root test process')
    result = subprocess.run([sys.executable, '-I', ROOT/'deploy/install_updater.py', ROOT], capture_output=True, text=True)
    assert result.returncode and 'root' in result.stderr
