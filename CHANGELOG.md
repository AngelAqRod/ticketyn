# Changelog

## Sin publicar — Dashboard operativo y listado de tickets

- **Identidad:** Control de cambios pasa de ámbar a cian (compartido con el Dashboard). Se conservan en ámbar «Tiempo excedido», «Hoy» y el aviso de sesión; los estados de cambios no varían.
- **Estados:** Abierto en ámbar y Cerrado en gris pizarra en todos los listados; responsable en texto normal y «Sin asignar» gris cursiva.
- **Totales y paginación:** `GET /api/tickets` y `GET /api/internal-tickets` devuelven `X-Total-Count` (total filtrado, antes de LIMIT/OFFSET; el cuerpo no cambia). Textos «Mostrando 1–50 de 183» y «Página 1 de 4 · Registros 1–50 de 183».
- **Zona horaria:** `formatDate` y `formatTableDate` usan `America/Guatemala` en lugar de la zona del navegador.
- **Dashboard:** secciones «Abiertos por antigüedad» (cuatro tramos excluyentes + «Sin responsable» transversal), «Abiertos más antiguos» (cinco, ordenados en backend) y «Abiertos por sector». Nuevo `GET /api/tickets/open-overview` (permiso `tickets.view`, una consulta agregada + una por sector, un único `now`). Las tres tarjetas superiores no cambian.
- **Filtros de `GET /api/tickets`:** `age_bucket` (`lt_1h`, `1_to_4h`, `4_to_24h`, `gt_24h`), `unassigned` y `order` (`start_at_asc`/`start_at_desc`, desempate por id). La antigüedad no es un SLA.
- **Listado:** cápsulas Abiertos/Todos/Cerrados, Sin responsable y Más de 24 h (reflejadas en la URL), filtros activos removibles, filtros menos frecuentes plegables, encabezado fijo, columna Descripción y selector de columnas (Nodo, Tipo y Fin ocultos por omisión; preferencia en `localStorage`).
- Sin migraciones Alembic ni cambios de autenticación, permisos o branding.

## v0.5.0 — En revisión

### Funcionalidades

- Tickets internos de infraestructura/NOC, sin cliente, circuito ni contenido para cliente.
- Seguimiento siempre interno, escalamientos, cierre y corrección de proveedor tras el cierre.
- Catálogos independientes de tipos de incidencia interna y proveedores.
- Numeración interna configurable e independiente; interfaz Capsule NOC.
- Vínculo opcional desde Tickets y consulta inversa paginada, sin propagar estados.
- Reportería y exportaciones de tickets internos.
- Sincronización de sectores entre circuitos y tickets recientes.
- Relaciones entre tickets internos y registros de Control de Cambios.

### Control de Cambios

- Nuevo módulo de Control de Cambios para registrar y consultar intervenciones.
- Catálogo administrable de Tipos de cambio.
- Vistas de listado y calendario, con filtros y navegación por períodos.
- Registro de cambios sin necesidad de crear un ticket interno.
- Gestión de fechas y horas de las intervenciones.
- Gráficas y estadísticas específicas de Control de Cambios.

### Datos y compatibilidad

- Migración aditiva `0021_internal_tickets` desde `0020_activation_cpe`; vínculos históricos NULL.
- Reutilización de servicios operativos, controles y componentes existentes.
- Se conserva el modelo de acceso externo sin usuarios ni autorización individual de backend.
- Pruebas con PostgreSQL temporal, migración y numeración concurrente; sin publicación automática.
- Migración aditiva `0022_change_control` para el módulo Control de Cambios.
- Migración `0023_change_types` para el catálogo de tipos de cambio.
- Migración `0024_default_change_types_upper` para normalizar los tipos de cambio predeterminados a mayúsculas.

## v0.4.4 — Rediseño integral de la interfaz

- Renovación visual general de Ticketyn, con una identidad gráfica consistente en los módulos de la aplicación.
- Rediseño del sidebar y encabezado, con nueva geometría, integración de curvas y paleta Electric Blue.
- Actualización de tipografía, colores, espaciados y estilos globales.
- Rediseño visual de formularios, modales, filtros, tablas, paginación y componentes compartidos.
- Renovación de dashboards, métricas, gráficas y presentación de reportes.
- Ajustes visuales en tickets, circuitos, operaciones FMS, catálogos y configuración.
- Incorporación y actualización de pruebas de componentes de la interfaz.


## v0.4.3 — Corrección de compilación del frontend

- Incorpora los archivos compilados del frontend correspondientes a las funcionalidades de CPE introducidas en v0.4.2.
- Corrige la distribución de recursos JavaScript y CSS desactualizados en los despliegues.
- Actualiza la versión de backend y frontend a 0.4.3.
- No incorpora nuevas migraciones ni cambios en el esquema de la base de datos.

## v0.4.2 — Publicado

- Catálogo administrable Modelos de CPE y asignación opcional en circuitos.
- Configuración CPE literal con lectura/edición en una tercera pestaña; excluida de listados y exportaciones.
- Condiciones históricas de servicio/capacidad inicial/CPE de activación en nuevas activaciones y su PDF individual.
- Indicador de versión desde el backend, independiente de conectividad.
- Migraciones aditivas 0019 y 0020; sin inferir datos históricos antiguos ni alterar numeraciones/estados.


## 0.4.1 — Corrección de Nodo histórico de tickets

g- Recupera Nodos faltantes desde circuitos con Nodo válido mediante `0018_recover_ticket_nodes`, bajo la confirmación de que esos Nodos no cambiaron.
- Preserva Nodos históricos existentes y registros FMS; aborta ante relaciones inconsistentes.
- Verifica creación transaccional, listado/detalle, filtros, reportería y exportaciones sobre el Nodo persistido.
- Sin sustituciones visuales ni sincronización permanente. El downgrade de la reparación conserva los datos.

## 0.4.0 — Publicado

### Gestión de servicios FMS

- Registro de activaciones con referencias independientes, numeración configurable y bitácora técnica opcional.
- Gestión de incrementos y decrementos de capacidad con precisión decimal y unidades Mbps/Gbps.
- Capacidad inicial opcional y capacidad actual calculada a partir del historial de operaciones.
- Registro independiente de bajas y reactivaciones, sin alterar el estado administrativo de los circuitos.
- Motivos de baja configurables desde Catálogos.
- Ficha operativa del circuito con información general, activación inicial e historiales paginados.
- Filtros operativos por cliente, circuito, período y tipo de operación.

### Circuitos y catálogos

- Tipos de servicio configurables.
- Sector y Nodo asociados a los circuitos, con validaciones para nuevas operaciones.
- Asignación de Sector y Nodo pendientes desde formularios operativos para circuitos históricos.
- Conservación de Sector y Nodo históricos en tickets y operaciones FMS.
- Creación contextual de circuitos desde formularios.
- Protección contra eliminación de circuitos con historial FMS.

### Reportería y exportaciones

- Reportes de activaciones, capacidad y bajas/reactivaciones.
- Indicadores operativos, gráficas de evolución y filtros por período y responsable.
- Estadísticas de clientes y distribución de motivos de baja.
- Exportaciones operativas y reporterías en formatos disponibles según el módulo, incluyendo PDF y XLSX.
- Documentos PDF con encabezados, indicadores, gráficas y detalle filtrado.
- Protección frente a exportaciones excesivamente grandes, sin truncar registros.

### Integridad y compatibilidad

- Operaciones FMS independientes de los tickets y de su numeración.
- Conservación del historial operativo y administrativo.
- Validaciones de integridad y referencias únicas.
- Compatibilidad con registros históricos.
- Pruebas automatizadas de operaciones, migraciones, reporterías y exportaciones.
- Sin modificaciones a los mecanismos existentes de respaldo, actualización y recuperación.

### Migraciones de base de datos

- `0014_circuit_operations`: operaciones FMS e historial de circuitos.
- `0015_circuit_service_types`: catálogo de tipos de servicio.
- `0016_circuit_sectors`: Sector centralizado en circuitos y conservación histórica.
- `0017_historical_nodes`: Nodo actual e histórico para circuitos, tickets y operaciones FMS.

Las migraciones son incrementales y están diseñadas para preservar los registros existentes.


## 0.3.1 — En desarrollo

- Corrección integral del período y poblaciones de los reportes de escalamientos.
- Fechas operativas reales y corrección auditada de fechas de escalamientos.
- Metadatos administrativos independientes; escalamientos en tickets cerrados.
- Destino por departamento, técnico opcional y asignación posterior auditada.
- Rankings de departamentos y categoría de responsables no asignados en PDF/XLSX.
- Períodos calendario en America/Guatemala y mayor coherencia estadística.
- Migración incremental `0013_escalation_operations`, sin eliminación de datos.

Detalles y limitaciones: [escalamientos v0.3.1](docs/escalations-v0.3.1.md).

## 0.3.0 — Publicación pendiente

### Funcionalidades nuevas
- Escalamientos como solicitudes de apoyo: nunca transfieren responsabilidad,
  departamento ni estado del ticket. Historial de solicitudes activas/finalizadas.
- Catálogo configurable de motivos y puestos por departamento; puesto opcional
  de responsables y snapshots históricos del destinatario.
- Intervenciones opcionalmente vinculadas a escalamientos del mismo ticket.
- Estadísticas de eventos, tickets únicos escalados, duración, destinatarios y evolución.

### Mejoras
- Historial de escalamientos en PDF interno; referencias desde el seguimiento,
  sin duplicar intervenciones. El PDF de cliente mantiene sus exclusiones privadas.
- Estadísticas de escalamientos en exportaciones PDF y XLSX.
- Un único período global de Reportería: Todos, Hoy, Ayer, 7D, 15D, 30D y Personalizado.
  Destinatario filtra únicamente estadísticas de escalamientos.
- Nombres de catálogos únicos sin diferencias de capitalización ni espacios externos;
  puestos únicos dentro de su departamento. Códigos conservan sus reglas anteriores.
- Pruebas de integridad, concurrencia, migración, reportes y compatibilidad histórica.

### Base de datos
- `0010_ticket_escalations`: motivos, escalamientos y relación opcional de intervenciones.
- `0011_department_positions`: puestos, relaciones del responsable, snapshots históricos
  y solicitante opcional. Conserva el texto legacy de nivel de atención.
- `0012_catalog_name_uniqueness`: índices únicos normalizados; exige `C.utf8`.
  Aborta ante conflictos antes de crear índices; no fusiona, elimina ni reasigna datos.

Consultar [actualización a v0.3.0](docs/upgrading-v0.3.0.md).

## 0.2.0
- Seguimiento interno/público, resolución documentada y PDF de ticket interno/cliente.
- Eliminación protegida de clientes y circuitos sin dependencias.
- Migraciones `0008_ticket_updates` y `0009_ticket_resolution`.

