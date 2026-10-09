#!/usr/bin/env bash
# Actualización explícita de releases; nunca ejecuta git pull sobre current.
set +x
set -Eeuo pipefail
if (( EUID != 0 )); then
    printf 'Error: ejecuta update.sh como root o mediante sudo.\n' >&2
    exit 1
fi
if ! { [[ $# == 1 && ( $1 != --* || $1 == --abort || $1 == --retry-migration ) ]] || [[ $# == 2 && $1 == --recover ]]; }; then
    printf 'Uso: ./update.sh [--recover] vX.Y.Z | --abort | --retry-migration (también admite prereleases SemVer)\n' >&2
    exit 1
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 -I -B "$SCRIPT_DIR/deploy/update_support.py" "$@"
