"""Validate the shipped site without loading or reloading any active service."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

SITE = Path(__file__).resolve().parents[1] / 'deploy/nginx/ticketyn.conf'


def test_site_logs_diagnostics_without_oauth_query_or_referer():
    source = SITE.read_text()
    definition = re.search(r'log_format ticketyn_no_args (.*?);', source, re.S).group(1)
    assert set(re.findall(r'\$\w+', definition)) == {
        '$remote_addr', '$time_local', '$request_method', '$uri', '$server_protocol',
        '$status', '$body_bytes_sent', '$request_time'}
    assert 'access_log /var/log/nginx/ticketyn-access.log ticketyn_no_args;' in source
    assert 'access_log off' not in source
    assert 'proxy_pass http://127.0.0.1:8000;' in source
    assert 'proxy_set_header X-Forwarded-For $remote_addr;' in source
    callback = re.search(r'location = /api/mail-notifications/oauth/callback\s*\{([^}]+)\}', source).group(1)
    assert 'error_log /dev/null;' in callback
    assert 'proxy_pass http://127.0.0.1:8000;' in callback


@pytest.mark.skipif(shutil.which('nginx') is None, reason='Nginx no está instalado localmente')
def test_nginx_configuration_in_isolated_prefix(tmp_path):
    site = SITE.read_text().replace('/var/log/nginx/ticketyn-access.log', str(tmp_path / 'access.log'))
    configuration = tmp_path / 'nginx.conf'
    configuration.write_text(f'pid {tmp_path}/nginx.pid;\nerror_log stderr;\nevents {{}}\nhttp {{\n{site}\n}}\n')
    result = subprocess.run(['nginx', '-t', '-p', str(tmp_path), '-c', str(configuration)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
