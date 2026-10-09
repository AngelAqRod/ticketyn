# Changelog

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
