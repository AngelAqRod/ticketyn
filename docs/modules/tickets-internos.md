# Ficha Técnica: Tickets Internos

## Responsabilidad del módulo
- **Qué gestiona:** Registro, diagnóstico, seguimiento y resolución de incidencias técnicas en infraestructura de red troncal, caídas de nodos, enlaces de fibra y fallas atribuibles a proveedores upstream.
- **Funcionalidades existentes:**
  - Registro de incidencias con numeración secuencial técnica independiente (`InternalTicketNumberConfig`).
  - Clasificación obligatoria por Tipo de Incidencia Interna y Sector.
  - Asociación opcional a Nodo y Proveedor mayorista responsable.
  - Gestión de estados operativos: **Abierto** y **Cerrado**.
  - Intervenciones de bitácora técnica de seguimiento (`InternalTicketUpdate`).
  - Escalamientos internos a departamentos y responsables técnicos (`InternalEscalation`).
  - Agrupación y consulta de múltiples tickets de clientes vinculados (relación 1:N).
  - Exportación de listados filtrados a PDF y Excel (.xlsx) y generación de reporte PDF individual interno.
- **Qué no le corresponde:** No se vincula a clientes ni circuitos específicos, no dispone de portal ni campos visibles para clientes finales y no propaga cierres o reaperturas automáticas sobre los tickets de clientes agrupados.

## Reglas de negocio críticas
- **Desacoplamiento total de clientes y circuitos:** El modelo carece conceptualmente de relaciones con clientes y circuitos. Toda la información es confidencial y para uso exclusivo del personal de operaciones y NOC.
- **Atribución flexible de proveedores:**
  - El catálogo de proveedores clasifica la responsabilidad externa del enlace o servicio troncal.
  - La opción «Ninguno» representa explícitamente ausencia de proveedor atribuible.
  - La atribución a un proveedor (o su cambio) puede realizarse **incluso cuando el ticket interno se encuentra Cerrado**, sin necesidad de reabrirlo operativamente ni invalidar su fecha de cierre.
- **Campos mandatorios y opcionales:**
  - *Obligatorios:* Sector y Tipo de Incidencia Interna.
  - *Opcionales:* Nodo (para fallas que abarcan más de un punto de presencia) y Proveedor.
- **Independencia operativa de tickets de cliente vinculados:**
  - Un ticket interno puede tener asociados múltiples tickets de clientes (a través de la clave foránea `Ticket.internal_ticket_id`).
  - La relación es estrictamente contextual y de trazabilidad de afectación masiva.
  - Cerrar, reabrir o cancelar el ticket interno jamás altera el estado de los tickets de clientes vinculados.
- **Numeración concurrente independiente:**
  - Esquema secuencial aislado del módulo de clientes, protegido contra colisiones mediante bloqueo de fila `SELECT ... FOR UPDATE` en `internal_ticket_number_configs`.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`internal_tickets.py`, `internal_ticket_data.py`, `internal_ticket_exports.py`, `internal_ticket_reports.py`), modelo en `src/ticketyn/models/internal_ticket.py` (contiene `InternalTicket`, `InternalTicketUpdate`, `InternalEscalation`, `Provider`, `InternalIncidentType`), esquemas en `src/ticketyn/schemas/internal_ticket.py`.
- **Componentes frontend:** Vistas y editores en `frontend/src/pages/InternalTickets.tsx`, componentes en `frontend/src/components/` (`InternalTicketSelect.tsx`, `RelatedInternalTicket.tsx`).
- **Dependencias:** Sectores, Nodos, Departamentos, Responsables, Proveedores y Tickets de Clientes (vía relación foránea de vinculación).
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `GET/POST /api/internal-tickets`, `GET/PUT /api/internal-tickets/{id}`, `POST /api/internal-tickets/{id}/updates`, `POST /api/internal-tickets/{id}/escalations`, `GET /api/internal-tickets/{id}/pdf`, `GET /api/internal-tickets/export`.
- **Permisos requeridos:** `internal_tickets.view`, `internal_tickets.create`, `internal_tickets.edit`, `internal_tickets.close`, `internal_tickets.escalate`, `internal_tickets.followup`, `internal_tickets.export`.
- **Nota arquitectónica de permisos:** La acción de asociar un ticket de cliente con un ticket interno se autoriza en el backend mediante el permiso `tickets.link` sobre el ticket de cliente; no existe un permiso artificial `internal_tickets.link`.
- **Privacidad contextual:** Los usuarios que no tienen permiso general de lectura de tickets internos únicamente pueden visualizar el identificador mínimo en tickets vinculados si ya cuentan con permiso para consultar el ticket de cliente afectado.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_internal_tickets.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/InternalTickets.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Comprobar que la edición de proveedor no falle con tickets cerrados y no altere la fecha `closed_at`.
  - Asegurar que la desvinculación de un ticket de cliente desde la interfaz limpie la clave foránea sin afectar la persistencia del ticket interno.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en el modelo `InternalTicket`, adición de campos de infraestructura o modificaciones en la lógica de vinculación masiva con incidencias de clientes.
