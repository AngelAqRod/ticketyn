# Ficha Técnica: Tickets de Clientes

## Responsabilidad del módulo
- **Qué gestiona:** Registro, diagnóstico, seguimiento operativo y resolución de incidencias técnicas reportadas por o asociadas a clientes y sus circuitos contratados.
- **Funcionalidades existentes:**
  - Creación de tickets con código secuencial automático estructurado (prefijo, correlativo y longitud configurable).
  - Consulta y edición de detalles operativos: cliente, circuito, clasificación por tipo de incidencia, sector, nodo y responsable asignado.
  - Gestión de ciclo de vida con estados operativos finitos: **Abierto** y **Cerrado**.
  - Intervenciones de bitácora (`TicketUpdate`) clasificando visibilidad interna o para cliente.
  - Escalamientos (`TicketEscalation`) solicitando apoyo a departamentos y responsables específicos con registro de motivo.
  - Vinculación opcional con un ticket interno de infraestructura (relación 1:1 desde la perspectiva del ticket de cliente).
  - Exportación de listados filtrados a PDF y Excel (.xlsx) y generación de reportes PDF individuales (versión interna y versión para cliente).
- **Qué no le corresponde:** No gestiona incidencias troncales sin cliente (corresponde a Tickets Internos), no envía correos salientes directos por sí mismo (delegado al subsistema de notificaciones), no calcula penalizaciones de SLA con temporizadores automáticos ni reasigna automáticamente el ticket al registrar escalamientos.

## Reglas de negocio críticas
- **Zona horaria institucional estricta:** Todos los sellos temporales, fechas de apertura, cierre e intervenciones se normalizan con `America/Guatemala`. La interfaz de usuario no debe reinterpretarlas según la zona horaria del navegador cliente.
- **Aislamiento estricto de visibilidad documental:**
  - Las entradas de seguimiento marcadas como internas (`is_customer_visible=false`) jamás deben aparecer en el PDF emitido para el cliente.
  - La relación con tickets internos vinculados solo se incluye en el reporte de uso interno.
- **Naturaleza de los escalamientos:**
  - Los escalamientos son registros independientes de apoyo colaborativo (`TicketEscalation`).
  - No constituyen un nuevo estado del ticket ni alteran su condición de Abierto o Cerrado.
  - No obligan a una jerarquía rígida (N1/N2/N3) ni modifican el responsable principal asignado al ticket.
- **Regla de sincronización de sector (168 horas):**
  - Al corregir el sector de un circuito, se sincronizan de forma transaccional los tickets de ese circuito creados en las últimas **168 horas** (7 días), incluyendo los que ya estén cerrados, siempre que su sector difiera del nuevo sector del circuito.
  - Cada sincronización genera automáticamente una entrada interna de bitácora de auditoría.
  - Los tickets con más de 168 horas de antigüedad preservan intacto su sector histórico para no desvirtuar estadísticas operativas pasadas.
- **Vínculos con Tickets Internos:**
  - Un ticket de cliente puede vincularse, reasignarse o desvincularse de un único ticket interno.
  - No se exige coincidencia geográfica previa (sector o nodo) entre ambos.
  - Los estados operativos de ambos tickets son completamente independientes: cerrar uno no afecta al otro.
- **Numeración concurrente sin huecos:**
  - La generación de nuevos identificadores se ejecuta bajo bloqueo exclusivo de fila en PostgreSQL (`SELECT ... FOR UPDATE` sobre `ticket_number_configs`).
  - La vista previa de numeración en formularios es una proyección inocua que no reserva ni avanza la secuencia real.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`tickets.py`, `ticket_data.py`, `ticket_updates.py`, `escalations.py`, `ticket_exports.py`), modelos en `src/ticketyn/models/` (`ticket.py`, `ticket_update.py`, `escalation.py`), esquemas en `src/ticketyn/schemas/ticket.py`.
- **Componentes frontend:** Vistas en `frontend/src/pages/` (`Tickets.tsx`, `TicketDetail.tsx`, `NewTicket.tsx`), componentes en `frontend/src/components/` (`TicketForm.tsx`, `TicketInterventionModal.tsx`, `TicketEscalations.tsx`).
- **Dependencias:** Clientes, Circuitos, Sectores, Nodos, Responsables (con filtro `operational_selectable=true`), Tipos de Incidencia y Tickets Internos.
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `GET/POST /api/tickets`, `GET/PUT /api/tickets/{id}`, `POST /api/tickets/{id}/updates`, `POST /api/tickets/{id}/escalations`, `GET /api/tickets/{id}/pdf`, `GET /api/tickets/export`.
- **Permisos requeridos:** `tickets.view`, `tickets.create`, `tickets.edit`, `tickets.close`, `tickets.escalate`, `tickets.followup`, `tickets.export`, `tickets.link`.
- **Integridad:** Las consultas validan pertenencia del circuito al cliente indicado; los selectores operativos descartan responsables inactivos o no seleccionables.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_ticket_updates.py tests/test_escalations.py tests/test_ticket_exports.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/Tickets.test.tsx frontend/src/pages/TicketDetail.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Probar siempre que un escalamiento no cierre el ticket ni borre notas de seguimiento existentes.
  - Comprobar que los filtros de exportación (cliente, nodo, sector, estado) exporten todos los registros coincidentes y no solo la página actual.
  - Verificar que la sincronización de 168h no modifique tickets más antiguos de esa ventana.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en el modelo `Ticket`, en las relaciones con `Circuit`, en las reglas de escalamiento o en los motores de generación de PDF.
