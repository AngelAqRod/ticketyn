#!/usr/bin/env python3
"""Enable HTTPS for a managed Ticketyn install without touching the installer, updater or managed Nginx site.

It writes one separate file, /etc/nginx/conf.d/ticketyn-https.conf, with: a 443 server, a catch-all port-80 server that
redirects to HTTPS, and a 127.0.0.1:80 server that still serves the app so the updater health check keeps working.
Standard library only. Run as root: sudo python3 deploy/enable_https.py
"""
import argparse
import ipaddress
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

CONF = Path('/etc/nginx/conf.d/ticketyn-https.conf')
TLS_DIR = Path('/etc/ticketyn/tls')
TLS_NAMES = ('fullchain.pem', 'privkey.pem')
HOOK = Path('/etc/letsencrypt/renewal-hooks/deploy/ticketyn-https.sh')
HOOK_MARK = '# Managed by Ticketyn deploy/enable_https.py'
# shortcut: fixed install path of the managed layout; the hook must not point at a release directory that updates remove.
LAUNCHER = '/opt/ticketyn/current/deploy/enable_https.py'
HOST = re.compile(r'(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*')

# shortcut: copy of the app locations in deploy/nginx/ticketyn.conf; re-run this script if that template changes.
LOCATIONS = '''
    root /opt/ticketyn/current/frontend/dist;
    index index.html;
    server_tokens off;
    access_log /var/log/nginx/ticketyn-access.log ticketyn_https_no_args;
    client_max_body_size 2m;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
    add_header X-Frame-Options SAMEORIGIN always;
%(hsts)s
    location /assets/ {
        try_files $uri =404;
        expires 1y;
    }
    location = /index.html {
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy same-origin always;
        add_header X-Frame-Options SAMEORIGIN always;
%(hsts_index)s
    }
    location ~ /\\. {
        deny all;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 180s;
        location = /api/mail-notifications/oauth/callback {
            error_log /dev/null;
            proxy_pass http://127.0.0.1:8000;
        }
    }
    location = /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
'''


class HttpsError(Exception):
    pass


def is_ipv4(value):
    try:
        return isinstance(ipaddress.ip_address(value or ''), ipaddress.IPv4Address)
    except ValueError:
        return False


def valid_host(value):
    """A DNS name, or an IPv4 address when staff reach the server by IP."""
    return is_ipv4(value) or (bool(HOST.fullmatch(value or '')) and not value.replace('.', '').isdigit())


def render(domain, cert, key, hsts_seconds=86400):
    if not valid_host(domain):
        raise HttpsError('Dominio inválido: usa un nombre como ticketyn.empresa.com o una dirección IPv4.')
    hsts = f'    add_header Strict-Transport-Security "max-age={hsts_seconds}" always;' if hsts_seconds else ''
    body = LOCATIONS % {'hsts': hsts, 'hsts_index': hsts.replace('    add', '        add', 1)}
    # Own format name: conf.d loads before sites-enabled, so the site's log_format is not visible here yet.
    return f'''# Managed by deploy/enable_https.py. Remove with: python3 deploy/enable_https.py --disable
log_format ticketyn_https_no_args '$remote_addr [$time_local] "$request_method $uri $server_protocol" '
                                  '$status $body_bytes_sent $request_time';

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name {domain};
    ssl_certificate {cert};
    ssl_certificate_key {key};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:ticketyn_tls:10m;
{body}}}

# Any external HTTP request is moved to HTTPS.
server {{
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://{domain}$request_uri;
}}

# Loopback only: the updater health check compares the real index.html over HTTP.
server {{
    listen 127.0.0.1:80;
    server_name localhost;
{body}}}
'''


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True, **kwargs).stdout


def validate_cert(cert, key, runner=run):
    """Certificate must be readable, unexpired and match its (unencrypted) private key."""
    for path in (cert, key):
        if not Path(path).is_file():
            raise HttpsError(f'No existe el archivo: {path}')
    try:
        runner(['openssl', 'x509', '-noout', '-in', cert, '-checkend', '0'])
    except subprocess.CalledProcessError:
        raise HttpsError('El certificado es inválido o está vencido.') from None
    try:
        from_cert = runner(['openssl', 'x509', '-noout', '-pubkey', '-in', cert])
        from_key = runner(['openssl', 'pkey', '-pubout', '-passin', 'pass:', '-in', key])
    except subprocess.CalledProcessError:
        raise HttpsError('No se pudo leer la llave privada (¿tiene contraseña? Nginx no puede usarla).') from None
    if from_cert != from_key:
        raise HttpsError('La llave privada no corresponde al certificado.')


def self_signed(domain, directory, runner=run):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    cert, key = directory/'selfsigned.crt', directory/'selfsigned.key'
    runner(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '825', '-subj', f'/CN={domain}',
            '-addext', f'subjectAltName={"IP" if is_ipv4(domain) else "DNS"}:{domain}', '-keyout', key, '-out', cert])
    key.chmod(0o600)
    return cert, key


def write_private(path, data):
    """Atomic write that is private from the first byte (mkstemp creates the file as 0600)."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.ticketyn-tls-')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def install_files(cert, key, directory):
    """Copy into a root-only directory so moving the originals later cannot break Nginx."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    target = []
    for source, name in zip((cert, key), TLS_NAMES):
        write_private(directory/name, Path(source).read_bytes())
        target.append(directory/name)
    return target


def write_atomic(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.ticketyn-https-')
    with os.fdopen(fd, 'w') as handle:
        handle.write(text)
    os.chmod(name, mode)
    os.replace(name, path)


def install_hook(domain, lineage, hsts_seconds, hook=HOOK, launcher=LAUNCHER):
    """Certbot runs this after each renewal; it only acts for the lineage Ticketyn uses and re-runs this script."""
    lineage = Path(lineage)
    q = shlex.quote
    script = (f'#!/bin/sh\n{HOOK_MARK}; removed by enable_https.py --disable or when another certificate is enabled.\n'
              f'[ "$RENEWED_LINEAGE" = {q(str(lineage))} ] || exit 0\n'
              f'exec python3 -I -B {q(launcher)} --domain {q(domain)} --cert {q(str(lineage/TLS_NAMES[0]))} '
              f'--key {q(str(lineage/TLS_NAMES[1]))} --hsts-seconds {int(hsts_seconds)} --yes\n')
    try:
        write_atomic(hook, script, 0o755)
    except OSError as error:
        raise HttpsError(f'No se pudo instalar el hook de renovación de Certbot: {error}') from None


def remove_hook(hook=HOOK):
    """Only ever removes a hook this script wrote."""
    try:
        if hook.is_file() and HOOK_MARK in hook.read_text():
            hook.unlink()
            return True
    except OSError as error:
        raise HttpsError(f'No se pudo retirar el hook de renovación de Certbot: {error}') from None
    return False


def reload_nginx(runner):
    runner(['nginx', '-t'])
    runner(['systemctl', 'reload', 'nginx'])


def probe(domain, runner):
    """HTTPS must answer, and the loopback HTTP path used by the updater must keep answering."""
    target = ['https://127.0.0.1/health'] if is_ipv4(domain) else ['--resolve', f'{domain}:443:127.0.0.1', f'https://{domain}/health']
    https = runner(['curl', '-ksS', '--max-time', '5', *target])
    local = runner(['curl', '-sS', '--max-time', '5', 'http://127.0.0.1/health'])
    if '"ok"' not in https or '"ok"' not in local:
        raise HttpsError('La verificación de /health falló.')


def enable(domain, cert, key, hsts_seconds=86400, conf=CONF, tls_dir=TLS_DIR, runner=run):
    validate_cert(cert, key, runner)  # nothing is replaced unless the pair is valid and matches
    text = render(domain, tls_dir/TLS_NAMES[0], tls_dir/TLS_NAMES[1], hsts_seconds)
    previous = conf.read_text() if conf.exists() else None
    # Kept in memory, not as extra files: no second copy of the private key is left on disk.
    saved = {name: (tls_dir/name).read_bytes() if (tls_dir/name).exists() else None for name in TLS_NAMES}
    try:
        install_files(cert, key, tls_dir)
        write_atomic(conf, text)
        reload_nginx(runner)
        probe(domain, runner)
    except (subprocess.CalledProcessError, HttpsError, OSError) as error:
        error = (getattr(error, 'stderr', None) or '').strip() or error  # nginx explains itself on stderr
        if previous is None:
            conf.unlink(missing_ok=True)
        else:
            write_atomic(conf, previous)
        warning = ''
        try:
            for name, data in saved.items():
                if data is None:
                    (tls_dir/name).unlink(missing_ok=True)
                else:
                    write_private(tls_dir/name, data)
        except OSError as failure:
            warning = f' ADVERTENCIA: no se pudieron restaurar los certificados anteriores ({failure}).'
        try:
            reload_nginx(runner)
        except (subprocess.CalledProcessError, OSError):
            pass
        raise HttpsError(f'No se pudo habilitar HTTPS; configuración anterior restaurada (certificados incluidos). Detalle: {error}{warning}') from None


def disable(conf=CONF, runner=run, hook=HOOK):
    if not conf.exists():
        raise HttpsError('HTTPS no está habilitado por este script.')
    saved = conf.read_text()
    conf.unlink()
    try:
        reload_nginx(runner)
    except (subprocess.CalledProcessError, OSError):
        write_atomic(conf, saved)
        raise HttpsError('Nginx rechazó la configuración sin HTTPS; se restauró el archivo.') from None
    remove_hook(hook)  # otherwise the next renewal would turn HTTPS back on


def check(conf=CONF, tls_dir=TLS_DIR, runner=run, hook=HOOK):
    lines = [f'Archivo de Nginx: {"presente" if conf.exists() else "ausente"} ({conf})']
    lines.append('Renovación Certbot (hook): ' + ('instalado' if hook.is_file() and HOOK_MARK in hook.read_text() else 'no instalado'))
    cert = tls_dir/TLS_NAMES[0]
    if cert.exists():
        lines.append('Certificado: ' + runner(['openssl', 'x509', '-noout', '-enddate', '-in', cert]).strip())
    try:
        runner(['openssl', 'x509', '-noout', '-in', cert, '-checkend', str(30*86400)])
    except (subprocess.CalledProcessError, OSError):
        lines.append('AVISO: el certificado vence en menos de 30 días o no es legible.')
    try:
        runner(['curl', '-sS', '--max-time', '3', 'http://127.0.0.1/health'])
        lines.append('HTTP local (updater): responde')
    except (subprocess.CalledProcessError, OSError):
        lines.append('AVISO: HTTP local no responde; el updater lo necesita.')
    lines.append('Recuerda: el puerto 80 externo solo redirige; revisa tu firewall para exponer únicamente 80 (redirección) y 443.')
    return '\n'.join(lines)


def ask(prompt, default=None):
    answer = input(f'{prompt}' + (f' [{default}]' if default else '') + ': ').strip()
    return answer or default or ''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--domain')
    parser.add_argument('--cert', help='Ruta del certificado (cadena completa)')
    parser.add_argument('--key', help='Ruta de la llave privada, sin contraseña')
    parser.add_argument('--self-signed', action='store_true', help='Generar un certificado autofirmado')
    parser.add_argument('--certbot-lineage', help='Directorio del certificado de Certbot (/etc/letsencrypt/live/<nombre>); instala el hook de renovación')
    parser.add_argument('--hsts-seconds', type=int, default=86400, help='0 desactiva HSTS')
    parser.add_argument('--yes', action='store_true', help='No pedir confirmación')
    parser.add_argument('--disable', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--print', dest='show', action='store_true', help='Solo imprimir la configuración')
    options = parser.parse_args(argv)
    try:
        if options.check:
            print(check()); return 0
        if options.show:
            print(render(options.domain or 'ticketyn.example.com', TLS_DIR/'fullchain.pem', TLS_DIR/'privkey.pem', options.hsts_seconds)); return 0
        if os.geteuid() != 0:
            raise HttpsError('Debe ejecutarse como root (sudo).')
        if options.disable:
            disable(); print('HTTPS deshabilitado. El sitio vuelve a responder solo por HTTP.'); return 0
        domain = options.domain or ask('Dominio o IPv4 del sistema (ej. ticketyn.empresa.com o 10.0.0.5)')
        if not valid_host(domain):
            raise HttpsError('Dominio inválido: usa un nombre o una dirección IPv4.')
        selfsigned, lineage = options.self_signed, options.certbot_lineage
        if lineage and (selfsigned or options.cert or options.key):
            raise HttpsError('--certbot-lineage no se combina con --cert, --key ni --self-signed.')
        if not (selfsigned or options.cert or lineage):
            choice = ask("Certificado: 1) propio  2) autofirmado  3) Certbot / Let's Encrypt", '1')
            selfsigned = choice == '2'
            if choice == '3':
                lineage = ask('Directorio del certificado de Certbot (ej. /etc/letsencrypt/live/ticketyn.empresa.com)')
        if lineage:
            if not os.path.isabs(lineage):
                raise HttpsError('El directorio de Certbot debe ser una ruta absoluta.')
            if not HOOK.parent.is_dir():
                raise HttpsError(f'No existe {HOOK.parent}: ¿está instalado Certbot?')
            lineage = Path(os.path.normpath(lineage))
            cert, key = lineage/TLS_NAMES[0], lineage/TLS_NAMES[1]
            validate_cert(cert, key)
        elif selfsigned:
            cert, key = self_signed(domain, TLS_DIR)
        else:
            cert = Path(options.cert or ask('Ruta del certificado (.crt/.pem)'))
            key = Path(options.key or ask('Ruta de la llave privada (.key)'))
            validate_cert(cert, key)
        if not options.yes and ask(f'Habilitar HTTPS para {domain} y redirigir el HTTP externo (s/N)', 'N').lower() not in ('s', 'si', 'sí', 'y', 'yes'):
            print('Cancelado; no se cambió nada.'); return 1
        enable(domain, cert, key, options.hsts_seconds)
        if lineage:
            install_hook(domain, lineage, options.hsts_seconds)
            print('Renovación automática: hook de Certbot instalado en ' + str(HOOK))
        elif remove_hook():
            print('Se retiró el hook de renovación de Certbot: este certificado ya no se renueva con Certbot.')
        print(f'HTTPS habilitado en https://{domain}/. Actualiza la redirect_uri de OAuth del correo si la usas.')
        print(check())
        return 0
    except HttpsError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
