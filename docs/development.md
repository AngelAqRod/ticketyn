# Desarrollo de Ticketyn

Guía para un entorno local separado de los datos operativos. Los procedimientos
de producción están en [Instalación y administración](deployment.md).

Para aprovisionar claves de cifrado en un directorio privado sin root, consulta
[Gestión de secretos](secrets-v0.6.0.md). No se requieren para arrancar la aplicación.

## Entorno local

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


## Migraciones y cambios

Utiliza revisiones nuevas para cambios de esquema; no edites migraciones históricas
ya aplicadas. Comprueba `alembic heads`, `alembic current` y las dependencias antes
de migrar una base local. La revisión actual es `0024_default_change_types_upper`;
este dato describe el código revisado y deberá actualizarse cuando avance el esquema.

Los tests backend utilizan PostgreSQL temporal. Asegura permisos y espacio en el
directorio temporal; no los ejecutes como root. No sustituyas su base descartable
por una base operativa. La compilación no reemplaza las pruebas funcionales.

`requirements.lock` fija dependencias de ejecución; no es el inventario de paquetes
de una instalación de desarrollo. No lo regeneres copiando indiscriminadamente
`pip freeze` de un entorno con herramientas de pruebas. El instalador utiliza
el lock y una instalación no editable del paquete sin resolver dependencias de nuevo.

## Criterios para contribuir

Reutiliza los componentes y servicios existentes y conserva el lenguaje visual
Capsule NOC. Cambia únicamente lo necesario para el problema tratado y agrega
pruebas de reglas de negocio o regresiones cuando corresponda.

Comprueba compatibilidad con datos históricos, campos opcionales, numeraciones y
exportaciones. Las fechas operativas se interpretan en `America/Guatemala`, con
conversiones compartidas; evita depender de la zona del navegador.

`frontend/dist/` está versionado: cuando cambie el frontend, genera y revisa sus
archivos junto con el código. Los cambios exclusivos de documentación no requieren
recompilarlo. Nunca incluyas `.env`, credenciales, dumps ni documentos operativos.

Consulta [Arquitectura](architecture.md), [Módulos](modules.md) y las guías
especializadas antes de alterar contratos o relaciones entre módulos.
