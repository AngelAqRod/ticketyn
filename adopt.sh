#!/bin/bash
# Adopción offline: no instala la aplicación ni modifica PostgreSQL/servicios.
set +x
set -Eeuo pipefail
umask 077
if (( EUID != 0 )); then
    echo 'Error: ejecuta adopt.sh como root o mediante sudo.' >&2
    exit 1
fi
if (( $# != 0 )); then
    echo 'Uso: ./adopt.sh (sin opciones ni --force).' >&2
    exit 1
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# No usar un Python del venv activado ni del PATH del administrador.
exec /usr/bin/python3 -I -B "$SCRIPT_DIR/deploy/adopt_support.py"
