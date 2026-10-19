# Notificaciones por correo — etapas 3 y 4 de v0.6.0

El detalle de configuración de esta guía corresponde a las etapas 3 y 4; las
capacidades de transporte y autorización vigentes se explican en la guía de etapa 5.
Los hallazgos y límites revisados durante la estabilización están en la
[auditoría de etapa 9](mail-audit-v0.6.0.md).

## Alcance actual

Administración separa **Configuración de correo** (`/mail-notifications`), con
transporte SMTP, modalidades y destinatarios, de **Plantillas de correo**
(`/mail-templates`), con el editor, inventario de campos y vista previa. Las rutas
API y la configuración almacenada se conservan. Permite
previsualizar asunto y cuerpo con una activación real, sin persistir el resultado.
La etapa 5 añade autorización OAuth2 y una prueba SMTP explícita; consulta
[Transporte SMTP y OAuth2](mail-transport-v0.6.0.md). Las
[etapas 6 y 7](mail-jobs-v0.6.0.md) incorporan procesamiento persistente e integración
transaccional con el registro FMS. La versión del proyecto no cambia.

El único evento registrado es `fms.activation.created`, «Registro de activación
FMS». Desde la etapa 7, registrar una activación consulta su modalidad para decidir
si debe persistir una intención automática en la misma transacción; no modifica
la configuración de correo.
Las notas, snapshots e intervenciones FMS conservan su funcionamiento.

## Modelo de acceso

**Administración es una agrupación de interfaz, no una frontera de autorización.**
Ticketyn no tiene login, usuarios, sesiones, roles ni autorización individual.
Cualquier persona con acceso a la aplicación o API puede consultar y modificar la
configuración, incluidos los destinatarios. Debe restringirse el acceso mediante
la infraestructura de red. Esta etapa no agrega middleware ni pruebas de rechazo
por un permiso administrativo inexistente.

## Persistencia y migración

`0026_mail_configuration` depende de `0025_activation_notes`. Solo incorpora:

- `mail_transport_config`: singleton de transporte; comienza sin servidor ni
  remitente, STARTTLS, puerto 587 y sin autenticación ni credenciales.
- `mail_event_config`: una fila por evento, con modalidad y grupos de destinatarios
  independientes en JSONB. El evento inicial comienza `DISABLED` con listas vacías.

Las contraseñas se almacenan únicamente en `smtp_password_encrypted`, mediante
AES-256-GCM y contexto `mail:transport:1:smtp-password`. Existe un contenedor
`oauth_credentials_encrypted` reservado para secretos futuros; esta etapa no
acepta ni solicita credenciales OAuth2. No hay columnas de contraseñas o tokens
en texto plano. No hay almacenamiento de mensajes ni colas.

Las escrituras usan transacciones y bloqueo de la fila para combinar cambios
parciales con el valor más reciente. La migración no modifica activaciones ni crea
solicitudes automáticas. El downgrade solo elimina configuración inicial intacta;
si existe configuración real, falla explícitamente para evitar perderla.

## API

| Método y ruta | Función |
|---|---|
| `GET /api/mail-notifications/smtp` | Consulta pública del transporte, sin secretos. |
| `PATCH /api/mail-notifications/smtp` | Crea o actualiza el singleton. |
| `GET /api/mail-notifications/events` | Lista los eventos registrados. |
| `GET /api/mail-notifications/events/{event_key}` | Consulta modalidad y destinatarios. |
| `PATCH /api/mail-notifications/events/{event_key}` | Actualiza modalidad y/o grupos. |
| `GET /api/mail-notifications/events/{event_key}/fields` | Consulta metadatos de campos admitidos. |

«Pública» describe la respuesta sin secretos, no publicación segura en Internet.
Los eventos desconocidos se rechazan; no es posible habilitar otros módulos por API.

### Transporte

Admite `STARTTLS`, `IMPLICIT_TLS` y `NONE`. La última opción requiere
`allow_unencrypted=true`, reconocimiento explícito del uso de un relé local o
confiable. No se supone que el backend pueda determinar qué servidor es confiable.
Se validan servidor sin URL/puerto embebido, puerto entero entre 1 y 65535,
remitente, cabeceras y coherencia de la autenticación.

Métodos: `NONE`, `PASSWORD`, `OAUTH2_DELEGATED`, `OAUTH2_APPLICATION`.
El método `PASSWORD` exige usuario y una contraseña nueva o previamente configurada.
Los perfiles delegados representan Gmail, Google Workspace, Outlook.com y
Microsoft 365; aplicación solo permite Google Workspace y Microsoft 365. **En la etapa 3 eran solo
metadatos.** La autorización y los tokens de la etapa 5 se describen en su guía.

Omitir `smtp_password` conserva la contraseña. Mandar null o una cadena vacía se
rechaza. El borrado exige `clear_password=true` y un método distinto de PASSWORD;
no se permite borrar y reemplazar simultáneamente. Cambiar de método no destruye
por sí solo una contraseña guardada, que permanece inactiva mientras no se use PASSWORD.

La respuesta devuelve `password_configured` y `oauth_credentials_configured`, nunca
las credenciales ni su ciphertext. `configured` solo indica presencia de servidor
y remitente; no certifica conexión, autenticación, plantillas ni disponibilidad de envío.

Las consultas y cambios que no cifran funcionan sin el archivo de claves.
Guardar/reemplazar una contraseña requiere el archivo válido de la
[etapa 2](secrets-v0.6.0.md); si falla, responde 503 saneado y revierte toda la
actualización. Los errores de validación de estas rutas omiten input y contexto
interno que pudieran contener contraseñas. No se registran cuerpos de solicitud.

### Destinatarios

`to`, `cc`, `bcc` son listas de hasta 100 direcciones por grupo. Se validan mediante
`email-validator` sin consultas DNS. Se eliminan duplicados sin distinguir
mayúsculas, conservando orden y primera dirección normalizada. Los grupos son
independientes: no se elimina una dirección de CC porque figure también en Para.
Se admiten listas vacías para preparar la configuración. Desde la etapa 8, el
detalle comprueba que haya destinatarios antes de aceptar una solicitud manual;
el procesador también valida la configuración al preparar cada envío.
No existen destinatarios globales obligatorios.

CCO se consulta en esta sección de configuración. El transporte lo utiliza
en el sobre SMTP sin exponerlo en cabeceras visibles.

## Registro de campos

`src/ticketyn/notifications/fields.py` mantiene una lista permitida con identificador
estable, grupo, etiqueta, formato, temporalidad, atributos reales de origen y clave
de resolución. No evalúa expresiones arbitrarias ni genera valores o mensajes.

- **Activación FMS:** correlativo, fechas, notas, sector, nodo, responsable, tipo de
  servicio, CPE y capacidad inicial histórica.
- **Circuito:** código, descripción, clasificación y datos técnicos actuales;
  capacidad inicial actual del circuito y capacidad actual calculada.
- **Cliente:** nombre y código actuales por la relación del circuito.

Los nombres de sector, nodo y responsable son actuales del catálogo sobre una
referencia histórica. Tipo de servicio, CPE y capacidad de la activación son copias
históricas; no deben completarse con valores actuales cuando falten.

`activation.initial_capacity` usa los campos de Activation.
`circuit.current_capacity` describe la misma regla existente en FMS: último cambio
de capacidad con fecha efectiva no futura, ordenado por fecha e ID descendentes,
o capacidad inicial del circuito si no existe. No se agrega una columna inventada
y se resuelve al generar la vista previa. La configuración CPE literal queda excluida.

## Modalidades y etapas posteriores

Las modalidades `AUTOMATIC`, `MANUAL` y `DISABLED` se guardan por evento.
El [procesador de etapa 6](mail-jobs-v0.6.0.md) aplica:

- Automático → Manual: cancelar trabajos automáticos todavía no iniciados.
- Automático → Desactivado: cancelar pendientes todavía no iniciados.
- SMTP ya iniciado: permitir que termine.

La etapa 6 incorpora esa cancelación y coordinación; la etapa 7 conecta la intención
automática con la creación FMS. Manual y Desactivado no crean solicitudes al registrar.
El editor y la vista previa corresponden a la etapa 4 descrita debajo. Las pruebas
SMTP y OAuth2 se incorporan en la etapa 5. La [etapa 8](mail-jobs-v0.6.0.md#envío-y-reenvío-desde-el-detalle--etapa-8)
permite solicitar envíos y reenvíos desde el detalle de activación, sin editar allí
destinatarios o plantillas y sin confirmar entrega al buzón.

## Validación local

Las pruebas usan claves sintéticas, PostgreSQL descartable y fetch simulado.
Cubren cifrado, respuestas sin secretos, ausencia de claves, destinatarios,
modalidades, campos contra los modelos reales y migración upgrade/downgrade.
Las pruebas de configuración bloquean llamadas SMTP y resolución DNS.
No se aplican migraciones a bases operativas ni se genera frontend/dist en esta etapa.

## Plantillas y vista previa (etapa 4)

`0027_mail_templates` depende de `0026_mail_configuration`. Añade únicamente la
columna JSONB nullable `mail_event_config.template`. Las instalaciones existentes
comienzan sin plantilla; sus modalidades, destinatarios y transporte no cambian.
El downgrade rechaza plantillas con contenido para evitar pérdidas accidentales;
permite revertir cuando están ausentes o vacías. No modifica datos FMS.

API adicional, bajo `/api/mail-notifications/events/{event_key}`:

- `GET /template`: devuelve la plantilla guardada o una estructura vacía.
- `PATCH /template`: reemplaza la plantilla completa, preservando la otra configuración.
- `POST /preview`: recibe `activation_id` y `template`, incluidos cambios no guardados;
  devuelve exclusivamente `subject` y `body`. Una activación inexistente devuelve 404.

La selección de activaciones reutiliza `GET /api/activations?limit=50&offset=...`;
se recorren páginas de 50, sin cargar todo el historial. No requiere claves ni
transporte SMTP configurado. El mismo renderizador lo utiliza el procesador
persistente para las solicitudes automáticas FMS incorporadas en la etapa 7. La
vista previa sigue sin crear solicitudes ni enviar correos. El editor elimina el
aviso de autenticación de la pantalla; el modelo de acceso sigue siendo el descrito
en esta guía.

El formato de plantilla tiene `version: 1`, `subject` y `body`. Cada lista admite
hasta 50 bloques; su orden es el orden de representación. El asunto admite texto
literal (`text`) y campos (`field`). Une los elementos no vacíos con un espacio, normalizando el espacio del asunto
sin agregar etiquetas. Los separadores personalizados (`|`, `-`, `/`, etc.) se
conservan como texto fijo, tanto en bloques propios como junto a otro texto.
Los bloques de texto fijo vacíos son válidos y no añaden separaciones.
El cuerpo admite introducción (`introduction`), campos y firma (`signature`),
con una línea en blanco entre texto y datos. Los campos dinámicos consecutivos
se unen con un solo salto de línea. Los saltos escritos dentro de un texto o dato
se conservan; un bloque de texto compuesto por saltos de línea permite añadir
separaciones explícitas entre campos. Cada campo usa su identificador estable del
registro único; el editor solo muestra grupos y nombres amigables.

En **Notas de activación**, la etiqueta predeterminada o personalizada termina en
dos puntos y el contenido comienza en la línea siguiente, sin añadir una línea
vacía. Se conservan los saltos y espacios originales de las notas. Los demás campos
mantienen `Etiqueta: valor`; las notas vacías se omiten igual que antes. Este formato
es común a la vista previa y al correo generado por el procesador.

Los campos del cuerpo usan **Por defecto** (`DEFAULT`, etiqueta del registro) o
**Personalizado** (`CUSTOM`, etiqueta local a la plantilla, de hasta 100 caracteres).
Al generar el cuerpo, todas las etiquetas Por defecto se muestran en mayúsculas,
conservando acentos y Unicode. Las etiquetas Personalizado mantienen exactamente
su texto. No se transforman los valores, las notas, el asunto, la introducción ni
la firma. La conversión se limita al renderizador compartido: no cambia el registro
de campos ni las plantillas almacenadas, incluidas las existentes que omiten
`label_mode` y utilizan Por defecto implícitamente. El editor conserva los nombres
amigables del selector y muestra el resultado devuelto por ese mismo renderizador.
No se admiten rutas libres, expresiones, HTML ejecutable ni atributos fuera del
registro. El texto fijo es literal, no un lenguaje de programación.

Los textos de introducción/firma admiten hasta 10.000 caracteres por bloque. El
resultado admite hasta 100.000 caracteres de cuerpo y 998 bytes UTF-8 de asunto;
se rechaza una vista previa que exceda esos límites. El transporte futuro deberá
aplicar su propia codificación y plegado de encabezados MIME. El texto fijo del
asunto y las etiquetas rechazan saltos de línea y controles. Si un dato dinámico
multilínea se usa en el asunto, sus saltos y controles se convierten en espacios;
en el cuerpo se conservan los saltos y espacios del dato original.

El renderizador `src/ticketyn/notifications/templates.py` utiliza exclusivamente
`fields.py`. Resuelve datos ausentes como valores vacíos, sin sustituir snapshots por datos
actuales ni mostrar null/None. Omite esos valores al construir el asunto y los
campos sin valor en el cuerpo; también omite bloques de texto vacíos (sin saltos de línea) al generar
el cuerpo. El contenido guardado de los bloques se conserva. Las referencias históricas de sector/nodo/responsable conservan
su relación histórica y muestran el nombre actual del catálogo. Las fechas se
representan en America/Guatemala. La capacidad actual consulta solo el último
cambio efectivo no futuro, con desempate por ID, o la capacidad inicial actual del
circuito cuando no hay cambios. Este fallback es el ya existente en FMS y no se
aplica a la capacidad histórica de activación. Cada campo se resuelve una sola
vez por vista previa; los datos se consultan en un snapshot coherente de lectura.

Las vistas previas no escriben en la base, no actualizan snapshots ni intervenciones,
no crean archivos EML, solicitudes de envío ni contenido generado persistente.
Las plantillas vacías son válidas para preparar la configuración; no implican que
un evento esté listo para enviar. Desde las etapas 6 y 8, el procesador y el
endpoint manual rechazan una plantilla que no produzca asunto ni cuerpo.
