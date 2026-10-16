# Corrección automática del sector de Tickets recientes — v0.5.0

## Disparador y alcance

`PATCH /api/circuits/{id}` bloquea el circuito mediante el mecanismo existente,
valida la modificación y llama a `synchronize_recent_ticket_sectors` únicamente
cuando el sector realmente cambia. Se conserva el guardado y sus validaciones
actuales; no cambia la creación de Tickets ni las asignaciones iniciales desde FMS.
No hay tareas periódicas, botones ni reparación retroactiva.

La hora de corrección proviene de `clock_timestamp()` de PostgreSQL, después de
adquirir el bloqueo del circuito. No utiliza `now()` de inicio de transacción ni
la zona horaria del navegador. Es un instante UTC con zona horaria.

## Selección y escritura

La selección se realiza en PostgreSQL, sin cargar filas de Tickets en Python:

```sql
WHERE tickets.circuit_id = :circuit_id
  AND tickets.created_at >= :corrected_at_minus_168_hours
  AND tickets.created_at <= :corrected_at
  AND tickets.sector_id <> :new_sector_id
```

El límite inferior es inclusivo. Los registros futuros quedan fuera de la ventana.
No se filtra por estado, fecha operativa o última actualización. El índice existente
`ix_tickets_circuit_id` sirve para delimitar el circuito; no se añade un índice ni
una migración sin evidencia de que sea necesario.

Un CTE bloquea las filas elegibles; un segundo CTE actualiza únicamente `sector_id`
y devuelve el ID y nombre del sector anterior. `updated_at` se asigna explícitamente
a su valor existente para conservar también ese metadato. Un `INSERT ... SELECT`
registra la evidencia en `ticket_updates` dentro de la misma sentencia SQL. La
confirmación pertenece al guardado del circuito: cualquier error revierte circuito,
Tickets y evidencia.

Las ediciones existentes de Tickets bloquean primero el Ticket y después el
circuito. Para evitar esperar en orden inverso o saltarse Tickets ocupados, esta
operación usa `FOR UPDATE OF tickets NOWAIT`. Si hay conflicto se devuelve HTTP
409 y no se guarda nada; se puede reintentar la modificación del circuito. No se
usa `SKIP LOCKED` ni se permiten sincronizaciones parciales.

## Bitácora

Se reutiliza `TicketUpdate`, siguiendo el patrón existente de cambios automáticos
de resolución. Cada fila modificada genera una entrada:

> Sector actualizado automáticamente de «SECTOR A» a «SECTOR B» por modificación del circuito asociado.

- `visibility = INTERNAL`.
- `responsible_id = NULL`: no atribuye una intervención a una persona inexistente.
- `escalation_id = NULL`: no modifica ni simula escalamientos.
- `occurred_at` y `created_at`: instante único de la corrección.

No se editan intervenciones anteriores. El reporte para cliente sigue excluyendo
entradas internas mediante sus reglas existentes. Si el sector ya coincide o el
circuito conserva el mismo sector, no se escribe evidencia redundante.

## Verificación manual en una base local de prueba

1. Preparar Tickets del mismo circuito con creación hace 1 día, exactamente 168
   horas y más de 168 horas; incluir abiertos y cerrados y un Ticket de otro
   circuito. Para la frontera exacta, preferir las pruebas automatizadas con reloj
   controlado, evitando el tiempo transcurrido entre acciones manuales.
2. Cambiar el sector del circuito y comprobar que solo los Tickets recientes del
   circuito reciben el nuevo sector y su entrada interna automática.
3. Verificar que estados, correlativos, fechas operativas, creación, actualización,
   resoluciones, Nodo y demás datos permanecen intactos.
4. Guardar una descripción del circuito o el mismo sector: no debe añadirse ninguna
   entrada. Repetir el cambio a otro sector debe volver a evaluar la ventana actual.
5. Comprobar que Tickets internos y registros FMS conservan sus valores.

Las pruebas utilizan exclusivamente PostgreSQL temporal. No se necesitan cambios
frontend, migraciones ni modificaciones de datos operativos para preparar el código.
