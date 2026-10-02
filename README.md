# Ticketyn

Base mínima de un sistema web de gestión de tickets con Python, FastAPI,
PostgreSQL, SQLAlchemy y Alembic. Requiere Python 3.11 o posterior.

## Estructura

```text
src/ticketyn/
  main.py          # Aplicación FastAPI
  api/             # Routers /api/*, /health y funciones de acceso a datos
  schemas/         # Schemas Pydantic de creación, actualización y respuesta
  core/            # Variables de entorno y estados OPEN/CLOSED
  db/base.py       # Base ORM y nombres de restricciones
  db/session.py    # Motor y sesiones SQLAlchemy
  models/          # Catálogos, Ticket y configuración de numeración
alembic/           # Entorno y revisiones de esquema
tests/             # Pruebas automáticas
```

Ejecuta los comandos desde la raíz del proyecto. Las variables del entorno
tienen prioridad sobre `.env`. La aplicación exige `DATABASE_URL` con el
esquema `postgresql+psycopg`; no hay alternativa SQLite.

## Preparar PostgreSQL en Arch Linux

Instala los paquetes:

```bash
sudo pacman -Syu python python-pip postgresql
```

Solo si PostgreSQL todavía no tiene un clúster inicializado, inicialízalo:

```bash
sudo -u postgres initdb --locale=C.UTF-8 --encoding=UTF8 -D /var/lib/postgres/data --data-checksums
```

Si ya tienes PostgreSQL funcionando, utiliza ese clúster. Inicia su servicio:

```bash
sudo systemctl start postgresql
```

Este comando gestiona PostgreSQL; Ticketyn todavía no tiene servicio systemd.
Crea un rol sin privilegios de administración y una base de datos propia:

```bash
sudo -u postgres createuser --pwprompt ticketyn
sudo -u postgres createdb --owner=ticketyn ticketyn
```

`createuser` solicita la contraseña de forma interactiva. Comprueba la conexión
TCP con ese usuario (solicitará la contraseña):

```bash
psql -h 127.0.0.1 -U ticketyn -d ticketyn -W -c 'SELECT 1;'
```

En un clúster existente, revisa sus reglas `pg_hba.conf` si rechaza la conexión.
Para conexiones locales TCP con contraseña, una regla específica es
`host ticketyn ticketyn 127.0.0.1/32 scram-sha-256`; las reglas se evalúan en
orden. Después de editarlo, recarga PostgreSQL con
`sudo systemctl reload postgresql`.

Referencia: [PostgreSQL en ArchWiki](https://wiki.archlinux.org/title/PostgreSQL).

## Preparar y ejecutar Ticketyn

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Edita `.env` y sustituye `CHANGE_ME` por la contraseña elegida. Si contiene
caracteres reservados de URL, codifícalos (por ejemplo, `@` como `%40`).
El archivo está excluido de Git. Nunca publiques credenciales reales.

```bash
uvicorn ticketyn.main:app --reload --host 127.0.0.1 --port 8000
```

En otra terminal:

```bash
curl http://127.0.0.1:8000/health
```

Respuesta: `{"status":"ok"}`. `/health` comprueba que la aplicación responde;
no verifica la disponibilidad de PostgreSQL. El motor conecta cuando se utiliza
una sesión; Alembic sí necesita PostgreSQL para ejecutar migraciones online.

## Frontend en desarrollo

El frontend está en `frontend/` y usa React, TypeScript, Vite y Tailwind CSS.
Requiere Node.js 22.22.2+, 24.15+ o 26+ y npm. En Arch puedes instalarlos con
`sudo pacman -Syu nodejs npm`.

Desde la raíz, inicia el backend como siempre:

```bash
.venv/bin/uvicorn ticketyn.main:app --reload
```

En otra terminal instala las dependencias reproducibles y arranca el frontend:

```bash
cd frontend
npm ci
npm run dev
```

Abre `http://127.0.0.1:5173` (Vite indicará otro puerto si está ocupado).
Su proxy envía `/api` y `/health` a `http://127.0.0.1:8000`. Los componentes
utilizan URLs relativas y no requieren cambios de CORS en FastAPI.
El dashboard consulta `/api/tickets/stats` para mostrar total, abiertos y
cerrados globales, calculados en PostgreSQL sin paginación. La tabla de
recientes utiliza por separado la primera página de tickets; ambas consultas
mantienen sus propios estados de carga/error.

Desde `frontend/`, ejecuta las pruebas con fetch simulado y genera el build:

```bash
npm test
npm run build
```

`npm run test:watch` ejecuta las pruebas en modo interactivo. El build verifica
TypeScript y genera `frontend/dist/`. Los archivos compilados se podrán servir
estáticamente en producción, con fallback a `index.html` para las rutas de la
aplicación y proxy de `/api` y `/health` al backend. Vite no será el servidor de
producción; no se configura Nginx en esta etapa.

## Migraciones

La primera revisión es `alembic/versions/0001_initial_catalogs.py`. Crea
`customers`, `circuits`, `services` y `sectors`, con sus restricciones e índices.
Esta revisión ya fue revisada y aplicada manualmente a la base de desarrollo.
Se conserva sin modificaciones como parte del historial.

La revisión `alembic/versions/0002_remove_services.py`, posterior a
`0001_initial_catalogs`, elimina el catálogo histórico Service porque Circuit
ya representa el circuito/servicio contratado por un cliente. Fue revisada y
aplicada manualmente a la base de desarrollo. Se conserva sin modificaciones.

`upgrade()` de 0002 elimina la tabla `services`, incluidos sus registros y
restricciones. No convierte datos de Service en Circuit ni modifica las otras
tablas. `downgrade()` vuelve a crear `services` con el mismo esquema original:
`name` VARCHAR único, `id` INTEGER IDENTITY y PK, `active` BOOLEAN con
predeterminado `true`, `created_at` TIMESTAMP WITH TIME ZONE con predeterminado
`now()`, todos NOT NULL. El downgrade restaura la estructura vacía, no los datos
eliminados.

La nueva revisión `0003_ticket_domain.py` está pendiente de revisión y
aplicación manual. Su upgrade crea `departments`, `incident_types`,
`ticket_number_config` y `tickets`, con sus PK, restricciones UNIQUE/CHECK,
cinco FK e índices sobre las FK de tickets. No inserta datos en catálogos ni
configuración. Su downgrade elimina, en este orden, `tickets`,
`ticket_number_config`, `incident_types` y `departments`, sin afectar las
estructuras anteriores. Los estados usan VARCHAR con CHECK OPEN/CLOSED,
sin un ENUM nativo que necesite creación/eliminación adicional.

Para ver la revisión actual y generar el SQL sin ejecutar cambios:

```bash
alembic current
alembic upgrade 0002_remove_services:0003_ticket_domain --sql
```

Solo después de revisar y aprobar la migración, puedes aplicarla manualmente
con `alembic upgrade head`. La aplicación no crea tablas al arrancar ni aplica
migraciones automáticamente. `Base.metadata.create_all()` se utiliza
exclusivamente en el clúster descartable de pruebas.

Los modelos se registran en `ticketyn.models`, importado desde
`alembic/env.py`. Para futuros cambios de esquema:

```bash
alembic revision --autogenerate -m "descripcion del cambio"
```

Revisa siempre cada revisión antes de aplicarla.

Referencia: [Autogeneración de Alembic](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).

## Modelos actuales

| Modelo | Identificador visible | Relación |
| --- | --- | --- |
| Customer | `customer_code`, VARCHAR único y manual | Representa al cliente; tiene múltiples circuitos |
| Circuit | `circuit_code`, VARCHAR único y manual | Representa el circuito/servicio contratado; `customer_id` referencia `customers.id` |
| Sector | `name`, VARCHAR único | Catálogo independiente |
| Department | `name`, VARCHAR único | Departamento responsable, definido por la instalación |
| IncidentType | `name`, VARCHAR único | Tipo de incidencia, definido por la instalación |

Cada catálogo tiene una PK entera `id` generada por PostgreSQL mediante
`IDENTITY`, `active` con valor predeterminado `true` y `created_at` con zona
horaria y valor predeterminado `now()`. Todos los campos son `NOT NULL`.
Customer incluye `name`; Circuit incluye `description` de tipo TEXT.
Los VARCHAR no tienen un límite de longitud arbitrario en esta etapa.

La unicidad compara el texto tal como se almacena, con distinción de
mayúsculas/minúsculas. No se generan, convierten a números ni normalizan los
códigos. Tampoco se impone todavía un formato ni se valida el prefijo del
circuito contra el código del cliente. La FK usa siempre los IDs internos.
No hay borrado en cascada: PostgreSQL impide eliminar un cliente referenciado.

Las restricciones únicas crean sus propios índices. Hay índices B-tree
adicionales en `customers.name`, `circuits.description` y
`circuits.customer_id`. Son una base para consultas exactas, ordenación y
consulta de los circuitos de un cliente; no garantizan acelerar búsquedas
parciales `ILIKE '%texto%'`. Las optimizaciones para ese tipo de búsqueda se
evaluarán al implementar la interfaz, sin añadir extensiones ahora.
Referencia: [Tipos de índices en PostgreSQL](https://www.postgresql.org/docs/18/indexes-types.html).

## Pruebas

```bash
source .venv/bin/activate
pytest
```

La prueba de `/health` proporciona una URL PostgreSQL de prueba sin abrir
conexiones; no necesita un servidor ni un `.env` local.

Las pruebas de modelos requieren `initdb` y `pg_ctl` en el PATH (incluidos en
el paquete PostgreSQL de Arch). Ejecútalas con tu usuario normal, no como
root. Pytest crea un clúster temporal bajo su directorio de pruebas, lo inicia
solo por un socket Unix privado y lo detiene al finalizar. La autenticación
`trust` se limita a ese clúster descartable sin escucha TCP. Las pruebas
habituales utilizan transacciones que se revierten al finalizar. La prueba de
concurrencia usa conexiones independientes con datos confirmados en un esquema
exclusivo del clúster temporal; ese esquema se elimina al finalizar.

Las pruebas de persistencia y API no usan la conexión de `.env` ni
`DATABASE_URL`: la API sustituye la dependencia de sesión por la sesión del
clúster temporal. No se conectan a la base de desarrollo.
Verifican los modelos sobre
PostgreSQL real, incluidos valores predeterminados, campos obligatorios,
unicidad y claves foráneas. Una prueba compara el SQL de las tablas conservadas
de 0001 con el SQL de los modelos en modo offline. Otra prueba ejecuta 0001,
el upgrade de 0002 y su downgrade en un esquema exclusivo dentro del clúster
temporal, verificando que `services` se crea, se elimina y se restaura con
idéntica estructura. Las pruebas de 0003 comprueban su DDL, sus tablas vacías,
las FK y su downgrade, conservando las tablas y los datos anteriores. Los
hashes de 0001 y 0002 verifican que ambas permanecen intactas. Los cambios de
las pruebas de migraciones se revierten al finalizar. Para
ejecutar solo la prueba HTTP:

```bash
pytest tests/test_health.py
```

La suite de API verifica catálogos, tickets, numeración, respuestas, actualizaciones
parciales, conflictos con rollback, filtros, búsquedas, activos/inactivos,
paginación, validación y documentación automática.
Incluye creación retroactiva, las cuatro combinaciones de estado/fecha de fin,
edición de tickets cerrados, referencias inmutables, contador con rollback y
ocho creaciones simultáneas iniciadas con una barrera, con sesiones PostgreSQL
independientes. Ninguna prueba utiliza la conexión de desarrollo.

## API REST

Con el backend en ejecución, abre [Swagger UI](http://127.0.0.1:8000/docs).
La especificación OpenAPI está en `/openapi.json`.

| Recurso | Colección | Registro individual |
| --- | --- | --- |
| Customers | `POST /api/customers`, `GET /api/customers` | `GET /api/customers/{id}`, `PATCH /api/customers/{id}` |
| Circuits | `POST /api/circuits`, `GET /api/circuits` | `GET /api/circuits/{id}`, `PATCH /api/circuits/{id}` |
| Sectors | `POST /api/sectors`, `GET /api/sectors` | `GET /api/sectors/{id}`, `PATCH /api/sectors/{id}` |
| Departments | `POST /api/departments`, `GET /api/departments` | `GET /api/departments/{id}`, `PATCH /api/departments/{id}` |
| Incident types | `POST /api/incident-types`, `GET /api/incident-types` | `GET /api/incident-types/{id}`, `PATCH /api/incident-types/{id}` |

No hay DELETE físico. Para desactivar o reactivar un catálogo, envía un PATCH con
`{"active": false}` o `{"active": true}`.

| Recurso | Campos obligatorios en POST | Campos editables en PATCH | Búsqueda y orden |
| --- | --- | --- | --- |
| Customers | `customer_code`, `name` | `customer_code`, `name`, `active` | Busca por código/nombre; ordena por `customer_code` |
| Circuits | `customer_id`, `circuit_code`, `description` | `customer_id`, `circuit_code`, `description`, `active` | Busca por código/descripción; ordena por `circuit_code` |
| Sectors | `name` | `name`, `active` | Busca y ordena por `name` |
| Departments | `name` | `name`, `active` | Busca y ordena por `name` |
| Incident types | `name` | `name`, `active` | Busca y ordena por `name` |

POST devuelve 201 y los campos del registro junto con `id`, `active` y
`created_at`. GET y PATCH devuelven 200. Circuit devuelve `customer_id`, sin
anidar Customer. La creación utiliza el estado activo predeterminado del
modelo; `active` se modifica mediante PATCH.

PATCH modifica exclusivamente los campos proporcionados. Un cuerpo vacío
`{}` conserva el registro. No se admiten `null`, textos vacíos o de solo
espacios, ni campos desconocidos o técnicos como `id` y `created_at`. Los
textos válidos se conservan sin cambiar mayúsculas ni normalizar códigos.
Las entradas inválidas devuelven 422.

Los listados de catálogos devuelven un array simple y admiten:

- `search`: coincidencia parcial de texto sin distinguir mayúsculas, mediante
  SQLAlchemy `icontains` (ILIKE en PostgreSQL). `%` y `_` se buscan literalmente,
  sin convertirlos en comodines.
- `include_inactive`: predeterminado `false`; con `true` incluye activos e
  inactivos. GET por ID puede devolver un registro inactivo.
- `limit`: predeterminado 50, mínimo 1 y máximo 200.
- `offset`: predeterminado 0, mínimo 0.

Los circuitos también admiten `customer_id` positivo. Los filtros se pueden
combinar y se aplican antes de paginar; un filtro sin coincidencias devuelve
`[]`. La ordenación incluye el ID como desempate.

```bash
curl -X POST http://127.0.0.1:8000/api/customers \
  -H 'Content-Type: application/json' \
  -d '{"customer_code":"SGgt-00000","name":"Empresa ABC"}'
curl 'http://127.0.0.1:8000/api/customers?search=sggt&limit=50&offset=0'
curl 'http://127.0.0.1:8000/api/circuits?customer_id=1&include_inactive=true'
curl -X PATCH http://127.0.0.1:8000/api/customers/1 \
  -H 'Content-Type: application/json' -d '{"active":false}'
```

Un registro inexistente o un `customer_id` inexistente al crear/actualizar un
circuito devuelve 404 con un mensaje claro. El cliente solo necesita existir;
puede estar inactivo. Su ID nunca se deduce del código del circuito.

Los códigos o nombres duplicados devuelven 409, incluso si el registro
existente está inactivo. La unicidad permanece sensible a mayúsculas, como en
el esquema existente. PostgreSQL es la autoridad de unicidad y claves
foráneas; los errores de integridad hacen rollback y se traducen a mensajes
HTTP sin exponer detalles internos del motor.

Referencia de búsqueda:
[SQLAlchemy icontains](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.ColumnOperators.icontains).

## Numeración de tickets

`GET /api/settings/ticket-number` consulta la configuración única.
`PATCH /api/settings/ticket-number` modifica parcialmente `prefix`,
`separator`, `next_number` y `padding`. No hay una API genérica de settings.

La configuración se crea al consultar/modificarla o al crear el primer ticket,
mediante INSERT ON CONFLICT DO NOTHING. Sus valores genéricos son:

```json
{"id": 1, "prefix": "", "separator": "", "next_number": 1, "padding": 0}
```

Una PK y un CHECK `id = 1` permiten como máximo una fila. La configuración no
tiene perfiles ni estado activo. Prefix y separator admiten strings vacíos;
separator admite varios caracteres. Next_number es un entero positivo;
padding acepta enteros de 0 a 20 mediante el API; valores fuera de ese rango
devuelven 422 antes de generar referencias. Ambos utilizan INTEGER de PostgreSQL.

La referencia se construye como `prefix + separator + número con padding`.
Por ejemplo, configurar `TKD`, `-`, próximo número 3 y padding 3 produce
`TKD-003`. Un número con más dígitos que padding nunca se trunca. La referencia
se guarda en el ticket y no se recalcula al cambiar la configuración.

Las creaciones y modificaciones de configuración bloquean la misma fila con
SELECT FOR UPDATE. La inserción del ticket y el incremento del contador se
confirman juntos. Un error revierte ambos cambios: no consume el número de
negocio; la PK técnica IDENTITY sí puede tener huecos. UNIQUE protege tanto
`ticket_number` como `reference`. Los conflictos devuelven 409 sin SQL interno.

Modificar next_number exige un valor mayor que todos los números ya asignados,
independientemente del prefijo. También se comprueba anticipadamente si la
próxima referencia propuesta ya existe. Las restricciones únicas protegen las
creaciones posteriores aunque una configuración produzca una colisión más
adelante. El agotamiento del rango INTEGER devuelve 409; se reserva su último
valor para representar el próximo contador.

Referencia: [Bloqueos de filas en PostgreSQL](https://www.postgresql.org/docs/17/explicit-locking.html).

## API de tickets

| Método | Endpoint | Comportamiento |
| --- | --- | --- |
| POST | `/api/tickets` | Crear y asignar número/referencia; devuelve 201 |
| GET | `/api/tickets` | Listar y filtrar; devuelve 200 |
| GET | `/api/tickets/{id}` | Consultar un ticket; devuelve 200 o 404 |
| PATCH | `/api/tickets/{id}` | Actualizar parcialmente; devuelve 200 o 404 |

No hay DELETE. La creación exige `title`, `description`, `customer_id`,
`circuit_id`, `sector_id`, `department_id`, `incident_type_id` y `start_at`.
`end_at` es opcional y nullable; `status` es OPEN por defecto y solo admite
OPEN/CLOSED. Todos los timestamps de entrada deben incluir zona horaria.

Las cinco referencias deben existir y estar activas al crear. Customer/Circuit
se validan como pareja mediante IDs, nunca mediante códigos. Un registro
inexistente devuelve 404; uno inactivo o una pareja incompatible devuelve 422.
No hay borrado en cascada ni objetos profundamente anidados en las respuestas.

PATCH permite modificar título, descripción, las cinco referencias, fechas y
estado, incluso en tickets CLOSED. Las fechas se validan combinando el PATCH
con los valores actuales: end_at debe ser nulo o >= start_at. Estado y fecha de
fin son independientes: las cuatro combinaciones OPEN/CLOSED y fin
definido/nulo son válidas. Es posible registrar tickets retroactivos.

En una reasignación, se exige que el nuevo catálogo esté activo. Al cambiar
Customer/Circuit se comprueban ambos como pareja activa. El circuito debe
pertenecer al cliente también al editar otros campos; si fue reasignado desde
el catálogo, se puede corregir la pareja en el mismo PATCH. Un ticket histórico
continúa consultable, y permite corregir texto, fechas y estado aunque sus
catálogos estén inactivos. No se exige reactivar referencias que no se cambian.

`id`, `ticket_number`, `reference`, `created_at`, `updated_at` y
`duration_seconds` son de solo lectura; enviarlos en POST/PATCH devuelve 422.
`updated_at` se actualiza mediante SQLAlchemy usando clock_timestamp() cuando
hay cambios persistidos. No se instala un trigger para modificaciones SQL
externas. PATCH vacío conserva los valores. End_at es el único campo que admite
null explícito en PATCH, para quitar la fecha de fin.

`duration_seconds` se calcula como end_at - start_at y devuelve null si no hay
fin. No existe una columna de duración en PostgreSQL.

El listado devuelve un array, con `limit=50`, máximo 200 y `offset=0`.
Ordena por `created_at DESC, id DESC`. Permite filtros combinables por `status`,
las cinco FK y `search`; la búsqueda parcial no distingue mayúsculas y busca
por referencia, título y descripción. No hay filtro activo/inactivo de tickets
porque Ticket no tiene ese campo.

Una instalación nueva no contiene departamentos, tipos ni otros datos
organizativos predeterminados. Crea los catálogos desde sus endpoints, consulta
sus IDs y utiliza `/docs` para probar POST/PATCH de tickets después de aplicar
manualmente 0003.

## Arquitectura prevista

El backend permanece como un único paquete Python modular. React con
TypeScript y Vite se incorporará posteriormente en un directorio separado
`frontend/`; Vite será exclusivamente una herramienta de desarrollo y build.

En producción, Nginx servirá los archivos compilados de React y enviará
`/api/*` a FastAPI. Las rutas funcionales del backend se agrupan
bajo `/api`; `/health` continúa siendo la ruta de comprobación.
FastAPI se ejecutará mediante systemd y accederá a PostgreSQL. La instalación
de producción no dependerá de un servidor Vite.

Los releases estables distribuirán los archivos del frontend ya compilados,
de modo que ejecutar Ticketyn no requiera Node.js, npm ni Vite. El empaquetado
de cada release incluirá el backend y el bundle de frontend correspondiente
a esa misma versión. El instalador futuro consumirá ese bundle ya construido;
no compilará el frontend en el LXC de producción.

La meta futura en un LXC limpio Debian/Ubuntu es:

```bash
git clone <repo>
cd ticketyn
sudo ./install.sh
```

El instalador futuro preparará dependencias, configuración, base de datos,
migraciones y servicios, sin exigir conocer las herramientas del stack.
Cada instalación tendrá su propia configuración y base PostgreSQL; no
compartirá datos con otras instalaciones. No existe todavía `install.sh`.

## Alcance actual

La capa funcional actual contiene Customer, Circuit, Sector, Department,
IncidentType, TicketNumberConfig y Ticket, tres revisiones de esquema y
endpoints REST de creación, consulta y actualización. Customer
representa al cliente; Circuit representa su circuito/servicio contratado;
Sector es un catálogo independiente, sin relación con Circuit.
Ticket utiliza FK hacia los cinco catálogos. Buscar o crear registros durante
el flujo de creación de un ticket será parte de la interfaz futura.

No se implementan usuarios, autenticación, responsable individual, adjuntos,
comentarios, historial/auditoría, reportería, notificaciones ni frontend.
Tampoco se añaden configuraciones Nginx/systemd, instaladores ni scripts de
actualización en esta etapa.
