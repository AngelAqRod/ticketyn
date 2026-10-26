# Rendimiento de recomendaciones de escalamiento y ACK

## Alcance de la revisión

Rama `features/v0.9.0`. Optimización del motor existente y de su consulta bajo demanda para tickets de clientes e internos. No incorpora vigilancia global, procesos por ticket, cron, Redis, Celery ni cambios de esquema. No cambia umbrales, selección de etapa, responsabilidad, permisos o reglas de escalamientos manuales.

## Comportamiento encontrado

- El motor evitaba añadir recomendaciones para CLOSED, pero solo después de resolver la etapa, cargar escalamientos y consultar/vencer ACK. También podía cargar destinos mediante relaciones ORM aunque el ticket estuviera cerrado.
- La etapa cargaba **todos** los escalamientos activos ordenados; la consulta del último finalizado tampoco tenía LIMIT SQL. Solo se utilizaba uno de cada conjunto.
- Relaciones eager de Position/Responsible podían cargar el grafo de destinos desde el ticket, el escalamiento, el ACK y el usuario autenticado. Esto excedía los datos que requieren esas operaciones.
- React consultaba al montar/cambiar de ticket y después de cambios ACK. No existía actualización periódica, control de visibilidad ni propagación del estado del ticket a `TicketRecommendationNotice`.
- El endpoint ya devolvía `ticket_status`; no hacía falta añadir un campo ni otra petición para detectar cierre remoto.

## Implementación actual

### Backend

- `/api/{tickets|internal-tickets}/{id}/recommendations` carga los campos del ticket sin relaciones operativas automáticas. Si está cerrado, devuelve inmediatamente su estado, recomendaciones vacías, sin ACK vigente y sin acciones ACK; los datos de etapa no aplicables son null y el contador presentado es 0. Esto no borra etapas, escalamientos ni historial.
- GET de ACK vigente utiliza la misma carga acotada. Para un ticket cerrado devuelve 204 sin evaluar la etapa ni actualizar ACK históricos.
- Las dos consultas de etapa filtran `ticket_id` y `status`, mantienen el orden determinista aprobado y usan `LIMIT 1` en SQL.
- Los destinos se cargan mediante una sola consulta con puesto y departamento. No se recorren sus destinos recursivamente ni se consulta por separado cada destino. Con ACK vigente o umbral GENERAL no alcanzado no se cargan destinos de recomendación.
- La autorización ACK conserva las mismas reglas, utilizando identificadores de puestos en lugar de cargar grafos completos. Un operador puede requerir consultas adicionales constantes para verificar su puesto y el flujo autorizado.
- El vencimiento de ACK conserva su registro y motivo originales; se persiste después de construir la respuesta, evitando el anterior `refresh(ticket)` y la recarga eager tras commit. No altera el inicio de etapa ni el contador.
- La resolución de identidad `principal()` aplica `lazyload('*')` a su consulta de cuenta/rol: solo necesita sus campos escalares. Conserva revisión inmediata de permisos, estado de acceso y expiración; no carga posiciones/destinos operativos ni renueva artificialmente la actividad.

### React

- Un único `setTimeout` de **60 000 ms después de finalizar la respuesta**, por componente/ticket abierto visualizado. Ante una petición lenta se espera su finalización; no hay intervalos acumulados ni solicitudes simultáneas del mismo ciclo.
- Cerrado al abrir la ficha: no consulta recomendaciones. Cierre local: elimina temporizador y aborta la petición pendiente. Reapertura reflejada en el estado de la ficha: vuelve a consultar inmediatamente y reanuda el ciclo.
- Cambio de ticket/ámbito y desmontaje: elimina temporizador, aborta la petición y descarta respuestas anteriores.
- `visibilitychange`: pestaña oculta no inicia consultas ni conserva temporizador periódico. Volver a visible consulta inmediatamente; si hay una petición en curso, agrupa la actualización pendiente en una sola comprobación posterior.
- Respuesta CLOSED: detiene el ciclo aun si el padre todavía cree que está abierto y pide recargar la ficha una vez. Los detalles de clientes e internos se sincronizan con el servidor. No continúa consultando indefinidamente el ticket cerrado.
- `refreshKey` enlaza creación/edición/finalización de escalamientos con la actualización inmediata. Crear o retirar ACK usa el mismo ciclo; múltiples invalidaciones durante una petición se agrupan sin solapar HTTP.
- Con ACK vigente se mantiene el mismo temporizador del ticket, sin temporizadores por destino o vencimiento. La recomendación reaparece en la siguiente comprobación al vencer si el ticket sigue abierto; el servidor mantiene el contador de etapa.
- Se propaga el indicador `internal` al modal de escalamientos para que sus operaciones y su refresco pertenezcan al ticket interno. No se modifican reglas ni payloads manuales.

## SQL observado e índices existentes

Mediciones reales mediante `before_cursor_execute` en PostgreSQL efímero, con sesiones nuevas para evitar que la caché de identidad oculte consultas. Mismo resultado en tickets de clientes e internos:

| Escenario medido | Consultas de negocio |
|---|---:|
| Cerrado, incluso con ACK histórico | 1 SELECT del ticket, sin JOIN operativo |
| Abierto, etapa inicial y recomendaciones, 12 destinos | 6 SELECT |
| Mismo escenario, reducido a 1 destino | 6 SELECT |
| ACK vigente | 5 SELECT, sin consultar destinos |
| ACK vencido y recomendaciones | 6 SELECT + 1 UPDATE del ACK |
| Histórico abierto sin puesto ni responsable | 4 SELECT |

**Petición HTTP completa a un cerrado**, usuario Superadmin con puesto y destinos configurados: **3 SELECT** = identidad/rol + configuración de seguridad + ticket. Cero consultas de destinos, escalamientos o ACK. Los permisos personalizados añaden su consulta de concesiones; la autenticación obligatoria no se omite. Las cifras anteriores corresponden a la etapa inicial y actor administrativo de la prueba, no a una promesa de igual número para cualquier etapa/rol.

Índices ya presentes y compatibles con las búsquedas acotadas:

- `ix_ticket_escalations_ticket_chronology` comienza por `ticket_id`; el orden es created_at/id. También existe índice por started_at. La elección de etapa usa started_at o finished_at, por lo que puede requerir ordenar el subconjunto de un ticket.
- `ix_internal_escalations_chronology` cubre ticket_id/started_at/id; el caso de finalizados puede requerir ordenar por finished_at.
- ACK: índices por ticket_id y únicos parciales `uq_ticket_active_ack` / `uq_internal_active_ack` para `active=true`.
- Destinos: índice por position_id y unicidad position_id/target_position_id; consulta de puestos y departamentos por sus PK.

No se añadieron índices ni migraciones sin evidencia de necesidad. No se ejecutó EXPLAIN/ANALYZE ni se midió latencia con volumen productivo; no se afirma qué plan elegirá PostgreSQL en cada instalación. Si un ticket acumula un historial muy grande, evaluar mediante un procedimiento autorizado un índice compuesto ticket_id/status/fecha de etapa antes de introducirlo.

## Validación ejecutada

- Backend: `tests/test_recommendation_performance.py`, `tests/test_escalation_recommendations.py`, `tests/test_ack_security.py`, `tests/test_security_foundation.py`, `tests/test_security_authorization.py`, `tests/test_escalations.py`, `tests/test_internal_tickets.py`: **92 aprobadas**, 0 fallos. Clúster PostgreSQL efímero; advertencia existente Starlette/httpx.
- Frontend: `TicketRecommendationNotice.test.tsx`, `TicketRecommendationPolling.test.tsx`, `TicketEscalations.test.tsx`, `TicketDetail.test.tsx`, `InternalTickets.test.tsx`: **78 aprobadas**, 0 fallos. Los ciclos de 60 segundos, visibilidad, concurrencia, cierre/reapertura y desmontaje usan temporizadores simulados, sin esperas reales de un minuto.
- Pruebas de cierre remoto verifican además que la ficha se recarga una sola vez y deja de consultar recomendaciones.
- TypeScript y `git diff --check`: correctos.
- Comparación SHA-256: 70 archivos previamente existentes de plantillas, nomenclaturas, distribución y frontend/dist sin diferencias respecto al comienzo de esta tarea.

## Límites operativos

La detección periódica es aproximada: 60 segundos más el tiempo de red/evaluación; con errores se reintenta sin acumular trabajo. No garantiza notificaciones instantáneas de otras sesiones.

Un ticket ya cerrado no se vigila para descubrir una eventual **reapertura remota**. Esa reapertura se conocerá al recargar o navegar de nuevo a la ficha, o mediante una actualización normal de sus datos; desde entonces se reactiva el ciclo. Esto evita reintroducir polling sobre cerrados.

No se ejecutaron suites globales completas, builds ni pruebas en instalaciones reales. No se aplicaron migraciones, modificaron bases persistentes, TEST/PROD, SMTP, reportes PDF o archivos de distribución/plantillas. No se hicieron commits, pushes ni despliegues.
