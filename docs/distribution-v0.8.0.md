# Equipos y puertos de distribución — Bloque 1

Backend de desarrollo sobre v0.7.0. No publica v0.8.0 ni autoriza migraciones en
DEV, TEST o producción. Las pantallas y selectores pertenecen a los bloques 2 y 3.

## Datos e integridad

`nodes` → `distribution_devices` → `distribution_ports`. `circuits` incorpora
`distribution_device_id` y `distribution_port_id`, ambos opcionales. Un circuito
puede tener equipo sin puerto; un puerto exige equipo y un equipo exige nodo.
Las FK compuestas verifican nodo/equipo y equipo/puerto también fuera de la API.
No existe unicidad de circuito por puerto: varios circuitos pueden compartirlo.

Los nombres se comparan dentro de su padre ignorando mayúsculas, espacios externos
y secuencias de espacios, mediante el patrón PostgreSQL y colación `C.utf8` ya
utilizados para CPE. Los nombres inactivos siguen reservados. No se interpretan
alias físicos: `sfp+1`, `sfpplus1` y `sfp de 10 g 1` siguen siendo identidades distintas.

- Los equipos no cambian de nodo si tienen circuitos, incluidos inactivos, por
  cualquiera de las dos referencias. Los puertos sin asociaciones acompañan al equipo.
- Los puertos con circuitos no se trasladan, desactivan ni eliminan.
- Un equipo con puertos registrados no se elimina, aunque tengan cero circuitos.
- Desactivar un equipo conserva sus puertos y circuitos; impide nuevas asignaciones.
  Cambiar nombres conserva los identificadores y todas sus asociaciones.
- Editar otros datos conserva referencias inactivas existentes. Retirar el puerto
  o toda la asociación sigue permitido. Asignar una relación nueva exige padres
  activos y coherentes. El backend no elimina asociaciones para corregir errores.

## Transacciones y concurrencia

`api/distribution_data.py` centraliza validación, snapshots permitidos y errores
saneados. Sus escrituras usan `pg_advisory_xact_lock(7808001)` antes de bloquear
filas: serializa cambios breves de topología y creación/edición general de circuitos
entre procesos, evitando la carrera entre comprobar dependencias y trasladar o
desactivar. Los catálogos se leen con `FOR SHARE` y las mutaciones bloquean su fila.
Las FK y los índices únicos son la defensa independiente de la API.

Cada transacción limita esperas de bloqueo a tres segundos; contención, deadlock
o conflicto de integridad se traducen a 409. Un fallo de persistencia se sanea como
503. No se guardan cambios parciales ni se hacen llamadas SMTP. Lecturas, CPE y
procesamiento SMTP no adquieren este advisory lock. El despliegue de sesiones RAM
sigue requiriendo un solo worker HTTP.

El lock del módulo prioriza integridad sobre escrituras paralelas; si aumenta
significativamente su volumen, medir contención antes de cambiar esta estrategia.

## API

Prefijo `/api`. Se conserva la paginación por `limit` (1–200, 50 predeterminado)
y `offset`, con respuestas de lista y orden por nombre/código e identificador.
Los puertos usan orden natural de todos los segmentos numéricos antes de paginar,
mediante `port_name_order` en `src/ticketyn/api/distribution_data.py`. El texto se
compara sin distinguir mayúsculas; empates numéricos (por ejemplo SFP01/SFP1)
se resuelven por nombre original en colación C e ID. Los nombres se conservan
literalmente y no se exige nomenclatura a puertos históricos. React mantiene
el orden de la API; los rangos de vista previa ya siguen la secuencia numérica.

| Recurso | Contratos |
|---|---|
| `/distribution-devices` | GET con `node_id`, `search`, `active`, `include_inactive`; POST con `node_id`, `name`, `description?`. |
| `/distribution-ports` | GET con `distribution_device_id` y filtros de nombre/estado; POST generado con nomenclatura/formato/números y `preview_token` (ver nomenclaturas). |
| Ambos `/{id}` | GET; PATCH de nombre/descripción (puertos admiten clasificación explícita completa); DELETE sin dependencias. |
| Equipo `/{id}/move` | POST `{node_id}`. |
| Puerto `/{id}/move` | POST `{distribution_device_id}`. |
| Ambos `/{id}/status` | PATCH `{active: boolean}`. |
| `/distribution-devices/{id}/circuits` | GET con `port_id` o `without_port`, `limit`, `offset`; incluye circuitos activos/inactivos y equipo sin puerto. |

Los registros nuevos se crean activos. Nombres: 1–255 caracteres, sin quedar en
blanco; descripción opcional hasta 10 000, anulable. Campos extra se rechazan.
Estado y ubicación no se aceptan en el PATCH de edición ni como acceso indirecto
a facultades administrativas en el POST de creación.

Equipos devuelven `port_count` y `circuit_count`; puertos, `circuit_count`, incluyendo
circuitos inactivos. La unión externa conserva puertos con cero asociaciones.
Esos conteos **no certifican que el puerto esté físicamente libre**.

La proyección de servicios incluye código/ID/descripción/estado del circuito,
ID/código/nombre del cliente, ID/nombre del tipo de servicio y puerto. No incluye
configuración CPE, credenciales ni snapshots FMS; sus campos están explícitamente
limitados mediante SQL y `DistributionCircuitResponse`.

Los contratos actuales de circuitos admiten las nuevas referencias: omitir un
campo conserva su valor; `null` lo retira. Retirar equipo exige retirar también
el puerto en el mismo PATCH si existía. Cambiar nodo exige relaciones finales
compatibles. No se requiere equipo o puerto al crear circuitos.

401: falta sesión; 403: falta permiso; 404: recurso ausente; 422: contrato o
relaciones incompatibles; 409: dependencia, duplicado o modificación concurrente.

## Permisos

Dos familias: `distribution_devices` y `distribution_ports`, cada una con
`view`, `lookup`, `create`, `edit`, `move`, `set_active`, `delete` (14 nuevos).

- Superadministrador y Administrador: las siete acciones en ambos recursos.
- Operador: `view`, `lookup`, `create`, `edit`.
- Auditor: `view`, `lookup`.
- Personalizados: permisos explícitos; no reciben nuevas facultades por tener
  permisos antiguos de circuitos. Nuevas copias usan la definición vigente del rol.
- Servicios asociados: `distribution_devices.view` **y** `circuits.view`.
- `lookup` permite alimentar selectores; no concede mutaciones. Los permisos del
  módulo permiten la lectura contextual del catálogo de nodos.

La autorización se registra en el inventario cerrado `security/routes.py` y se
comprueba en backend. No se agregan roles, identidades ni otra autenticación.

## Bitácora operativa

`distribution_audit` registra actor autenticado (`responsibles.id`), fecha
PostgreSQL, tipo/ID del recurso, acción y valores antes/después. Los recursos son
DEVICE, PORT y CIRCUIT; las acciones CREATE, EDIT, MOVE, SET_ACTIVE, DELETE y ASSIGN.
ASSIGN cubre cambios de distribución del circuito; no audita todas sus operaciones.
No se generan registros por consultas, no-op o acciones rechazadas.

Los snapshots de equipo/puerto contienen únicamente nombre, descripción, padre
y estado. Los de circuito, solo nodo/equipo/puerto. No se copian objetos completos,
CPE ni secretos. La bitácora y los datos se confirman juntos; un error revierte
ambos. El identificador del recurso no es una FK, para preservar la evidencia de
eliminaciones autorizadas. El actor sí conserva su FK a la identidad existente.

No se utiliza `SecurityAudit`, ni se amplían su limpieza o su pantalla. No hay
pantalla, exportación o endpoint de borrado de la nueva bitácora en este bloque.

## Migración y datos anteriores

`0033_distribution_devices_ports` depende de `0032_responsible_selectable`. Agrega
tres tablas, dos columnas opcionales, restricciones/índices y las definiciones de
permisos. No cambia nodos, identidades, credenciales, versiones ni datos FMS.
No deduce distribución de notas o descripciones ni rellena datos históricos.

El downgrade elimina las entidades, asociaciones y bitácora nuevas: no es una
recuperación operativa sin pérdida. Como 0031, conserva definiciones y asignaciones
de permisos de roles personalizados; el código anterior rechaza los códigos
desconocidos. Upgrade/downgrade solo deben validarse en PostgreSQL descartable.

La preparación del Bloque 1 no aplicó la migración a DEV. Al autorizar el Bloque 2,
el usuario confirmó DEV en 0033. El Bloque 2 no modifica ni consulta esa base.

## Bloque 2 — Formularios de circuitos

`CircuitDistributionFields` reutiliza `SearchableSelect`, `FormField` y
`RequestState` en alta/edición de `CatalogAdmin`, el `CircuitEditModal` de la ficha,
y las altas contextuales de `QuickCatalogCreate`. No duplica formularios completos
ni cambia la navegación. `CircuitDetail` muestra nodo/equipo/puerto como distribución
actual, con «No asignado» donde corresponde; no se atribuye a activaciones anteriores.

- GET de equipos requiere node_id; GET de puertos requiere distribution_device_id.
  El cliente recorre páginas de 200. Solo se ofrecen activos del padre actual;
  las asignaciones originales inactivas se incluyen para lectura y conservación.
- Sin nodo se deshabilita equipo; sin equipo se deshabilita puerto. Cambiar nodo
  limpia equipo/puerto; cambiar equipo limpia puerto. Ninguna consulta elige por sí
  sola una opción. Datos ajenos al cambio permanecen intactos.
- PATCH omite las asociaciones sin cambios. Retirar equipo envía null para las
  referencias retiradas; retirar puerto conserva equipo. Altas sin distribución
  conservan su payload anterior, omitiendo ambos campos opcionales.
- `QuickDistributionCreate` abre un diálogo independiente mediante portal, sin
  anidar formularios HTML. Hereda nodo/equipo y no ofrece traslado. Comprueba
  duplicados con inactivos antes de cada POST; la restricción del backend resuelve
  carreras y el frontend muestra 409. No fusiona aliases ni reutiliza un duplicado
  automáticamente. Nombre obligatorio de hasta 255 caracteres; descripción opcional
  de hasta 10000. No se hacen reintentos automáticos tras resultados de red inciertos.
- Tras crear, se agrega y selecciona el ID devuelto. Guardar el catálogo no envía el
  circuito ni elimina datos escritos. Cancelar el circuito conserva equipos/puertos.
- AbortController y catálogos identificados por padre descartan respuestas tardías.
  Cambiar contexto o perder permisos cierra el diálogo e invalida sus callbacks.
  Una cancelación de red no garantiza revertir un POST ya recibido en el servidor;
  el registro independiente puede existir, pero no se asigna al nuevo contexto.
- Los botones + requieren permiso create y lectura lookup/view del recurso.
  Los roles personalizados antiguos pueden requerir concesión explícita; no se
  les conceden permisos implícitos. Auditor consulta la ficha sin acciones de edición.

Pruebas del frontend: `CircuitDistributionFields.test.tsx` (selectores, asincronía,
permisos, modal, errores, duplicados) y `CircuitDistributionIntegration.test.tsx`
(payloads, listado, ficha, edición, creación contextual y paginación).

## Continuación

Bloque 3: listado/ficha de equipos y catálogo de puertos dentro de Circuitos,
servicios paginados y enlaces autorizados. No cambiar el diseño Electric Blue ni
presentar cero asociaciones como disponibilidad física. El Bloque 3 no está implementado.

## Ampliación: nomenclaturas y creación avanzada

La creación individual y masiva utiliza el catálogo global y la vista previa del servidor. El antiguo POST con nombre libre se rechaza; las consultas y referencias históricas se conservan. Detalles de API, permisos, migraciones 0037/0038, lotes y política de concurrencia en [Nomenclaturas de puertos](port-nomenclatures-v0.8.0.md).
