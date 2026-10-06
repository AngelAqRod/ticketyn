#!/usr/bin/env bash
# Restauración conservadora de ticketyn-backup-v1. Nunca cambia current.
set +x
set -Eeuo pipefail

restore_fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
restore_args() {
    REPLACE=0
    if [[ ${1:-} == --replace ]]; then REPLACE=1; shift; fi
    [[ $# == 1 && -n $1 && $1 != -* ]] || restore_fail 'Uso: ./restore.sh [--replace] /ruta/backup.tar'
    ARCHIVE=$1
}
restore_pg() {
    local tool=$1; shift
    runuser -u postgres -- env -i PATH=/usr/bin:/bin HOME=/nonexistent PGPASSFILE=/dev/null \
        PGAPPNAME=ticketyn-restore "$tool" --host=/var/run/postgresql --port=5432 \
        --username=postgres --no-password "$@"
}
restore_sql() { restore_pg psql --dbname=postgres -X -At --set=ON_ERROR_STOP=1 "$@"; }
restore_query() { restore_sql -c "$1" 2> "$WORK/diagnostic.log"; }
restore_oid() { restore_query "SELECT oid FROM pg_database WHERE datname='$1'"; }
restore_record() {
    # Estado sin contraseñas. Configuración anterior se conserva separada y privada.
    printf 'phase=%s\noperation=%s\nstaging_database=%s\nprevious_database=%s\noriginal_oid=%s\nstaging_oid=%s\nsafety_backup=%s\n' \
        "$PHASE" "$TOKEN" "$STAGE" "$PREVIOUS" "${ORIGINAL_OID:-}" "${STAGE_OID:-}" "${SAFETY_BACKUP:-}" > "$STATE/progress.tmp"
    chmod 0600 "$STATE/progress.tmp"
    mv -T -- "$STATE/progress.tmp" "$STATE/progress.txt"
    sync -f "$STATE"
}
restore_cleanup() {
    local code=$?
    trap - EXIT ERR INT TERM
    if [[ $code != 0 && ${MUTATING:-0} == 1 ]]; then
        printf 'Restauración incompleta. Fase: %s. Estado privado: %s\n' "$PHASE" "$STATE" >&2
        # Única recuperación automática: todavía NO se cambió el nombre/credencial/config.
        # Después de intentar cutover (incluido resultado ambiguo), nunca adivinar.
        if [[ ${CUTOVER_ATTEMPTED:-0} == 0 && ${BLOCK_ATTEMPTED:-0} == 1 && ${ORIGINAL_OID:-} != '' && \
            $(restore_oid ticketyn) == "$ORIGINAL_OID" && \
            $(sha256sum "$CONFIG_FILE" | cut -d ' ' -f1) == "$OLD_CONFIG_HASH" && \
            $(readlink -e "$CURRENT_FILE") == "$RELEASE" ]]; then
            if restore_sql -c 'ALTER DATABASE ticketyn ALLOW_CONNECTIONS true' > /dev/null 2> "$STATE/diagnostic.log"; then
                if [[ ${WAS_ACTIVE:-0} == 1 ]]; then
                    systemctl start ticketyn > /dev/null 2>&1 || printf 'No se pudo reiniciar la instalación anterior; revisar manualmente.\n' >&2
                fi
                printf 'La DB anterior sigue intacta bajo ticketyn; se habilitaron sus conexiones.\n' >&2
            fi
        elif [[ ${CUTOVER_ATTEMPTED:-0} == 1 ]]; then
            systemctl stop ticketyn >/dev/null 2>&1 || printf 'No se pudo detener Ticketyn; impedir escrituras antes de recuperar.\n' >&2
            printf 'No se realiza rollback automático después del cutover. Conservar DB anterior y backup de seguridad; revisar RECUPERACION.txt.\n' >&2
        fi
        printf 'No elimines el estado ni las DB conservadas sin revisar la operación.\n' >&2
    fi
    if [[ -n ${WORK:-} && $WORK == /tmp/ticketyn-restore.* && -d $WORK && ! -L $WORK && \
        $(backup_identity "$WORK") == "${WORK_ID:-}" ]]; then rm -rf -- "$WORK"; fi
    exit "$code"
}
restore_validate_dump() {
    env -i PATH=/usr/bin:/bin pg_restore --file=/dev/null "$1/database.dump" \
        > /dev/null 2> "$WORK/diagnostic.log" || restore_fail 'Dump PostgreSQL inválido o ilegible.'
}
restore_validate() {
    local tool
    for tool in python3 runuser setsid psql pg_restore systemctl curl ss flock mktemp sha256sum sync locale; do
        command -v "$tool" >/dev/null || restore_fail "Falta herramienta: $tool"
    done
    backup_secure_directory "$CONFIG_DIR"
    backup_check_config "$CONFIG_FILE"
    backup_release_version
    backup_secure_file "$UNIT_FILE"
    grep -qFx 'User=ticketyn' "$UNIT_FILE" && grep -qFx 'Group=ticketyn' "$UNIT_FILE" && \
        grep -qFx 'EnvironmentFile=/etc/ticketyn/ticketyn.env' "$UNIT_FILE" && \
        grep -q -- '--host 127.0.0.1 --port 8000' "$UNIT_FILE" || restore_fail 'Unidad Ticketyn incompatible.'
    backup_secure_file "$NGINX_SITE"
    [[ -L $NGINX_LINK && $(readlink -e "$NGINX_LINK") == "$NGINX_SITE" ]] || restore_fail 'Sitio Nginx Ticketyn no habilitado de forma esperada.'
    systemctl is-active --quiet nginx || restore_fail 'Nginx debe estar activo antes de restaurar.'
    HTTP_PORT=$(python3 -I "$SUPPORT" port "$NGINX_SITE") || restore_fail 'No se pudo identificar el puerto HTTP.'
    [[ ! -e $STATE && ! -L $STATE ]] || restore_fail "Hay una operación anterior pendiente en $STATE; requiere revisión manual."
    python3 -I "$SUPPORT" validate "$ARCHIVE" "$CONTENT" || restore_fail 'Backup inválido; no se modificó la instalación.'
    restore_validate_dump "$CONTENT"
    [[ -x $RELEASE/.venv/bin/python ]] || restore_fail 'No existe Python del release instalado.'
    HEAD=$("$RELEASE/.venv/bin/python" -I "$SUPPORT" head "$RELEASE") || restore_fail 'No se pudo determinar HEAD Alembic sin migrar.'
    [[ $HEAD =~ ^[A-Za-z0-9_]+$ ]] || restore_fail 'HEAD Alembic inválido.'
    SERVER_NUMBER=$(restore_query "SELECT current_setting('server_version_num')") || restore_fail 'PostgreSQL local no accesible.'
    CLIENT_VERSION=$(env -i PATH=/usr/bin:/bin pg_restore --version)
    python3 -I "$SUPPORT" compatibility "$CONTENT" "$RELEASE" "$HEAD" "$SERVER_NUMBER" "$CLIENT_VERSION" \
        || restore_fail 'Versión, metadata, Alembic o PostgreSQL incompatibles.'
    ORIGINAL_OID=$(restore_oid ticketyn) || restore_fail 'No se pudo comprobar existencia de DB.'
    if [[ -n $ORIGINAL_OID ]]; then
        [[ $REPLACE == 1 ]] || restore_fail 'La DB ticketyn ya existe. Se requiere --replace; no se modifica.'
        [[ $(restore_query "SELECT pg_get_userbyid(datdba)||':'||pg_encoding_to_char(encoding) FROM pg_database WHERE datname='ticketyn'") == ticketyn:UTF8 ]] \
            || restore_fail 'Propietario/encoding de DB existente inesperado.'
    elif [[ $REPLACE == 1 ]]; then restore_fail '--replace exige una DB ticketyn existente.'; fi
    if [[ -n $ORIGINAL_OID ]]; then
        [[ $(restore_pg psql --dbname=ticketyn -X -At --set=ON_ERROR_STOP=1 -c 'SELECT version_num FROM public.alembic_version' 2> "$WORK/diagnostic.log") == "$HEAD" ]] || restore_fail 'Alembic de la DB existente no coincide con la instalación.'
    fi
    ROLE_EXISTS=$(restore_query "SELECT count(*) FROM pg_roles WHERE rolname='ticketyn'") || restore_fail 'No se pudo validar el rol.'
    if [[ $ROLE_EXISTS == 1 ]]; then
        [[ $(restore_query "SELECT count(*) FROM pg_roles WHERE rolname='ticketyn' AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND shobj_description(oid,'pg_authid') ~ '^ticketyn-(install|restore):[a-f0-9]{32}$' AND NOT EXISTS(SELECT FROM pg_auth_members WHERE member=pg_roles.oid OR roleid=pg_roles.oid) AND NOT EXISTS(SELECT FROM pg_database WHERE datdba=pg_roles.oid AND datname<>'ticketyn')") == 1 ]] \
            || restore_fail 'Rol ticketyn ajeno o con permisos/relaciones inesperados; no se modifica.'
    elif [[ $ROLE_EXISTS != 0 ]]; then restore_fail 'Estado de rol ambiguo.'; fi
    OLD_CONFIG_HASH=$(sha256sum "$CONFIG_FILE" | cut -d ' ' -f1)
    CONFIG_ID=$(backup_identity "$CONFIG_FILE")
    [[ $ORIGINAL_OID == '' || $ORIGINAL_OID =~ ^[0-9]+$ ]] || restore_fail 'OID inválido.'
}
restore_confirm() {
    [[ $REPLACE == 1 ]] || return 0
    printf 'Se reemplazará la base ticketyn. Se creará un backup de seguridad obligatorio.\n'
    printf 'Escribe exactamente REEMPLAZAR ticketyn para confirmar (Enter cancela): '
    local answer
    read -r answer || restore_fail 'Cancelado: no se recibió confirmación.'
    [[ $answer == 'REEMPLAZAR ticketyn' ]] || restore_fail 'Cancelado: no se confirmó explícitamente el reemplazo.'
}
restore_lock() {
    # Se toma después de validar/confirmar. Misma exclusión que install.sh.
    backup_secure_directory /run
    local lock=/run/ticketyn-install.lock
    if [[ ! -e $lock && ! -L $lock ]]; then
        (umask 077; set -o noclobber; : > "$lock") || restore_fail 'No se pudo crear lock exclusivo.'
    fi
    backup_secure_file "$lock" private
    exec 9>>"$lock"
    flock -n 9 || restore_fail 'Otro instalador/restore está en ejecución.'
}
restore_begin() {
    # Revalidar bajo lock antes de escribir estado o ejecutar backup de seguridad.
    [[ $(restore_oid ticketyn) == "$ORIGINAL_OID" && $(backup_identity "$CURRENT_FILE") == "$CURRENT_ID" && \
        $(backup_identity "$CONFIG_FILE") == "$CONFIG_ID" && \
        $(sha256sum "$CONFIG_FILE" | cut -d ' ' -f1) == "$OLD_CONFIG_HASH" ]] || restore_fail 'La instalación cambió después de validar.'
    TOKEN=$(python3 -I -c 'import secrets; print(secrets.token_hex(16))')
    [[ $TOKEN =~ ^[a-f0-9]{32}$ ]] || restore_fail 'Identificador inválido.'
    STAGE="ticketyn_restore_$TOKEN"; PREVIOUS="ticketyn_previous_$TOKEN"
    [[ $(restore_oid "$STAGE") == '' && $(restore_oid "$PREVIOUS") == '' ]] || restore_fail 'Colisión de nombre DB.'
    mkdir -m 0700 -- "$STATE" || restore_fail 'No se puede crear estado exclusivo.'
    chown root:root "$STATE"
    cp --no-dereference -- "$CONFIG_FILE" "$STATE/previous.env"
    chmod 0600 "$STATE/previous.env"
    chown root:root "$STATE/previous.env"
    PHASE=backup_previo; restore_record
    if [[ $REPLACE == 1 ]]; then
        [[ -x $BACKUP_SCRIPT ]] || restore_fail 'No existe backup.sh ejecutable.'
        "$BACKUP_SCRIPT" > "$WORK/safety.log" 2> "$WORK/diagnostic.log" || restore_fail "Backup de seguridad falló; DB/config intactas. Revisa $STATE."
        SAFETY_BACKUP=$(sed -n 's/^✓ Backup completo y verificado: //p' "$WORK/safety.log")
        [[ $SAFETY_BACKUP == "$SAFETY_DIR/"*.tar && $SAFETY_BACKUP != *$'\n'* ]] || restore_fail 'No se pudo identificar backup de seguridad publicado.'
        backup_secure_file "$SAFETY_BACKUP" private
        python3 -I "$SUPPORT" validate "$SAFETY_BACKUP" "$WORK/safety" || restore_fail 'Backup de seguridad no válido.'
        restore_validate_dump "$WORK/safety"
        cmp -s "$WORK/safety/ticketyn.env" "$STATE/previous.env" || restore_fail 'La configuración cambió durante el backup de seguridad.'
        restore_record
    fi
    cat > "$STATE/RECUPERACION.txt" <<EOF
Operación: $TOKEN
DB original OID: $ORIGINAL_OID
DB original conservada tras cutover: $PREVIOUS (conexiones deshabilitadas)
DB preparada: $STAGE
Backup de seguridad: ${SAFETY_BACKUP:-no aplica; DB inicialmente inexistente}
Config anterior: previous.env (privada)
NO ejecutar restore de nuevo ni borrar este estado sin revisar progress.txt y los OIDs.
Antes del cutover, ticketyn sigue siendo la DB original; es seguro recuperarla solo
si se comprueba su OID, configuración/credenciales originales y ausencia de cutover.
Tras cutover/fallo de arranque, detener Ticketyn y excluir escritores externos antes
de decidir recuperar DB anterior + previous.env + contraseña o el backup de seguridad.
No renombrar/borrar una DB si su identidad no coincide. No se hace rollback automático.
La DB anterior contiene también las escrituras posteriores al backup previo.
En éxito, conservar backup previo; la DB anterior y este estado se retiran SOLO
tras verificación/manual y una decisión explícita. Restore no elimina datos de negocio.
EOF
    cp -- "$CONTENT/metadata.txt" "$STATE/source-metadata.txt"
    restore_record
}
restore_disable_original() {
    if [[ -n $ORIGINAL_OID ]]; then
        [[ $(restore_oid ticketyn) == "$ORIGINAL_OID" ]] || restore_fail 'La DB original cambió.'
        BLOCK_ATTEMPTED=1
        restore_sql -c 'ALTER DATABASE ticketyn ALLOW_CONNECTIONS false' > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'No se pudo bloquear ticketyn.'
        restore_sql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datid=$ORIGINAL_OID AND pid<>pg_backend_pid()" \
            > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'No se pudieron bloquear/terminar conexiones de ticketyn.'
    fi
}
restore_revision() {
    restore_pg psql --dbname="$1" -X -At --set=ON_ERROR_STOP=1 -c 'SELECT version_num FROM public.alembic_version' 2> "$STATE/diagnostic.log"
}
restore_run() {
    PHASE=deteniendo; MUTATING=1; restore_record
    if systemctl is-active --quiet ticketyn; then WAS_ACTIVE=1; fi
    systemctl stop ticketyn > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'No se pudo detener ticketyn.service.'
    if systemctl is-active --quiet ticketyn; then restore_fail 'Ticketyn continúa activo; no se restaura.'; fi
    restore_disable_original
    if [[ $ROLE_EXISTS == 0 ]]; then
        restore_sql -c "BEGIN; CREATE ROLE ticketyn LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; COMMENT ON ROLE ticketyn IS 'ticketyn-restore:$TOKEN'; COMMIT" \
            > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'No se pudo crear rol Ticketyn.'
    fi
    PHASE=preparando_db; restore_record
    # C existe en todas las instalaciones PostgreSQL; UTF8 explícito, no SQL_ASCII.
    restore_sql -c "CREATE DATABASE $STAGE OWNER ticketyn TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C'" \
        > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'No se pudo crear DB de restauración.'
    STAGE_OID=$(restore_oid "$STAGE"); [[ $STAGE_OID =~ ^[0-9]+$ ]] || restore_fail 'OID de staging inválido.'
    PHASE=pg_restore; restore_record
    # Dump entra por stdin: el usuario postgres no necesita leer temporales root 0700.
    restore_pg pg_restore --dbname="$STAGE" --role=ticketyn --no-owner --no-privileges \
        --single-transaction --exit-on-error < "$CONTENT/database.dump" \
        > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'pg_restore falló; no se cambió la DB activa.'
    [[ $(restore_revision "$STAGE") == "$HEAD" ]] || restore_fail 'La revisión Alembic del dump restaurado no coincide.'
    [[ $(restore_query "SELECT pg_get_userbyid(datdba)||':'||pg_encoding_to_char(encoding) FROM pg_database WHERE datname='$STAGE'") == ticketyn:UTF8 ]] || restore_fail 'Propietario/encoding incorrectos.'
    [[ $(restore_pg psql --dbname="$STAGE" -X -At --set=ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m') AND pg_get_userbyid(c.relowner)<>'ticketyn'" 2> "$STATE/diagnostic.log") == 0 ]] || restore_fail 'Objetos restaurados con propietario inesperado.'
    restore_cutover
    PHASE=configuracion; restore_record
    [[ $(backup_identity "$CONFIG_FILE") == "$CONFIG_ID" && $(sha256sum "$CONFIG_FILE" | cut -d ' ' -f1) == "$OLD_CONFIG_HASH" ]] || restore_fail 'Configuración original cambió; no se sobrescribe.'
    cp -- "$CONTENT/ticketyn.env" "$STATE/restored.env"
    chmod 0600 "$STATE/restored.env"; chown root:root "$STATE/restored.env"
    mv -T -- "$STATE/restored.env" "$CONFIG_FILE"
    sync -f "$CONFIG_FILE"; sync -f "$CONFIG_DIR"
    PHASE=credenciales; restore_record
    python3 -I "$SUPPORT" password "$CONFIG_FILE" || restore_fail 'Falló sincronización de contraseña; Ticketyn queda detenido.'
    backup_check_config "$CONFIG_FILE"
    restore_sql -c 'ALTER DATABASE ticketyn ALLOW_CONNECTIONS true' > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'No se pudo habilitar DB restaurada.'
    [[ $(restore_revision ticketyn) == "$HEAD" ]] || restore_fail 'Revisión Alembic final incorrecta.'
    PHASE=arranque; restore_record
    systemctl start ticketyn > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'No se pudo arrancar Ticketyn.'
    restore_http_checks
    PHASE=completado; restore_record
    printf '✓ Ticketyn restaurado y verificado. Estado: %s\n' "$STATE"
    if [[ -n $ORIGINAL_OID ]]; then printf 'DB anterior conservada, deshabilitada: %s\nBackup de seguridad: %s\n' "$PREVIOUS" "$SAFETY_BACKUP"; fi
}
restore_cutover() {
    [[ $(readlink -e "$CURRENT_FILE") == "$RELEASE" && $(backup_identity "$CURRENT_FILE") == "$CURRENT_ID" && \
        $(restore_oid "$STAGE") == "$STAGE_OID" && $(restore_oid ticketyn) == "$ORIGINAL_OID" && \
        $(sha256sum "$CONFIG_FILE" | cut -d ' ' -f1) == "$OLD_CONFIG_HASH" && \
        $(sha256sum "$RELEASE/pyproject.toml" | cut -d ' ' -f1) == "$RELEASE_METADATA_HASH" ]] || restore_fail 'Identidades cambiaron; no se realiza cutover.'
    restore_sql -c "ALTER DATABASE $STAGE ALLOW_CONNECTIONS false" > /dev/null 2> "$STATE/diagnostic.log"
    restore_sql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datid=$STAGE_OID AND pid<>pg_backend_pid()" > /dev/null 2> "$STATE/diagnostic.log"
    PHASE=cutover_intentado; CUTOVER_ATTEMPTED=1; restore_record
    local sql='BEGIN;'
    if [[ -n $ORIGINAL_OID ]]; then sql+=" ALTER DATABASE ticketyn RENAME TO $PREVIOUS;"; fi
    sql+=" ALTER DATABASE $STAGE RENAME TO ticketyn; COMMIT;"
    restore_sql -c "$sql" > /dev/null 2> "$STATE/diagnostic.log" || restore_fail 'Cutover falló o su resultado es ambiguo; requiere revisión manual.'
    [[ $(restore_oid ticketyn) == "$STAGE_OID" ]] || restore_fail 'OID final incorrecto.'
}
restore_http_checks() {
    PHASE=comprobaciones; restore_record
    local kind path attempt ready base="http://127.0.0.1:$HTTP_PORT"
    systemctl is-active --quiet ticketyn && systemctl is-active --quiet nginx || restore_fail 'Servicio Ticketyn/Nginx no activo.'
    for kind in health api; do
        if [[ $kind == health ]]; then path=/health; else path=/api/customers; fi
        ready=0
        for attempt in {1..30}; do
            if curl -fsS --max-time 3 "$base$path" > "$WORK/http.json" 2>/dev/null && \
                python3 -I "$SUPPORT" http-valid "$WORK/http.json" "$kind" >/dev/null 2>&1; then ready=1; break; fi
            sleep 1
        done
        [[ $ready == 1 ]] || restore_fail "$path no respondió correctamente mediante Nginx tras 30 intentos; revisar servicios/credenciales."
    done
    [[ $(ss -H -ltn 'sport = :8000' | awk '{print $4}') == 127.0.0.1:8000 ]] || restore_fail 'Uvicorn no escucha exclusivamente en loopback.'
    [[ $(readlink -e "$CURRENT_FILE") == "$RELEASE" ]] || restore_fail 'Release activo cambió.'
}
restore_main() {
    (( EUID == 0 )) || restore_fail 'Ejecuta restore.sh como root o mediante sudo.'
    restore_args "$@"
    PATH=/usr/sbin:/usr/bin:/sbin:/bin; export PATH
    unset DATABASE_URL PGPASSWORD; umask 077
    SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
    source "$SCRIPT_DIR/backup.sh"
    SUPPORT="$SCRIPT_DIR/deploy/restore_support.py"; BACKUP_SCRIPT="$SCRIPT_DIR/backup.sh"
    CONFIG_DIR=/etc/ticketyn; CONFIG_FILE=$CONFIG_DIR/ticketyn.env
    APP_ROOT=/opt/ticketyn; RELEASES_DIR=$APP_ROOT/releases; CURRENT_FILE=$APP_ROOT/current
    UNIT_FILE=/etc/systemd/system/ticketyn.service
    NGINX_SITE=/etc/nginx/sites-available/ticketyn; NGINX_LINK=/etc/nginx/sites-enabled/ticketyn
    SAFETY_DIR=/var/backups/ticketyn
    STATE=$CONFIG_DIR/restore-state
    WORK=$(mktemp -d /tmp/ticketyn-restore.XXXXXXXX); chown root:root "$WORK"
    WORK_ID=$(backup_identity "$WORK"); CONTENT=$WORK/components
    MUTATING=0; CUTOVER_ATTEMPTED=0; BLOCK_ATTEMPTED=0; WAS_ACTIVE=0; PHASE=validacion; SAFETY_BACKUP=''; STAGE_OID=''
    trap 'printf "Error: restore interrumpido en fase %s; no se declara éxito.\n" "$PHASE" >&2' ERR
    trap restore_cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    printf 'Utiliza únicamente backups de confianza: los hashes no autentican el SQL restaurado.\n'
    restore_validate
    restore_confirm
    restore_lock
    restore_begin
    restore_run
}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then restore_main "$@"; fi
