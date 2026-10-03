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
El despliegue automatizado está **en preparación**: no existen `install.sh`,
`update.sh` ni `backup.sh`. Los archivos de `deploy/` son templates; no constituyen
un procedimiento definitivo de instalación manual.

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
frontend/         # Source, tests y lockfile npm; dist generado e ignorado
tests/           # Tests backend con PostgreSQL descartable
deploy/          # Templates Nginx/systemd (no instalados automáticamente)
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
produce `frontend/dist`, que no se versiona. Los tests de exportaciones verifican
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

## Producción: preparación, no instalador definitivo

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

Templates disponibles, **sin instalar en /etc**:

- `deploy/systemd/ticketyn.service`: usuario/grupo ticketyn, sin reload, localhost,
  restart ante fallo, journal y hardening moderado. La unidad PostgreSQL umbrella
  no verifica readiness. Validar permisos y restricciones en el LXC objetivo.
- `deploy/nginx/ticketyn.conf`: HTTP, SPA fallback, proxy conservando /api, assets
  cacheables, index sin cache largo y timeouts para exportaciones. TLS y control
  de acceso deben definirse antes de exposición. Docs/OpenAPI pueden bloquearse
  o habilitarse deliberadamente en Nginx; ocultarlos no es autenticación.

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

Pendientes: instalador, actualizador, backup/restauración, CI, artefactos
versionados, validación LXC limpia y política HTTPS/acceso. No hay tags/releases
creados automáticamente.
