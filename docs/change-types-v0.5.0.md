# Tipos de cambio — Ticketyn v0.5.0

## Persistencia y catálogo

La revisión `0023_change_types` continúa desde `0022_change_control`. Crea
`change_types` con nombre, descripción opcional, estado y fecha de creación,
utilizando los campos técnicos de los catálogos existentes. El índice normalizado
impide duplicados ignorando mayúsculas y espacios externos, tanto en API como en
PostgreSQL. Se administra con GET/POST `/api/change-types` y GET/PATCH
`/api/change-types/{id}`. No se ofrece eliminación física; la FK también impide
eliminar un tipo utilizado por un cambio.

Los ocho valores iniciales se insertan desde la migración con `ON CONFLICT DO
NOTHING`. Repetir la carga no duplica ni sobreescribe descripciones o estados.

La revisión posterior `0024_default_change_types_upper` cambia únicamente los
nombres originales de los ocho tipos iniciales a mayúsculas. Se identifica cada
predeterminado por su ID inicial y nombre exacto, según la tabla vacía y el orden
de inserción de `0023`. Nombres personalizados y filas creadas manualmente no se
normalizan. IDs, descripciones, estados, fechas y relaciones se conservan. La
operación es idempotente y forma parte también de las instalaciones nuevas al
aplicar la cadena completa. No se modifica la migración anterior ni se transforma
la entrada de nombres en frontend o API.

`maintenance_changes.change_type_id` es una FK nullable e indexada. La migración
no clasifica los registros históricos ni modifica sus fechas, numeraciones,
estados o resultados. La API exige un tipo activo para nuevos cambios. Un cambio
puede conservar su tipo posteriormente inactivo; cambiar la asignación requiere
otro tipo activo. Se conserva la relación con el catálogo, siguiendo el patrón
existente, sin introducir un snapshot adicional del nombre.

Un registro histórico NULL puede consultarse y recibir seguimientos o cambios de
vínculos independientes. Guardar modificaciones del registro principal exige
clasificarlo. En todas las superficies de lectura y exportación, NULL se presenta
como «Sin clasificar», sin inferir una categoría.

## Integración

- Administración → Catálogos → Tipos de cambio: administrador existente, incluyendo
  descripción, edición y activación/desactivación.
- Creación/edición: selector obligatorio, activos para nuevas asignaciones e
  inactivos visibles si ya estaban asociados.
- Listado y detalle: nueva clasificación, con tratamiento explícito de NULL.
- El filtro `change_type_id` utiliza la consulta compartida del listado,
  calendario, reportería y exportaciones. No cambia la geometría ni los eventos
  del calendario.
- Reportería: distribución `change_types` con conteos por FK y categoría NULL,
  usando `categoryColor` y la paleta compartida Capsule NOC.
- PDF individual y PDF/Excel del listado y reportería incluyen la clasificación.
  La reportería exportada añade la distribución «Tipos de cambio».
- Duraciones, eficiencia, puntualidad, estados, tipos de finalización y correlativo
  CAM mantienen sus reglas actuales.

## Revisión local

1. Usar una base local de prueba con respaldo y configuración separada de las
   bases operativas. Comprobar `alembic current` y `alembic heads`.
2. Aplicar `alembic upgrade head` mediante el procedimiento del proyecto. La nueva
   revisión esperada es `0024_default_change_types_upper`. No se aplica automáticamente al abrir
   el frontend.
3. Comprobar los ocho tipos, crear/editar uno y desactivarlo/reactivarlo.
4. Crear un cambio con tipo activo; verificar que no se pueda guardar sin él.
5. Consultar un cambio anterior sin clasificar y agregarle seguimiento o vínculos.
   Al editar sus datos principales, seleccionar una clasificación.
6. Desactivar un tipo asignado y comprobar que se conserva al editar el cambio.
7. Probar el filtro en listado, Mes/Semana/Día y reportería; comparar los conteos.
8. Revisar el tipo en detalle, PDF individual y exportaciones PDF/Excel, incluyendo
   un histórico «Sin clasificar» y resultados filtrados.

La migración se valida exclusivamente en PostgreSQL descartable de pruebas. Su
downgrade se bloquea para evitar pérdida de clasificaciones; cualquier reversión
operativa requiere un procedimiento de recuperación revisado.
