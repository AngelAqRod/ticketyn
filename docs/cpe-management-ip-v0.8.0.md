# IP de gestión CPE — Ticketyn v0.8.0

## Alcance implementado

`Circuit.cpe_management_ip` contiene una única dirección IPv4 o IPv6 opcional del registro técnico actual. No es inventario CPE ni una instantánea histórica. No consulta equipos de red, no genera enlaces de acceso ni modifica el estado administrativo.

- PostgreSQL: columna `INET`, nullable, sin valor predeterminado, índice ni unicidad.
- Validación compartida de creación y edición: `ipaddress.ip_address()`, salida normalizada. Recorta espacios exteriores; vacío o solo espacios equivale a `null`. Rechaza DNS, CIDR (incluso `/32` y `/128`), listas, texto añadido, valores no textuales y zonas IPv6 (`%eth0`), que no son compatibles con `INET`.
- No limita rangos privados, públicos, reservados ni loopback.
- Restricción `ck_circuits_cpe_management_ip_host`: solo máscaras de host (32 bits en IPv4, 128 en IPv6), también ante escrituras SQL directas. PostgreSQL representa internamente el prefijo de host; la API nunca acepta notación CIDR.

## Contratos y permisos

Se reutilizan `POST/GET /api/circuits`, `GET/PATCH /api/circuits/{id}` y la proyección existente de circuito en `/api/circuits/{id}/operational-detail`. No hay endpoints ni permisos nuevos.

| Entrada | Creación | PATCH |
|---|---|---|
| Campo omitido | `NULL` | Conserva el valor |
| `null`, vacío o espacios | `NULL` | Limpia el valor |
| IPv4/IPv6 válida | Normaliza y guarda | Normaliza y guarda |
| Valor inválido | HTTP 422 | HTTP 422, sin cambios |

Lectura, creación (incluida la contextual) y edición conservan los controles de Circuitos. Los datos técnicos y snapshots FMS no se modifican ni se incorpora el campo a PDF/XLSX.

## Frontend

- `CatalogAdmin`: campo opcional de una línea, utilizado por el catálogo y `CircuitEditModal`. Omite la IP sin cambios en PATCH; envía `null` al borrar una existente.
- `QuickCatalogCreate`: campo equivalente en las altas rápidas de circuitos.
- `CircuitDetail`: muestra la dirección o «No asignada».
- Etiqueta «IP de gestión CPE», placeholder `192.0.2.10`, sin máscaras. La API valida y sus errores se muestran asociados al campo, conservando la entrada y las demás selecciones.
- Tipos en `types/catalog.ts`; etiqueta de errores en `api/client.ts`.

## Migración y operación

Nueva revisión **`0035_cpe_management_ip`**, posterior a `0034_activation_distribution`. Añade exclusivamente la columna y su restricción en `circuits`, sin backfill. No modifica 0033 ni 0034.

**No aplicada a DEV, TEST ni PROD por esta tarea.** El backend actualizado necesita este esquema antes de utilizarse contra una base persistente; su aplicación requiere autorización y el procedimiento operativo habitual.

La reversión elimina la columna solo si no existen direcciones registradas; en caso contrario se detiene para evitar pérdida de información. Nunca limpiar datos reales automáticamente para permitir un downgrade.

## Verificación y continuidad

Pruebas nuevas: `tests/test_cpe_management_ip.py`; integración de formularios en `frontend/src/components/CircuitDistributionIntegration.test.tsx`. La prueba de migración crea una base separada dentro del clúster PostgreSQL efímero del proyecto, verifica datos existentes, tipo y nulabilidad, rechazo de redes y downgrade seguro. La fixture histórica de `tests/test_migration.py` excluye el nuevo campo y su restricción al representar la revisión 0003. La prueba de migración en `tests/test_activation_distribution.py` apunta ahora explícitamente a 0034 en lugar de `head`; conserva sus demás comprobaciones y todos sus casos de exportación sin cambios.

No editar `AGENT_HANDOFF.md` durante el trabajo paralelo de Antigravity. Incorporar luego: campo técnico actual de Circuitos terminado, migración 0035 pendiente de autorización en bases persistentes, resultados finales de las pruebas y ausencia de cambios en generadores PDF/FMS, dist, autenticación y permisos. El mapa técnico y la ficha de Clientes/Circuitos pueden enlazar esta guía en la siguiente integración documental coordinada.

### Resultados dirigidos comprobados

- Backend específico: **31 aprobadas**, incluidas alta/edición/limpieza, serialización, permisos, migración y conservación de filas FMS.
- Frontend relacionado: **121 aprobadas en 7 archivos** (CatalogAdmin, QuickCatalogCreate, CpeModelCircuit, CircuitSectorField, CircuitDistributionFields, CircuitDistributionIntegration y Catalogs).
- TypeScript: `tsc --noEmit -p frontend/tsconfig.json` sin errores.
- `git diff --check` sin errores.
- El primer intento backend dentro del sandbox no pudo iniciar el socket PostgreSQL; las ejecuciones posteriores usaron exclusivamente clústeres temporales con el permiso necesario. Advertencia existente de deprecación Starlette/TestClient, sin fallos funcionales en las pruebas dirigidas.
- Catálogos backend completos: **264 aprobadas** tras actualizar la comprobación del contrato de Circuitos.
- Regresión final de sincronización de sector, distribución, migraciones, FMS, nodos, sectores y snapshots CPE: **154 aprobadas, 1 fallida**. Las revisiones 0034 y 0035 se validaron en PostgreSQL descartable.
- Fallo fuera del alcance: `tests/test_cpe_activation_snapshots.py::test_snapshot_name_and_initial_capacity_survive_mutable_circuit`, línea 77, espera el subtítulo `GESTIÓN DE SERVICIOS · OPERACIONES FMS`. `activation_reports.py` utiliza ahora `modular=True` y `ModularCanvas.chrome()` en A4 vertical dibuja el título, pero no el subtítulo (este solo se dibuja en horizontal). Esos archivos no fueron editados por esta tarea y conservan su hash inicial. La prueba no envía ni utiliza la IP de gestión. No se modificó ni omitió la aserción fallida: corresponde coordinar su resolución con Antigravity, responsable del rediseño PDF.
- Una ejecución amplia anterior obtuvo 415 aprobadas y dos fallidas: contrato exacto de Circuitos sin el nuevo campo y prueba de 0034 que asumía que `head` seguiría siendo 0034. Se corrigieron ambas expectativas y se repitieron las suites afectadas; el fallo del subtítulo apareció al ampliar la regresión a snapshots CPE.

### Archivos de esta tarea

- `src/ticketyn/models/circuit.py`, `src/ticketyn/schemas/circuit.py`.
- `alembic/versions/0035_cpe_management_ip.py` (nuevo).
- `frontend/src/types/catalog.ts`, `frontend/src/api/client.ts`.
- `frontend/src/components/CatalogAdmin.tsx`, `frontend/src/components/QuickCatalogCreate.tsx`, `frontend/src/pages/CircuitDetail.tsx`.
- `frontend/src/components/CircuitDistributionIntegration.test.tsx`, `frontend/src/components/CatalogAdmin.test.tsx`, `frontend/src/components/QuickCatalogCreate.test.tsx`.
- `tests/test_cpe_management_ip.py` (nuevo), `tests/test_catalog_api.py`, `tests/test_migration.py`, `tests/test_activation_distribution.py` (solo destino de la prueba de migración 0034).
- Esta guía (nueva).

No se editaron `AGENT_HANDOFF.md`, los mapas técnicos compartidos, generadores PDF, exportadores XLSX, `frontend/dist/`, migraciones históricas, autenticación ni permisos. Se observaron cambios concurrentes en `fms_exports.py` y `fms_report_exports.py` durante la tarea; no fueron sobrescritos ni modificados por Codex.

### Pendiente para el handoff coordinado

La funcionalidad de IP está implementada y probada. No presentar la regresión ampliada como completamente verde: registrar el fallo del subtítulo PDF anterior y remitirlo a Antigravity sin modificar sus generadores. La revisión 0035 es el head **del código**, no una afirmación del estado de ninguna base persistente. No se aplicó a DEV, TEST ni PROD. No hubo builds, commits ni despliegues.
