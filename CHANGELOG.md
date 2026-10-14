# Changelog

## v0.4.1 — Corrección de Nodo histórico de tickets

- Recupera Nodos faltantes desde circuitos con Nodo válido mediante `0018_recover_ticket_nodes`, bajo la confirmación de que esos Nodos no cambiaron.
- Preserva Nodos históricos existentes y registros FMS; aborta ante relaciones inconsistentes.
- Verifica creación transaccional, listado/detalle, filtros, reportería y exportaciones sobre el Nodo persistido.
- Sin sustituciones visuales ni sincronización permanente. El downgrade de la reparación conserva los datos.


## 0.4.0 — Publicada

### Funcionalidades
- Activaciones con numeración independiente y bitácora técnica opcional.
- Incrementos/decrementos con valores decimales y unidades Mbps/Gbps.
- Bajas/reactivaciones independientes del estado administrativo y motivos configurables.
- Ficha operativa de circuitos, capacidad inicial opcional y capacidad actual derivada del historial.

### Integridad y compatibilidad
- Migración incremental `0014_circuit_operations`, preservando los registros existentes.
- Protección contra eliminación de circuitos con historial FMS y referencias concurrentes únicas.
- Formularios reutilizados en módulos/ficha; listados de 50 y pestañas independientes de 10 registros.
- Sin cambios en tickets, su numeración, backups ni mecanismos de actualización/recuperación.

### Revisión funcional de v0.4.0
- Filtrado cliente–circuito en activaciones y precarga editable de capacidad vigente.
- Acciones compartidas en la ficha del circuito y descripciones en detalles/listados FMS.
- Intervenciones reubicadas en la bitácora y creación contextual de circuitos junto al selector.
- Tipos de servicio configurables y motivos de baja accesibles desde Catálogos.
- Migración incremental `0015_circuit_service_types`, sin modificar `0014` ni asignar tipos a circuitos históricos.

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


### Sector centralizado en circuitos — preparación v0.4.0

- Sector obligatorio en circuitos nuevos y sus formularios principales/rápidos.
- Tickets y operaciones FMS heredan Sector del circuito; asignación pendiente
  transaccional desde el formulario cuando falta en un circuito histórico.
- Sector histórico independiente en tickets, activaciones, capacidad y bajas/reactivaciones.
- Migración `0016_circuit_sectors`: inferencia conservadora desde tickets,
  conservación de conflictos y operaciones antiguas sin Sector comprobable.

### Nodo actual e histórico — preparación v0.4.0

- Nodo obligatorio en circuitos nuevos y en tickets/operaciones FMS nuevos.
- Asignación pendiente transaccional desde formularios operativos, reutilizando Sector.
- Nodo histórico independiente del circuito en tickets y FMS; filtros y exportaciones coherentes.
- Migración `0017_historical_nodes`, sin inferir datos históricos que no existían en el esquema anterior.
