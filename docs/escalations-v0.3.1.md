# Escalamientos en Ticketyn v0.3.1

## Poblaciones de Reportería

El período global utiliza días calendario de `America/Guatemala`, con inicio
inclusivo y fin exclusivo. Hoy y Ayer no son ventanas móviles de 24 horas.
7D/15D/30D incluyen hoy y los días anteriores; Todos omite ambos límites.

- **Tickets del período:** tickets cuyo `start_at` pertenece al período. El numerador
  de cobertura cuenta, una sola vez, aquellos que tienen un escalamiento cuyo
  `started_at` también pertenece al período. Con + sin escalamiento = denominador.
- **Eventos del período:** escalamientos cuyo `started_at` pertenece al período,
  aunque el ticket haya iniciado antes. Activos/finalizados son su estado actual.
- **Duración:** promedio de `finished_at - started_at` para eventos finalizados.
  Los activos no aportan una duración de cierre. Corregir fechas cambia los informes.
- Rankings de personas/departamentos, evolución y tickets relacionados usan la
  población de eventos. `event_tickets` cuenta tickets distintos de esa población;
  puede superar la cobertura, porque incluye tickets anteriores.
- Sector, nodo y responsable principal restringen el contexto de tickets existente.
  Destinatario y los filtros específicos de departamento de destino, motivo y estado
  solo restringen los escalamientos; no cambian las estadísticas generales de tickets.
- PDF/XLSX reutilizan el resumen del backend, sin cálculos paralelos en el navegador.

## Operaciones e historial

Crear exige un departamento activo. El técnico es opcional; al seleccionarlo su
pertenencia debe coincidir con el destino. El departamento se almacena independiente
del técnico y los nombres de departamento/puesto se conservan como snapshots.
Una asignación o cambio explícito crea evidencia anterior/nueva; no se refrescan
snapshots por corregir solamente fechas o reenviar la misma asignación.

`started_at` y `finished_at` son fechas operativas editables. `created_at` es la fecha
original de registro y `updated_at` refleja modificaciones administrativas efectivas.
Finalizar es idempotente; para corregir después se utiliza PATCH explícito.
Se permiten todas estas operaciones en tickets cerrados, sin tocar sus fechas,
departamento, responsable o estado principal. Solo existen ACTIVE y FINISHED.

La auditoría persistente registra creación, finalización y cambios efectivos de
fechas/asignación/destino, con valores anteriores/nuevos y fecha de servidor. GET
`/api/tickets/{id}/escalations/{escalation_id}/audit` permite consultarla. No existen
endpoints para modificar o eliminar auditoría.

**Ticketyn sigue sin autenticación/autorización.** No existe un usuario verificable
para atribuir estas acciones: `actor=null`, presentado como usuario no identificado.
No se acepta un nombre enviado por el cliente como identidad probada ni se atribuye
el cierre al destinatario. Restringir todos los endpoints a la red/proxy de confianza.
Si se necesita demostrar quién autorizó o efectuó un cambio, deberá existir primero
un mecanismo de identidad y permisos; esta versión no lo inventa.

## Migración 0013 y registros históricos

No se modifican migraciones publicadas. `0013_escalation_operations` conserva todos
los registros y reutiliza exactamente `created_at` como inicio histórico, porque era
la única fecha de inicio registrada; `finished_at` se mantiene sin cambios.
`updated_at` reutiliza el cierre registrado en los finalizados y la creación en
los activos: el flujo anterior solo exponía creación y finalización, y generaba
el cierre desde el servidor. No permite reconstruir modificaciones externas
antiguas que nunca se registraron. No se generan actores/eventos
históricos ficticios.

Solo un nombre histórico de departamento exactamente coincidente con un catálogo
actual permite reconstruir `department_id`. No se utiliza el departamento actual del
responsable: podría haber cambiado. Los casos desconocidos/renombrados conservan su
texto histórico, con ID nulo. Por compatibilidad la columna DB admite estos NULL solo con el marcador interno
`legacy_destination` de los registros históricos sin destino reconstruible; una
constraint exige departamento para los demás registros. El marcador no es editable
mediante la API;
el servicio exige un destino válido para nuevas solicitudes y cambios de destino.
Los informes incluyen también los destinos históricos sin ID y técnicos no asignados.

El downgrade se rechaza si perdería fechas operativas, auditoría o destinos sin técnico.
El updater no realiza downgrades ni restauraciones automáticas por este cambio.

## Validación y actualización posterior

Primero probar en Debian aislado desde v0.3.0, conservando un backup y verificando
HEAD `0012` antes de actualizar. La candidata debe llegar a
`0013_escalation_operations`, conservar todos los IDs/datos, funcionar después de
reboot y exportar informes coherentes. No ejecutar la migración en producción durante
el desarrollo. Usar el updater administrado cuando la release haya sido autorizada.

Para una base **DEV autorizada expresamente**, el comando posterior es
`alembic upgrade head`. Esta preparación no lo ejecuta contra DEV. Ante fallo revisar
el estado durable y usar exclusivamente el procedimiento de recovery/retry aprobado;
no editar checkpoints, restaurar sin autorización ni fusionar datos automáticamente.
