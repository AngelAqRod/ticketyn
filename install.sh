#!/usr/bin/env bash
# Instalación inicial. Nunca se utiliza sudo ni se actualizan instalaciones existentes.
set +x
set -Eeuo pipefail

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }
require_root() { (( EUID == 0 )) || fail 'Ejecuta este instalador como root o mediante sudo ./install.sh.'; }
valid_port() {
    [[ $1 =~ ^[0-9]{1,5}$ ]] || return 1
    local number=$((10#$1))
    (( number >= 1 && number <= 65535 ))
}
check_os() {
    local file=${1:-/etc/os-release} id version
    [[ -r $file ]] || fail 'No se puede leer /etc/os-release.'
    id=$(sed -n 's/^ID=//p' "$file" | tr -d '"')
    version=$(sed -n 's/^VERSION_ID=//p' "$file" | tr -d '"')
    case "$id:$version" in
        debian:12|debian:13|ubuntu:24.04) ;;
        *) fail "Sistema no soportado: $id $version. Se admiten Debian 12/13 y Ubuntu 24.04 LTS." ;;
    esac
}
project_version() {
    local version tags tag dirty
    version=$(sed -n 's/^version = "\([^" ]*\)"/\1/p' "$1/pyproject.toml")
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+([a-zA-Z0-9.+-]*)?$ ]] || fail 'Versión de proyecto inválida.'
    if [[ -e $1/.git ]]; then
        command -v git >/dev/null || fail 'El checkout necesita Git para verificar su versión.'
        git -C "$1" rev-parse --verify HEAD >/dev/null || fail 'No se puede verificar HEAD; revisa permisos/propiedad del checkout Git.'
        tags=$(git -C "$1" tag --points-at HEAD) || fail 'Error real de Git al consultar tags.'
        while IFS= read -r tag; do
            [[ -z $tag || $tag == "v$version" ]] || fail "El tag $tag no coincide con la versión $version."
        done <<< "$tags"
        dirty=$(git -C "$1" status --porcelain) || fail 'Error real de Git al consultar cambios locales.'
        [[ -z $dirty ]] || printf 'Advertencia: árbol Git modificado. Una release oficial debe instalarse limpia y taggeada.\n' >&2
        [[ -n $tags ]] || printf 'Advertencia: HEAD sin tag exacto; se utiliza project.version para esta fase de desarrollo.\n' >&2
    fi
    printf '%s' "$version"
}
frontend_assets() {
    grep -oE '/assets/[^"<>[:space:]]+' "$1" || true
}
require_absent() {
    [[ ! -e $1 && ! -L $1 ]] || fail "$2"
}
check_project() {
    local file assets asset
    for file in frontend/dist/index.html requirements.lock pyproject.toml LICENSE alembic.ini \
        alembic/env.py alembic/versions/0001_initial_catalogs.py alembic/versions/0002_remove_services.py \
        alembic/versions/0003_ticket_domain.py alembic/versions/0004_nodes_responsibles.py src/ticketyn/main.py deploy/systemd/ticketyn.service deploy/nginx/ticketyn.conf; do
        [[ -s $SOURCE/$file ]] || fail "Falta $file. Utiliza una release con frontend precompilado; no se instala Node/npm."
    done
    assets=$(frontend_assets "$SOURCE/frontend/dist/index.html")
    [[ -n $assets ]] || fail 'index.html no referencia un build Vite precompilado.'
    for asset in $assets; do
        [[ $asset != *'..'* && -s $SOURCE/frontend/dist$asset ]] || fail "Falta el asset compilado $asset."
    done
    [[ -d $SOURCE/alembic/versions ]] || fail 'Faltan las migraciones Alembic.'
    compgen -G "$SOURCE/alembic/versions/0004_*.py" >/dev/null || fail 'Falta la migración 0004.'
}
# Solo la dirección LOCAL y estado LISTEN de /proc/net/tcp{,6}; nunca el peer.
listening_port() {
    local hex
    printf -v hex '%04X' "$1"
    local files=(/proc/net/tcp)
    [[ ! -r /proc/net/tcp6 ]] || files+=(/proc/net/tcp6)
    awk -v port="$hex" '$4 == "0A" { split($2, addr, ":"); if (toupper(addr[2]) == port) found=1 } END { exit !found }' "${files[@]}"
}
nginx_port_configured() {
    local config code=0
    command -v nginx >/dev/null || return 1
    config=$(nginx -T 2>/dev/null) || fail 'La configuración Nginx existente no es válida; revísala antes de instalar.'
    # En recuperación solo omitir nuestro archivo si conserva identidad y contenido.
    if [[ ${RECOVERING:-0} == 1 && -e ${NGINX_SITE:-/etc/nginx/sites-available/ticketyn} ]]; then
        require_owned nginx "$NGINX_SITE"
        config=$(printf '%s\n' "$config" | awk '
            /^# configuration file / {skip=($0 == "# configuration file /etc/nginx/sites-enabled/ticketyn:" || $0 == "# configuration file /etc/nginx/sites-available/ticketyn:")}
            !skip {print}')
    fi
    printf '%s\n' "$config" | nginx_config_uses_port "$1" || code=$?
    [[ $code != 2 ]] || fail 'Directiva listen de Nginx no interpretable con seguridad; revisa la configuración manualmente.'
    return "$code"
}
nginx_config_uses_port() {
    # Subconjunto deliberado. Nunca adivinar el puerto de una sintaxis desconocida.
    sed 's/#[^\n]*//g' | awk -v port="$1" 'BEGIN {RS=";"}
        {if (match($0, /(^|[[:space:]{}])listen[[:space:]]+/)) {
            value=substr($0,RSTART+RLENGTH); split(value,words,/[[:space:]]+/); value=words[1];
            if (value ~ /^"[^" ]+"$/) {sub(/^"/,"",value); sub(/"$/,"",value)}
            if (value ~ /^unix:\//) next;
            if (value ~ /^[0-9]+$/) number=value;
            else if (value ~ /^([0-9]+\.){3}[0-9]+:[0-9]+$/ || value ~ /^\[[0-9a-fA-F:]+\]:[0-9]+$/ || value ~ /^\*:[0-9]+$/) {
                number=value; sub(/^.*:/,"",number)
            } else if (value ~ /^([0-9]+\.){3}[0-9]+$/ || value ~ /^\[[0-9a-fA-F:]+\]$/) number=80;
            else {unknown=1; next}
            if (number+0<1 || number+0>65535) unknown=1;
            if (number+0==port+0) found=1;
        }} END {if(unknown) exit 2; exit !found}'
}
choose_port() {
    local answer
    while true; do
        read -r -p 'Puerto HTTP [80] (C para cancelar): ' answer || fail 'Se requiere entrada interactiva para seleccionar el puerto.'
        [[ $answer != [Cc] ]] || { info 'Instalación cancelada.'; exit 0; }
        answer=${answer:-80}
        if ! valid_port "$answer"; then info 'Puerto inválido: utiliza un entero entre 1 y 65535.'; continue; fi
        HTTP_PORT=$((10#$answer))
        if [[ $HTTP_PORT == 8000 || $HTTP_PORT == 5432 ]]; then info "El puerto $HTTP_PORT está reservado para backend/PostgreSQL. Elige otro."; continue; fi
        if listening_port "$HTTP_PORT" || nginx_port_configured "$HTTP_PORT"; then
            info "El puerto $HTTP_PORT está ocupado o configurado por un servicio/sitio existente. Elige otro puerto o C para cancelar."
            continue
        fi
        break
    done
}
confirm_install() {
    local answer
    info "Resumen de instalación

Puerto HTTP: $HTTP_PORT
Base de datos: ticketyn
Usuario PostgreSQL: ticketyn
Usuario del sistema: ticketyn
Ruta base: /opt/ticketyn
Configuración: /etc/ticketyn"
    while true; do
        read -r -p '¿Continuar con la instalación? [S/n]: ' answer || fail 'No se recibió confirmación.'
        case "$answer" in ''|[SsYy]) return ;; [Nn]) info 'Instalación cancelada.'; exit 0 ;; *) info 'Responde S o N.' ;; esac
    done
}
# Estado de instalación: datos no secretos, nunca se ejecuta con source/eval.
# Las rutas de producción se fijan en main; los helpers admiten rutas temporales en tests.
protected_path() {
    [[ ! -L $1 && $(stat -c %u "$1") == 0 && $(stat -c %g "$1") == 0 ]] || fail "Estado/configuración sin propietario root seguro: $1"
    [[ $(stat -c %a "$1") == "$2" ]] || fail "Permisos inesperados: $1 (esperados $2)."
}
state_put() {
    local temporary
    temporary=$(mktemp "$INSTALL_STATE/.state.XXXXXXXX")
    chmod 0600 "$temporary"
    chown root:root "$temporary"
    printf '%s\n' "$2" > "$temporary"
    mv -Tf -- "$temporary" "$INSTALL_STATE/$1"
}
state_get() {
    [[ -f $INSTALL_STATE/$1 ]] || fail "Falta archivo de estado: $1"
    protected_path "$INSTALL_STATE/$1" 600
    cat -- "$INSTALL_STATE/$1"
}
load_state() {
    RECOVERING=0
    [[ -e $INSTALL_STATE || -L $INSTALL_STATE ]] || return 0
    protected_path "$INSTALL_STATE" 700
    [[ $(state_get format) == 1 ]] || fail 'Formato de recuperación desconocido.'
    [[ $(state_get version) == "$VERSION" ]] || fail 'La instalación parcial pertenece a otra versión; no se actualiza.'
    [[ $(state_get source) == "$SOURCE_HASH" ]] || fail 'El contenido fuente cambió desde la instalación parcial; requiere revisión manual.'
    INSTALL_TOKEN=$(state_get token)
    [[ $INSTALL_TOKEN =~ ^[0-9a-f]{32}$ ]] || fail 'Token de recuperación inválido.'
    HTTP_PORT=$(state_get port); valid_port "$HTTP_PORT" || fail 'Puerto de recuperación inválido.'
    NEW_NGINX=$(state_get new_nginx); DEFAULT_ABSENT=$(state_get default_absent)
    [[ $NEW_NGINX =~ ^[01]$ && $DEFAULT_ABSENT =~ ^[01]$ ]] || fail 'Estado Nginx inválido.'
    RELEASE_READY=$(state_get release_ready)
    [[ $RELEASE_READY =~ ^[01]$ ]] || fail 'Estado del release inválido.'
    PHASE=$(state_get phase)
    [[ $PHASE =~ ^(inicial|paquetes|database|release|servicios|comprobaciones|completa)$ ]] || fail 'Fase de recuperación inválida.'
    local status
    status=$(state_get status)
    [[ $status == partial || $status == failed || $status == complete ]] || fail 'Estado de recuperación inválido.'
    [[ $status != complete ]] || fail 'Ticketyn ya está instalado. install.sh no actualiza instalaciones completas.'
    RECOVERING=1
    info "Instalación parcial reconocida: fase $PHASE; puerto HTTP $HTTP_PORT. Se conservarán todos los datos."
}
init_state() {
    local destination=$INSTALL_STATE staging
    require_absent "$destination" 'Apareció un estado de instalación inesperado.'
    staging=$(mktemp -d "$(dirname "$destination")/.ticketyn-state.XXXXXXXX")
    INSTALL_STATE=$staging
    chown root:root "$staging"
    INSTALL_TOKEN=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
    [[ $INSTALL_TOKEN =~ ^[0-9a-f]{32}$ ]] || fail 'No se pudo crear token de recuperación.'
    state_put format 1; state_put version "$VERSION"; state_put source "$SOURCE_HASH"
    state_put token "$INSTALL_TOKEN"; state_put port "$HTTP_PORT"
    state_put new_nginx "$NEW_NGINX"; state_put default_absent "$DEFAULT_ABSENT"
    RELEASE_READY=0; state_put release_ready 0
    state_put phase inicial; state_put status partial
    mv -Tn -- "$staging" "$destination"
    [[ ! -d $staging ]] || fail 'Apareció un estado inesperado; no se reemplaza.'
    INSTALL_STATE=$destination
}
phase() { PHASE=$1; state_put phase "$1"; state_put status partial; }
path_signature() {
    local digest=-
    if [[ -L $1 ]]; then digest=$(readlink -- "$1" | sha256sum | cut -d ' ' -f1)
    elif [[ -f $1 ]]; then digest=$(sha256sum -- "$1" | cut -d ' ' -f1); fi
    printf '%s %s' "$(stat -c '%d:%i:%w' -- "$1")" "$digest"
}
record_owned() { state_put "owned-$1" "$(path_signature "$2" "$1")"; }
is_owned() {
    [[ -e $2 || -L $2 ]] || return 1
    [[ -f $INSTALL_STATE/owned-$1 ]] || return 1
    [[ $(state_get "owned-$1") == "$(path_signature "$2" "$1")" ]]
}
require_owned() { is_owned "$1" "$2" || fail "Recurso no reconocido o modificado: $2. No se sobrescribe ni elimina."; }
allow_owned_or_absent() {
    if [[ -e $2 || -L $2 ]]; then
        [[ ${RECOVERING:-0} == 1 ]] || fail "Ya existe $2; se conserva."
        require_owned "$1" "$2"
    fi
}
publish_file() {
    # Enlace duro exclusivo: publica el inode preparado sin reemplazar un destino.
    # Origen debe estar en el mismo filesystem que destino.
    record_owned "$1" "$2"
    ln -T -- "$2" "$3" || fail "Apareció un destino inesperado: $3; no se reemplaza."
    unlink -- "$2"
}
create_owned_link() {
    local temporary
    temporary=$(mktemp -d "$(dirname -- "$3")/.ticketyn-link.XXXXXXXX")
    ln -sT -- "$2" "$temporary/link"
    record_owned "$1" "$temporary/link"
    ln -PT -- "$temporary/link" "$3" || fail "Apareció un destino inesperado: $3; no se reemplaza."
    unlink -- "$temporary/link"
    rmdir -- "$temporary"
}
release_tar() {
    tar -C "$SOURCE" --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='.env*' --exclude='*.egg-info' \
        --exclude='.git' --exclude='node_modules' --exclude='.pytest_cache' --exclude='.mypy_cache' --exclude='.ruff_cache' \
        -cf - src alembic alembic.ini pyproject.toml requirements.lock LICENSE README.md deploy frontend/dist
}
validate_release_source() {
    local root=$1 entry base
    local trees=(src alembic deploy frontend/dist)
    [[ ! -L $root/frontend ]] || fail "Symlink no permitido: $root/frontend"
    for entry in "${trees[@]}"; do
        [[ -d $root/$entry && ! -L $root/$entry ]] || fail "Árbol inesperado del release: $root/$entry"
    done
    while IFS= read -r -d '' entry; do
        base=${entry##*/}; base=${base,,}
        case "$base" in
            .git|.env*|*.key|*.pem|*.p12|*.pfx|id_rsa*|id_dsa*|id_ecdsa*|id_ed25519*|*.dump|*.sql|*.sql.gz|*.dump.gz|*.pgdump|*.bak|*.bak.*|*.backup|*.old|backups|backup*.tar*)
                fail "Contenido sospechoso del release: $entry" ;;
        esac
        [[ ! -L $entry ]] || fail "Symlink no permitido en fuente del release: $entry"
        if [[ -f $entry ]]; then
            [[ $(stat -c %h "$entry") == 1 ]] || fail "Hardlink inesperado en fuente del release: $entry"
            if grep -aqE -- '-----BEGIN ([A-Z0-9 ]*PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----' "$entry"; then
                fail "Posible clave privada en release: $entry"
            fi
        elif [[ ! -d $entry ]]; then fail "Tipo de archivo inesperado en release: $entry"; fi
    done < <(find "${trees[@]/#/$root/}" \
        \( -type d \( -name node_modules -o -name __pycache__ -o -name '*.egg-info' -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune \) -o -print0)
    for entry in alembic.ini pyproject.toml requirements.lock LICENSE README.md; do
        [[ -f $root/$entry && ! -L $root/$entry ]] || fail "Archivo fuente inesperado: $root/$entry"
    done
}
check_existing() {
    allow_owned_or_absent current "$CURRENT_FILE"
    allow_owned_or_absent env "$ENV_FILE"
    allow_owned_or_absent release "$RELEASE"
    [[ ! -e $CURRENT_FILE || ${RELEASE_READY:-0} == 1 ]] || fail 'current existe antes de completar el release; requiere revisión manual.'
    if [[ -e $ENV_FILE ]]; then protected_path "$ENV_FILE" 600; fi
    local directory mode
    for directory in /opt/ticketyn /opt/ticketyn/releases /etc/ticketyn /var/backups/ticketyn; do
        [[ ! -L $directory ]] || fail "Ruta de instalación inesperada (symlink): $directory."
        if [[ -e $directory ]]; then
            [[ -d $directory && $(stat -c %u "$directory") == 0 ]] || fail "Directorio ajeno: $directory."
            mode=$(stat -c %a "$directory")
            (( (8#$mode & 0022) == 0 )) || fail "Permisos inseguros en $directory."
        fi
    done
    local file
    for file in /etc/systemd/system/ticketyn.service /etc/nginx/sites-available/ticketyn /etc/nginx/sites-enabled/ticketyn; do
        case "$file" in
            */ticketyn.service) allow_owned_or_absent unit "$file" ;;
            */sites-available/*) allow_owned_or_absent nginx "$file" ;;
            *) allow_owned_or_absent nginx-link "$file" ;;
        esac
    done
    if systemctl cat ticketyn.service >/dev/null 2>&1; then require_owned unit /etc/systemd/system/ticketyn.service; fi
    if [[ ${RECOVERING:-0} == 0 ]] && command -v psql >/dev/null && getent passwd postgres >/dev/null; then
        if psql_admin -c 'SELECT 1' >/dev/null 2>&1; then
            [[ $(psql_admin -c "SELECT (EXISTS(SELECT FROM pg_roles WHERE rolname='ticketyn') OR EXISTS(SELECT FROM pg_database WHERE datname='ticketyn'))::int") == 0 ]] || fail 'Ya existe rol o DB ticketyn; no se reinstala ni se cambia su contraseña.'
        fi
    fi
    if getent passwd ticketyn >/dev/null; then
        local uid shell home
        IFS=: read -r _ _ uid _ _ home shell < <(getent passwd ticketyn)
        [[ $uid -gt 0 && $uid -lt 1000 && $shell == */nologin && $home == /nonexistent ]] || fail 'El usuario ticketyn existente no es compatible; no se modifica.'
        [[ $(id -gn ticketyn) == ticketyn ]] || fail 'El grupo primario de ticketyn no es compatible.'
    elif getent group ticketyn >/dev/null; then
        fail 'Existe un grupo ticketyn sin el usuario esperado; requiere revisión manual.'
    fi
}
psql_admin() { runuser -u postgres -- psql -X -h /var/run/postgresql -U postgres -p 5432 --set ON_ERROR_STOP=1 -At postgres "$@"; }
prepare_database() {
    systemctl enable --now postgresql
    psql_admin -c 'SELECT 1' >/dev/null || fail 'PostgreSQL local en 5432 no está disponible.'
    local existing locale_name binds address ipv4=0
    binds=$(ss -H -ltn 'sport = :5432' | awk '{print $4}')
    for address in $binds; do
        case "$address" in
            127.0.0.1:5432) ipv4=1 ;;
            '[::1]:5432'|'::1:5432') ;;
            *) fail 'PostgreSQL escucha fuera de localhost; no se altera su configuración.' ;;
        esac
    done
    [[ $ipv4 == 1 ]] || fail 'PostgreSQL debe escuchar en 127.0.0.1:5432. Revisa su configuración local.'
    locale_name=$(locale -a | awk 'tolower($0) ~ /^c\.utf-?8$/ {print; exit}')
    [[ -n $locale_name ]] || fail 'No se encontró locale C.UTF-8 disponible.'
    ensure_credentials
    local role_count role_owner db_count db_owner
    role_count=$(psql_admin -c "SELECT count(*) FROM pg_roles WHERE rolname='ticketyn'")
    if [[ $role_count == 0 ]]; then
        # CREATE + COMMENT en la misma transacción: no queda un rol sin prueba de propiedad.
        psql_admin -c "BEGIN; CREATE ROLE ticketyn LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE; COMMENT ON ROLE ticketyn IS 'ticketyn-install:$INSTALL_TOKEN'; COMMIT" >/dev/null
    else
        role_owner=$(psql_admin -c "SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname='ticketyn' AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole")
        [[ $role_owner == "ticketyn-install:$INSTALL_TOKEN" ]] || fail 'El rol ticketyn no pertenece a esta instalación; no se cambia su contraseña.'
    fi
    if [[ -e $INSTALL_STATE/password_ready || -L $INSTALL_STATE/password_ready ]]; then
        [[ $(state_get password_ready) == 1 ]] || fail 'Estado de contraseña inválido.'
    else
        set_database_password
        state_put password_ready 1
    fi
    unset DB_PASSWORD
    db_count=$(psql_admin -c "SELECT count(*) FROM pg_database WHERE datname='ticketyn'")
    if [[ $db_count == 0 ]]; then
        runuser -u postgres -- createdb -h /var/run/postgresql -U postgres -p 5432 --owner=ticketyn --encoding=UTF8 \
            --template=template0 --locale="$locale_name" ticketyn
        # CREATE DATABASE no admite transacción. Si se interrumpe antes del COMMENT,
        # se requiere revisión manual; nunca asumir propiedad de una DB desconocida.
        psql_admin -c "COMMENT ON DATABASE ticketyn IS 'ticketyn-install:$INSTALL_TOKEN'" >/dev/null
    fi
    db_owner=$(psql_admin -c "SELECT shobj_description(oid,'pg_database') || ':' || pg_get_userbyid(datdba) || ':' || pg_encoding_to_char(encoding) FROM pg_database WHERE datname='ticketyn'")
    [[ $db_owner == "ticketyn-install:$INSTALL_TOKEN:ticketyn:UTF8" ]] || fail 'La DB ticketyn no tiene identidad/propietario/encoding esperado; no se modifica.'
}
ensure_credentials() {
    if [[ -e $ENV_FILE || -L $ENV_FILE ]]; then
        require_owned env "$ENV_FILE"; protected_path "$ENV_FILE" 600
        local line
        line=$(cat -- "$ENV_FILE")
        [[ $line =~ ^DATABASE_URL=postgresql\+psycopg://ticketyn:([0-9a-f]{64})@127\.0\.0\.1:5432/ticketyn$ ]] || fail 'Configuración de recuperación inesperada; no se ejecuta como código.'
        unset DB_PASSWORD
        DB_PASSWORD=${BASH_REMATCH[1]}
    else
        unset DB_PASSWORD
        DB_PASSWORD=$(openssl rand -hex 32)
        [[ $DB_PASSWORD =~ ^[0-9a-f]{64}$ ]] || fail 'No se pudo generar la contraseña segura.'
        # Único archivo que contiene la contraseña: destino final exclusivo, no temporal.
        (umask 077; set -o noclobber; printf 'DATABASE_URL=postgresql+psycopg://ticketyn:%s@127.0.0.1:5432/ticketyn\n' "$DB_PASSWORD" > "$ENV_FILE") \
            || fail 'Apareció configuración inesperada; no se sobrescribe.'
        chown root:root "$ENV_FILE"
        record_owned env "$ENV_FILE"
    fi
}
set_database_password() {
    # Contraseña únicamente por stdin. --wait propaga el exit code incluso si setsid bifurca.
    printf '%s\n%s\n' "$DB_PASSWORD" "$DB_PASSWORD" | env PGOPTIONS='-c password_encryption=scram-sha-256' \
        runuser -u postgres -- setsid --wait psql -X -h /var/run/postgresql -U postgres -p 5432 \
        --set ON_ERROR_STOP=1 -q -c '\password ticketyn' postgres >/dev/null 2>&1 \
        || fail 'No se pudo establecer la contraseña PostgreSQL. No se continúa creando la DB; el estado permite reintentar.'
}
copy_release() {
    validate_release_source "$SOURCE"
    [[ $(release_tar | sha256sum | cut -d ' ' -f1) == "$SOURCE_HASH" ]] || fail 'La fuente cambió durante la instalación; no se continúa.'
    release_tar | tar -C "$RELEASE" -xf -
    validate_release_source "$RELEASE"
    local copied_hash
    copied_hash=$(SOURCE=$RELEASE; release_tar | sha256sum | cut -d ' ' -f1)
    [[ $copied_hash == "$SOURCE_HASH" ]] || fail 'El release copiado no coincide con la fuente verificada.'
}
verify_database_head() {
    (cd "$RELEASE"; DATABASE_URL=$(cat -- "$ENV_FILE"); export DATABASE_URL=${DATABASE_URL#DATABASE_URL=}
        "$RELEASE/.venv/bin/python" -c 'from ticketyn.main import app'
        "$RELEASE/.venv/bin/alembic" -c "$RELEASE/alembic.ini" upgrade head
        "$RELEASE/.venv/bin/python" - <<'PYTHON'
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
import os
config = Config('alembic.ini')
expected = set(ScriptDirectory.from_config(config).get_heads())
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as connection:
    if set(MigrationContext.configure(connection).get_current_heads()) != expected:
        raise SystemExit('Error: la DB no está en HEAD')
engine.dispose()
print('✓ Revisión Alembic verificada en HEAD')
PYTHON
    )
}
prepare_release() {
    if [[ -e $RELEASE || -L $RELEASE ]]; then
        require_owned release "$RELEASE"
        [[ -d $RELEASE && ! -L $RELEASE ]] || fail 'Release inesperado.'
    else
        install -d -m 0755 "$RELEASES_DIR"
        mkdir -m 0700 -- "$RELEASE" || fail 'Apareció un release inesperado.'
        record_owned release "$RELEASE"
    fi
    if [[ $RELEASE_READY == 0 ]]; then
        # Solo reparar el release propio aún no publicado. No borrar directorios persistentes.
        copy_release
        python3 -m venv "$RELEASE/.venv"
        "$RELEASE/.venv/bin/python" -m pip install --no-cache-dir -r "$RELEASE/requirements.lock"
        "$RELEASE/.venv/bin/python" -m pip install --no-cache-dir --no-deps "$RELEASE"
        validate_release_source "$RELEASE"
        chown -RP root:root "$RELEASE"
        chmod -R go-w,a+rX "$RELEASE"
    fi
    "$RELEASE/.venv/bin/python" -m pip check
    (cd /; "$RELEASE/.venv/bin/python" -c 'import ticketyn')
    ensure_credentials; unset DB_PASSWORD
    verify_database_head
    RELEASE_READY=1; state_put release_ready 1
    if [[ -e $CURRENT_FILE || -L $CURRENT_FILE ]]; then
        require_owned current "$CURRENT_FILE"
        [[ -L $CURRENT_FILE && $(readlink "$CURRENT_FILE") == "$RELEASE" ]] || fail 'current inesperado; no se reemplaza.'
    else
        create_owned_link current "$RELEASE" "$CURRENT_FILE"
    fi
}
capture_packaged_default() {
    [[ $NEW_NGINX == 1 && $DEFAULT_ABSENT == 1 && -L $NGINX_DEFAULT_LINK ]] || return 0
    if [[ -f $INSTALL_STATE/owned-default ]]; then
        require_owned default "$NGINX_DEFAULT_LINK"
        return 0
    fi
    [[ ${RECOVERING:-0} == 0 ]] || fail 'Default sin prueba de propiedad tras apt interrumpido; revisar manualmente, no se elimina.'
    local checksum identity
    identity=$(path_signature "$NGINX_DEFAULT_LINK")
    checksum=$(dpkg-query -W -f='${Conffiles}\n' nginx-common | awk '$1 == "/etc/nginx/sites-available/default" {print $2}')
    [[ -n $checksum && $(readlink -f "$NGINX_DEFAULT_LINK") == "$NGINX_DEFAULT_FILE" && \
        $(md5sum -- "$NGINX_DEFAULT_FILE" | awk '{print $1}') == "$checksum" && \
        $(path_signature "$NGINX_DEFAULT_LINK") == "$identity" ]] || fail 'Default Nginx inesperado/modificado; no se registra como propio.'
    state_put owned-default "$identity"
}
remove_new_packaged_default() {
    [[ $NEW_NGINX == 1 && $DEFAULT_ABSENT == 1 ]] || return 0
    local checksum actual identity
    [[ -L $NGINX_DEFAULT_LINK ]] || return 0
    require_owned default "$NGINX_DEFAULT_LINK"
    [[ $(readlink -f "$NGINX_DEFAULT_LINK") == "$NGINX_DEFAULT_FILE" ]] || fail 'Default Nginx inesperado; no se elimina.'
    identity=$(stat -c '%d:%i' "$NGINX_DEFAULT_LINK")
    checksum=$(dpkg-query -W -f='${Conffiles}\n' nginx-common | awk '$1 == "/etc/nginx/sites-available/default" {print $2}')
    actual=$(md5sum -- "$NGINX_DEFAULT_FILE" | awk '{print $1}')
    [[ -n $checksum && $checksum == "$actual" ]] || fail 'El sitio default generado no coincide con el paquete; no se modifica.'
    # Última revalidación inmediatamente antes de unlink. No cambiar Nginx concurrentemente.
    [[ -L $NGINX_DEFAULT_LINK && $(stat -c '%d:%i' "$NGINX_DEFAULT_LINK") == "$identity" && \
        $(readlink -f "$NGINX_DEFAULT_LINK") == "$NGINX_DEFAULT_FILE" && \
        $(md5sum -- "$NGINX_DEFAULT_FILE" | awk '{print $1}') == "$checksum" ]] || fail 'Default cambió durante la comprobación; no se elimina.'
    unlink -- "$NGINX_DEFAULT_LINK"
    info 'Se deshabilitó únicamente el enlace default recién generado por apt; el archivo se conserva.'
}
render_nginx() {
    # IPv4 obligatorio. No se exige IPv6 para la instalación inicial.
    sed -e '/^[[:space:]]*listen \[::\]:80;/d' -e "s/listen 80;/listen $HTTP_PORT;/" "$1"
}
configure_services() {
    remove_new_packaged_default
    nginx_port_configured "$HTTP_PORT" && fail "Otro sitio Nginx usa el puerto $HTTP_PORT."
    if listening_port "$HTTP_PORT"; then
        [[ ( $NEW_NGINX == 1 && $DEFAULT_ABSENT == 1 && $HTTP_PORT == 80 ) || \
            ( ${RECOVERING:-0} == 1 && -e $NGINX_SITE ) ]] && \
            ss -H -ltnp "sport = :$HTTP_PORT" | awk '$0 !~ /"nginx"/ {bad=1} END {exit bad}' \
            || fail "El puerto $HTTP_PORT ya no está disponible."
    fi
    local temporary
    if [[ -e $UNIT_FILE || -L $UNIT_FILE ]]; then
        require_owned unit "$UNIT_FILE"
        cmp -s "$UNIT_FILE" "$RELEASE/deploy/systemd/ticketyn.service" || fail 'Unidad diferente a la del release; no se reemplaza.'
    else
        temporary=$(mktemp "$(dirname "$UNIT_FILE")/.ticketyn-unit.XXXXXXXX")
        install -m 0644 "$RELEASE/deploy/systemd/ticketyn.service" "$temporary"
        publish_file unit "$temporary" "$UNIT_FILE"
    fi
    if [[ -e $NGINX_SITE || -L $NGINX_SITE ]]; then require_owned nginx "$NGINX_SITE"
    else
        temporary=$(mktemp "$(dirname "$NGINX_SITE")/.ticketyn-nginx.XXXXXXXX")
        render_nginx "$RELEASE/deploy/nginx/ticketyn.conf" > "$temporary"
        chmod 0644 "$temporary"
        publish_file nginx "$temporary" "$NGINX_SITE"
    fi
    if [[ -e $NGINX_LINK || -L $NGINX_LINK ]]; then require_owned nginx-link "$NGINX_LINK"
    else create_owned_link nginx-link "$NGINX_SITE" "$NGINX_LINK"; fi
    nginx -t || fail 'Nginx rechazó la configuración; no se recarga. Reejecuta desde el mismo árbol para recuperar la instalación parcial.'
    systemctl daemon-reload
    systemctl enable --now ticketyn
    systemctl enable nginx
    if systemctl is-active --quiet nginx; then systemctl reload nginx; else systemctl start nginx; fi
}
check_backend_socket() {
    local addresses
    addresses=$(ss -H -ltn 'sport = :8000' | awk '{print $4}')
    [[ $addresses == 127.0.0.1:8000 ]] || fail "Uvicorn no escucha exclusivamente en 127.0.0.1:8000."
}
final_checks() {
    systemctl is-active --quiet nginx || fail 'Nginx no está activo.'
    local base="http://127.0.0.1:$HTTP_PORT" attempt ready=0 asset
    for attempt in {1..30}; do
        if curl -fsS --max-time 3 "$base/health" > "$WORK/health.json"; then ready=1; break; fi
        sleep 1
    done
    [[ $ready == 1 ]] || fail 'El health check mediante Nginx no responde.'
    systemctl is-active --quiet ticketyn || fail 'ticketyn.service no está activo.'
    curl -fsS --max-time 10 "$base/" > "$WORK/index.html" || fail 'El frontend no responde mediante Nginx.'
    cmp -s "$WORK/index.html" "$RELEASE/frontend/dist/index.html" || fail 'Nginx no sirve el frontend esperado.'
    for asset in $(frontend_assets "$RELEASE/frontend/dist/index.html"); do
        curl -fsS --max-time 10 "$base$asset" > "$WORK/asset" || fail "No se sirve el asset $asset."
        cmp -s "$WORK/asset" "$RELEASE/frontend/dist$asset" || fail "Asset incorrecto: $asset."
    done
    curl -fsS --max-time 10 "$base/api/customers" > "$WORK/customers.json" || fail 'La API/DB no responde mediante Nginx.'
    python3 - "$WORK" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
if json.loads((root/'health.json').read_text()) != {'status': 'ok'}:
    raise SystemExit('Error: respuesta health inválida')
if not isinstance(json.loads((root/'customers.json').read_text()), list):
    raise SystemExit('Error: respuesta API inválida')
PY
    check_backend_socket
    [[ $(readlink -f "$CURRENT_FILE") == "$RELEASE" && -s $CURRENT_FILE/frontend/dist/index.html ]] || fail 'Release activo/frontend incorrecto.'
}
show_success() {
    local address suffix
    address=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1);exit}}' || true)
    [[ -n $address && $address != 127.* ]] || address=$(hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i !~ /:/ && $i !~ /^127\./) {print $i;exit}}' || true)
    address=${address:-'<IP-del-servidor>'}
    suffix=":$HTTP_PORT"; [[ $HTTP_PORT != 80 ]] || suffix=''
    info "✓ PostgreSQL configurado
✓ Base de datos preparada
✓ Migraciones aplicadas
✓ Ticketyn iniciado
✓ Nginx configurado
✓ Frontend verificado
✓ API verificada

Ticketyn se instaló correctamente.
URL: http://$address$suffix

Esta instalación utiliza HTTP y no incorpora autenticación.
Para exposición fuera de una red controlada configura HTTPS
y los controles de acceso correspondientes."
}
policy_content() {
    printf '%s\n' '#!/bin/sh' '# Temporal Ticketyn v2; sin lock activo no bloquea servicios.' "# Instalación: $INSTALL_TOKEN" \
        "flock -E 101 -n '$INSTALL_LOCK' -c :" 'code=$?' '[ "$code" -eq 101 ] && exit 101' 'exit 0'
}
recover_policy() {
    [[ -e $POLICY_FILE || -L $POLICY_FILE ]] || return 0
    if [[ -f $INSTALL_STATE/owned-policy ]]; then
        require_owned policy "$POLICY_FILE"
        [[ -f $POLICY_FILE && ! -L $POLICY_FILE && $(cat "$POLICY_FILE") == "$(policy_content)" ]] || fail 'Política temporal modificada; se conserva para revisión manual.'
        unlink -- "$POLICY_FILE"
        info 'Política temporal propia recuperada; no se cambió una política del administrador.'
    fi
}
cleanup() {
    local code=$?
    trap - EXIT
    if [[ ${STATE_ACTIVE:-0} == 1 ]]; then
        if [[ $code != 0 ]]; then
            state_put status failed || true
            printf 'Instalación parcial conservada (fase %s). Reejecuta el mismo install.sh/árbol; no borres la DB.\n' "${PHASE:-inicial}" >&2
        fi
        if [[ ${OWN_POLICY:-0} == 1 ]]; then
            # Si alguien la cambió, nunca eliminarla basándose solo en el nombre.
            if is_owned policy "$POLICY_FILE"; then unlink -- "$POLICY_FILE"
            else printf 'Advertencia: policy-rc.d cambió; se conserva.\n' >&2; fi
        fi
    fi
    [[ -z ${WORK:-} ]] || rm -rf -- "$WORK"
    exit "$code"
}
install_dependencies() {
    OWN_POLICY=0
    recover_policy
    if [[ ! -e $POLICY_FILE && ! -L $POLICY_FILE ]]; then
        local temporary
        temporary=$(mktemp "$(dirname "$POLICY_FILE")/.ticketyn-policy.XXXXXXXX")
        policy_content > "$temporary"; chmod 0755 "$temporary"
        OWN_POLICY=1
        publish_file policy "$temporary" "$POLICY_FILE"
    fi
    export DEBIAN_FRONTEND=noninteractive
    apt-get update 9>&-
    apt-get install -y git python3 python3-venv postgresql postgresql-client nginx openssl curl iproute2 locales util-linux ca-certificates 9>&-
    capture_packaged_default
    if [[ $OWN_POLICY == 1 ]]; then
        recover_policy
        OWN_POLICY=0
    fi
}
main() {
    require_root
    STATE_ACTIVE=0; OWN_POLICY=0; WORK=''; PHASE=preflight
    unset DB_PASSWORD
    trap 'printf "Error: la instalación falló en la línea %s. Se conservan datos y archivos; revisa la instalación parcial antes de reintentar.\n" "$LINENO" >&2' ERR
    umask 022
    unset DATABASE_URL PYTHONPATH PYTHONHOME
    local variable
    for variable in "${!PG@}"; do unset "$variable"; done
    SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
    check_os
    command -v systemctl >/dev/null && [[ -d /run/systemd/system ]] || fail 'Se requiere systemd en ejecución.'
    systemctl show-environment >/dev/null || fail 'No se puede comunicar con systemd.'
    command -v apt-get >/dev/null || fail 'No se encontró apt-get.'
    command -v flock >/dev/null || fail 'Falta flock (util-linux), requerido para evitar instalaciones simultáneas.'
    [[ -r /proc/net/tcp ]] || fail 'No se pueden comprobar los puertos TCP locales.'
    INSTALL_LOCK=/run/ticketyn-install.lock
    CURRENT_FILE=/opt/ticketyn/current
    RELEASES_DIR=/opt/ticketyn/releases
    INSTALL_STATE=/etc/ticketyn/install-state
    ENV_FILE=/etc/ticketyn/ticketyn.env
    UNIT_FILE=/etc/systemd/system/ticketyn.service
    NGINX_SITE=/etc/nginx/sites-available/ticketyn
    NGINX_LINK=/etc/nginx/sites-enabled/ticketyn
    NGINX_DEFAULT_LINK=/etc/nginx/sites-enabled/default
    NGINX_DEFAULT_FILE=/etc/nginx/sites-available/default
    POLICY_FILE=/usr/sbin/policy-rc.d
    check_project
    validate_release_source "$SOURCE"
    SOURCE_HASH=$(release_tar | sha256sum | cut -d ' ' -f1)
    VERSION=$(project_version "$SOURCE")
    RELEASE="/opt/ticketyn/releases/$VERSION"
    load_state
    check_existing
    if listening_port 8000; then
        [[ $RECOVERING == 1 && -L $CURRENT_FILE ]] || fail 'El puerto backend 8000 está ocupado; no se altera ese servicio.'
        require_owned unit "$UNIT_FILE"; check_backend_socket
        systemctl is-active --quiet ticketyn || fail 'El socket 8000 no corresponde a una recuperación del servicio activo.'
    fi
    if [[ $RECOVERING == 0 ]]; then choose_port; fi
    confirm_install
    WORK=$(mktemp -d /tmp/ticketyn-install.XXXXXXXX)
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    [[ ! -L $INSTALL_LOCK ]] || fail 'Lock inesperado (symlink); no se abre.'
    if [[ -e $INSTALL_LOCK ]]; then
        [[ -f $INSTALL_LOCK && $(stat -c %u "$INSTALL_LOCK") == 0 ]] || fail 'Lock ajeno; no se modifica.'
    else
        (umask 077; set -o noclobber; : > "$INSTALL_LOCK") || fail 'Apareció un lock inesperado.'
    fi
    exec 9>>"$INSTALL_LOCK"
    flock -n 9 || fail 'Hay otra instalación Ticketyn en ejecución.'
    # Volver a leer el estado bajo lock: otro instalador pudo terminar entretanto.
    load_state
    check_existing
    if [[ $RECOVERING == 0 ]]; then
        NEW_NGINX=1; command -v nginx >/dev/null && NEW_NGINX=0
        DEFAULT_ABSENT=0
        [[ -e $NGINX_DEFAULT_LINK || -L $NGINX_DEFAULT_LINK || -e $NGINX_DEFAULT_FILE ]] || DEFAULT_ABSENT=1
        install -d -m 0755 /etc/ticketyn
        init_state
    fi
    STATE_ACTIVE=1
    phase paquetes
    info 'Instalando dependencias del sistema (sin Node/npm)...'
    install_dependencies
    python3 -c 'import sys; sys.version_info >= (3,11) or sys.exit("Se requiere Python >= 3.11")'
    if ! getent passwd ticketyn >/dev/null; then
        useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin ticketyn
    fi
    install -d -m 0700 /var/backups/ticketyn
    phase database
    info 'Preparando PostgreSQL y configuración protegida...'
    prepare_database
    phase release
    info 'Preparando release, Python y migraciones...'
    prepare_release
    phase servicios
    info 'Configurando systemd y Nginx...'
    configure_services
    phase comprobaciones
    info 'Comprobando servicios, frontend y API...'
    final_checks
    state_put phase completa; state_put status complete
    show_success
}
# Se puede cargar para probar funciones puras/mocks sin modificar el host.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
