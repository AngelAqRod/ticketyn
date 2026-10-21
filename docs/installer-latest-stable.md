# Instalador: selección de la última release estable pública

## Alcance vigente

`install.sh` instala una release publicada de `AngelAqRod/ticketyn`, en lugar de
instalar el código del checkout local desde el que se invoca. No actualiza una
instalación ya completada. El updater no cambia.

El script y `deploy/install_release.py` deben proceder de una copia local de
confianza y conservar su ubicación relativa. No se debe ejecutar el instalador
mediante `curl | bash`. Se mantiene la invocación existente, desde esa copia:

```bash
sudo ./install.sh
```

Esta instrucción modifica el sistema cuando se ejecuta; no es una comprobación
de diagnóstico. Esta tarea no ha ejecutado una instalación real.

Se conservan los sistemas soportados: Debian 12/13 y Ubuntu 24.04 con systemd.
**Antes de iniciar se necesitan Python 3.11 o posterior y certificados de
confianza HTTPS disponibles.** La consulta utiliza exclusivamente la biblioteca
estándar de Python, sin jq ni dependencias pip adicionales. Si no se cumple este
requisito, se detiene antes de instalar paquetes. La fase de dependencias del
instalador permanece intacta.

## Selección y descarga

1. Consultar `https://api.github.com/repos/AngelAqRod/ticketyn/releases/latest`.
   Es la release estable designada como última por GitHub, no el mayor tag por
   orden alfabético ni el último commit de una rama. Se utiliza el contrato de
   [GitHub para la última release](https://docs.github.com/en/rest/releases/releases#get-the-latest-release).
2. Validar que el JSON describe una release publicada, con `draft=false`,
   `prerelease=false`, fecha de publicación válida y tag estable `vX.Y.Z`.
   Los componentes numéricos no admiten ceros iniciales. No se interpretan
   `target_commitish`, nombres de ramas ni assets arbitrarios como fuente.
3. Descargar el `tarball_url` oficial, que debe corresponder exactamente a ese
   tag bajo el repositorio oficial. Solo se permiten HTTPS y redirecciones al
   mismo repositorio en `api.github.com` o `codeload.github.com`; se verifica TLS.
4. Completar la descarga en un archivo temporal antes de extraer. Validar tamaño
   anunciado cuando exista, integridad gzip y límites de recursos. Extraer solo
   archivos ordinarios y directorios permitidos, sin restaurar propietarios,
   enlaces, dispositivos ni rutas que escapen del directorio temporal.
5. Comprobar que `[project].name` sea `ticketyn` y `[project].version` coincida
   exactamente con el tag sin la `v`. Mantener las comprobaciones existentes de
   archivos, migraciones, frontend compilado y contenido sospechoso.
6. Informar la release seleccionada al operador antes de la confirmación y de
   cualquier preparación persistente de la instalación.

En la consulta de releases públicas realizada durante esta tarea, la última era
`v0.6.2` y no tenía assets adjuntos. Por eso se utiliza el archivo fuente que
GitHub genera para el tag. **Ese número no está fijado en el instalador.**
No se presupone que cualquier distribución futura sea compatible: debe contener
los archivos que necesita el instalador y `frontend/dist/` completo. Si una
release cambia de formato o no incluye el frontend precompilado, se rechaza con
un error; no se instala Node/npm, no se adivina un asset alternativo y no se
recurre a una rama.

El código remoto de `install.sh` no se ejecuta: la selección y validación las
realiza el instalador local confiable. Después se conserva la preparación
existente del código validado, su entorno Python y sus migraciones.

## Fallos y límites

- Sin alternativa automática ante red inaccesible, TLS inválido, HTTP fallido,
  rate limiting, JSON inválido, ausencia de release estable, tag inexistente,
  archivo corrupto, descarga incompleta o distribución incompatible.
- Timeout de socket de 30 segundos y límite de tiempo comprobado durante cada
  transferencia de 120 segundos. No hay reintentos automáticos ni autenticación
  GitHub; se aplica el límite de consultas públicas de GitHub.
- Límites: metadatos de 1 MiB, archivo comprimido de 128 MiB, contenido expandido
  de 512 MiB y 50 000 entradas. Si se exceden, se detiene la instalación.
- La descarga reside en un directorio privado creado mediante `mktemp`; el
  mecanismo existente de salida limpia ese directorio en salidas normales y
  señales controladas. Un apagado o SIGKILL puede dejar temporales para revisión.
- La confianza de origen descansa en GitHub oficial y HTTPS. La suma SHA-256
  interna identifica la fuente para copia y recuperación; no equivale a una
  firma independiente del publicador ni impide que se mueva un tag antes de la
  primera instalación. Los tags publicados deben mantenerse inmutables.

## Recuperación y estructura persistente

Una instalación nueva siempre consulta `/releases/latest`. Si existe un estado
protegido de instalación parcial o fallida en `/etc/ticketyn/install-state`, el
instalador anuncia explícitamente que recuperará su versión original y consulta
`/releases/tags/vX.Y.Z`. No la sustituye por la última release mientras reanuda
operaciones parcialmente realizadas.

Se mantienen las comprobaciones existentes de versión, hash de fuente,
propiedad, archivos y recursos previamente creados. Si cambió la fuente del tag
o no coincide con el estado local, se detiene. Una instalación parcial creada
desde un árbol local modificado puede requerir diagnóstico manual al no coincidir
con el archivo público; no se ignora ese desacuerdo. Un estado completado remite
al updater antes de consultar o descargar otra release.

Se conserva `/opt/ticketyn/releases/<version>` con su entorno virtual,
`/opt/ticketyn/current`, la configuración PostgreSQL, Alembic, systemd, Nginx,
los permisos y la configuración persistente. Los archivos locales sin publicar
no pasan a la instalación por estar junto al instalador.

## Inicialización administrativa integrada (fase 2)

Esta sección sustituye la integración pendiente de la primera fase. Se reutiliza
el bootstrap existente sin duplicar creación de personas, contraseñas o roles.

### Detección y empaquetado

El helper local `deploy/install_security.py` analiza el paquete descargado sin
importarlo ni conectarse a PostgreSQL. Contrasta:

- Metadatos reales `revision`/`down_revision`: `0030_security_foundation`,
  `0031_role_permissions` y `0032_responsible_selectable`, con sus dependencias.
- Instalación de la seguridad en `main.py` y registro del router de autenticación.
- Contrato de login `/api/auth/login` del router.
- Script ejecutable y módulo bootstrap con los contratos `main`,
  `check_status_cli`, `interactive_bootstrap`, `--check` y `--config`.

No se utiliza un umbral de versión ni se decide únicamente por un archivo.
Una release anterior sin señales de autenticación sigue el flujo **legacy**.
Un paquete parcial o incompatible se rechaza antes de instalar dependencias o
preparar PostgreSQL; nunca se degrada silenciosamente al flujo sin autenticación.
Un futuro cambio de esos contratos requiere revisar el detector.

`bootstrap-superadmin.sh` se admite en la descarga y, cuando existe, forma parte
de la copia y del hash verificado de la fuente. Se rechazan enlaces y sintaxis
Bash inválida. Las releases antiguas sin script conservan su hash y su lista de
copia anteriores. No se les incorpora el bootstrap del checkout local.

### Orden de integración

1. Seleccionar y validar la release y sus capacidades de autenticación.
2. Preparar dependencias, PostgreSQL, configuración privada y entorno Python.
3. `prepare_release`: instalar el paquete, aplicar Alembic y verificar que la base
   esté en el HEAD de esa release. Publicar `current` como antes.
4. `phase bootstrap` / `initialize_administration`: verificar el Superadministrador
   **antes de `configure_services`**. No se inicia un nuevo servicio Ticketyn ni
   se publica su sitio Nginx hasta completar esta etapa.
5. Ejecutar el script de la release preparada con su intérprete obligatorio y
   `--config /etc/ticketyn/ticketyn.env`. No recurrir a otra release o intérprete.
6. Interpretar `--check`: `0` significa satisfecho; `3` permite abrir el asistente;
   `1` indica inconsistencia y `2` error de configuración o base. Solo el caso `3`
   permite creación, para la cual el instalador exige una terminal interactiva.
7. Repetir `--check` tras el asistente o la detección de una cuenta existente.
   Un código cero del asistente por sí solo no acredita la inicialización.
8. Preparar el comando updater existente, iniciar servicios y comprobar salud.
   Solo después marcar la instalación como completada.

No se pasan contraseñas por argumentos ni archivos temporales, no se capturan las
entradas del asistente y no se crean sesiones para comprobar salud. Se mantienen
Argon2id, contraseña temporal y `operational_selectable=false`. Los ajustes
internos del bootstrap se limitan a sanear errores de configuración que podían
incluir la URL PostgreSQL con contraseña y a rechazar credenciales cuyo formato
Argon2id esté corrupto. No se verifica una contraseña desconocida ni se reparan
credenciales automáticamente.

### Verificaciones finales

`GET /health` sigue siendo público y debe devolver exactamente
`{"status":"ok"}`. Acredita respuesta HTTP, no una consulta PostgreSQL. También
se comprueban servicio, frontend, assets y socket local del backend.

Con autenticación, `GET /api/customers` **sin credenciales debe responder 401**.
Se descarta el cuerpo; una respuesta 200 se considera un defecto de protección.
Se ejecuta nuevamente `bootstrap --check` para confirmar inicialización y conexión
a PostgreSQL. No se inicia sesión ni se generan tokens.

Sin autenticación se conserva la comprobación de clientes con respuesta 200/lista.
El mensaje final distingue ambos tipos de instalación y recuerda configurar HTTPS
para la instalación HTTP.

### Interrupciones y recuperación

`release_ready=1` acredita preparación técnica y revisión Alembic, **no existencia
de Superadministrador**. La fase persistida puede quedar en `bootstrap`, con estado
`failed`. No se anuncia que Ticketyn esté listo si su inicialización está pendiente.

Si falla el asistente, se conservan código, esquema y configuración. Una creación
confirmada antes de una interrupción posterior permanece válida. Puede reejecutarse
el mismo instalador confiable: descarga la versión original, conserva las pruebas
de identidad, verifica nuevamente el esquema y repite `--check`. Si el administrador
ya existe, no vuelve a solicitar credenciales ni cambia su contraseña.

También puede ejecutarse manualmente la ruta exacta indicada en el diagnóstico del
instalador. Si `current` apunta a esa release preparada, equivale a:

```bash
sudo /opt/ticketyn/current/bootstrap-superadmin.sh --config /etc/ticketyn/ticketyn.env
sudo /opt/ticketyn/current/bootstrap-superadmin.sh --config /etc/ticketyn/ticketyn.env --check
```

Son instrucciones administrativas futuras; no se ejecutaron en esta tarea. Después
se reejecuta el instalador para completar servicios y verificaciones.

Ante errores de migraciones o conexión debe resolverse primero la preparación
técnica; no se omiten comprobaciones ni se inicializa sobre un esquema anterior.
Las inconsistencias administrativas requieren diagnóstico, sin reparaciones ni
promociones automáticas. Un fallo de servicios conserva el administrador creado.
No hay rollback destructivo ni detención o sustitución de una instalación ajena.
Las instalaciones completadas siguen rechazándose por el instalador.

### Límite con el updater: compatibilidad corregida por separado

La integración del instalador permanece intacta. Una tarea posterior corrigió
el updater para verificar 401 en releases autenticadas y conservar el bootstrap
original. Se reutiliza el detector compartido, sin ejecutar inicialización
administrativa desde el updater. Las actualizaciones siguen requiriendo el paso
manual de DevOps; las instalaciones nuevas conservan su integración interactiva.

Ver [Compatibilidad del updater](updater-authentication-v0.7.0.md), incluidos
el uso de una herramienta corregida (el bundle anterior no se actualiza solo),
los límites de recuperación después de migraciones y el ensayo pendiente en VM.

## Pruebas sin instalación

```bash
.venv/bin/pytest -q tests/test_installer.py tests/test_installer_releases.py tests/test_installer_bootstrap.py tests/test_bootstrap_superadmin.py tests/test_security_foundation.py
bash -n install.sh bootstrap-superadmin.sh
```

Las pruebas simulan GitHub y servicios y trabajan en rutas temporales. No usan
Internet, apt, usuarios del sistema ni systemd reales. Comprueban selección,
extracción, copias, detección de autenticación, fallos, recuperación y salud HTTP.
Las pruebas PostgreSQL usan exclusivamente el clúster descartable de
`tests/conftest.py`: incluyen migraciones reales desde una base vacía, el script
existente, contraseñas por terminal, reejecución y esquemas no preparados. No leen
`DATABASE_URL` ni `.env` para seleccionar una base operativa. No ejecutan el
instalador completo contra el sistema.

La fase anterior terminó con 189 pruebas aprobadas. Los resultados de esta
integración y sus regresiones se registran en `AGENT_HANDOFF.md`. No se validó una
instalación real Debian/Ubuntu ni se modificaron DEV, TEST o PRODUCCIÓN.
