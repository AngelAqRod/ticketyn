#!/usr/bin/env bash
# Backup lógico de producción. No detiene servicios ni modifica PostgreSQL.
set +x
set -Eeuo pipefail

backup_fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
backup_require_root() { (( EUID == 0 )) || backup_fail 'Ejecuta backup.sh como root o mediante sudo.'; }
backup_identity() { stat -c '%d:%i:%w' -- "$1"; }
backup_secure_directory() {
    [[ -d $1 && ! -L $1 ]] || backup_fail "Directorio inexistente o symlink inesperado: $1"
    [[ $(stat -c %u:%g "$1") == 0:0 ]] || backup_fail "El directorio debe pertenecer a root:root: $1"
    local mode
    mode=$(stat -c %a "$1")
    (( (8#$mode & 0022) == 0 )) || backup_fail "Directorio escribible por otros usuarios: $1"
}
backup_secure_file() {
    [[ -f $1 && ! -L $1 && $(stat -c %h "$1") == 1 ]] || backup_fail "Archivo inexistente, symlink o hardlink inesperado: $1"
    [[ $(stat -c %u:%g "$1") == 0:0 ]] || backup_fail "El archivo debe pertenecer a root:root: $1"
    if [[ ${2:-} == private ]]; then
        [[ $(stat -c %a "$1") == 600 ]] || backup_fail "La configuración debe tener permisos 0600: $1"
    else
        local mode
        mode=$(stat -c %a "$1")
        (( (8#$mode & 0022) == 0 )) || backup_fail "Archivo escribible por otros usuarios: $1"
    fi
}
backup_check_config() {
    backup_secure_file "$1" private
    # No source/eval ni variables con la URL. Contrato del despliegue local actual.
    [[ $(grep -c '^DATABASE_URL=' "$1") == 1 ]] && \
        grep -qEx 'DATABASE_URL=postgresql\+psycopg://ticketyn:[^@[:space:]]+@127\.0\.0\.1:5432/ticketyn' "$1" \
        || backup_fail 'DATABASE_URL ausente o incompatible con el PostgreSQL local esperado; no se muestra su contenido.'
    if grep -qEv '^(DATABASE_URL=.+|[[:space:]]*#.*|[[:space:]]*)$' "$1"; then
        backup_fail 'La configuración contiene entradas no soportadas por este formato de backup.'
    fi
}
backup_release_version() {
    backup_secure_directory "$APP_ROOT"
    backup_secure_directory "$RELEASES_DIR"
    [[ -L $CURRENT_FILE && $(stat -c %u:%g "$CURRENT_FILE") == 0:0 ]] || backup_fail 'No existe un enlace current de producción seguro.'
    RELEASE=$(readlink -e -- "$CURRENT_FILE") || backup_fail 'current no apunta a un release existente.'
    [[ $RELEASE == "$RELEASES_DIR/"* && ${RELEASE#"$RELEASES_DIR/"} != */* ]] || backup_fail 'current apunta fuera del directorio de releases.'
    backup_secure_directory "$RELEASE"
    backup_secure_file "$RELEASE/pyproject.toml"
    VERSION=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$RELEASE/pyproject.toml")
    [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+([a-zA-Z0-9.+-]*)?$ && ${RELEASE##*/} == "$VERSION" ]] || backup_fail 'Versión/release activa inválida o incoherente.'
    CURRENT_ID=$(backup_identity "$CURRENT_FILE")
    RELEASE_METADATA_HASH=$(sha256sum -- "$RELEASE/pyproject.toml" | cut -d ' ' -f1)
}
backup_postgres() {
    # Peer local; no DATABASE_URL, PGPASSWORD, .pgpass ni conexión TCP heredados.
    runuser -u postgres -- env -i PATH=/usr/bin:/bin HOME=/nonexistent \
        PGPASSFILE=/dev/null PGAPPNAME=ticketyn-backup \
        PGOPTIONS='-c default_transaction_read_only=on' \
        "$1" --host=/var/run/postgresql --port=5432 --username=postgres \
        --dbname=ticketyn --no-password "${@:2}"
}
backup_db_metadata() {
    backup_postgres psql -X -A -t --set=ON_ERROR_STOP=1 --command="SELECT 'server_version=' || current_setting('server_version') UNION ALL SELECT 'encoding=' || pg_encoding_to_char(encoding) FROM pg_database WHERE datname=current_database() UNION ALL SELECT 'owner=' || pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database() UNION ALL SELECT 'alembic_revision=' || version_num FROM public.alembic_version" \
        > "$1" 2> "$WORK/diagnostic.log" || backup_fail 'No se pudo obtener metadata PostgreSQL/Alembic por conexión peer local.'
    [[ $(wc -l < "$1") == 4 ]] && grep -qFx 'encoding=UTF8' "$1" && \
        grep -qFx 'owner=ticketyn' "$1" && grep -qEx 'server_version=[0-9].*' "$1" && \
        grep -qEx 'alembic_revision=[A-Za-z0-9_]+' "$1" \
        || backup_fail 'La DB no presenta propietario, encoding o revisión Alembic esperados.'
    # UNION ALL no garantiza orden: normalizar para la comparación posterior.
    sort -o "$1" "$1"
}
backup_cleanup() {
    local code=$?
    trap - EXIT
    # Solo retirar una publicación fallida que aún es exactamente nuestro inode.
    if [[ $code != 0 && -n ${FINAL_PATH:-} && -n ${WORK:-} && \
        -f $FINAL_PATH && ! -L $FINAL_PATH && -f $WORK/backup.tar && $FINAL_PATH -ef $WORK/backup.tar ]]; then
        unlink -- "$FINAL_PATH"
    fi
    if [[ -n ${WORK:-} && $WORK == "$BACKUP_DIR/.ticketyn-backup."* && -d $WORK && ! -L $WORK && \
        $(backup_identity "$WORK") == "${WORK_ID:-}" ]]; then
        rm -rf -- "$WORK"
    fi
    exit "$code"
}
backup_preflight() {
    local tool
    for tool in runuser pg_dump pg_restore psql tar sha256sum mktemp stat readlink date sed grep sort wc cmp ln sync cp mkdir chown chmod rm unlink cut dirname cat; do
        command -v "$tool" >/dev/null || backup_fail "Falta la herramienta requerida: $tool"
    done
    backup_secure_directory "$CONFIG_DIR"
    backup_check_config "$CONFIG_FILE"
    backup_release_version
    backup_secure_directory "$(dirname -- "$BACKUP_DIR")"
    if [[ -e $BACKUP_DIR || -L $BACKUP_DIR ]]; then
        backup_secure_directory "$BACKUP_DIR"
        [[ $(stat -c %a "$BACKUP_DIR") == 700 ]] || backup_fail 'El directorio de backups debe tener permisos 0700; no se cambia automáticamente.'
    else
        mkdir -m 0700 -- "$BACKUP_DIR" || backup_fail 'No se pudo crear el directorio privado de backups.'
        chown root:root "$BACKUP_DIR"
    fi
}
backup_prepare() {
    WORK=$(mktemp -d "$BACKUP_DIR/.ticketyn-backup.XXXXXXXX")
    chown root:root "$WORK"
    WORK_ID=$(backup_identity "$WORK")
    CONTENT="$WORK/components"
    mkdir -m 0700 -- "$CONTENT"
    chown root:root "$CONTENT"
    CREATED_AT=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
    STAMP=$(date -u +'%Y%m%dT%H%M%SZ')
    [[ $STAMP =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || backup_fail 'Timestamp inválido.'
    NAME="ticketyn-backup-$STAMP-v$VERSION-${WORK##*.}.tar"
    FINAL_PATH="$BACKUP_DIR/$NAME"
    [[ ! -e $FINAL_PATH && ! -L $FINAL_PATH ]] || backup_fail 'Ya existe el nombre de backup; no se reemplaza.'
    CONFIG_ID=$(backup_identity "$CONFIG_FILE")
    CONFIG_HASH=$(sha256sum -- "$CONFIG_FILE" | cut -d ' ' -f1)
    cp --no-dereference -- "$CONFIG_FILE" "$CONTENT/ticketyn.env"
    backup_check_config "$CONTENT/ticketyn.env"
    [[ $(sha256sum -- "$CONTENT/ticketyn.env" | cut -d ' ' -f1) == "$CONFIG_HASH" ]] || backup_fail 'La configuración cambió durante la copia.'
}
backup_dump() {
    backup_db_metadata "$WORK/db-before.txt"
    printf 'Creando dump PostgreSQL consistente (sin detener Ticketyn)...\n'
    backup_postgres pg_dump --format=custom --compress=6 --lock-wait-timeout=60s \
        > "$CONTENT/database.dump" 2> "$WORK/diagnostic.log" || backup_fail 'pg_dump falló; no se publica ningún backup. Revisa PostgreSQL y el espacio disponible.'
    [[ -s $CONTENT/database.dump ]] || backup_fail 'pg_dump produjo un archivo vacío.'
    # Renderiza todo el dump a /dev/null: comprueba el contenido sin ejecutar SQL.
    env -i PATH=/usr/bin:/bin pg_restore --file=/dev/null "$CONTENT/database.dump" \
        >/dev/null 2> "$WORK/diagnostic.log" || backup_fail 'pg_restore no pudo leer íntegramente el dump; no se publica.'
    backup_db_metadata "$WORK/db-after.txt"
    cmp -s "$WORK/db-before.txt" "$WORK/db-after.txt" || backup_fail 'La metadata/revisión DB cambió durante el backup; vuelve a intentarlo sin migraciones concurrentes.'
    backup_verify_sources
}
backup_verify_sources() {
    backup_check_config "$CONFIG_FILE"
    [[ $(backup_identity "$CONFIG_FILE") == "$CONFIG_ID" && \
        $(sha256sum -- "$CONFIG_FILE" | cut -d ' ' -f1) == "$CONFIG_HASH" && \
        $(backup_identity "$CURRENT_FILE") == "$CURRENT_ID" && \
        $(readlink -e "$CURRENT_FILE") == "$RELEASE" && \
        $(sha256sum -- "$RELEASE/pyproject.toml" | cut -d ' ' -f1) == "$RELEASE_METADATA_HASH" ]] \
        || backup_fail 'La configuración o el release activo cambió durante el backup; no se publica.'
}
backup_metadata() {
    local dump_version
    dump_version=$(env -i PATH=/usr/bin:/bin pg_dump --version 2> "$WORK/diagnostic.log") || backup_fail 'No se pudo identificar la versión de pg_dump.'
    {
        printf 'backup_format=ticketyn-backup-v1\ncreated_at_utc=%s\ncompleted_dump_at_utc=%s\n' "$CREATED_AT" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        printf 'ticketyn_version=%s\nexpected_git_tag=v%s\nrelease_name=%s\nsource_release_path=%s\n' "$VERSION" "$VERSION" "${RELEASE##*/}" "$RELEASE"
        printf 'pyproject_sha256=%s\ndatabase=ticketyn\ndump_format=PostgreSQL custom\npg_dump_version=%s\n' "$RELEASE_METADATA_HASH" "$dump_version"
        cat -- "$WORK/db-before.txt"
    } > "$CONTENT/metadata.txt"
    cat > "$CONTENT/MANIFEST.txt" <<EOF
Ticketyn — backup lógico completo
Formato: ticketyn-backup-v1 (tar sin compresión adicional; dump custom comprimido)
Fecha UTC: $CREATED_AT
Versión: $VERSION · Tag esperado: v$VERSION
Release de origen: $RELEASE

Archivos incluidos:
  database.dump — esquema, datos, secuencias, objetos grandes, propietarios y ACL de ticketyn
  ticketyn.env — configuración persistente; contiene secretos
  metadata.txt — versión, release, PostgreSQL, encoding y revisión Alembic
  MANIFEST.txt — este manifiesto
  SHA256SUMS — hashes de los cuatro componentes anteriores

Integridad sin restaurar: extraer en directorio privado y ejecutar sha256sum -c SHA256SUMS.
Inspección DB: pg_restore --list database.dump.
La instantánea de datos la proporciona pg_dump. No incluye roles globales ni código.
Restaurar requiere la release indicada, PostgreSQL compatible y el rol ticketyn.
Antes de usar la configuración restaurada, sincronizar la contraseña del rol local.
Los hashes detectan corrupción; no aportan autenticidad ni cifrado.
EOF
}
backup_publish() {
    local member expected actual
    local members=(database.dump ticketyn.env metadata.txt MANIFEST.txt SHA256SUMS)
    for member in "${members[@]:0:4}"; do
        [[ -s $CONTENT/$member && -f $CONTENT/$member && ! -L $CONTENT/$member ]] || backup_fail "Componente ausente: $member"
        chmod 0600 -- "$CONTENT/$member"
    done
    (cd "$CONTENT"; sha256sum -- "${members[@]:0:4}" > SHA256SUMS
        sha256sum --check --strict SHA256SUMS >/dev/null) || backup_fail 'Falló la verificación SHA-256 de los componentes.'
    tar -C "$CONTENT" -cf "$WORK/backup.tar" -- "${members[@]}" 2> "$WORK/diagnostic.log" || backup_fail 'No se pudo crear el artefacto; revisa espacio disponible.'
    chown root:root "$WORK/backup.tar"
    chmod 0600 "$WORK/backup.tar"
    [[ $(tar -tf "$WORK/backup.tar" 2> "$WORK/diagnostic.log") == "$(printf '%s\n' "${members[@]}")" ]] || backup_fail 'El artefacto no contiene exactamente los componentes esperados.'
    for member in "${members[@]}"; do
        expected=$(sha256sum -- "$CONTENT/$member" | cut -d ' ' -f1)
        actual=$(tar -xOf "$WORK/backup.tar" -- "$member" 2> "$WORK/diagnostic.log" | sha256sum | cut -d ' ' -f1)
        [[ $actual == "$expected" ]] || backup_fail "Integridad del artefacto incorrecta: $member"
    done
    backup_verify_sources
    # Mismo filesystem: hardlink exclusivo/atómico, nunca sobrescribir archivos ni dirs.
    sync -f "$WORK/backup.tar" || backup_fail 'No se pudo sincronizar el artefacto a disco.'
    ln -T -- "$WORK/backup.tar" "$FINAL_PATH" || backup_fail 'No se pudo publicar el backup; un destino existente nunca se reemplaza.'
    [[ -f $FINAL_PATH && ! -L $FINAL_PATH && $FINAL_PATH -ef $WORK/backup.tar && \
        $(stat -c %a "$FINAL_PATH") == 600 ]] || backup_fail 'No se pudo verificar el backup publicado.'
    sync -f "$BACKUP_DIR" || backup_fail 'No se pudo sincronizar la publicación del backup.'
    printf '✓ Backup completo y verificado: %s\n' "$FINAL_PATH"
}
backup_main() {
    backup_require_root
    [[ $# == 0 ]] || backup_fail 'Uso: ./backup.sh (sin argumentos).'
    PATH=/usr/sbin:/usr/bin:/sbin:/bin; export PATH
    umask 077
    WORK=''; WORK_ID=''; FINAL_PATH=''
    CONFIG_DIR=/etc/ticketyn; CONFIG_FILE=/etc/ticketyn/ticketyn.env
    APP_ROOT=/opt/ticketyn; RELEASES_DIR=/opt/ticketyn/releases; CURRENT_FILE=/opt/ticketyn/current
    BACKUP_DIR=/var/backups/ticketyn
    unset DATABASE_URL PGPASSWORD
    trap 'printf "Error: backup falló en la línea %s; no se considera completado.\n" "$LINENO" >&2' ERR
    trap backup_cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    backup_preflight
    backup_prepare
    backup_dump
    backup_metadata
    backup_publish
}
# Permite probar helpers con rutas temporales, sin ejecutar el backup de producción.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then backup_main "$@"; fi
