# Ticketyn

Ticketyn es un producto web de gestión de incidencias: tickets, clientes,
circuitos/servicios contratados, catálogos, filtros operativos y reportería.
Licencia **GNU AGPL v3, AGPL-3.0-only**; texto completo en [LICENSE](LICENSE).

> **Candidata temporal saludable `v0.1.5-test.1`: exclusivamente para validar
> recovery hacia delante desde el fallo de v0.1.4-test.1 en laboratorio.
> `/health` vuelve a HTTP 200; HEAD permanece en `0007_e2e_recovery_probe`.
> No añade migraciones. No constituye una release normal de producción.
> Ejecuta el updater v2; esta candidata no omite ninguna garantía de recovery.

Versión del proyecto: `0.1.5`.

> **Seguridad:** Ticketyn actualmente NO implementa autenticación ni autorización.
> No expongas el servicio directamente a Internet. Para pruebas internas utiliza
> una red controlada, VPN, firewall o reverse proxy con control de acceso.
> Ocultar Swagger/OpenAPI no sustituye autenticación.

## Estado actual

- Dashboard con estadísticas globales SQL y tickets recientes.
- Creación, detalle, edición y finalización de tickets; referencias inmutables.
- Clientes y circuitos con códigos manuales, administración y activación.
- Catálogos: sectores, departamentos, tipos de incidencia, nodos y responsables.
- Combobox de cliente/circuito y creación rápida Circuito → Nodo sin perder el ticket.
- Configuración persistente de numeración con vista previa.
- Filtros operativos persistidos en URL.
- Reportería General, Por sector, Por nodo y Por responsable.
- Exportaciones PDF/XLSX de reportes y todos los tickets filtrados.

No hay usuarios/auth, adjuntos, auditoría, comentarios, SLA ni borrado físico.
Existe un instalador de primera instalación, `install.sh`, para sistemas
soportados con frontend precompilado. Existen `update.sh`, `backup.sh`,
`restore.sh` y `restore.sh --finalize`; no existe rollback automático de updates.
El instalador, backup/restore y el updater con forward recovery fueron validados
end-to-end en Debian. La provisión del nuevo comando `ticketyn-update` debe
validarse también en el laboratorio antes de desplegarla en producción.

## Stack y estructura

Backend: Python >= 3.11, FastAPI, SQLAlchemy 2, PostgreSQL >= 14, psycopg 3,
Alembic, ReportLab y openpyxl. Frontend: React, TypeScript, Vite, Tailwind,
React Router, lucide-react y Recharts. Tests: pytest, Vitest y Testing Library.

```text
src/ticketyn/
  api/             # Routers, queries compartidas, reportes y documentos
  core/            # Configuración y estados
  db/              # Base y sesiones SQLAlchemy
  models/          # Modelos del dominio
  schemas/         # Entradas/respuestas Pydantic
  main.py          # ticketyn.main:app
alembic/versions/  # Historial inmutable de esquema
frontend/         # Source, tests, lockfile npm y dist precompilado
tests/           # Tests backend con PostgreSQL descartable
deploy/          # Templates Nginx/systemd utilizados por install.sh
requirements.lock # Versiones runtime Python resueltas y verificadas
```

## Desarrollo

### Requisitos

- Python >= 3.11 con venv/pip.
- PostgreSQL >= 14 (`date_bin` se utiliza en Reportería), cliente y herramientas
  `initdb`/`pg_ctl` para tests. No se requieren extensiones.
- Node compatible con `frontend/package.json`: `^22.22.2 || ^24.15.0 || >=26.0.0`, y npm.
- UTF-8 y datos de zonas horarias IANA (`tzdata`).

En Debian/Ubuntu, los binarios PostgreSQL pueden estar en
`/usr/lib/postgresql/<major>/bin`; inclúyelos en PATH para ejecutar los tests.
Ejecuta tests con un usuario normal, no root: `initdb` rechaza root.
No hace falta Docker.

### Backend y configuración

Desde la raíz del repositorio:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
chmod 600 .env
```

Configura localmente `DATABASE_URL` para una base de desarrollo y un rol propios.
El ejemplo usa `postgresql+psycopg` y una contraseña placeholder; no publiques
credenciales. Codifica caracteres reservados de la contraseña como parte de URL.

Las variables de entorno tienen prioridad sobre `.env`, que se busca relativo
al directorio de trabajo. `DATABASE_URL` es obligatoria; no hay fallback SQLite
ni credenciales predeterminadas. Si falta, la aplicación falla al arrancar.
No hay variables propias HOST/PORT/TICKETYN_ENV actualmente.

Tras revisar las migraciones, aplícalas deliberadamente a la base elegida:

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn ticketyn.main:app --reload --host 127.0.0.1 --port 8000
```

Este comando Alembic modifica la DB de `DATABASE_URL`: comprueba siempre el
entorno antes de ejecutarlo. La aplicación no crea tablas ni migra al arrancar.
Swagger está en `/docs`, ReDoc en `/redoc`, y OpenAPI en `/openapi.json`.

`GET /health` devuelve `{"status":"ok"}`: comprueba el proceso HTTP,
**no PostgreSQL**. Una futura instalación debe verificar también conexión,
revisión Alembic y una consulta real dependiente de DB.

### Frontend

En otra terminal:

```bash
cd frontend
npm ci
npm run dev
```

Vite sirve desarrollo en `http://127.0.0.1:5173`. Su proxy envía `/api` y `/health`
a `http://127.0.0.1:8000`; la aplicación usa URLs relativas. No se necesita CORS
para este diseño. Vite no es el servidor de producción.

### Tests y build

```bash
# Raíz: clúster PostgreSQL temporal, sin utilizar .env ni DB DEV.
.venv/bin/pytest

# Desde frontend/: fetch simulado, sin backend real.
npm test
npm run build
```

`npm run test:watch` permite pruebas interactivas. Build verifica TypeScript y
produce `frontend/dist`, incluido actualmente para permitir instalación sin Node/npm. Los tests de exportaciones verifican
PDF/XLSX, reportes, relaciones Node/Responsible y datos históricos. Algunos tests
escriben documentos de inspección en el directorio temporal del sistema.

## Migraciones y dominio

La cadena actual tiene un único HEAD:

```text
0001_initial_catalogs
→ 0002_remove_services
→ 0003_ticket_domain
→ 0004_nodes_responsibles
→ 0005_e2e_update_probe
→ 0006_e2e_postmigration_probe
→ 0007_e2e_recovery_probe (head)
```

0001 crea los primeros catálogos; 0002 elimina Service histórico; 0003 añade
Tickets, departamentos, tipos y numeración; 0004 añade Nodes/Responsibles y sus
FK nullable. 0005–0007 añaden únicamente columnas internas nullable para las
pruebas E2E; la aplicación no depende de ellas. Esta candidata mantiene HEAD
0007 y no añade 0008. No modificar revisiones aplicadas. Una instalación vacía no contiene
catálogos empresariales ni asignaciones ficticias.

`alembic.ini` localiza `alembic/` respecto al propio archivo. `env.py` importa los
modelos instalados y usa `DATABASE_URL`. El wheel Python no incluye por sí solo
el directorio de migraciones: la release debe incluirlo con `alembic.ini`.

- Customer tiene muchos Circuits; Circuit representa el servicio contratado.
- Circuit puede tener Node; Ticket deriva Node mediante Circuit, sin `tickets.node_id`.
- Ticket puede tener Responsible, catálogo independiente de autenticación.
- NULL significa «Sin asignar»; no existe un registro ficticio con ese nombre.
- Nuevas asignaciones requieren registros activos; históricos siguen legibles.
- Cambiar Node de un Circuit cambia el contexto derivado de sus tickets; no hay snapshot.
- OPEN/CLOSED y end_at son independientes. Fin definido debe ser >= Inicio.
- Timestamps de entrada requieren zona horaria. La UI convierte hora local del
  navegador al instante ISO correspondiente; no fija una zona geográfica.
- Numeración global transaccional con bloqueo y UNIQUE: referencia almacenada,
  sin recálculo. Valores genéricos: prefix/separator vacíos, próximo número 1,
  padding 0; API admite padding 0..20.

## API, filtros y reportes

CRUD sin DELETE para `/api/customers`, `/api/circuits`, `/api/sectors`,
`/api/departments`, `/api/incident-types`, `/api/nodes` y `/api/responsibles`:
POST/GET colección y GET/PATCH por ID. Listas activas por defecto;
`include_inactive=true` incluye históricos. `active` permite desactivar/reactivar.

Tickets: POST/GET `/api/tickets`, GET/PATCH `/api/tickets/{id}` y
GET `/api/tickets/stats`. Numeración: GET/PATCH `/api/settings/ticket-number`.

Los filtros de tickets incluyen search, status, customer_id, circuit_id,
sector_id, department_id, incident_type_id, node_id, responsible_id, from y to.
Listado paginado con limit/offset; filtros temporales sobre `start_at >= from`
y `start_at < to`. La UI incluye toda la fecha Hasta convirtiendo al inicio local
del día siguiente. Query builders compartidos mantienen la misma semántica en
listado, reportes y exportaciones; no se exporta solo la página visible.

Reportes: `/api/reports/summary`, `/api/reports/export/pdf` y
`/api/reports/export/xlsx`, con from/to, timezone IANA y dimensiones opcionales.
Tickets: `/api/tickets/export/pdf` y `/api/tickets/export/xlsx`.

Definiciones de reportes:

- Iniciadas, evolución, rankings y detalle: start_at en `[from, to)`.
- Cerradas: estado CLOSED y end_at en el período, aunque Inicio sea anterior.
- CLOSED sin Fin no aporta cierre ni duración.
- Duración promedio/acumulada: promedio/suma de Fin - Inicio de esos cierres.
- Rankings Node/Responsible excluyen NULL; KPIs conservan los no asignados.
- Buckets incluyen ceros y respetan timezone. Pantalla y exports comparten el motor;
  descargas posteriores pueden reflejar cambios posteriores a cargar la pantalla.

PDF conserva gráficos vectoriales, rankings completos, detalle y paginación.
Distribución horaria: 24 barras sin tabla duplicada en PDF; API/XLSX conservan
los 24 buckets. XLSX contiene datos completos, ISO con offset y duración numérica.

## Producción: primera instalación

Objetivo Debian estable/Ubuntu LTS en LXC:

```text
Cliente → Nginx → frontend estático
               → /api y /health → Uvicorn 127.0.0.1:8000 → PostgreSQL local
```

Frontend source permanece en Git. Las futuras releases distribuirán `dist`
precompilado de la misma versión: **Node/npm no será requisito runtime**.
No servir el repositorio entero ni utilizar Vite en producción.

Layout previsto:

- `/opt/ticketyn/releases/<version>`: aplicación, venv y frontend; root escribe.
- `/opt/ticketyn/current`: release activa.
- `/etc/ticketyn/ticketyn.env`: secretos, root `0600`, cargado por systemd.
- `/var/backups/ticketyn`: backups privados generados por `backup.sh`.

No se necesitan directorios propios de datos/logs por ahora: PostgreSQL conserva
los datos; stdout/stderr van a journald.

### Uso del instalador

Sistemas iniciales: Debian 12/13 y Ubuntu 24.04 LTS, con systemd en ejecución.
Funciona en LXC, VM o servidor físico; no depende del tipo de virtualización.
Requiere acceso a apt y al índice Python. No instala Node.js ni npm.

```bash
git clone https://github.com/AngelAqRod/ticketyn.git
cd ticketyn
sudo ./install.sh
```

Si ya estás trabajando como root (sudo no es necesario ni se utiliza internamente):

```bash
./install.sh
```

**Prerequisito importante:** `frontend/dist` debe venir ya compilado y corresponder
a la versión del backend. El repositorio actual incluye este build mediante una
excepción explícita en .gitignore, por lo que el checkout proporciona los archivos
estáticos. Las futuras releases deberán incluir el build de su misma versión.
Si falta dist, el instalador se detiene: no lo descarga ni lo compila en producción.

El instalador pregunta únicamente **Puerto HTTP [80]**. Enter elige 80; valida
1–65535, permite elegir otro puerto ante conflicto y C cancela. 8000 y 5432 están
reservados. Después muestra un resumen y pide confirmación (Enter = Sí).

PostgreSQL, usuario/base `ticketyn`, usuario Linux y rutas son automáticos.
Genera una contraseña aleatoria local y guarda solo la configuración externa
root:root `0600`, sin mostrarla. Crea la DB UTF-8 explícitamente con C.UTF-8.
Instala runtime desde requirements.lock y el paquete no editable, ejecuta Alembic
y verifica HEAD antes de activar el release. Instala los templates Nginx/systemd
con el puerto elegido; Nginx conserva `/api`, descargas y rutas SPA.

La versión del directorio se toma de `project.version` en pyproject.toml. Si el
checkout tiene un tag exacto, debe coincidir con `v<version>`. No se sobrescriben
releases de la misma versión. La copia usa una lista positiva de archivos, sin
.git, .env, node_modules ni cachés. `current` solo se crea tras preparar Python,
imports, dependencias y migraciones correctamente.

### Reejecución y seguridad

Es un instalador inicial, no un actualizador. Una instalación completada o recursos
preexistentes sin prueba de propiedad se rechazan; nunca borra DB, roles ni releases.
Un usuario Linux existente solo se reutiliza si es compatible (sistema, grupo
ticketyn, nologin y home /nonexistent).

Una instalación interrumpida puede reanudarse ejecutando **el mismo árbol fuente**
y `install.sh`, con la confirmación normal. Conserva el puerto previamente elegido.
El estado `/etc/ticketyn/install-state` es root:root `0700`, con archivos `0600`:
versión, fingerprint del contenido fuente, identificador aleatorio, puerto, fase,
resultado e identidades/hashes de archivos. No contiene contraseñas ni DATABASE_URL;
la configuración secreta permanece únicamente en `ticketyn.env` root:root `0600`.
Rol y DB se identifican mediante comentarios PostgreSQL con ese identificador.
Los comentarios son evidencia de creación, no un mecanismo de autenticación.

Al reintentar, instala dependencias pendientes, repara el release propio todavía no
publicado, repite/verifica Alembic y completa servicios y comprobaciones. Un release
ya preparado/publicado no se recopia ni se reinstala con pip. No reemplaza `current`:
solo reutiliza el enlace propio verificado. Después de las comprobaciones marca la
instalación completa y deja de admitir reinstalación. No implementa rollback.

SIGINT/SIGTERM conservan el estado de fallo y limpian la política temporal propia.
SIGKILL o un apagado no permiten cleanup; el estado previamente persistido permite
reintentar. Hay ventanas inevitables donde falta evidencia suficiente (por ejemplo,
entre CREATE DATABASE y su COMMENT, o entre crear el archivo de configuración/directorio
release y registrar su identidad, o entre apt y registrar el default). En esos casos exige revisión manual, sin asumir
propiedad ni borrar datos. No resuelvas un fallo borrando la DB. Si apt/dpkg queda
interrumpido, puede ser necesario reparar primero el gestor de paquetes.

No reemplaza sitios Nginx ajenos. Detecta listeners y puertos configurados antes
de instalar y vuelve a comprobar después; ante una directiva `listen` no interpretable
con seguridad aborta. La configuración generada exige IPv4 y no requiere IPv6.
Solo deshabilita el enlace **default recién generado por apt**, registrando su
identidad al terminar apt y comprobando checksum, identidad y destino inmediatamente
antes de retirarlo; conserva el archivo y sitios
preexistentes. **No modifiques Nginx concurrentemente durante la instalación.**

Durante apt crea policy-rc.d únicamente si no existe una política del administrador.
La política propia bloquea arranques solo mientras está ocupado el lock del instalador;
sin lock activo (incluido tras reinicio) permite servicios, aunque el archivo haya
quedado abandonado. Un reintento verifica su identidad/contenido antes de eliminarla.
El descriptor del lock se cierra al invocar apt para que sus procesos hijos no lo
retengan después de SIGKILL del instalador.
Una política ajena/modificada nunca se elimina automáticamente.

La copia incluye explícitamente frontend/dist y valida los árboles de código,
migraciones, deploy y dist antes de copiar y ampliar permisos. Rechaza claves privadas
comunes, .env inesperados, backups evidentes, .git anidados, symlinks y hardlinks
inesperados. Excluye node_modules y cachés. Esto **no es detección perfecta de secretos**:
la release debe revisarse antes de distribuirse. Los tags exactos deben coincidir con
project.version; los errores reales de Git abortan, sin cambiar safe.directory global.
Un checkout modificado o sin tag exacto muestra advertencias durante esta fase DEV.

La instalación inicial utiliza **HTTP**. HTTPS y control de acceso deben
configurarse posteriormente según el entorno; no expongas esta aplicación sin
auth a Internet. El frontend/backend se verifican mediante Nginx, incluyendo una
consulta DB real; `/health` por sí solo no comprueba PostgreSQL.

Templates: `deploy/systemd/ticketyn.service` y `deploy/nginx/ticketyn.conf`.
La unidad PostgreSQL umbrella no verifica readiness; el instalador sí comprueba
conexión local. Validar las restricciones systemd en el sistema objetivo.
Docs/OpenAPI no se proxían en el template: decidir su acceso deliberadamente
no sustituye autenticación.

Temporales: exports usan SpooledTemporaryFile (pasa a disco por encima de 2 MiB)
y openpyxl write-only también escribe temporales. PrivateTmp permite esos
archivos sin necesitar acceso de escritura al checkout. ReportLab usa fuentes
incluidas en su paquete, sin descargas, Chromium ni fuentes del host.

### Runtime Python reproducible

`pyproject.toml` sigue siendo la fuente de rangos soportados. `requirements.lock`
registra el cierre transitivo de runtime, generado a partir de una resolución
limpia de pip; no incluye Ticketyn editable ni dependencias de test. No hace falta
una herramienta de locking nueva.

Para validar una release en una venv nueva (no ejecutar sobre DEV):

```bash
python3 -m venv /tmp/ticketyn-runtime
/tmp/ticketyn-runtime/bin/python -m pip install -r requirements.lock
/tmp/ticketyn-runtime/bin/python -m pip install --no-deps .
/tmp/ticketyn-runtime/bin/python -m pip check
```

Para regenerar los pins tras cambiar los rangos, usa una venv nueva y ejecuta
`python -m pip install . --report /tmp/ticketyn-runtime-resolution.json` sin el
extra dev. Obtén los pares `metadata.name`/`metadata.version` de cada entrada
`install` del JSON, excluye `ticketyn`, ordénalos y escribe `nombre==versión`.
No uses `pip freeze` de DEV: incluiría dependencias ajenas al runtime. Repite
la instalación no editable y la suite aislada antes de aceptar el nuevo lock.

Las versiones están fijadas, no los hashes de todos los wheels/plataformas.
El entorno exacto de generación figura en el lock. La matriz Python/Debian/Ubuntu
y el empaquetado de wheels/checksums quedan para FASE 2; no copiar una venv DEV
ni asumir que una resolución en una plataforma valida todas las demás.

Pendientes: CI, artefactos versionados y política HTTPS/acceso. No hay tags/releases
creados automáticamente.


### Backups de producción

Desde el checkout/release de Ticketyn, como root ejecuta `./backup.sh` (o
`sudo ./backup.sh`). No detiene Ticketyn ni modifica PostgreSQL/configuración.
Requiere la instalación estándar local, herramientas cliente PostgreSQL compatibles,
configuración root:root 0600 y autenticación peer local del usuario postgres.
No usa ni muestra la contraseña de Ticketyn.

Publica en `/var/backups/ticketyn` (root:root 0700) un archivo privado 0600:
`ticketyn-backup-<timestamp UTC>-v<versión>-<identificador aleatorio>.tar`.
Incluye `database.dump` (PostgreSQL custom comprimido), `ticketyn.env`,
`metadata.txt`, `MANIFEST.txt` y `SHA256SUMS`. Metadata registra release activa,
tag esperado, revisión Alembic, versión PostgreSQL/pg_dump y encoding.
El código no se copia: conserva/publica la release correspondiente por separado.

La publicación es exclusiva y atómica después de verificar componentes, hashes
SHA-256 y lectura completa del dump mediante pg_restore sin ejecutar SQL.
No reemplaza backups existentes ni aplica retención automática. Errores y
SIGINT/SIGTERM limpian temporales propios. SIGKILL/apagado puede dejar un
subdirectorio oculto privado `.ticketyn-backup.*`; no se elimina automáticamente
porque otra ejecución podría estar utilizándolo. No es un backup publicado.
Se requiere aproximadamente espacio para dump y tar simultáneamente.
Evita migraciones/cambios de release o configuración concurrentes al backup.

Para inspeccionar sin restaurar, extrae como root en un directorio privado 0700
con umask 077 y ejecuta `sha256sum --check --strict SHA256SUMS` y
`pg_restore --list database.dump`. No extraigas archivos de backups no confiables.
Los hashes detectan corrupción, no autenticidad. El archivo **no está cifrado** y
contiene credenciales: transferencias y copias externas deben protegerse.

`restore.sh` permite recuperar el formato oficial en una instalación compatible;
las restricciones y recuperación se describen a continuación. El dump contiene una sola DB con objetos, datos,
secuencias y permisos; no incluye roles globales, configuración PostgreSQL,
Nginx/systemd ni recuperación a un instante mediante WAL.


### Restauración de producción

Desde el árbol confiable de Ticketyn que contiene `restore.sh`, `backup.sh` y
`deploy/restore_support.py`, como root:

```bash
./restore.sh /ruta/arbitraria/backup.tar
# Para reemplazar una DB ticketyn existente, incluso si está vacía:
./restore.sh --replace /ruta/arbitraria/backup.tar
```

Sin `--replace`, cualquier DB ticketyn existente causa aborto. `--replace` exige
escribir **REEMPLAZAR ticketyn**; Enter/otra respuesta cancela. Antes de detener
Ticketyn ejecuta obligatoriamente backup.sh y valida el backup de seguridad.
Si ese backup falla, DB/configuración permanecen intactas.

Requisitos: instalación estándar con current, Python/venv, Alembic, configuración
root:root 0600, unidad Ticketyn y sitio Nginx activo. No instala otra release,
no modifica current ni ejecuta migraciones. Exige coincidencia exacta de versión,
hash del pyproject y HEAD Alembic; PostgreSQL servidor y herramientas cliente
requieren la misma versión mayor que el backup. Un rol existente debe tener el
marker del instalador/restore, LOGIN sin privilegios elevados, sin membresías ni
otras DB propias. Un rol ajeno nunca se adopta. Puede crear el rol si falta.

La validación inicial solo escribe temporales privados: rechaza symlinks en la
ruta de entrada, TAR corruptos, rutas extrañas, componentes adicionales/duplicados,
enlaces, dispositivos y extensiones inesperadas. Extrae únicamente los cinco
archivos oficiales mediante streaming; comprueba hashes, configuración, metadata
y lectura completa del dump. **Utiliza exclusivamente backups confiables**:
SHA-256 no autentica un backup y pg_restore ejecuta su SQL.

Después de confirmar toma el lock del instalador, revalida identidades y guarda
estado privado bajo `/etc/ticketyn/restore-state`. Detiene únicamente Ticketyn,
bloquea conexiones a su DB y termina solo sesiones de esa DB. Restaura primero
una DB identificada por la operación, en transacción y con propietario ticketyn,
sin propietarios/ACL de otros roles. Comprueba revisión y propietarios antes de
hacer un cambio transaccional de nombres. El flujo de restore no elimina DBs;
la limpieza posterior requiere `--finalize` explícito.

En `--replace`, la original queda bajo `ticketyn_previous_<identificador>`, con
conexiones deshabilitadas. Conserva incluso escrituras posteriores al backup previo.
Se reemplaza la configuración de forma atómica (root:root 0600) y se sincroniza
la contraseña recuperada mediante `psql \password`, por stdin y `setsid --wait`,
sin secretos en argumentos/salida. Se habilita la DB restaurada solo después de
sincronizar credenciales, se inicia Ticketyn y se comprueban health y customers
**mediante Nginx**, con reintentos y validación JSON, más escucha loopback de Uvicorn.

Si falla antes de intentar el cambio de nombres, puede habilitar/reiniciar la DB
original únicamente cuando OID, configuración y release siguen coincidiendo y se
habían bloqueado sus conexiones. Si falla después de intentar ese cambio, deja
Ticketyn detenido: no hace rollback automático porque puede haber escrituras o
un resultado ambiguo. Conserva DBs, backup previo, `previous.env`, diagnósticos
privados y `progress.txt`/`RECUPERACION.txt`. No imprime errores PostgreSQL que
pudieran contener datos sensibles. Un fallo al detener el servicio no toca la DB.

SIGINT/SIGTERM siguen esa misma política y limpian temporales propios. SIGKILL o
pérdida de energía pueden dejar temporales, DB bloqueada o una operación parcial:
revisar OIDs/estado y procesos antes de actuar. No reejecutar ciegamente. Incluso
tras éxito, el estado y la DB anterior se conservan; una segunda restauración
se bloquea hasta finalizar explícitamente la operación exitosa con `--finalize`.
Los estados fallidos siguen requiriendo revisión manual.
No se garantiza detener servicios si systemd falla: el diagnóstico lo indica.

Primera versión: solo PostgreSQL local estándar y HTTP, sin migración entre
versiones, descarga de releases ni recuperación automática completa. Usa UTF8 con
locale C para la DB restaurada; el formato v1 no registra la collation original.
No preserva ACL personalizadas: normaliza objetos al rol Ticketyn. Reserva espacio
para DB original, DB restaurada y backup previo. No ejecutar instalación, migraciones,
backups externos ni cambios administrativos concurrentes durante restore.
No adapta automáticamente markers de `install-state`: restore no es reinstalación.


### Finalizar una restauración verificada

Cuando hayas revisado los datos restaurados, como root:

```bash
./restore.sh --finalize
```

Exige restore-state completado, archivos privados válidos y coincidencia de
operación, OIDs, metadata/release/Alembic. Comprueba que ticketyn es la DB restaurada
esperada y la anterior conserva su OID, propietario, UTF8 y conexiones deshabilitadas,
sin sesiones activas. Valida el backup previo y su relación con previous.env.
Exige servicio activo, health/API correctos mediante Nginx y Uvicorn en loopback.
Todas estas comprobaciones preceden a cualquier cambio del estado/DB.

Muestra el nombre/OID exactos de la DB anterior, advierte que dejará de estar
disponible como rollback local y confirma que el backup de seguridad permanece.
Exige escribir exactamente **FINALIZAR RESTAURACION**, sin comillas; Enter, texto
parcial o con comillas cancela. Revalida bajo el lock de instalación y registra
una intención durable antes del DROP. Solo elimina la DB registrada, nunca usa
wildcards ni FORCE; no termina sesiones, modifica configuración, reinicia servicios,
ejecuta migraciones ni elimina backups.

Si el DROP falla, conserva restore-state y permite reintentar. Si SIGKILL/apagado
ocurre después del DROP pero antes del cierre, otro `--finalize` reconoce la
intención registrada, confirma que ese OID ya no existe y completa el archivo
sin otro DROP. Una DB ausente sin intención, renombrada o con un nombre reutilizado
por otro OID provoca aborto conservador. La confirmación se exige también al reintentar.
SIGINT/SIGTERM antes del DROP son inocuos para la DB; después, conservan el estado
necesario para completar. No realizar DDL/cambios administrativos concurrentes:
el lock coordina scripts Ticketyn, no sesiones independientes de un administrador.

Tras verificar la ausencia del OID anterior, conserva un registro mínimo sin
secretos en `/etc/ticketyn/restore-history/<operación>.json` (root:root 0600,
directorio 0700). Registra OIDs, release/Alembic, clúster, fecha de confirmación y
ruta/hash del backup previo. Publica ese registro, retira restore-state mediante
rename exclusivo y limpia únicamente sus archivos verificados, incluidos los
secretos anteriores. Futuras restauraciones ya no quedan bloqueadas.
Una interrupción durante esa última limpieza puede dejar un directorio privado
`<operación>.pending` en restore-history; el cierre ya está registrado y no bloquea
un restore nuevo. Revisar/limpiar ese residuo manualmente; no contiene una DB pendiente
que deba eliminarse. No hay retención automática ni eliminación de backups.

Los nuevos restores completados incluyen un comprobante de integridad que liga
archivos, configuración, release y clúster. Los estados anteriores sin comprobante
se aceptan únicamente mediante validación cruzada de progress, metadata, documento
de recuperación, backup y OIDs. Esto detecta inconsistencias; no protege contra
un administrador root que falsifique coherentemente todos los registros.
Un restore exitoso que no reemplazó una DB también puede finalizar: cierra su
estado sin ejecutar ningún DROP ni exigir un backup previo inexistente.

## Actualización de producción

### Abandonar un update fallido antes de migrar

```bash
ticketyn-update --abort
# Desde la fuente, también: ./update.sh --abort
```

Solo admite operaciones normales v2 con resultado `interrupted_or_failed` y
fase `preparing`, `backup`, `prepared` o `stopping` (`SAFE_RETRY`). Verifica
checkpoint independiente, release anterior/inode/snapshot, symlink `current`,
configuración, unidad/Nginx y DB (OID, cluster, propietario/UTF-8 y revisión
Alembic original, coincidente con HEAD anterior). Rechaza estados complete,
v1, recovery, posteriores al límite de migración o cualquier incoherencia.
Un checkpoint `pending` tras SIGKILL no se interpreta automáticamente como
fallido: requiere diagnóstico administrativo; no existe `--force`.

No hace backup, migración, restore, cambio de current, borrado de releases ni
modificación de servicios/DB. Conserva backups y releases preparados; por eso
una nueva actualización puede elegir otro tag, pero no sobrescribe el destino
abandonado. Si el servicio ya estaba detenido, permanece detenido.

Registra una intención durable `abort.reason=voluntarily_aborted`, preservando
fase, resultado fallido, diagnóstico y checkpoint original. Luego mueve
atómicamente todo `update-state` a `update-history/<operation>` y sincroniza
ambos directorios. El historial no presenta la operación como exitosa.
Una interrupción antes del movimiento conserva el bloqueo: repetir `--abort`
revalida y completa el archivado; update/recovery rechazan un abort pendiente.
Después del movimiento ya no existe `update-state`: otra llamada a `--abort`
informa que no hay operación pendiente, sin tocar el historial. No se borra
ningún estado ambiguo ni se hace rollback de esquema.

Para instalaciones con bundle administrativo anterior, provisionar primero
el updater aprobado mediante el procedimiento descrito a continuación.

Las nuevas instalaciones publican `/usr/local/sbin/ticketyn-update`. Puede
invocarse como root desde cualquier directorio, sin checkout externo:

```bash
ticketyn-update v0.2.0
ticketyn-update --recover v0.2.1
```

Utiliza copias completas y verificadas de `update.sh`, `backup.sh` y sus tres
auxiliares Python bajo `/opt/ticketyn/admin/updater/<sha256>`. El lanzador y
bundles son root-owned y no escribibles por el servicio. No dependen de
`/opt/ticketyn/current`; cambiar la release activa no cambia el updater en uso.
Se conservan bundles anteriores. No se actualiza automáticamente la herramienta
administrativa desde una candidata: se publica mediante el instalador aprobado.

Para incorporar o renovar el comando en una instalación anterior, desde una
release/checkout de confianza que contenga estos archivos (solo este paso de
provisión requiere la fuente), como root:

```bash
python3 -I -B deploy/install_updater.py /ruta/absoluta/a/la/fuente
```

Esto solo publica el comando y auxiliares; no ejecuta update, migraciones ni
reinicia servicios. `install.sh` sigue siendo un instalador inicial y conserva
su rechazo a reinstalar una instalación completada. Sus reruns parciales pueden
repetir la provisión de forma segura. El provisionador verifica el bundle y la
identidad del lanzador antes de renovarlos; rechaza comandos ajenos, enlaces,
permisos inseguros o bundles modificados. La publicación es atómica y está
serializada. No editar concurrentemente estos archivos como root.

Se mantienen compatibles `./update.sh <tag>` y `./update.sh --recover <tag>`
desde la fuente original, con exactamente las mismas garantías.

Ejecutar como root, o mediante sudo, indicando **un tag explícito** del repositorio
oficial `https://github.com/AngelAqRod/ticketyn.git`:

```bash
./update.sh v0.2.0
# También se admiten prereleases SemVer:
./update.sh v0.1.1-test.1
```

No selecciona «latest», no ejecuta `git pull` en la instalación, no instala
Node/npm ni modifica Nginx. Requiere una instalación administrada completada,
servicios saludables, configuración privada, PostgreSQL local y DB en el HEAD
Alembic de la release activa. Un restore pendiente debe finalizarse primero.
Utiliza el mismo lock de install/restore; los subprocesos lo heredan para impedir
un reintento mientras una dependencia/migración siga ejecutándose tras SIGKILL.
No realizar cambios administrativos
concurrentes en PostgreSQL, releases, configuración, systemd o Nginx.

Obtiene exclusivamente el tag remoto solicitado, comprueba su objeto y commit,
rechaza tags que cambien durante la descarga/reintento y copia únicamente el
contenido permitido. Los tags no están firmados/verificados criptográficamente:
se confía en HTTPS y en el control del repositorio oficial. Solo admite avance
SemVer dentro de la misma versión mayor; rechaza misma versión, downgrade,
build metadata y cadenas Alembic ramificadas o revisiones aplicadas modificadas.

**Contrato de versionado:** `project.version` debe ser el núcleo numérico del tag
(por ejemplo `0.1.1` para `v0.1.1-test.1` y para `v0.1.1`). Esto se aplica de forma
uniforme, porque identificadores SemVer arbitrarios no son versiones Python
PEP 440. El directorio sigue la identidad completa del tag, por ejemplo
`releases/0.1.1-test.1`. `.ticketyn-release.json` liga tag, commit, versión del
paquete y hash de pyproject; backup/restore reconocen esa identidad sin cambiar
el formato de los backups. Las instalaciones originales sin manifiesto siguen
usando pyproject y el nombre de su directorio. Una release debe incluir
`frontend/dist` precompilado, lock, migraciones y helpers/scripts de mantenimiento.

Prepara el venv en su ruta definitiva, con dependencias runtime exactamente
bloqueadas y paquete no editable; comprueba `pip check`, imports, versiones,
assets e integridad del código. Pip puede descargar las dependencias de build
indicadas en pyproject en un entorno de build aislado; el lock actual fija
versiones runtime, no hashes ni herramientas de build. No se sobreescribe una
release destino preexistente: solo se retoma una preparación identificada por
el estado propio y el inode del directorio.

Antes de detener Ticketyn exige un backup íntegro de `backup.sh`, verifica su
contenido/configuración/revisión y registra ruta y SHA-256. No elimina backups
ni releases anteriores. Deshabilita temporalmente el arranque automático y
luego detiene Ticketyn; esto evita arrancar código viejo tras un corte de energía
durante una migración. Ejecuta Alembic con el venv/código destino únicamente si
cambia HEAD; exige continuidad lineal y conserva las revisiones aplicadas. Una
vez verificado el HEAD, activa `current` mediante intercambio atómico que
preserva/rechaza objetos inesperados. Arranca y comprueba servicio, escucha
**local** 127.0.0.1:8000, health/API mediante Nginx, index y assets. Los errores
HTTP/conexión transitorios se reintentan silenciosamente; el fallo definitivo
aborta. Tras éxito vuelve a habilitar el arranque automático.

### Estado y recuperación de una actualización

`/etc/ticketyn/update-state/state.json` (directorio 0700, archivo 0600, root:root)
registra operación, origen/destino, commit/tag, revisiones Alembic, identidades de
DB/clúster/directorios, hashes, backup, fase y resultado. No contiene contraseña
ni DATABASE_URL. Tras éxito se archiva en
`/etc/ticketyn/update-history/<operación>/state.json`; no bloquea otra actualización.
Si el cierre se interrumpe con fase `complete`, repetir el mismo comando valida
la instalación y termina de archivar.

Antes de intentar migraciones, repetir **el mismo tag** puede retomar la descarga,
preparación o backup. Revalida la instalación y el contenido y crea otro backup;
no reutiliza silenciosamente una instantánea antigua. Si quedó detenido durante
`stopping`, solo reactiva el origen tras demostrar pointer, OID, configuración
y revisión originales. No borra destinos desconocidos ni operaciones de otro tag.

Desde la fase `migrating` (registrada **antes** de DDL), un fallo deja Ticketyn
**detenido y deshabilitado** y conserva ambas releases, backup y estado. Esta
primera versión no realiza rollback automático, incluso cuando HEAD no cambió:
no adivina compatibilidad. SIGINT/SIGTERM conservan el estado y ejecutan esta
protección; SIGKILL/pérdida de energía pueden dejar una fase pendiente y un
workspace privado `.ticketyn-update-*` en releases. Un reintento reconoce el
estado y rechaza continuar desde el límite de migración/activación. No limpiar
esos artefactos sin revisión; pueden contener una copia privada de la configuración
extraída del backup. Los temporales normales se eliminan al salir.

### Recuperación hacia delante

```bash
# Siempre un tag explícito posterior a la release fallida:
./update.sh --recover v0.2.1
```

No es rollback, downgrade ni restore. No hay `--force`. La recuperación requiere
Ticketyn detenido **y deshabilitado**, sin listener backend, una DB/revisión,
configuración, current, releases y backup coherentes con una operación fallida.
También verifica que systemd/Nginx no cambiaron. Ante ambigüedad aborta sin
modificar DB, current, configuración ni servicios.

**Los estados antiguos `ticketyn-update-v1` no pueden recuperarse con este
comando.** Les faltan huellas completas de la release anterior/venv, la identidad
del symlink activado y checkpoints independientes. Esto incluye la operación
fallida de laboratorio creada por el updater anterior en v0.1.3-test.1. No se
convierte retrospectivamente ni se admiten excepciones por versión/tag. Para
probar recovery habrá que generar una nueva operación fallida con este updater;
este cambio no publica una nueva release ni modifica el laboratorio.

Las operaciones nuevas usan `ticketyn-update-v2`. Cada checkpoint se escribe
privadamente (directorios 0700, archivos 0600, root:root) en
`/etc/ticketyn/update-evidence/<operación>/<checkpoint>.json` antes de publicar
state.json. Incluye hashes del contenido y del Python instalado, identidades de
DB/clúster/directorios/symlinks y backup; no incluye secretos. Recovery coteja
state.json con esa evidencia independiente y con los recursos reales. Los
checkpoints se conservan, no se eliminan automáticamente. No son firmas ni
protegen contra un root malicioso que falsifique coordinadamente toda la evidencia.

Prepara íntegramente la candidata sin cambiar current. Exige **otro backup** de
la DB post-fallo, además del backup original. Ambos quedan conservados. Verifica
una cadena Alembic única y revisiones previas intactas usando la release fallida
como baseline. Si la DB ya está en HEAD no ejecuta migraciones; si HEAD es
posterior migra únicamente hacia delante con el nuevo venv. Tras verificar DB,
intercambia current atómicamente, arranca y comprueba loopback, health, API,
frontend y assets. Solo entonces habilita autostart.

La operación original permanece **fallida** en el mismo `update-history`.
La recovery tiene su propio identificador, `parent_operation_id` y hash del
registro padre, con su backup, revisiones y resultado. Una recovery fallida puede
tener otra recovery posterior cuando todas las identidades/límites lo permiten.
No se cambia el resultado original a success ni se eliminan releases/backups.

SIGINT/SIGTERM conservan diagnóstico; después del límite sensible detienen y
deshabilitan Ticketyn. Un reintento del mismo tag antes de migrar vuelve a
verificar/preparar y crea otro backup. Un venv parcial sin huella de preparación completa
exige intervención administrativa: no se ejecutan binarios no verificables ni se
borran automáticamente. Después de una migración **confirmada**
podrá completar activación sin repetir DDL, si DB, releases, backups y symlinks
siguen exactamente como se registraron. Una interrupción durante una migración
real exige intervención; no se deduce seguridad únicamente de alembic_version.
Si no había cambio de HEAD, ese límite se puede retomar sin DDL.

SIGKILL/pérdida de energía no ejecutan handlers. Se cotejan estado e identidades:
la intención del intercambio registra el inode del nuevo symlink antes de
activarlo, permitiendo distinguir ambos lados del intercambio. Si quedó un
servicio activo/habilitado en una operación pendiente, recovery **rechaza**:
el administrador debe inspeccionar y detener/deshabilitar Ticketyn antes de
reintentar. No seguir funcionando automáticamente después de una situación
ambigua. Pueden quedar temporales privados y symlinks de intercambio; no se
borran automáticamente. Una recovery completada puede repetirse para verificar
su estado/cerrar el archivo pendiente, sin migrar ni crear otro backup.

No basta con volver current al código anterior si cambió el esquema. Para un
estado v1 o una migración incierta sigue siendo necesaria recuperación
administrativa sobre una combinación demostrablemente compatible. No ejecutar
Alembic downgrade genéricamente ni forzar restore entre revisiones distintas.

Prueba E2E recomendada: sobre una copia/LXC descartable v0.1.0 con datos y backup
externo verificado, publicar un tag inmutable `v0.1.1-test.1` con project.version
`0.1.1`, dist precompilado y esta implementación. Ejecutar update, comprobar
preservación de datos/exports/configuración, HEAD, current, releases, backup e
historial; reiniciar y repetir pruebas funcionales. Comprobar rechazo de misma
versión/downgrade. Usar un segundo entorno descartable para probar un tag con
migración y fallos/interrupciones; nunca retargetear un tag publicado para reintentar.

## Adoptar una instalación manual existente

`./adopt.sh` (como root, o `sudo ./adopt.sh`) permite adoptar una instalación
manual **sin reinstalar, actualizar ni migrar Ticketyn**. Ejecuta el script desde
una copia local y confiable de estas herramientas administrativas; no requiere
red y no modifica el checkout de la aplicación activa. No es un mecanismo de
reparación, no tiene `--force` y no permite omitir verificaciones.

La primera versión acepta exclusivamente el baseline **0.1.0**, commit
`5d478abc97ffa18bb5293b96dfedc8649e89a013`, con un checkout Git limpio dentro de
`/opt/ticketyn/releases/0.1.0`, `current` apuntando a él y Alembic en
`0004_nodes_responsibles`. Compara literalmente los archivos versionados con
los blobs del commit, incluso si Git oculta cambios mediante `assume-unchanged`
o `skip-worktree`. Verifica los hashes internos de commit/tree/blobs y ejecuta
`git fsck --full --strict`; rechaza alternates, replace objects, grafts y shallow clones.
Este baseline requiere `.git` como directorio seguro dentro de la release;
no admite worktrees con metadatos externos ni `.git` como archivo/enlace.
También comprueba permisos, propietario root, entorno privado, dependencias e
código instalado mediante lectura estática (sin ejecutar Python/pip/imports de
la release como root), DB local con propietario `ticketyn` y UTF8, OID/cluster,
servicio activo/habilitado, backend loopback, frontend/assets, health y API.

La unidad debe conservar las directivas del template de ese commit, sin
`drop-ins`, y Nginx debe usar sus directivas; se permite cambiar el puerto HTTP
y omitir la escucha IPv6. No se aceptan otras personalizaciones automáticamente.
`/var/backups/ticketyn` debe existir con propietario root y permisos 0700.
Una configuración distinta debe revisarse, no eludirse mediante metadatos manuales.
No deben modificarse Git, Nginx, systemd ni la configuración concurrentemente.

Solo después de validar se provisiona el updater mediante el mismo mecanismo
que `install.sh`: bundle root-owned en `/opt/ticketyn/admin/updater` y comando
`/usr/local/sbin/ticketyn-update`, independiente de `current` y del CWD. Después
se revalidan las identidades y la integridad/permisos/durabilidad del updater
(incluyendo fsync de archivos y directorios padre), y se publica atómicamente `install-state` completo.
El formato común sigue siendo `format=1`, `status=complete`; `origin=adopted`
y `adoption.json` junto con `adoption.sha256` registran honestamente la operación, fecha, commit, release,
inodes, snapshot, hashes de configuración, revisión Alembic, OID y cluster,
sin contraseñas. El updater y `--abort` validan esta evidencia histórica; los
updates/restores no la reinterpretan como identidad de la DB/release actual.
No contiene campos ficticios de recuperación de `install.sh`.

La adopción no crea backups, no modifica PostgreSQL, la release ni `current`,
y no detiene/reinicia/recarga servicios. Después deben ejecutarse **por separado**
`backup.sh` y, cuando corresponda, `ticketyn-update <tag>`.

Un fallo previo a publicar el estado permite reintentar: puede quedar un bundle
administrativo válido, que el provisioner reconoce y reutiliza. SIGINT/SIGTERM
limpian el staging privado; SIGKILL puede dejar un directorio `.adoption-*` privado
sin publicar, que no se interpreta como instalación completa ni se borra mediante
wildcards. Si el rename final ya ocurrió, el estado aparece completo y durable;
una segunda adopción se rechaza sin cambios. Un `install-state`, `update-state`
o `restore-state` preexistente también se rechaza: requiere diagnóstico, no adopción.
La evidencia prueba coherencia ante cambios accidentales, no protege frente a un
administrador root malicioso ni certifica todos los binarios de terceros del venv.

Durante adopción todas las conexiones PostgreSQL propias fuerzan
`default_transaction_read_only=on` y `search_path=pg_catalog`. Antes de consultar
Alembic verifica que sea una tabla ordinaria del propietario esperado, sin RLS
y con el tipo de columna esperado. La autenticación local utiliza `psql` y un
archivo anónimo en memoria (memfd), sin contraseñas en argumentos, entorno, disco
ni salida. Las peticiones HTTP usan los GET existentes de la aplicación.

Se verifican las propiedades **cargadas** de systemd (usuario, grupo, ejecutable,
entorno, directorio y protecciones), no solo su archivo en disco; una unidad
antigua en memoria se rechaza sin daemon-reload. Para Nginx se verifica la
configuración en disco y el comportamiento HTTP observable, sin pretender
equivalencia byte-a-byte de los workers en memoria ni recargarlos.

La validación estática admite únicamente enlaces internos del venv e intérpretes
Python del sistema seguros; `pyvenv.cfg` debe apuntar a `/usr/bin` y excluir
site-packages globales. Comprueba también permisos de cachés y bytecode de
Ticketyn contra su fuente verificada. Cachés de otra versión de Python o
personalizaciones `.pth` (salvo el shim estándar de setuptools) se rechazan;
requieren revisión administrativa, no una opción force. El hash del recibo
detecta alteración/inconsistencia, no constituye una firma contra root malicioso.
