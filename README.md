# Ticketyn

Base mínima de un sistema web de gestión de tickets con Python, FastAPI,
PostgreSQL, SQLAlchemy y Alembic. Requiere Python 3.11 o posterior.

## Estructura

```text
src/ticketyn/
  main.py          # Aplicación FastAPI
  api/             # Routers /api/*, /health y funciones de acceso a datos
  schemas/         # Schemas Pydantic de creación, actualización y respuesta
  core/config.py   # Variables de entorno y .env
  db/base.py       # Base ORM y nombres de restricciones
  db/session.py    # Motor y sesiones SQLAlchemy
  models/          # Customer, Circuit, Sector y campos comunes
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

## Migraciones

La primera revisión es `alembic/versions/0001_initial_catalogs.py`. Crea
`customers`, `circuits`, `services` y `sectors`, con sus restricciones e índices.
Esta revisión ya fue revisada y aplicada manualmente a la base de desarrollo.
Se conserva sin modificaciones como parte del historial.

La nueva revisión `alembic/versions/0002_remove_services.py`, posterior a
`0001_initial_catalogs`, elimina el catálogo histórico Service porque Circuit
ya representa el circuito/servicio contratado por un cliente. Está pendiente
de revisión y aplicación manual a la base de desarrollo.

`upgrade()` de 0002 elimina la tabla `services`, incluidos sus registros y
restricciones. No convierte datos de Service en Circuit ni modifica las otras
tablas. `downgrade()` vuelve a crear `services` con el mismo esquema original:
`name` VARCHAR único, `id` INTEGER IDENTITY y PK, `active` BOOLEAN con
predeterminado `true`, `created_at` TIMESTAMP WITH TIME ZONE con predeterminado
`now()`, todos NOT NULL. El downgrade restaura la estructura vacía, no los datos
eliminados.

Para ver la revisión actual y generar el SQL sin ejecutar cambios:

```bash
alembic current
alembic upgrade 0001_initial_catalogs:0002_remove_services --sql
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

Cada tabla tiene una PK entera `id` generada por PostgreSQL mediante
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
`trust` se limita a ese clúster descartable sin escucha TCP. Cada prueba utiliza
una transacción independiente que se revierte al finalizar.

Las pruebas de persistencia y API no usan la conexión de `.env` ni
`DATABASE_URL`: la API sustituye la dependencia de sesión por la sesión del
clúster temporal. No se conectan a la base de desarrollo.
Verifican los modelos sobre
PostgreSQL real, incluidos valores predeterminados, campos obligatorios,
unicidad y claves foráneas. Una prueba compara el SQL de las tablas conservadas
de 0001 con el SQL de los modelos en modo offline. Otra prueba ejecuta 0001,
el upgrade de 0002 y su downgrade en un esquema exclusivo dentro del clúster
temporal, verificando que `services` se crea, se elimina y se restaura con
idéntica estructura. Los cambios de esa prueba se revierten al finalizar. Para
ejecutar solo la prueba HTTP:

```bash
pytest tests/test_health.py
```

La suite de API verifica los tres recursos, respuestas, actualizaciones
parciales, conflictos con rollback, filtros, búsquedas, activos/inactivos,
paginación, validación y documentación automática.

## API REST

Con el backend en ejecución, abre [Swagger UI](http://127.0.0.1:8000/docs).
La especificación OpenAPI está en `/openapi.json`.

| Recurso | Colección | Registro individual |
| --- | --- | --- |
| Customers | `POST /api/customers`, `GET /api/customers` | `GET /api/customers/{id}`, `PATCH /api/customers/{id}` |
| Circuits | `POST /api/circuits`, `GET /api/circuits` | `GET /api/circuits/{id}`, `PATCH /api/circuits/{id}` |
| Sectors | `POST /api/sectors`, `GET /api/sectors` | `GET /api/sectors/{id}`, `PATCH /api/sectors/{id}` |

No hay DELETE físico. Para desactivar o reactivar, envía un PATCH con
`{"active": false}` o `{"active": true}`.

| Recurso | Campos obligatorios en POST | Campos editables en PATCH | Búsqueda y orden |
| --- | --- | --- | --- |
| Customers | `customer_code`, `name` | `customer_code`, `name`, `active` | Busca por código/nombre; ordena por `customer_code` |
| Circuits | `customer_id`, `circuit_code`, `description` | `customer_id`, `circuit_code`, `description`, `active` | Busca por código/descripción; ordena por `circuit_code` |
| Sectors | `name` | `name`, `active` | Busca y ordena por `name` |

POST devuelve 201 y los campos del registro junto con `id`, `active` y
`created_at`. GET y PATCH devuelven 200. Circuit devuelve `customer_id`, sin
anidar Customer. La creación utiliza el estado activo predeterminado del
modelo; `active` se modifica mediante PATCH.

PATCH modifica exclusivamente los campos proporcionados. Un cuerpo vacío
`{}` conserva el registro. No se admiten `null`, textos vacíos o de solo
espacios, ni campos desconocidos o técnicos como `id` y `created_at`. Los
textos válidos se conservan sin cambiar mayúsculas ni normalizar códigos.
Las entradas inválidas devuelven 422.

Todos los listados devuelven un array simple y admiten:

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

La capa funcional actual contiene Customer, Circuit y Sector, dos revisiones
de esquema y endpoints REST de creación, consulta y actualización. Customer
representa al cliente; Circuit representa su circuito/servicio contratado;
Sector es un catálogo independiente, sin relación con Circuit.
Las futuras relaciones de tickets usarán claves foráneas hacia
estas entidades, permitiendo buscar o crear registros durante el flujo de
creación del ticket cuando se implementen API e interfaz.

Los tickets, sus dos estados ABIERTO/CERRADO, fechas manuales, duración,
referencia configurable por instalación, edición, historial y reportería
permanecen como requisitos futuros. No se implementan usuarios, autenticación,
departamentos, responsables, tipos de incidencia, adjuntos ni frontend.
Tampoco se añaden configuraciones Nginx/systemd, instaladores ni scripts de
actualización en esta etapa.
