# Trabajos persistentes e integración FMS — etapas 6 a 8 de v0.6.0

## Alcance y estado inicial

La etapa 6 añade coordinación y procesamiento, reutilizando [plantillas](mail-configuration-v0.6.0.md),
[transporte SMTP/OAuth2](mail-transport-v0.6.0.md) y [cifrado de secretos](secrets-v0.6.0.md).
**Desde la etapa 7, registrar una activación crea una intención de correo si el
evento está en Automático.** El procesador la gestiona después del commit.
La etapa 8 permite solicitar envíos y reenvíos explícitos desde el detalle de una
activación, usando la misma fila y el mismo procesador; nunca conecta a SMTP desde FMS.

La migración `0029_mail_requests` depende de `0028_mail_transport` y deja el
procesador **pausado**. No altera activaciones, snapshots, intervenciones,
credenciales, eventos ni plantillas. No se han aplicado migraciones a bases operativas.
Una instalación nueva necesita revisar el estado y autorizar su ejecución; cambiar
la modalidad del evento a Automático no sustituye esa decisión.

## Persistencia y servicio transaccional

`mail_notification_requests` conserva una sola fila por `(event_key, activation_id)`,
con UNIQUE y claves foráneas RESTRICT a evento y activación. El único evento permitido
actualmente es `fms.activation.created`. Los campos son estado, origen AUTOMATIC/MANUAL,
revisión de estado, identificador opaco del procesador, fechas de solicitud/preparación/SMTP/
finalización y código de error saneado. Se conserva la misma fila en cada reenvío;
no hay tabla de intentos ni historial individual. No se almacenan asunto, cuerpo,
EML, destinatarios, credenciales ni contenido generado.

El índice parcial de pendientes permite ordenarlos por solicitud/ID. El índice de
estado evita escanear todo el historial al recuperar trabajos interrumpidos. La
relación con activación también tiene índice.

`notifications/requests.py::request_notification(session, event_key, activation_id,
automatic=..., expected_revision=...)` no hace commit ni conecta a SMTP:

- Automático: solo inserta si el evento está AUTOMATIC y no existe fila. Las llamadas
  repetidas devuelven la fila existente, incluso si terminó: no reintentan un fallo.
- Manual: exige evento habilitado y revisión observada (`0` si no hay fila). Un trabajo
  activo se reutiliza sin añadir otro envío. Si estaba pendiente/preparándose en
  automático, una intención manual lo convierte en MANUAL, manteniendo su generación.
- Después de un estado terminal, una intención manual con la revisión vigente
  avanza la revisión y vuelve a PENDING. La revisión también avanza en cada
  transición técnica; un doble clic tardío con revisión vieja
  se rechaza, incluso si el primer clic se unió a un pendiente y ese envío ya terminó. Se permiten reenvíos deliberados
  posteriores sin límite; UNCERTAIN exige especial revisión operativa.

La coalescencia descrita corresponde al servicio interno. El endpoint del detalle
añade una comprobación de estado/revisión bajo los mismos bloqueos y devuelve 409
si ya hay trabajo activo: no convierte una solicitud automática en manual al pulsar
accidentalmente el botón ni genera una segunda solicitud.

## Integración transaccional con FMS — etapa 7

`POST /api/activations` delega en
`src/ticketyn/api/fms_data.py::create_operation()`. Una vez validados los datos,
obtenidos los snapshots y reservada la numeración, ese servicio añade la activación
y ejecuta `session.flush()` para obtener su ID **sin commit**. Entonces llama a
`request_notification(session, ACTIVATION_EVENT, activation.id, automatic=True)`
y finalmente a `save_item()`, que confirma la misma transacción PostgreSQL.

| Modalidad al registrar | Resultado |
|---|---|
| AUTOMATIC | Activación y solicitud PENDING con origen AUTOMATIC se confirman juntas. |
| MANUAL | Se confirma únicamente la activación; no se crea solicitud. |
| DISABLED, o evento sin configurar | Se confirma únicamente la activación; no se crea solicitud. |

La modalidad se consulta en el servicio existente, bajo los bloqueos de control y
evento de la etapa 6; no se duplica su coordinación. Estos bloqueos se conservan
hasta el commit, serializando la creación con los cambios de modalidad. El contador
y las asignaciones pendientes de sector/nodo al circuito forman parte de la misma
transacción. Un fallo al persistir la intención o al confirmar revierte todos esos
datos: no queda una activación confirmada sin su intención automática. Los errores
de integridad mantienen el 409 existente; los errores de almacenamiento detectados
en la preparación de activación/intención devuelven 503 sin diagnósticos SQL.

El registro FMS no renderiza plantillas, no prepara destinatarios ni descifra
credenciales y no hace llamadas SMTP/OAuth2. El procesador solo puede ver filas confirmadas y resuelve
el mensaje con los datos/configuración vigentes al prepararlo. Una falla SMTP
posterior cambia únicamente el estado técnico; nunca revierte ni modifica la
activación, numeración, snapshots, notas o intervenciones. Un procesador pausado
conserva la solicitud PENDING: seleccionar Automático no lo reanuda.

La integración solo se ejecuta al crear `Activation`. No hay backfill de registros
históricos ni solicitudes al consultar, previsualizar, corregir mediante una
intervención o registrar capacidad, baja y reactivación. Las activaciones siguen
siendo inmutables: no se añade un endpoint de edición. Registrar hoy una activación
con fecha operativa pasada sí es una creación nueva y respeta la modalidad actual.

**Idempotencia del correo y del POST son conceptos distintos:** el servicio no
crea otra fila ni reintenta un resultado terminal para la misma activación. El POST
FMS mantiene su contrato previo, sin clave de idempotencia HTTP. Repetir una creación
exitosa produce otra activación/correlativo y, en Automático, otra intención. Si se
pierde la respuesta HTTP, verificar el listado antes de repetir el registro; no se
promete deduplicación de operaciones de negocio ni entrega SMTP exactamente una vez.

La etapa 7 no necesita migración: el HEAD permanece en `0029_mail_requests`. No
modifica transporte, procesador, recuperaciones ni procedimientos administrativos.

## Máquina de estados

| Desde | Hacia | Criterio |
|---|---|---|
| PENDING | PREPARING | Procesador autorizado reclama trabajo habilitado. |
| PENDING/PREPARING | CANCELLED | Cambio de modalidad antes de iniciar SMTP. |
| PREPARING | SENDING | Contenido y credenciales preparados; se confirma el límite SMTP en DB antes de conectar. |
| PREPARING | FAILED | Error de configuración, plantilla, cifrado o preparación. |
| PREPARING | PENDING | Reinicio normal sin posibilidad de SMTP; transporte temporalmente ocupado, pausa o cierre ordenado. |
| SENDING | ACCEPTED | El servidor aceptó todos los destinatarios. No confirma entrega al buzón. |
| SENDING | PARTIAL | Algunos destinatarios aceptados y otros rechazados. |
| SENDING | FAILED | Rechazo conocido o fallo técnico con resultado determinado. |
| SENDING | UNCERTAIN | Interrupción o resultado SMTP ambiguo. |
| PREPARING/SENDING | UNCERTAIN | Restauración: no se reanuda automáticamente nada que ya había iniciado. |
| ACCEPTED/FAILED/PARTIAL/UNCERTAIN/CANCELLED | PENDING | Únicamente una nueva intención manual explícita y con revisión vigente. |

FAILED, PARTIAL y UNCERTAIN no se reintentan automáticamente. Las transiciones se
centralizan en el backend; una revisión y un owner_token impiden que un resultado
antiguo sobrescriba una revisión posterior. Los errores guardados y logs contienen
solo códigos técnicos e identificadores, sin mensajes del servidor ni excepciones crudas.

## Procesador, concurrencia y sesiones

`NotificationProcessor` se inicia y se detiene desde el lifespan de FastAPI. Cada
proceso puede iniciar su hilo, pero PostgreSQL permite **un solo ciclo de procesamiento
activo por base de datos**, con advisory lock de sesión en una conexión AUTOCOMMIT.
Se procesan trabajos de uno en uno, con espera de un segundo después de trabajar y
dos segundos cuando no hay trabajo. La parada solicita cierre y espera hasta 30
segundos al hilo; una terminación durante SMTP se recupera como incierta.

Las lecturas/escrituras usan sesiones SQLAlchemy independientes y cortas. La conexión
que mantiene el advisory lock no mantiene una transacción abierta durante SMTP.
La selección usa `FOR UPDATE SKIP LOCKED`; los cambios se coordinan mediante el
singleton de control y bloqueo de filas, siguiendo el orden control → evento/trabajo.

La plantilla, destinatarios y datos reales se resuelven durante la preparación,
no al crear la solicitud. Se usa un snapshot de lectura para plantilla y datos FMS.
Después se preparan transporte y credenciales con el mecanismo existente, incluida
renovación OAuth2. Se comparte la reserva temporal del transporte con las pruebas
SMTP, sin aplicar al procesador el cooldown exclusivo de las pruebas. Un transporte
ocupado difiere el trabajo antes de SMTP, sin convertirlo en un fallo de envío.

Antes de marcar SENDING se vuelven a comprobar pausa, modalidad, revisión, propiedad
del trabajo y posesión del advisory lock. Ese cambio se confirma **antes** de llamar
al transporte. SMTP no se ejecuta dentro de transacciones FMS ni de escritura de
trabajos. Los cambios de configuración del transporte respetan su reserva existente.

El advisory lock se libera al terminar o al perderse la conexión/proceso. Su posesión,
no una simple fecha de vencimiento, impide recuperar como abandonado el trabajo de
otro procesador vivo. Si una conexión se pierde durante SMTP, no puede garantizarse
si el servidor recibió el mensaje: se conserva el criterio UNCERTAIN, sin reintento.
No se promete entrega exactamente una vez; un reenvío deliberado de un resultado
incierto puede duplicar un correo que el servidor haya aceptado.

## Modalidades

- AUTOMATIC → MANUAL: cancela automáticos PENDING/PREPARING. Una intención manual
  ya registrada se conserva como manual.
- Cualquier modalidad → DISABLED: cancela todos los PENDING/PREPARING del evento.
- SENDING ya está iniciado y puede finalizar, incluso después de desactivar o pausar.

Las reglas se aplican en la API de configuración y se verifican otra vez en el
procesador. No se cambia ningún dato de activación al cancelar una solicitud.

## Reinicio y restauración

En un reinicio normal se conserva la autorización de ejecución del control:
PENDING continúa; PREPARING vuelve a PENDING porque todavía no pudo conectar a
SMTP; SENDING pasa a UNCERTAIN. La recuperación se ejecuta únicamente poseyendo el
advisory lock, incluso mientras el procesador permanece pausado.

`mail_processor_control` guarda pausa, motivo, revisión de control e identidad OID
de la base. Una fila ausente o una identidad de base diferente provoca pausa segura
y cuarentena de solicitudes iniciadas. El OID es una comprobación adicional, no un
identificador universal de restauraciones.

El procedimiento soportado incorpora dos defensas:

1. `backup.sh` conserva solicitudes y toda la información de negocio, pero excluye
   **los datos** de `mail_processor_control` del dump. No se respalda la autorización
   para enviar correos; la estructura sí se incluye. Una restauración de ese dump
   arranca pausada, incluso si no cambia el OID.
2. `restore.sh::restore_pause_mail` marca el staging como RESTORED/pausado y convierte
   PREPARING/SENDING en UNCERTAIN **antes** del cutover y arranque. Si falla esa
   operación, no cambia la base activa. El hook es condicional para respaldos de
   versiones anteriores que no tenían estas tablas.

No se elimina información de negocio ni se cambia el formato del paquete de backup.
El archivo de claves sigue respaldándose/restaurándose por separado. La reanudación
no recifra ni sustituye claves y no recupera automáticamente secretos ausentes.

Las restauraciones manuales ajenas a estos procedimientos deben detener la aplicación
y marcar explícitamente pausa/cuarentena antes del arranque. Un dump externo que
incluya la autorización y se restaure sobre el mismo OID no se distingue de un
reinicio por el contenido de la DB: no se debe iniciar Ticketyn en ese estado.
Usar el hook de restore o aplicar, en la base restaurada y con Ticketyn detenido:

```sql
BEGIN;
UPDATE mail_processor_control
SET paused=true, reason='RESTORED', revision=revision+1, database_oid=NULL,
    updated_at=clock_timestamp();
UPDATE mail_notification_requests
SET state='UNCERTAIN', revision=revision+1, error_code='RESTORED_INTERRUPTED', owner_token=NULL,
    finished_at=clock_timestamp()
WHERE state IN ('PREPARING','SENDING');
COMMIT;
```

Si no existe fila de control, el arranque crea una pausada y aplica la cuarentena.
Nunca reanudar una instalación restaurada sin revisar las solicitudes.
Un PENDING del respaldo pudo enviarse después de tomar esa copia y antes de la
restauración: el respaldo no permite deducir ese hecho. Revisar también estos
pendientes; si no deben recuperarse, desactivar el evento los cancela antes de
reanudar. La pausa no convierte el respaldo en una garantía de entrega única.

## Controles operativos

Bajo `/api/mail-notifications` se conservan los controles del procesador:

| Método y ruta | Uso |
|---|---|
| `GET /processor` | Pausa, motivo, revisión y cantidades por estado. |
| `GET /requests?state=PENDING&limit=50&offset=0` | Revisión paginada (máximo 100); no expone owner_token ni secretos. |
| `POST /processor/pause` | Pausa persistente. No interrumpe SMTP ya iniciado. |
| `POST /processor/resume` | Reanuda con revisión vigente y confirmación explícita. |

Después de revisar el estado y los pendientes, enviar a resume:

```json
{"revision": 7, "confirmation": "REANUDAR"}
```

`7` es solo ilustrativo: usar la revisión devuelta por GET. Si cambió el estado o
entraron nuevas solicitudes, devuelve 409 y debe repetirse la revisión. No se puede
reanudar mientras haya PREPARING/SENDING sin finalizar o recuperar. La reanudación
solo habilita PENDING: no transforma UNCERTAIN, FAILED o PARTIAL en nuevos envíos.

Estos controles mantienen el modelo actual sin login, roles ni autorización individual.
La confirmación es operativa, no una frontera de seguridad. Restringir la aplicación
y API mediante la infraestructura de red. No se añade un banner a la interfaz.

## Verificación y límites de esta etapa

Las pruebas usan PostgreSQL descartable, SMTP/OAuth2 simulados y claves sintéticas.
Cubren unicidad, rollback, revisiones, reenvíos, concurrencia con conexiones distintas,
sesión AUTOCOMMIT durante SMTP, inicio/parada del lifespan, modos, recuperación,
respuestas parciales/inciertas y errores saneados. También ejercitan pg_dump/pg_restore
reales y el hook de pausa con bases descartables, así como upgrade/downgrade de 0029.
El downgrade se rechaza si existen solicitudes para evitar perder estado técnico.

Las pruebas de módulos que usan una sesión inyectada desactivan explícitamente el
hilo del procesador; el lifespan tiene una prueba propia con sesiones independientes.
No se utiliza una base de producción ni se envían mensajes externos. No se genera
frontend/dist, se cambian versiones ni se publica una release.


## Archivos involucrados en la etapa 6

Los cambios de etapas 1–5 se conservan; esta lista identifica la integración de
trabajos y sus verificaciones, sin atribuir a esta etapa todo el diff acumulado.

- Persistencia: `src/ticketyn/models/mail_jobs.py`, registro en
  `src/ticketyn/models/__init__.py` y `alembic/versions/0029_mail_requests.py`.
- Servicio y procesador: `src/ticketyn/notifications/requests.py`, `processor.py`,
  `delivery.py` y `coordination.py` en el mismo directorio.
- API y arranque: `src/ticketyn/api/mail_jobs.py`, `mail_notifications.py`,
  `mail_transport.py` en el mismo directorio y `src/ticketyn/main.py`.
- Respaldo y restauración: `backup.sh` y `restore.sh`.
- Pruebas de trabajos y scripts: `tests/test_mail_jobs.py`, `tests/test_backup.py`
  y `tests/test_restore.py`.
- Aislamiento del procesador en pruebas existentes: `tests/conftest.py`,
  `tests/test_health.py`, `tests/test_secret_store.py`,
  `tests/test_release_020_upgrade.py` y `tests/test_e2e_update_migration.py`.
- Fixtures y expectativas históricas de migraciones actualizadas:
  `tests/test_change_migration.py`, `tests/test_default_change_types.py`,
  `tests/test_internal_ticket_migration.py`, `tests/test_nodes_responsibles.py`,
  `tests/test_migration.py`, `tests/test_deployment.py` y
  `tests/test_e2e_update_migration.py`. Se conservan las comprobaciones de datos
  históricos y de los bytes de migraciones ya aplicadas.
- Fixture de exportación: `tests/test_ticket_exports.py` usa circuitos separados
  para comparar sectores; no cambia el servicio de sincronización de tickets.
- Documentación: este archivo y enlaces de continuidad en
  `docs/mail-configuration-v0.6.0.md`, `docs/mail-transport-v0.6.0.md` y
  `docs/secrets-v0.6.0.md`.

Esta etapa no modifica componentes frontend ni genera `frontend/dist/`.


## Verificación de la integración — etapa 7

`tests/test_activation_notifications.py` utiliza conexiones independientes y datos
confirmados en PostgreSQL descartable. Comprueba las modalidades, visibilidad solo
después del commit, rollback ante una restricción real y fallos de persistencia/
commit, conservación de numeración y asignaciones, creación concurrente sobre el
mismo circuito y circuitos distintos, serialización con cambios de modalidad,
coalescencia de intenciones, comportamiento
de POST repetidos, recuperación de pendientes y aislamiento de fallos SMTP.
También comprueba notas inmutables, registros históricos, intervenciones y otras
operaciones FMS sin nuevas notificaciones. No utiliza credenciales reales ni envía
mensajes externos; SMTP/OAuth2 están sustituidos por mocks o guardas de red.

Los archivos de implementación de esta etapa son `src/ticketyn/api/fms_data.py`
y las aclaraciones de alcance de `src/ticketyn/notifications/requests.py` y
`src/ticketyn/api/mail_notifications.py`. Se actualizan las expectativas de
`tests/test_mail_jobs.py` y el nombre de la prueba correspondiente de
`tests/test_mail_notifications.py`, además de esta guía y los enlaces de continuidad
en las guías de configuración y transporte. No hay cambios frontend.

La verificación manual del flujo completo en DEV (registro automático, revisión de
la solicitud y aceptación SMTP) debe usar una configuración y destinatarios de
prueba aprobados. No se realiza contra bases operativas durante las pruebas
automatizadas. El envío/reenvío manual se incorpora de forma independiente en la
etapa 8, descrita a continuación; no cambia la creación automática de la etapa 7.

## Envío y reenvío desde el detalle — etapa 8

El detalle de activación consulta la modalidad y el estado técnico. En Manual,
sin solicitud anterior, muestra **Enviar notificación**. Cuando existe una fila,
Manual y Automático muestran **Enviar nuevamente**. No hay un límite de reenvíos
deliberados posteriores. Desactivado oculta la acción y el backend rechaza solicitudes.
Las activaciones históricas sin fila también pueden solicitar su primer envío;
no se crean solicitudes por el mero hecho de abrir la ficha.

PENDING, PREPARING y SENDING deshabilitan el botón. ACCEPTED permite reenviar, pero
solo significa **aceptado por SMTP**, no entregado al buzón. FAILED, PARTIAL y
CANCELLED permiten una nueva solicitud manual con la revisión actual. PARTIAL
advierte sobre posibles duplicados para los destinatarios que ya fueron aceptados.
UNCERTAIN exige marcar una confirmación de posible duplicado, validada también por
el backend: el mensaje anterior podría haberse enviado. Ninguno de estos estados
provoca un reintento automático.

### Contrato API

| Método y ruta | Contrato |
|---|---|
| `GET /api/activations/{id}/notification` | Devuelve modalidad, estado nullable, revisión (`0` sin fila), pausa, disponibilidad de la acción y error de configuración saneado. |
| `POST /api/activations/{id}/notification` | Recibe `revision` entero no negativo y `confirm_uncertain` booleano opcional. Devuelve 202 con el nuevo estado PENDING y un mensaje de solicitud, no de entrega. |

La respuesta contiene `activation_id`, `mode`, `state`, `revision`,
`processor_paused`, `can_request`, `configuration_error` y `message`. No devuelve
destinatarios, contenido, claves ni credenciales. El POST no admite asunto, cuerpo,
destinatarios, servidor u otros campos adicionales.

Errores: 404 si no existe la activación; 409 si cambió la revisión o hay trabajo
activo; 422 por evento desactivado, configuración inválida, contrato inválido o
falta de confirmación UNCERTAIN; 503 ante fallos de almacenamiento, sin diagnósticos
SQL. Un conflicto requiere consultar el estado nuevamente antes de otra acción.

El endpoint usa el orden de bloqueos de la etapa 6: control → evento → solicitud.
La revisión observada se comprueba dentro de esa transacción. Llama al servicio
`request_notification(..., automatic=False, expected_revision=...)` y confirma
la intención antes de responder. Fallar la persistencia revierte esta solicitud,
sin modificar la activación. Dos pestañas con la misma revisión no pueden crear
dos intenciones; una respuesta HTTP perdida se reconcilia mediante GET, sin repetir
automáticamente el POST.

### Configuración, pausa y presentación

Antes de habilitar/aceptar una solicitud se comprueban transporte, destinatarios,
plantilla y requisitos de credenciales mediante los validadores, renderizador y
constructor MIME existentes. El contenido transitorio se descarta: no se almacena
ni se devuelve. Esta comprobación no descifra secretos, renueva tokens ni conecta
a SMTP. Una clave ausente, credenciales revocadas o errores del proveedor solo se
detectan al preparar/procesar el trabajo; no se promete que la validación estructural
garantice un envío satisfactorio.

El procesador resuelve los datos y la configuración vigentes al procesar, incluidos
Para/CC/CCO y plantilla. La ficha no permite editarlos. Cambiar la configuración
después de solicitar sigue las reglas de modalidad/cancelación existentes.

Si el procesador está pausado, se permite dejar una solicitud PENDING, advirtiendo
que esperará una revisión y reanudación explícitas mediante los controles existentes.
Solicitar desde FMS **nunca reanuda el procesador**. La recuperación tras restauración
y los resultados ambiguos mantienen las garantías y límites de la etapa 6.

La interfaz protege el doble clic, muestra el estado en español y permite
**Consultar estado**. Mientras hay trabajo activo y el procesador no está pausado,
consulta cada tres segundos; se detiene al terminar, pausar, fallar la consulta o
salir de la ficha. Ante error/conflicto del POST consulta nuevamente sin reintentar
el envío. El texto de confirmación indica que la notificación fue **solicitada**.

### Archivos y pruebas de la etapa 8

- API: `src/ticketyn/api/activation_notifications.py`,
  `src/ticketyn/schemas/activation_notifications.py` y registro en
  `src/ticketyn/main.py`.
- Interfaz: `frontend/src/components/ActivationNotificationActions.tsx`,
  `frontend/src/pages/ActivationDetail.tsx` y `frontend/src/api/mailNotifications.ts`.
- Pruebas PostgreSQL: `tests/test_activation_manual_notifications.py`; se mantiene
  la comprobación de integración/rutas en `tests/test_mail_jobs.py`.
- Pruebas frontend: `ActivationNotificationActions.test.tsx` y adaptación de los
  mocks de `ActivationNotes.test.tsx` y `ActivationReport.test.tsx`.

Se cubren los tres modos, todos los estados, concurrencia/revisión, confirmación
de resultados inciertos, pausa, configuración inválida, errores HTTP, ausencia de
descifrado/SMTP en la API, rollback, reutilización de fila y uso de la configuración
vigente. Las pruebas verifican que notas, intervenciones y datos FMS permanecen intactos.
No se necesita migración adicional: el HEAD sigue en `0029_mail_requests`.
