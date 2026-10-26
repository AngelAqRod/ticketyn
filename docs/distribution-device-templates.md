# Plantillas de equipos de distribución

## Alcance y estado

Implementación en la rama de desarrollo `features/v0.9.0`, sin cambiar la versión oficial. Las plantillas son definiciones para **futuras** creaciones; nunca sincronizan equipos existentes ni modifican circuitos o snapshots FMS. La creación manual continúa disponible. No hay plantillas ni nomenclaturas precargadas.

## Modelo y migración

`0039_device_templates` depende de `0038_port_classification`:

- `distribution_device_templates`: identidad, nombre/modelo único con la normalización conservadora existente, fabricante informativo opcional, descripción, estado y fecha. No existe un catálogo de fabricantes actual; el texto no introduce otra entidad ni condiciona nomenclaturas.
- `distribution_device_template_groups`: FK a plantilla, orden 0–15 único por plantilla, FK `RESTRICT` a `port_nomenclatures`, definición JSONB `{numbering_format, positions, start, end}`. El JSON conserva enteros y posiciones como la clasificación de puertos, sin truncarlos a un entero SQL de ancho fijo.
- Bitácora `distribution_audit`: se añade `TEMPLATE` como tipo de recurso. Cambios de definición y creación de equipos/puertos se auditan dentro de su transacción.
- No se cambian tablas de equipos, puertos, circuitos ni activaciones; no hay backfill ni referencia obligatoria a plantilla desde un equipo.
- Downgrade bloqueado si hay plantillas o evidencia de auditoría de plantillas. No elimina definiciones para facilitar una reversión. Como las migraciones de permisos anteriores, conserva los códigos de permisos para no destruir asignaciones a roles personalizados.

**Límites:** 1–16 grupos y **256 puertos en total por plantilla**, además del límite existente de 256 nombres por rango. Evita eludir el límite dividiendo rangos y mantiene acotada una única transacción de equipo + puertos + auditoría.

## Validación central

`PortNumbering` comparte el contrato numérico con la creación individual/masiva. `generated_names()` sigue siendo el único generador. Se admiten N, X/Y, X/Y/Z, W/X/Y/Z, enteros no negativos y rangos desde cero. Se conserva literalmente el prefijo del catálogo. Los nombres de cada grupo se generan en orden numérico ascendente, incluyendo 2 antes de 10.

La vista previa comprueba todos los grupos y aplica exactamente la expresión PostgreSQL de normalización del índice de nombres (mayúsculas/espacios, sin interpretar interfaces). Rechaza colisiones entre grupos e identifica los números de grupo. El navegador no implementa otro generador ni acepta prefijos libres.

Una nomenclatura inexistente, inactiva o con formato no habilitado impide guardar una configuración nueva. Una referencia anterior que queda inactiva se mantiene consultable, con advertencia; puede conservarse al editar metadatos o desactivar la plantilla. Reactivar una plantilla exige regularizar sus referencias. Aplicarla a un equipo siempre exige plantilla activa y todas sus nomenclaturas/formatos habilitados. No se activan ni sustituyen nomenclaturas automáticamente.

## API

Base `/api/distribution-device-templates`:

| Método y ruta | Contrato y autorización |
|---|---|
| GET base | Lista paginada (`limit` 1–200, `offset`, `include_inactive`), permisos `.view` o `.lookup` |
| GET `/{id}` y `/{id}/preview` | Definición con grupos, nombres, advertencias, `total_ports`, `usable` y `preview_token`; `.view` o `.lookup` |
| POST `/preview` | Comprobación de borrador; `.create` o `.edit`. `template_id` opcional identifica referencias históricas durante una edición |
| POST base | Creación completa con grupos y huella de vista previa; `.create` |
| PATCH `/{id}` | Sustitución validada de la definición completa, incluidos estado y grupos; `.edit` |

Campos del cuerpo: `name`, `manufacturer?`, `description?`, `active` y `groups` (cada grupo con `nomenclature_id`, `numbering_format`, `positions`, `start`, `end`). Para guardar se envía `preview_token` de la comprobación vigente. Los campos adicionales son rechazados. No se ofrece eliminación física ni endpoints para editar nomenclaturas dentro de las plantillas.

El POST existente `/api/distribution-devices` admite `template_id` y `template_token` opcionales; sin ellos mantiene la creación manual. Con plantilla requiere su comprobación vigente. Respuesta sin cambios: equipo normal con sus contadores. No se crea una ruta paralela de equipos.

## Permisos

Se registran `catalogs.distribution_device_templates.{view,lookup,create,edit}`. Admin y Superadmin reciben administración mediante la política existente de catálogos. Operador/Auditor tienen lectura contextual (`lookup`), sin acciones administrativas. Roles personalizados conservan el modelo granular habitual.

Los permisos de equipos implican lectura contextual de plantillas; los de administración de plantillas implican lectura de nomenclaturas. **No** implican crear o editar nomenclaturas. Aplicar una plantilla exige `distribution_devices.create`, incluso para un rol personalizado sin `distribution_ports.create`: solo genera los puertos de ese equipo nuevo mediante una definición administrada. No concede creación de puertos sobre equipos existentes.

## Atomicidad y concurrencia

Todas las mutaciones utilizan `distribution_write`: mismo advisory lock transaccional de topología, límite de espera de 3 s, rollback y errores 409/503 existentes. Aplicar una plantilla relee su definición y nomenclaturas bajo bloqueo y comprueba la huella antes de generar los puertos.

`insert_ports()` reutiliza inserción y auditoría en la creación individual, masiva y desde plantilla, sin commits propios. El equipo, todos sus puertos y sus bitácoras se confirman juntos; cualquier fallo revierte todo. No hay transacción entre crear un catálogo y guardar luego un circuito.

La huella detecta cambios en grupos, prefijos, formatos y estado de nomenclaturas desde la comprobación. Si cambia la definición, la API devuelve 409 y pide comprobar nuevamente. La unicidad de equipo por nodo y de puertos por equipo impide duplicados concurrentes. Los formularios también bloquean doble envío; no se introduce una infraestructura de idempotencia adicional.

## Frontend

- Administración → Catálogos → **Plantillas de equipos**, visible mediante `.view`.
- `DeviceTemplateAdmin`: lista, datos generales, edición/activación/desactivación, grupos agregables/removibles y vista previa del backend agrupada por interfaces. No permite crear nomenclaturas.
- `DeviceTemplateChoice`: selector compartido de creación manual o desde plantilla, con resumen de solo lectura. Utilizado por `DeviceFormModal` y `QuickDistributionCreate` desde Circuitos. No altera el flujo de edición de equipos ni los formularios de puertos existentes.
- Las consultas usan `AbortController` y descartan respuestas obsoletas. Guardado deshabilitado hasta que exista una comprobación válida. Los datos del equipo y del circuito padre se conservan.
- Una creación rápida confirmada persiste aunque después se cancele el circuito, igual que los demás catálogos rápidos.

## Verificación y despliegue

Pruebas: `tests/test_device_templates.py`, `tests/test_device_template_migration.py`, `frontend/src/components/DeviceTemplates.test.tsx`; regresiones de distribución, nomenclaturas, seguridad, FMS y navegación de catálogos. Resultados exactos en `AGENT_HANDOFF.md`.

La migración se prueba con upgrade/downgrade en una base independiente del clúster PostgreSQL efímero de pytest. **No se aplica a DEV persistente, TEST o PROD en esta tarea.** Su aplicación requiere autorización y respaldo conforme al procedimiento del proyecto. No se cambian versión, PDF, SMTP ni frontend/dist.
