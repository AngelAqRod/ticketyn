# Changelog

## v0.4.2 — En desarrollo

- Catálogo administrable Modelos de CPE y asignación opcional en circuitos.
- Configuración CPE literal con lectura/edición en una tercera pestaña; excluida de listados y exportaciones.
- Condiciones históricas de servicio/capacidad inicial/CPE de activación en nuevas activaciones y su PDF individual.
- Indicador de versión desde el backend, independiente de conectividad.
- Migraciones aditivas 0019 y 0020; sin inferir datos históricos antiguos ni alterar numeraciones/estados.


## 0.4.1 — Corrección de Nodo histórico de tickets

- Recupera Nodos faltantes desde circuitos con Nodo válido mediante `0018_recover_ticket_nodes`, bajo la confirmación de que esos Nodos no cambiaron.
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

