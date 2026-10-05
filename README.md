# Ticketyn

Ticketyn es un producto web de gestión de incidencias: tickets, clientes,
circuitos/servicios contratados, catálogos, filtros operativos y reportería.
Licencia **GNU AGPL v3, AGPL-3.0-only**; texto completo en [LICENSE](LICENSE).
Versión actual: `0.1.0`.

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
soportados con frontend precompilado. No existen `update.sh`, `backup.sh`
ni rollback automático. La aceptación end-to-end en un sistema limpio sigue
siendo necesaria antes de desplegar datos reales.

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
→ 0004_nodes_responsibles (head)
```

0001 crea los primeros catálogos; 0002 elimina Service histórico; 0003 añade
Tickets, departamentos, tipos y numeración; 0004 añade Nodes/Responsibles y sus
FK nullable. No modificar revisiones aplicadas. Una instalación vacía no contiene
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
- `/var/backups/ticketyn`: backups protegidos, implementación pendiente.

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

Pendientes: actualizador, restauración, CI, artefactos versionados y política HTTPS/acceso. No hay tags/releases
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

`restore.sh` todavía no existe. Restaurar en otro servidor requerirá una release
compatible, crear el rol local ticketyn y sincronizar su contraseña con la
configuración recuperada. El dump contiene una sola DB con objetos, datos,
secuencias y permisos; no incluye roles globales, configuración PostgreSQL,
Nginx/systemd ni recuperación a un instante mediante WAL.
