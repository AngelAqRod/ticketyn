#!/usr/bin/env bash
# Habilita HTTPS delante de Ticketyn (Nginx). Ver «Habilitar HTTPS» en docs/deployment.md.
set +x
set -Eeuo pipefail
if (( EUID != 0 )); then
    printf 'Error: ejecuta enable-https.sh como root o mediante sudo.\n' >&2
    exit 1
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 -I -B "$SCRIPT_DIR/enable_https.py" "$@"
