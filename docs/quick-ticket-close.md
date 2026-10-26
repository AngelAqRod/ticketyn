# Cierre rápido de tickets

Implementado en `features/v0.9.0`, como acción adicional de las fichas de clientes e internos. No requiere migraciones, campos persistentes ni permisos nuevos.

## Contrato

- `POST /api/tickets/{id}/close`: requiere `tickets.close`.
- `POST /api/internal-tickets/{id}/close`: requiere `internal_tickets.close`.
- Respuesta 200: la misma proyección de detalle de su dominio.
- Cuerpo: `expected_updated_at` obligatorio, conservado exactamente desde el detalle; `end_at` opcional/null para cerrar con la hora UTC del servidor al confirmar; fecha ISO con zona explícita para cierre manual.
- `resolution` opcional/null, en ambos dominios; `customer_resolution` opcional/null solo en clientes. Omitir conserva el valor, null elimina intencionalmente, texto sustituye. Se conservan validación y límite de 10000 caracteres existentes; la UI convierte una resolución borrada/blanca en null. No se exige ninguna resolución.
- No acepta estado, responsable ni campos ajenos al comando. El servidor establece `status=CLOSED` y `end_at`.
- No autenticado: 401. Sin permiso: 403. Revisión obsoleta o ticket ya cerrado: 409. Fecha inválida/sin zona/anterior a apertura/futura o contenido incompatible: 422. Ticket inexistente: 404.

La edición de `customer_resolution` conserva su requisito previo `tickets.edit`; un permiso exclusivo de cierre permite cerrar y cambiar resolución interna, pero no editar la resolución pública. La UI conserva el texto público y lo muestra deshabilitado cuando falta ese permiso. No se amplían privilegios.

## Persistencia y concurrencia

`api/ticket_close.py` bloquea el ticket con `SELECT FOR UPDATE` y refresca sus datos antes de comparar `status` y `updated_at`. Un cambio concurrente del ticket invalida el comando completo: no sobreescribe resoluciones, fechas ni estado. Un reintento tras una respuesta de red ambigua tampoco duplica el cierre; corresponde recargar la ficha y comprobar su estado.

Tras validar, delega en `ticket_data.patch_ticket` o `internal_ticket_data.persist`. Se utiliza una única transacción y el commit existente; cualquier error previo al commit revierte estado, fecha, resoluciones, evidencia interna y finalización del ACK. No se duplica la lógica de ciclo de vida.

El cierre conserva escalamientos, relaciones, responsable y seguimientos previos. Los ACK activos finalizan mediante la lógica existente y conservan sus registros históricos. El frontend recibe inmediatamente el estado CLOSED, deteniendo el ciclo de recomendaciones existente. No se modifica el motor.

## Interfaz

`TicketQuickClose.tsx` comparte botón y diálogo entre `TicketDetail.tsx` e `InternalTickets.tsx`. Solo se ofrece para tickets OPEN con permiso de cierre. Usa diálogo nativo modal con foco contenido, retorno de foco, cancelación y estilos existentes de DESIGN.md. Cancelar no escribe; durante el envío se bloquean controles, Escape y dobles confirmaciones. Al desmontar se cancela la espera HTTP; si el servidor ya confirmó, cancelar la espera no deshace el cierre: al volver se debe consultar la ficha.

- Cerrar ahora predeterminado: no captura la hora al abrir el modal.
- Fecha manual: `America/Guatemala`, formato de valor de 24 horas y conversión explícita mediante `ticketynDateTimeToIso`, independiente de la zona del navegador. Valida en frontend y backend; el reloj definitivo es el del servidor.
- Resoluciones precargadas; el payload solo incluye las que el usuario cambió. La revisión queda congelada junto con la precarga incluso si llega un refresco de la ficha.
- Internos nunca muestran ni aceptan resolución para cliente.
- Éxito actualiza detalle, estado, fin y duración, oculta la acción de cierre y muestra confirmación. Se conservan Editar y Exportar según sus permisos. En ambos dominios se recarga el seguimiento para mostrar la evidencia existente de edición de resolución.

La edición tradicional permanece intacta: corrección de fecha, resoluciones, estado y reapertura. Sus reglas previas no se restringen. El cierre rápido rechaza fechas futuras expresamente; los formularios tradicionales y sus endpoints PATCH no se modifican. La reapertura continúa acumulando `closed_seconds` y conserva la semántica previa de etapas/ACK.

## Confidencialidad

El texto interno sigue en `resolution`; el autorizado para cliente, en `customer_resolution`. No se modifica `CustomerReport`, consultas ni generadores PDF; el nuevo flujo nunca copia una resolución interna al campo público.

## Pruebas y revisión

- `tests/test_ticket_quick_close.py`: ambos dominios, fechas, resoluciones opcionales/conservación/limpieza, permisos reales, conflictos, fallo de persistencia, reapertura, ACK e historial; dos cierres simultáneos en PostgreSQL con un único ganador.
- `TicketQuickClose.test.tsx`: modalidades, precarga, campos condicionales, fechas y zona horaria, conservación de revisión, errores/conflictos/red, doble envío, cancelación, foco, desmontaje y permisos.
- Integración en `TicketDetail.test.tsx` e `InternalTickets.test.tsx`: cierre desde cabecera, actualización y conservación de edición.
- Regresiones dirigidas de tickets, intervenciones, escalamientos, recomendaciones, autorización y PDFs. Resultados exactos en `AGENT_HANDOFF.md`.
- Capturas de componentes reales con fixtures ficticios, Firefox headless: `/tmp/ticketyn-quick-close-customer.png` (1440 px) y `/tmp/ticketyn-quick-close-internal-mobile.png` (390 px, modalidad manual). Sin sesiones, cuentas ni bases reales.

No se ejecutan migraciones, builds, commits ni despliegues. Ningún cambio de frontend/dist ni de módulos ajenos.
