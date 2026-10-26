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
  - Principio fundamental: **un escalamiento NO equivale a un cambio de responsable**. Un ticket puede escalarse a otro puesto y conservar su responsable actual intacto.
  - No obligan a una jerarquía rígida (N1/N2/N3) ni modifican el responsable principal asignado al ticket.
- **Motor de recomendaciones de escalamiento por etapas:**
  - **Cálculo bajo demanda:** El cálculo se realiza al consultar las recomendaciones del ticket sin procesos de fondo ni cron jobs innecesarios.
  - **Etapa inicial:** El contador arranca con `created_at` del ticket y toma la configuración del puesto original (`initial_position_id`, capturado al crear el ticket a partir del responsable asignado).
  - **Etapa escalada:** Al registrar un escalamiento efectivo con puesto de destino (`position_id`), concluye la etapa previa y el contador inicia en la fecha/hora del escalamiento más reciente (regla determinista ante escalamientos concurrentes).
  - **Finalización de escalamientos:** Cuando termina el último escalamiento activo y el ticket continúa abierto, concluye la etapa escalada y se reactiva la configuración del puesto original. El contador original se reinicia desde la fecha de finalización del último escalamiento (sin reutilizar tiempo previo).
  - **Deducción de tiempo cerrado:** Al reabrir un ticket, se acumula el tiempo que permaneció cerrado en `closed_seconds` y se descuenta del tiempo transcurrido en la etapa activa.
  - **Acciones que NO reinician el contador:** Cambios de responsable, seguimiento, cambios de prioridad o descripción no alteran el tiempo de referencia.
- **Reconocimiento de alarma (ACK):**
  - Acción para silenciar exclusivamente las recomendaciones automáticas de escalamiento del ticket.
  - Duraciones seleccionables: `1H` (1 hora), `4H` (4 horas), `8H` (8 horas), `INDEFINITE` (hasta retiro manual). Predeterminado: `1H`.
  - Como máximo un ACK activo por ticket (índice único parcial `WHERE active = true`).
  - El ACK no reinicia ni detiene contadores, no cambia responsables ni estado. Al vencer o revocarse, las recomendaciones que superen el umbral reaparecen de inmediato.
  - Al cerrarse un ticket, los ACKs activos se concluyen automáticamente preservando el historial.
  - **Autorización:** Roles `SUPERADMIN` y `ADMIN` autorizados; rol `OPERATOR` requiere permiso `tickets.escalate` y pertenecer a un puesto habilitado en el flujo operativo del ticket (puesto de referencia de etapa, puestos destino o puesto inicial/actual del responsable).
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
- **Endpoints clave:** `GET/POST /api/tickets`, `GET/PUT /api/tickets/{id}`, `POST /api/tickets/{id}/updates`, `POST /api/tickets/{id}/escalations`, `GET /api/tickets/{id}/pdf`, `GET /api/tickets/export`, `GET /api/my-tickets`, `GET /api/my-tickets/summary`.
- **Permisos requeridos:** `tickets.view`, `tickets.create`, `tickets.edit`, `tickets.close`, `tickets.escalate`, `tickets.followup`, `tickets.export`, `tickets.link`. `my-tickets` requiere `tickets.view` o `internal_tickets.view`.
- **Integridad:** Las consultas validan pertenencia del circuito al cliente indicado; los selectores operativos descartan responsables inactivos o no seleccionables. Módulo «Mis tickets» respeta la autoría de intervenciones y escalamientos, y aísla tickets por puesto operativo del usuario autenticado.

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


## Rendimiento de recomendaciones y ACK

- Retorno temprano para tickets cerrados: no calcula etapa, destinos ni ACK y no modifica historial. El endpoint conserva `ticket_status`; datos de etapa no aplicables son null y contador 0 en esa respuesta.
- `TicketRecommendationNotice` recibe el estado de la ficha: actualización única cada 60 segundos tras completar la consulta, solo para el ticket abierto visible. Pausa en pestaña oculta, limpia al desmontar/cambiar de ticket y detiene el ciclo ante cierre remoto, sincronizando la ficha una vez.
- Creación, edición y finalización de escalamientos, así como creación/retiro de ACK, invalidan inmediatamente la recomendación sin solicitudes superpuestas. ACK vigente no detiene ni reinicia la etapa y no necesita temporizadores por destino.
- Consultas acotadas con LIMIT 1 para la etapa y carga conjunta de destinos, sin cargar grafos ORM operativos desde identidad/ACK. No hay vigilancia global ni nueva infraestructura.
- Ver [auditoría SQL, pruebas y límites de reapertura remota](../escalation-recommendation-performance.md). Pruebas específicas en `tests/test_recommendation_performance.py` y `frontend/src/components/TicketRecommendationPolling.test.tsx`.


## Cierre rápido desde la ficha

- Acción adicional `Cerrar ticket` para OPEN con permiso de cierre; no sustituye la edición ni la reapertura.
- `POST /api/tickets/{id}/close`: `expected_updated_at` obligatorio; `end_at` omitido/null usa hora del servidor al confirmar, o fecha ISO con zona explícita. Resolución interna opcional y `customer_resolution` opcional con permiso `tickets.edit`. No se crea ningún permiso ni migración.
- Bloqueo de fila y revisión optimista: cambios concurrentes o ticket ya cerrado → 409, sin sobrescrituras. Se reutiliza la persistencia previa para estado/fecha/resoluciones y cierre de ACK, atómicamente. No crea ni finaliza escalamientos.
- Fecha manual en America/Guatemala, validada y convertida explícitamente a UTC; no anterior a apertura ni futura en el cierre rápido. La edición tradicional conserva sus reglas.
- `TicketQuickClose.tsx` compartido: precarga, envío solo de resoluciones cambiadas, cancelación, doble envío y actualización inmediata. Pruebas `tests/test_ticket_quick_close.py` y `frontend/src/components/TicketQuickClose.test.tsx`.
- Contrato completo y validación: [cierre rápido](../quick-ticket-close.md).


## Navegación a la ficha del circuito

- `CircuitLink.tsx` representa un enlace discreto a `/circuits/{circuit_id}` con React Router. Requiere `circuits.view` e ID positivo, seguro y resuelto; sin ese permiso muestra el mismo texto, sin enlace ni icono. No confunde código visible con ID ni filtra por active: los circuitos desactivados conservan acceso a su expediente.
- Se utiliza en el campo Circuito de `TicketDetail.tsx` y en la columna existente de `TicketTable.tsx`, compartida por Tickets, Dashboard y Reportería. No añade columnas, botones por fila ni consultas HTTP. Evita propagar el clic al contenedor y conserva navegación de regreso.
- Los IDs del resumen de circuito y `ticket.circuit_id` deben coincidir. Sin resumen disponible o con ID incompatible no se construye una ruta. Los listados ya reciben referencias resueltas desde la consulta existente; la FK y el borrado protegido impiden eliminar circuitos asociados a tickets.
- `getTicketCatalogs` conserva por defecto su contrato estricto para edición. Solo el detalle usa la opción `allowUnavailableCircuit=true`: ante 403/404 de la consulta de circuito, conserva el código/descripción que ya traiga el ticket como texto sin enlace. Si tampoco existe ese texto, muestra «Sin circuito asociado». No reconstruye históricos ni silencia errores de red, 401 o de otros catálogos.
- «Mis tickets» no dibuja actualmente el dato del circuito; no se añade allí información o columnas únicamente para esta mejora, ni se amplía su contrato API. Formularios, filtros, cierre rápido, permisos y PDF permanecen intactos.
- La disponibilidad refleja los datos recibidos: una revocación posterior se vuelve a comprobar en la ruta y backend de destino; no se añaden sondeos por fila para anticiparla.
- Pruebas: `CircuitLink.test.tsx` (rutas, regreso, clic sin propagación, permisos, datos no resueltos e inactivos, ausencia de peticiones/columnas adicionales) y regresiones de detalle, edición, Tickets, Dashboard, Reportería, Mis tickets y cierre rápido.
