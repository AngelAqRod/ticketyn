# Nomenclaturas y creación de puertos — v0.8.0

Catálogo global en Administración → Catálogos → Nomenclaturas de puertos.
No requiere fabricante ni configura características físicas del puerto.
No se incluyen prefijos ni fabricantes obligatorios ni se clasifican registros automáticamente.

## Datos y compatibilidad

`port_nomenclatures` guarda nombre descriptivo, prefijo literal, formatos y estado.
El prefijo admite símbolos imprimibles y conserva exactamente su escritura;
es único mediante `lower(prefix COLLATE "C.utf8")`, incluso estando inactivo.
Una nomenclatura activa exige al menos un formato habilitado, sin duplicados.
El prefijo no cambia si existen puertos asociados; la eliminación física también
se rechaza. Cambiar el nombre descriptivo, los formatos o el estado no renombra
ni modifica puertos existentes.

`distribution_ports` añade `nomenclature_id`, `numbering_format` y
`number_components`, opcionales. Los puertos anteriores conservan nombre, ID,
estado, asociaciones y edición de descripción/nombre sin clasificación obligatoria.
El PATCH permite clasificarlos explícitamente enviando los tres campos: la
clasificación debe coincidir con el nombre existente, sin renombrarlo automáticamente.
Para retirar una clasificación se envían los tres campos como null. Los nombres
clasificados no admiten una edición libre que contradiga su clasificación.

La migración pendiente `0037_port_nomenclatures`, ya presente al iniciar esta tarea,
depende de `0036_customer_activation_notes`. Comprueba duplicados históricos y
detiene el upgrade mostrando equipos/IDs afectados; no fusiona, renombra ni elimina.
La nueva revisión `0038_port_classification` sigue a 0037 y verifica en
base de datos la coherencia de la clasificación opcional. No modifica filas.
0037 rechaza un downgrade si existen nomenclaturas o su evidencia operativa.
No se ejecutaron migraciones en bases persistentes.

El índice existente `uq_distribution_ports_name_normalized` sigue garantizando
unicidad por equipo sobre `lower(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g')) COLLATE "C.utf8")`.
Incluye puertos históricos e inactivos; no confunde alias físicos distintos.

## Generación y API

Una sola implementación en `src/ticketyn/api/port_nomenclatures.py`,
`generated_names`, genera los nombres. N, X/Y, X/Y/Z y W/X/Y/Z usan respectivamente
0, 1, 2 y 3 posiciones fijas, seguidas por el número principal. Todos los números
son enteros no negativos, incluido cero. El nombre completo admite hasta 255 caracteres.

| Ruta | Contrato |
|---|---|
| `GET /api/port-nomenclatures` | Activas por defecto; `include_inactive`, `limit` 1–200 y `offset`. |
| `GET /api/port-nomenclatures/{id}` | Consulta incluyendo referencias inactivas. |
| `POST /api/port-nomenclatures` | `{name, prefix, formats, active?}`. |
| `PATCH /api/port-nomenclatures/{id}` | Configuración completa `{name, prefix, formats, active}`. |
| `DELETE /api/port-nomenclatures/{id}` | Solo sin puertos referenciados. |
| `POST /api/distribution-ports/preview` | Generación y comprobación real sin escrituras ni reserva. |
| `POST /api/distribution-ports` | Creación individual, mismo cuerpo de generación y `preview_token`. |
| `POST /api/distribution-ports/batch` | Creación transaccional de rango, mismo cuerpo y `preview_token`. |

Ejemplo de petición de vista previa:

```json
{
  "distribution_device_id": 10,
  "nomenclature_id": 2,
  "numbering_format": "X/Y/Z",
  "positions": [1, 0],
  "start": 0,
  "end": 23,
  "mode": "missing",
  "description": null
}
```

`end` se omite en creación individual. `complete` exige que todos los nombres
sean nuevos; `missing` conserva los existentes y crea solo los faltantes.
Cada solicitud admite hasta **256 nombres**, antes de descontar existentes.
La respuesta de vista previa incluye `names: [{name, existing}]`, `total`,
`existing_count`, `create_count`, `blocked` y `preview_token`.
La confirmación repite exactamente la petición añadiendo ese token.
El resultado masivo devuelve `created`, `existing_count` y `total`.

**Cambio de contrato deliberado:** el antiguo POST con `{distribution_device_id,
name}` devuelve 422. Las integraciones deben usar nomenclatura, formato, números
y vista previa. No se mantiene una vía de creación libre que evite las reglas.
Las consultas, IDs y asociaciones históricas siguen siendo compatibles.

## Atomicidad y concurrencia

La vista previa usa la misma expresión SQL del índice, no una comparación local
del navegador. Su huella SHA-256 incluye solicitud, equipo, configuración de
nomenclatura y los puertos encontrados (IDs, nombres y estados).

La confirmación adquiere `pg_advisory_xact_lock(7808001)` mediante
`distribution_write`, vuelve a comprobar padres activos, formatos y nombres,
y contrasta la huella dentro de la transacción. Las escrituras del catálogo,
individuales y masivas comparten esa protección con los cambios de topología.
Si la vista previa cambió, devuelve **409 sin escrituras** y exige otra revisión.
Esta política también se aplica a `missing`: nunca incorpora silenciosamente un
resultado distinto al que confirmó el operador.

Se insertan todos los faltantes y su bitácora en una sola transacción.
Un conflicto del índice o fallo de persistencia/bitácora revierte el lote entero.
La base de datos sigue impidiendo duplicados incluso fuera de la API.
Un rango `missing` completo devuelve cero creados sin escrituras; la interfaz
deshabilita su confirmación para evitar solicitudes vacías.

## Interfaz y permisos

`PortCreateDialog` se reutiliza en `PortFormModal`, en la creación masiva de la
ficha y en `CircuitDistributionFields` (circuitos normales, edición y alta rápida).
Su vista previa se actualiza desde el backend al cambiar los campos. Distingue
existentes/nuevos y bloquea conflictos, datos incompletos y doble envío.
Una respuesta 409 pide revisar la nueva comprobación; no reintenta crear automáticamente.
Los selectores recorren todas las páginas para incluir lotes de 256 puertos.

En circuitos, exactamente un puerto creado se selecciona; varios actualizan las
opciones sin elegir uno arbitrariamente. Los datos del formulario padre permanecen.
Cancelar el circuito no elimina los puertos ya confirmados, como indica el diálogo.

Permisos: `catalogs.port_nomenclatures.{view,lookup,create,edit,delete}`.
Admin/Superadmin administran; Auditor consulta sin escribir. Operador solo usa
lookup y su permiso existente `distribution_ports.create` para vista previa y
creación individual/masiva. Los permisos de puertos habilitan lookup contextual,
sin dar administración del catálogo. Los roles personalizados requieren facultades explícitas.
La bitácora usa `NOMENCL` para el catálogo y `PORT` para cada puerto nuevo.

## Verificación

- `tests/test_port_nomenclatures.py`: generación, catálogo, roles, unicidad,
  faltantes, clasificación explícita, rollback y concurrencia real.
- `tests/test_port_nomenclature_migration.py`: upgrade/downgrade efímero,
  duplicados históricos y conservación de puertos, circuitos y snapshots FMS.
- `frontend/src/components/PortCreateDialog.test.tsx`: cuatro formatos,
  conflictos, límite, cero faltantes, doble envío, circuito y catálogo.
- Regresión de distribución, activaciones, catálogos, permisos y circuitos.

El catálogo empieza vacío: Administración debe configurar nomenclaturas antes
de crear puertos nuevos. No se aplican estas migraciones a DEV/TEST/PROD desde el desarrollo.

## Archivos de la entrega

Nuevos o completados desde la base parcial existente:

- `alembic/versions/0037_port_nomenclatures.py`
- `alembic/versions/0038_port_classification.py`
- `src/ticketyn/api/port_nomenclatures.py`
- `src/ticketyn/schemas/port_nomenclature.py`
- `frontend/src/api/portNomenclatures.ts`
- `frontend/src/components/PortCreateDialog.tsx`
- `frontend/src/components/PortNomenclatureAdmin.tsx`
- `frontend/src/hooks/useDistributionDialog.ts`
- `frontend/src/test/portGeneration.ts`
- `tests/test_port_nomenclatures.py`
- `tests/test_port_nomenclature_migration.py`
- `frontend/src/components/PortCreateDialog.test.tsx`

Integración modificada: `src/ticketyn/models/distribution.py`,
`src/ticketyn/models/__init__.py`, `src/ticketyn/api/distribution.py`,
`src/ticketyn/api/distribution_data.py`, `src/ticketyn/schemas/distribution.py`,
`src/ticketyn/main.py`, `src/ticketyn/security/permissions.py`,
`src/ticketyn/security/routes.py`, `frontend/src/api/index.ts`, `frontend/src/api/client.ts`,
`frontend/src/types/distribution.ts`, `frontend/src/auth/permissions.tsx`,
`frontend/src/pages/Catalogs.tsx`, `frontend/src/pages/SecurityRoles.tsx`,
`frontend/src/pages/DistributionDeviceDetail.tsx`,
`frontend/src/components/DistributionModals.tsx`,
`frontend/src/components/QuickDistributionCreate.tsx`,
`frontend/src/components/CircuitDistributionFields.tsx` y
`frontend/src/styles/distribution.css`.

Fixtures/regresiones adaptados: `tests/conftest.py`, `tests/test_distribution.py`,
`tests/test_activation_distribution.py`, `tests/test_mail_template_variables_v080.py`,
`tests/test_security_authorization.py`, `frontend/src/pages/Catalogs.test.tsx`,
`frontend/src/pages/DistributionDeviceDetail.test.tsx`,
`frontend/src/components/CircuitDistributionFields.test.tsx` y
`frontend/src/components/CircuitDistributionIntegration.test.tsx`.
Documentación sincronizada: `docs/SYSTEM_MAP.md`, `docs/distribution-v0.8.0.md`,
`docs/modules/clientes-circuitos.md`, `docs/modules/catalogos-configuracion.md`
y `AGENT_HANDOFF.md`.

## Resultado de validación de esta entrega

381 pruebas backend dirigidas aprobadas; 184 pruebas frontend distintas aprobadas
(175 de integración/componentes y 9 del cliente API). TypeScript y `git diff --check` correctos.
Upgrade/downgrade y conflictos históricos verificados solo en PostgreSQL efímero.
Revisión visual con Firefox headless en 1440/390 px y API simulada, sin escrituras reales.
No se ejecutó build de producción ni migración sobre bases persistentes.
