# Ficha Técnica: Clientes y Circuitos

## Responsabilidad del módulo
- **Qué gestiona:** El catálogo maestro de clientes corporativos y residenciales, el inventario técnico de circuitos de telecomunicaciones y los parámetros de configuración del equipamiento de usuario final (CPE).
- **Funcionalidades existentes:**
  - Registro, edición y consulta de clientes (`Customer`) con datos administrativos de contacto.
  - Gestión de circuitos (`Circuit`) asociados a clientes con selector de cliente con búsqueda integrada (búsqueda parcial por código y nombre con normalización de acentos y mayúsculas/minúsculas), identificado con un código único no nulo, sector, nodo, tipo de servicio y capacidad inicial contratada.
  - Ficha técnica integral del circuito con consolidación de activación inicial, bitácora de intervenciones, historial de capacidad, bajas/reactivaciones y parámetros CPE.
  - Actualización de sector con sincronización automática de tickets recientes (regla de 168 horas).
  - Eliminación condicionada a la ausencia total de dependencias operativas o históricas.
  - Consulta y edición de configuración técnica CPE en texto plano.
- **Qué no le corresponde:** No es un sistema de facturación o gestión comercial (CRM), no interactúa directamente con equipos físicos mediante protocolos de red (SSH, SNMP, TR-069) ni almacena contraseñas o llaves criptográficas de routers en una bóveda cifrada.

## Reglas de negocio críticas
- **Integridad referencial y protección del historial:**
  - Está estrictamente prohibido eliminar un cliente o circuito que posea registros vinculados en tickets, activaciones, cambios de capacidad, bajas o reactivaciones.
  - No existe borrado en cascada hacia entidades de trazabilidad operativa; la base de datos y la API rechazan la operación si existen dependencias.
- **Cálculo dinámico de la capacidad actual:**
  - La capacidad actual de un circuito no reemplaza ni sobrescribe la `initial_bandwidth` registrada durante la activación.
  - Se deriva dinámicamente de la última operación de cambio de capacidad registrada en el módulo FMS. Si no existen cambios de capacidad posteriores, la capacidad actual es igual a la inicial.
- **Regla de sincronización de sector y HUB/nodo (168 horas):**
  - Al actualizar el sector o el HUB (nodo) de un circuito, se ejecuta una sincronización automática y transaccional sobre todos sus tickets asociados creados en las últimas **168 horas** (7 días), incluyendo los cerrados, cuyo valor asignado sea distinto al nuevo valor del circuito.
  - La sincronización actualiza de forma atómica el identificador (`sector_id` o `node_id`) y registra una entrada interna en `ticket_updates` describiendo el cambio automático.
  - Se preservan estrictamente la fecha de actualización (`updated_at`), responsables, fechas operativas, estados y resoluciones de los tickets modificados.
  - Los tickets con más de 168 horas de antigüedad preservan intacto su HUB/sector histórico original para garantizar la inmutabilidad de reportes pasados.
  - En la interfaz de usuario (`TicketForm` / `CircuitAssignmentField`), los tickets con antigüedad superior a 168 horas muestran su HUB persistido original en lugar del HUB actual del circuito, evitando discrepancias visuales o falsas apariencias de reversión al guardar.
  - Los tickets internos no participan en esta sincronización.
- **Configuración CPE como texto plano técnico:**
  - El campo de configuración CPE es texto literal consultable y editable por el NOC.
  - No ejecuta scripts en la red, no valida sintaxis propietaria de fabricantes ni almacena versiones de firmware por sí solo.
- **Independencia Sector / Nodo:**
  - Los sectores representan zonas lógicas de cobertura y los nodos puntos físicos de presencia.
  - No existe relación jerárquica estricta que subordine un nodo a un único sector; ambos se eligen de forma independiente en el circuito.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`customers.py`, `circuits.py`, `circuit_sector.py`, `circuit_ticket_sectors.py`, `circuit_ticket_nodes.py`, `cpe_models.py`), modelos en `src/ticketyn/models/` (`customer.py`, `circuit.py`, `cpe_model.py`), esquemas en `src/ticketyn/schemas/` (`customer.py`, `circuit.py`, `cpe_model.py`).
- **Componentes frontend:** Vistas en `frontend/src/pages/CircuitDetail.tsx`, componentes en `frontend/src/components/` (`CircuitActions.tsx`, `CpeConfiguration.tsx`).
- **Dependencias:** Sectores, Nodos, Tipos de Servicio, Modelos CPE, Operaciones FMS y Tickets de Clientes.
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `GET/POST /api/customers`, `GET/PATCH/DELETE /api/customers/{id}`, `GET/POST /api/circuits`, `GET/PATCH/DELETE /api/circuits/{id}`, `GET/PATCH /api/circuits/{id}/cpe-configuration`. El sector se modifica mediante el PATCH del circuito, no mediante un endpoint separado.
- **Permisos requeridos:** `customers.view`, `customers.create`, `customers.edit`, `customers.delete`, `customers.lookup`, `circuits.view`, `circuits.create`, `circuits.edit`, `circuits.delete`, `circuits.lookup`, `cpe.view`, `cpe.edit`.
- **Jerarquía y creación rápida:**
  - El permiso `cpe.view` exige obligatoriamente contar con `circuits.view`.
  - La creación rápida desde selectores contextuales se valida mediante los permisos `context.customers.create` y `context.circuits.create`.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_circuit_ticket_sector_sync.py tests/test_circuit_ticket_node_sync.py tests/test_catalog_api.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/components/CircuitSectorField.test.tsx frontend/src/components/CpeConfiguration.test.tsx frontend/src/pages/TicketDetail.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Asegurar que la actualización de sector y HUB/nodo no modifique tickets creados fuera de la ventana de 168 horas.
  - Verificar que el formulario de edición de ticket muestre el HUB persistido histórico para tickets con más de 7 días.
  - Verificar que el recálculo de capacidad actual consulte correctamente la última operación de FMS sin depender del modelo local de circuito.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en el modelo `Circuit`, variaciones en la ventana temporal de sincronización de sectores o ampliación de capacidades en la gestión de equipamiento CPE.

## Distribución — v0.8.0, bloques 1, 2 y 3

- Jerarquía actual opcional: Nodo → equipo → puerto → circuitos. Un circuito puede
  tener equipo sin puerto y varios circuitos compartir el mismo puerto. No se
  deducen asociaciones históricas ni se modifican snapshots o solicitudes FMS.
- Modelos en `src/ticketyn/models/distribution.py`: equipos, puertos y bitácora
  operativa. Circuitos incorpora referencias opcionales con FK compuestas que
  verifican nodo/equipo y equipo/puerto. Nombres únicos por padre con normalización
  conservadora; no fusionar alias de interfaces.
- API en `src/ticketyn/api/distribution.py`, coordinación en
  `src/ticketyn/api/distribution_data.py`. Escrituras y bitácora en la misma
  transacción, advisory lock 7808001 y locks de filas. No hay contacto con equipos
  físicos ni llamadas SMTP.
- Equipos asociados no se trasladan ni se eliminan; tampoco se eliminan si conservan
  puertos. Los puertos con circuitos no se trasladan, desactivan ni eliminan. Los
  circuitos inactivos también cuentan. Desactivar un equipo conserva referencias.
- Los PATCH de circuito conservan campos omitidos y retiran referencias con null
  explícito; rechazan relaciones incompatibles sin corregirlas silenciosamente.
  Referencias inactivas existentes se conservan al editar otros datos.
- Rutas base: `/api/distribution-devices` y `/api/distribution-ports`, con consulta,
  creación, edición de nombre/descripción, eliminación protegida y acciones
  separadas de traslado y estado. Servicios paginados en
  `/api/distribution-devices/{id}/circuits`, sin CPE ni credenciales. Conteo cero
  significa sin circuitos asociados, no puerto físicamente libre.
- Las respuestas de equipo (listado y detalle) incluyen `unassigned_port_count`:
  puertos registrados sin ningún circuito asociado, incluidos puertos inactivos.
  Los circuitos inactivos mantienen la asociación y los circuitos sin puerto no
  ocupan un puerto. Agregación SQL compartida sin consultas por equipo; cero para
  equipos sin puertos. El frontend muestra «—» si el dato no está disponible,
  nunca lo sustituye por cero ni lo calcula con una página de servicios.
- El sidebar reutiliza `moduleIdentity.theme` mediante `data-theme` y
  `frontend/src/styles/navigation.css`: solo el elemento activo toma el color
  temático; sin tema específico se conserva Electric Blue. Distribución exige
  `distribution_devices.view` para mostrar su entrada independiente.
- Permisos por recurso: view/lookup/create/edit/move/set_active/delete.
  Superadmin/Admin: todos; Operador: consultar/crear/editar; Auditor: lectura.
  Personalizados antiguos no adquieren facultades nuevas automáticamente.
- Migración `alembic/versions/0033_distribution_devices_ports.py`, posterior a
  0032; aplicada a DEV según confirmación del usuario al autorizar el Bloque 2.
  No se aplican migraciones desde este bloque. Probar upgrade/downgrade solo en PostgreSQL efímero.
- `CircuitDistributionFields` comparte selección Nodo → equipo → puerto entre
  `CatalogAdmin` (alta/listado y `CircuitEditModal`) y `QuickCatalogCreate`.
  Solo ofrece altas activas y conserva referencias inactivas originales; cambiar
  nodo limpia equipo/puerto y cambiar equipo limpia puerto. PATCH omite asociaciones
  sin cambios y usa null explícito al retirarlas. La ficha muestra distribución actual,
  sin atribuirla a snapshots FMS.
- `QuickDistributionCreate` utiliza un diálogo con padre heredado de solo lectura.
  Consulta duplicados incluidos inactivos antes de cada intento, usa los endpoints
  existentes y selecciona el registro creado sin guardar el circuito. Cancelar el
  circuito no elimina el catálogo. Solicitudes abortables y contexto de padre
  impiden aplicar respuestas obsoletas. Los permisos lookup/view y create se
  consultan en la sesión; el backend sigue siendo la autoridad final.
- Pantallas y navegación del Bloque 3:
  - Listado operativo de equipos (`DistributionDevices.tsx`, ruta /distribution-devices) con búsqueda, filtro por nodo y estado, contadores, paginación y modales contextuales.
  - Ficha de equipo (`DistributionDeviceDetail.tsx`, ruta /distribution-devices/:id) con 4 métricas operativas (total puertos, con circuitos, sin circuitos, total circuitos), tabla de puertos con conteo/etiqueta «Sin circuitos asociados», agrupación/filtro de circuitos asociados con soporte para circuitos sin puerto, y navegación cruzada hacia circuitos.
  - Navegación contextual mediante pestañas segmentadas Electric Blue (`CircuitsNavigation.tsx`) en Circuitos y Equipos de distribución.
  - Contratos y restricciones completos: [Equipos y puertos de distribución](../distribution-v0.8.0.md).
- Pruebas: `tests/test_distribution.py`, `tests/test_distribution_migration.py`,
  `frontend/src/components/CircuitDistributionFields.test.tsx`,
  `frontend/src/components/CircuitDistributionIntegration.test.tsx`,
  `frontend/src/pages/DistributionDevices.test.tsx` y
  `frontend/src/pages/DistributionDeviceDetail.test.tsx`.

## Nomenclaturas y generación de puertos

- Catálogo global `port_nomenclatures`, sin fabricante obligatorio, con prefijo literal, formatos múltiples y estado. Referencia nullable en puertos históricos.
- Generador y validación únicos en `src/ticketyn/api/port_nomenclatures.py`; contratos en `src/ticketyn/schemas/port_nomenclature.py`.
- Vista previa de servidor y confirmación protegida por huella y transacción de distribución. Hasta 256 nombres por solicitud; rango completo o solo faltantes, sin escrituras parciales.
- `PortCreateDialog` sustituye el alta libre y se comparte entre la ficha y todos los circuitos. El POST individual exige nomenclatura, formato, números y preview_token; los datos históricos no requieren clasificación retroactiva.
- Migraciones: 0037 (ya presente, posterior a 0036) y 0038 (integridad de clasificación, posterior a 0037), pendientes de aplicación persistente autorizada.
- Contratos, concurrencia, permisos y transición: [Nomenclaturas de puertos](../port-nomenclatures-v0.8.0.md). Pruebas: `tests/test_port_nomenclatures.py`, `tests/test_port_nomenclature_migration.py`, `frontend/src/components/PortCreateDialog.test.tsx`.

## Orden natural de puertos

- `port_name_order` en `src/ticketyn/api/distribution_data.py` centraliza el orden SQL de segmentos de texto y números. Los números se comparan por su valor entero sin conversiones limitadas a bigint; no se modifica el nombre almacenado.
- `/api/distribution-ports` aplica ese orden antes de `limit`/`offset`, con desempate por nombre original en colación C e ID. Aplica a puertos históricos, clasificados e inactivos.
- La tabla de la ficha, los selectores normales/de edición/alta rápida y sus búsquedas respetan el orden recibido. El selector obtiene también inactivos para mantener la posición del histórico seleccionado, pero oculta los demás inactivos y conserva la referencia actual deshabilitada.
- Vista previa y resultados de lotes ya siguen la secuencia numérica del rango; no se cambia el generador ni se añade otra ordenación en React.
- Pruebas específicas: `tests/test_port_order.py`, tabla con 24 puertos en `frontend/src/pages/DistributionDeviceDetail.test.tsx`, selectores en `frontend/src/components/CircuitDistributionFields.test.tsx` y vista previa en `frontend/src/components/PortCreateDialog.test.tsx`.


## Plantillas de equipos de distribución

- Administración → Catálogos → Plantillas de equipos, `DeviceTemplateAdmin.tsx` y `/api/distribution-device-templates`; nombre/modelo, fabricante informativo opcional, descripción, estado y grupos que referencian exclusivamente nomenclaturas existentes.
- Máximo 16 grupos y 256 puertos por plantilla; formatos y generación compartidos con los puertos existentes. Vista previa en backend, colisiones entre grupos rechazadas y referencias inactivas preservadas pero bloqueadas para nuevos equipos.
- `DeviceTemplateChoice.tsx` integra creación manual o desde plantilla en el modal de equipos y el alta rápida desde Circuitos. POST `/api/distribution-devices` admite `template_id`/`template_token`: equipo, puertos y bitácora se confirman en una sola transacción. No sincroniza equipos anteriores ni altera FMS.
- Permisos `catalogs.distribution_device_templates.{view,lookup,create,edit}`; Admin/Superadmin administran, los creadores de equipos pueden aplicar definiciones mediante lectura contextual sin administrar catálogos.
- Migración aditiva `0039_device_templates` → `0038_port_classification`; ver [contratos, límites y pruebas](../distribution-device-templates.md). Backend en `api/device_templates.py`, modelos en `models/distribution.py`, esquemas en `schemas/device_template.py`.
