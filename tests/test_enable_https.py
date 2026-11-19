import importlib.util
import shutil
import subprocess
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('enable_https', Path(__file__).parents[1] / 'deploy/enable_https.py')
https = importlib.util.module_from_spec(spec)
spec.loader.exec_module(https)
needs_openssl = pytest.mark.skipif(shutil.which('openssl') is None, reason='openssl no disponible')


def test_render_redirects_external_http_and_keeps_loopback_for_the_updater():
    text = https.render('ticketyn.empresa.com', '/c.pem', '/k.pem')
    assert text.count('{') == text.count('}')
    assert 'listen 443 ssl;' in text and 'ssl_certificate /c.pem;' in text and 'ssl_certificate_key /k.pem;' in text
    assert 'listen 80 default_server;' in text and 'return 301 https://ticketyn.empresa.com$request_uri;' in text
    assert 'listen 127.0.0.1:80;' in text  # health check of the updater compares the real index.html
    assert text.count('location /api/') == 2 and text.count('Strict-Transport-Security') == 4
    assert 'Strict-Transport-Security' not in https.render('a.b', '/c', '/k', hsts_seconds=0)


@pytest.mark.parametrize('bad', ['', '999.1.1.1', '1234', '::1', '10.0.0', 'a b', 'x;y', 'dominio.com{', '-a.com', 'a' * 300])
def test_invalid_domains_are_rejected(bad):
    with pytest.raises(https.HttpsError):
        https.render(bad, '/c', '/k')


def fake_runner(fail_on=None, log=None):
    def runner(args, **kwargs):
        args = [str(a) for a in args]
        if log is not None:
            log.append(args)
        if fail_on and args[:2] == fail_on:
            raise subprocess.CalledProcessError(1, args)
        return '{"status":"ok"}' if args[0] == 'curl' else ''
    return runner


@needs_openssl
def test_self_signed_certificate_validates_and_mismatched_key_or_missing_files_fail(tmp_path):
    cert, key = https.self_signed('ticketyn.local', tmp_path/'a')
    https.validate_cert(cert, key)
    assert oct(key.stat().st_mode & 0o777) == '0o600'
    other_cert, other_key = https.self_signed('otro.local', tmp_path/'b')
    with pytest.raises(https.HttpsError, match='no corresponde'):
        https.validate_cert(cert, other_key)
    with pytest.raises(https.HttpsError, match='No existe'):
        https.validate_cert(tmp_path/'nope.crt', key)


def setup(tmp_path):
    cert, key = tmp_path/'in.crt', tmp_path/'in.key'
    cert.write_text('c'); key.write_text('k')
    return cert, key, tmp_path/'nginx/ticketyn-https.conf', tmp_path/'tls'


def test_enable_installs_private_copies_validates_nginx_and_reloads(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    log = []
    https.enable('ticketyn.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner(log=log))
    assert 'server_name ticketyn.empresa.com;' in conf.read_text()
    assert oct((tls/'privkey.pem').stat().st_mode & 0o777) == '0o600'
    commands = [a[:2] for a in log]
    assert commands.index(['nginx', '-t']) < commands.index(['systemctl', 'reload'])


def test_failed_nginx_test_rolls_back_to_the_previous_file_or_removes_it(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    with pytest.raises(https.HttpsError, match='restaurada'):
        https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner(fail_on=['nginx', '-t']))
    assert not conf.exists()
    conf.parent.mkdir(parents=True, exist_ok=True); conf.write_text('anterior')
    with pytest.raises(https.HttpsError):
        https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner(fail_on=['nginx', '-t']))
    assert conf.read_text() == 'anterior'


def test_failed_health_probe_rolls_back(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    with pytest.raises(https.HttpsError):
        https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner(fail_on=['curl', '-ksS']))
    assert not conf.exists()


def test_disable_removes_file_and_restores_it_when_nginx_rejects(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    with pytest.raises(https.HttpsError, match='no está habilitado'):
        https.disable(conf, fake_runner(), hook=tmp_path/'h.sh')
    https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner())
    saved = conf.read_text()
    with pytest.raises(https.HttpsError, match='restauró'):
        https.disable(conf, fake_runner(fail_on=['nginx', '-t']), hook=tmp_path/'h.sh')
    assert conf.read_text() == saved
    https.disable(conf, fake_runner(), hook=tmp_path/'h.sh')
    assert not conf.exists()


def test_cli_print_and_non_root_refusal(capsys, monkeypatch):
    assert https.main(['--print', '--domain', 'x.empresa.com']) == 0
    assert 'return 301 https://x.empresa.com' in capsys.readouterr().out
    monkeypatch.setattr(https.os, 'geteuid', lambda: 1000)
    assert https.main(['--disable']) == 2
    assert 'root' in capsys.readouterr().err


def tls_state(tls):
    return {n: ((tls/n).read_bytes(), oct((tls/n).stat().st_mode & 0o777)) for n in https.TLS_NAMES}


def test_rerun_replaces_certificates_privately_and_failure_restores_the_previous_ones(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner())
    old_conf, old_tls = conf.read_text(), tls_state(tls)
    cert.write_text('nuevo-c'); key.write_text('nuevo-k')
    with pytest.raises(https.HttpsError, match='restaurada'):
        https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner(fail_on=['nginx', '-t']))
    assert conf.read_text() == old_conf and tls_state(tls) == old_tls  # content and 0600 modes
    https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner())
    assert (tls/'fullchain.pem').read_bytes() == b'nuevo-c' and tls_state(tls)['privkey.pem'] == (b'nuevo-k', '0o600')
    assert not [p for p in tls.iterdir() if p.name.startswith('.')]  # no temporary key copies left behind


def test_failed_first_enable_leaves_no_certificates_and_a_bad_pair_changes_nothing(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    with pytest.raises(https.HttpsError):
        https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner(fail_on=['systemctl', 'reload']))
    assert not conf.exists() and not any((tls/n).exists() for n in https.TLS_NAMES)
    with pytest.raises(https.HttpsError, match='No existe'):
        https.enable('a.empresa.com', tmp_path/'missing.crt', key, conf=conf, tls_dir=tls, runner=fake_runner())
    assert not conf.exists() and not any((tls/n).exists() for n in https.TLS_NAMES)


@needs_openssl
def test_enable_refuses_a_key_that_does_not_match_before_replacing_anything(tmp_path):
    cert, key = https.self_signed('a.local', tmp_path/'a')
    _, other_key = https.self_signed('b.local', tmp_path/'b')
    conf, tls = tmp_path/'n/ticketyn-https.conf', tmp_path/'tls'
    with pytest.raises(https.HttpsError, match='no corresponde'):
        https.enable('a.local', cert, other_key, conf=conf, tls_dir=tls, runner=https.run)
    assert not conf.exists() and not tls.exists()


def run_hook(hook, lineage, tmp_path):
    return subprocess.run(['sh', hook], env={'RENEWED_LINEAGE': lineage, 'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)


def test_certbot_hook_reruns_enable_only_for_its_own_lineage(tmp_path):
    marker = tmp_path/'called'
    launcher = tmp_path/'launcher.py'
    launcher.write_text(f'import sys, pathlib\npathlib.Path({str(marker)!r}).write_text(" ".join(sys.argv[1:]))\n')
    hook = tmp_path/'hooks/ticketyn-https.sh'
    hook.parent.mkdir()
    https.install_hook('a.empresa.com', '/etc/letsencrypt/live/a.empresa.com', 3600, hook=hook, launcher=str(launcher))
    assert oct(hook.stat().st_mode & 0o777) == '0o755'
    assert run_hook(hook, '/etc/letsencrypt/live/otro.com', tmp_path).returncode == 0 and not marker.exists()
    assert run_hook(hook, '/etc/letsencrypt/live/a.empresa.com', tmp_path).returncode == 0
    assert marker.read_text() == ('--domain a.empresa.com --cert /etc/letsencrypt/live/a.empresa.com/fullchain.pem '
                                  '--key /etc/letsencrypt/live/a.empresa.com/privkey.pem --hsts-seconds 3600 --yes')


def test_hook_quotes_untrusted_values_and_is_only_removed_when_managed(tmp_path):
    hook = tmp_path/'ticketyn-https.sh'
    https.install_hook('a.empresa.com', '/etc/letsencrypt/live/x; touch /tmp/pwned', 0, hook=hook)
    assert "'/etc/letsencrypt/live/x; touch /tmp/pwned'" in hook.read_text()
    assert https.remove_hook(hook) is True and not hook.exists()
    hook.write_text('#!/bin/sh\n# hook del administrador\n')
    assert https.remove_hook(hook) is False and hook.exists()


def test_disable_and_switching_certificate_type_remove_the_renewal_hook(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    hook = tmp_path/'ticketyn-https.sh'
    https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner())
    https.install_hook('a.empresa.com', '/etc/letsencrypt/live/a', 0, hook=hook)
    https.disable(conf, fake_runner(), hook=hook)
    assert not conf.exists() and not hook.exists()
    https.enable('a.empresa.com', cert, key, conf=conf, tls_dir=tls, runner=fake_runner())
    https.install_hook('a.empresa.com', '/etc/letsencrypt/live/a', 0, hook=hook)
    with pytest.raises(https.HttpsError):
        https.disable(conf, fake_runner(fail_on=['nginx', '-t']), hook=hook)
    assert hook.exists()  # still enabled, so renewals must keep working


def test_check_reports_the_renewal_hook(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    hook = tmp_path/'ticketyn-https.sh'
    assert 'no instalado' in https.check(conf, tls, fake_runner(), hook=hook)
    https.install_hook('a.empresa.com', '/etc/letsencrypt/live/a', 0, hook=hook)
    assert 'instalado' in https.check(conf, tls, fake_runner(), hook=hook).replace('no instalado', '')


def test_cli_rejects_certbot_lineage_combined_with_other_certificates(monkeypatch, capsys):
    monkeypatch.setattr(https.os, 'geteuid', lambda: 0)
    assert https.main(['--domain', 'a.empresa.com', '--certbot-lineage', '/x', '--self-signed']) == 2
    assert '--certbot-lineage no se combina' in capsys.readouterr().err
    assert https.main(['--domain', 'a.empresa.com', '--certbot-lineage', 'relativo']) == 2
    assert 'ruta absoluta' in capsys.readouterr().err


def test_ipv4_is_accepted_and_redirects_to_that_ip():
    text = https.render('10.0.0.5', '/c.pem', '/k.pem')
    assert 'server_name 10.0.0.5;' in text and 'return 301 https://10.0.0.5$request_uri;' in text


def test_probe_for_an_ip_uses_loopback_without_name_resolution(tmp_path):
    cert, key, conf, tls = setup(tmp_path)
    log = []
    https.enable('10.0.0.5', cert, key, conf=conf, tls_dir=tls, runner=fake_runner(log=log))
    curls = [a for a in log if a[0] == 'curl']
    assert ['https://127.0.0.1/health'] == [a[-1] for a in curls][:1] and '--resolve' not in curls[0]


@needs_openssl
def test_self_signed_certificate_for_an_ip_carries_an_ip_san(tmp_path):
    cert, key = https.self_signed('10.0.0.5', tmp_path/'a')
    https.validate_cert(cert, key)
    assert 'IP Address:10.0.0.5' in https.run(['openssl', 'x509', '-noout', '-ext', 'subjectAltName', '-in', cert])
