#!/usr/bin/env bash
# Ticketyn v0.7.0 — Bootstrap seguro del superadministrador inicial
# Interfaz administrativa interactiva para la inicialización del primer superadministrador.
# Nunca imprime ni registra contraseñas, hashes ni cadenas de conexión.
set +x
set -Eeuo pipefail

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

# 1. Localización confiable del directorio base de Ticketyn
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

if [[ -f "$SCRIPT_DIR/src/ticketyn/main.py" ]]; then
    APP_DIR="$SCRIPT_DIR"
elif [[ -L "/opt/ticketyn/current" && -e "/opt/ticketyn/current" ]]; then
    APP_DIR="/opt/ticketyn/current"
elif [[ -d "/opt/ticketyn/current" ]]; then
    APP_DIR="/opt/ticketyn/current"
else
    APP_DIR="$SCRIPT_DIR"
fi

# 2. Localización del intérprete Python con las dependencias de Ticketyn
PYTHON=""
if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
    PYTHON="$APP_DIR/.venv/bin/python"
elif [[ -x "/opt/ticketyn/current/.venv/bin/python" ]]; then
    PYTHON="/opt/ticketyn/current/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    if python3 -c "import ticketyn" >/dev/null 2>&1; then
        PYTHON="python3"
    fi
fi

if [[ -z "$PYTHON" ]]; then
    fail "No se encontró el entorno virtual Python de Ticketyn en '$APP_DIR/.venv' ni en '/opt/ticketyn/current/.venv'."
fi

# 3. Detección de configuración (.env o /etc/ticketyn/ticketyn.env)
# Si el operador no pasó --config y no tiene DATABASE_URL en su entorno:
HAS_CONFIG_ARG=0
for arg in "$@"; do
    if [[ "$arg" == "--config" || "$arg" == --config=* ]]; then
        HAS_CONFIG_ARG=1
        break
    fi
done

EXTRA_ARGS=()
if (( HAS_CONFIG_ARG == 0 )) && [[ -z "${DATABASE_URL:-}" ]]; then
    if [[ -f "/etc/ticketyn/ticketyn.env" ]]; then
        if [[ -r "/etc/ticketyn/ticketyn.env" ]]; then
            EXTRA_ARGS+=(--config "/etc/ticketyn/ticketyn.env")
        else
            fail "Se detectó '/etc/ticketyn/ticketyn.env' pero no tiene permisos de lectura para este usuario. Ejecuta este script como root o mediante sudo."
        fi
    elif [[ -f "$APP_DIR/.env" ]]; then
        if [[ -r "$APP_DIR/.env" ]]; then
            EXTRA_ARGS+=(--config "$APP_DIR/.env")
        fi
    fi
fi

# 4. Asegurar que PYTHONPATH incluya src si se ejecuta desde el árbol de código fuente
if [[ -d "$APP_DIR/src/ticketyn" ]]; then
    export PYTHONPATH="$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
fi

# 5. Ejecución segura del módulo backend
exec "$PYTHON" -I -B -m ticketyn.security.bootstrap "${EXTRA_ARGS[@]}" "$@"
