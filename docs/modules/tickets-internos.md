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
- **Escalamientos inteligentes y reconocimiento ACK en Tickets Internos:**
  - Aplica simétricamente el motor de recomendaciones por etapas, tiempos configurables del catálogo de puestos y reconocimientos ACK (`InternalTicketEscalationAck`).
  - Endpoints dedicados: `/api/internal-tickets/{id}/recommendations`, `/api/internal-tickets/{id}/ack`, `/api/internal-tickets/{id}/ack/revoke`.
  - El escalamiento interno registra `position_id` para evaluar recomendaciones de la etapa escalada.
  - Al igual que en tickets de clientes, el escalamiento interno jamás modifica el responsable del ticket interno ni altera su estado.
  - Al cerrar un ticket interno, los reconocimientos ACK activos concluyen automáticamente.

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


## Rendimiento de recomendaciones y ACK

- Retorno temprano para tickets cerrados: no calcula etapa, destinos ni ACK y no modifica historial. El endpoint conserva `ticket_status`; datos de etapa no aplicables son null y contador 0 en esa respuesta.
- `TicketRecommendationNotice` recibe el estado de la ficha: actualización única cada 60 segundos tras completar la consulta, solo para el ticket abierto visible. Pausa en pestaña oculta, limpia al desmontar/cambiar de ticket y detiene el ciclo ante cierre remoto, sincronizando la ficha una vez.
- Creación, edición y finalización de escalamientos, así como creación/retiro de ACK, invalidan inmediatamente la recomendación sin solicitudes superpuestas. ACK vigente no detiene ni reinicia la etapa y no necesita temporizadores por destino.
- Consultas acotadas con LIMIT 1 para la etapa y carga conjunta de destinos, sin cargar grafos ORM operativos desde identidad/ACK. No hay vigilancia global ni nueva infraestructura.
- Ver [auditoría SQL, pruebas y límites de reapertura remota](../escalation-recommendation-performance.md). Pruebas específicas en `tests/test_recommendation_performance.py` y `frontend/src/components/TicketRecommendationPolling.test.tsx`.


## Cierre rápido desde la ficha

- Acción adicional `Cerrar ticket` para OPEN con permiso de cierre; no sustituye la edición ni la reapertura.
- `POST /api/internal-tickets/{id}/close`: `expected_updated_at` obligatorio; `end_at` omitido/null usa hora del servidor al confirmar, o fecha ISO con zona explícita. Resolución interna opcional; no acepta campos de cliente. No se crea ningún permiso ni migración.
- Bloqueo de fila y revisión optimista: cambios concurrentes o ticket ya cerrado → 409, sin sobrescrituras. Se reutiliza la persistencia previa para estado/fecha/resoluciones y cierre de ACK, atómicamente. No crea ni finaliza escalamientos.
- Fecha manual en America/Guatemala, validada y convertida explícitamente a UTC; no anterior a apertura ni futura en el cierre rápido. La edición tradicional conserva sus reglas.
- `TicketQuickClose.tsx` compartido: precarga, envío solo de resoluciones cambiadas, cancelación, doble envío y actualización inmediata. Pruebas `tests/test_ticket_quick_close.py` y `frontend/src/components/TicketQuickClose.test.tsx`.
- Contrato completo y validación: [cierre rápido](../quick-ticket-close.md).
