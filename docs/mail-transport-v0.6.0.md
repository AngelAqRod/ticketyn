# Transporte SMTP y OAuth2 — etapa 5 de v0.6.0

## Alcance y acceso

La configuración y las plantillas se conservan en las dos entradas de Administración:
**Configuración de correo** y **Plantillas de correo**. Esta etapa habilita únicamente
el transporte reutilizable, la autorización del proveedor y **Enviar correo de prueba**.
La etapa 5 no conectaba el registro FMS al transporte. Las
[etapas 6 a 8](mail-jobs-v0.6.0.md) incorporan el procesador persistente, el envío manual y la intención
transaccional al crear activaciones en Automático. El envío ocurre fuera de la
transacción FMS; las intervenciones no generan notificaciones. No hay historial de
pruebas ni copias de mensajes.

Ticketyn sigue sin autenticación individual. Cualquier persona con acceso a la API
puede modificar esta configuración y solicitar una prueba. El acceso debe limitarse
mediante red/proxy. La autorización OAuth2 es de una cuenta de correo externa, no
un login a Ticketyn; la cookie temporal solo vincula ese flujo con el navegador.
No se agrega un banner permanente a la interfaz.

## Transporte y mensaje

`notifications/smtp.py` no consulta FMS ni PostgreSQL. Recibe la configuración, las
credenciales descifradas en memoria y un mensaje MIME. Utiliza `smtplib`, TLS con
`ssl.create_default_context()` y timeout de socket de 20 segundos. STARTTLS debe
anunciarse y completarse; luego se repite EHLO. TLS implícito cifra desde la conexión.
No se desactiva la comprobación de certificados/nombre. Los relés sin cifrado
requieren autorización explícita y **no pueden usar contraseña ni OAuth2**.

El constructor valida direcciones y encabezados. Genera texto plano UTF-8 con
From, To, Cc, Subject, Date y Message-ID. CCO solo figura en el sobre SMTP, nunca
en encabezados. Las direcciones de dominio internacional se convierten a IDNA en
el sobre. No incorpora HTML, adjuntos ni datos FMS por iniciativa propia.

El contenido ya renderizado conserva los saltos de línea y la agrupación compacta
establecida en la etapa 4; MIME normaliza finales de línea a CRLF y añade el final
de línea propio del contenido de texto. La prueba no usa plantillas: su asunto y
texto son fijos. No hay endpoint para enviar mensajes arbitrarios.

## Endpoints

Bajo `/api/mail-notifications`:

| Método y ruta | Uso |
|---|---|
| `GET /oauth` | Metadatos, estado e indicadores de credenciales; no secretos. |
| `PATCH /oauth` | Configura aplicación o cuenta de servicio del perfil SMTP guardado. |
| `POST /oauth/authorize` | Inicia Authorization Code con PKCE S256 y state aleatorio. |
| `GET /oauth/callback` | Valida y consume el retorno del proveedor; redirige a configuración. |
| `POST /oauth/disconnect` | Elimina tokens y autorizaciones locales pendientes. |
| `POST /smtp/test` | Prueba con un único `recipient` temporal. |

`PATCH /smtp` y las APIs de eventos/plantillas continúan funcionando. Cambiar
método, proveedor o buzón invalida la configuración y credenciales OAuth2 anteriores.
Cambiar el usuario de una contraseña exige reemplazarla; los cambios de host,
puerto o remitente conservan las credenciales. Los cambios parciales de OAuth2 no
borran un secreto omitido; cambiar el identificador de aplicación exige su nueva
credencial. Reemplazar metadatos/credenciales OAuth2 invalida los tokens anteriores.
Un PATCH vacío conserva la conexión. No se devuelve ciphertext, contraseña,
token, PKCE verifier, JSON de cuenta de servicio ni clave privada.

Estados OAuth2: Sin configurar, Configurado (aplicación), Requiere autorización
(delegado), Autorización en curso, Autorizado y Error de autenticación. «Configurado»
no certifica aceptación SMTP; un token válido tampoco garantiza entrega.

## URL pública, navegador y despliegue

Debe configurarse `MAIL_OAUTH_REDIRECT_URI` con una URL absoluta cuyo path sea
exactamente `/api/mail-notifications/oauth/callback`, sin query, fragmentos ni
credenciales. Fuera de loopback exige HTTPS. No se deriva de Host ni de
X-Forwarded-*. Registrar **exactamente la misma URI** con el proveedor.

En DEV, mediante el proxy `/api` de Vite, por ejemplo:

```dotenv
MAIL_OAUTH_REDIRECT_URI=http://localhost:5173/api/mail-notifications/oauth/callback
```

Abrir la interfaz desde ese mismo origen. No mezclar localhost y 127.0.0.1: la
cookie del navegador debe regresar al mismo host. En producción utilizar el origen
HTTPS real de la instalación, no un dominio supuesto por Ticketyn.

La unidad existente carga `/etc/ticketyn/ticketyn.env`, pero backup/restore solo
aceptan DATABASE_URL en ese archivo. **No añadir allí nuevas variables.** Aprovisionar
la URI mediante un override de systemd con `Environment=MAIL_OAUTH_REDIRECT_URI=...`,
conservando intactos los scripts administrativos. La URI no es un secreto. Respaldar
por separado ese override y la clave como se explica debajo. No se instalan overrides
ni se reinicia ningún servicio automáticamente en esta etapa.

El callback usa state aleatorio de 256 bits y PKCE, además de una cookie HttpOnly,
SameSite=Lax y Secure cuando la URI es HTTPS. State se guarda como hash dentro del
contenedor cifrado, vence a los 10 minutos y se consume transaccionalmente **antes**
del intercambio externo. El callback comprueba parámetros duplicados, longitud,
vinculación con navegador, caducidad y URI; no acepta destinos de retorno libres.
La respuesta final solo contiene `oauth=connected` u `oauth=error`, nunca tokens
ni diagnósticos sensibles del proveedor. Acceso/refresh tokens viajan solo en POST
HTTPS al proveedor y en el contenedor cifrado de PostgreSQL.

Uvicorn omite los accesos al callback para no registrar códigos de autorización.
El Nginx actual puede registrar la query: configurar externamente su access log
para omitirla en esta ruta (o desactivar únicamente el access log del callback),
conservando todas las restricciones y cabeceras del proxy. Aplicar la misma regla
en proxies aguas arriba. No se modifica Nginx desde Ticketyn ni en esta etapa.

## Compatibilidad OAuth2 y preparación externa

### Gmail personal y Google Workspace, delegado

Crear un cliente OAuth de aplicación web en Google Cloud, configurar consentimiento,
usuarios de prueba o publicación según las políticas del proveedor y la URI de
retorno. Guardar identificador y secreto de cliente; el buzón se configura como
Usuario SMTP. Ticketyn pide acceso offline y consentimiento para obtener refresh
token, usa Authorization Code con PKCE y renueva el token al solicitar una prueba
si le quedan menos de 60 segundos. No hay renovación periódica ni reintento de
peticiones fallidas.

SMTP XOAUTH2 requiere `https://mail.google.com/`; `gmail.send` corresponde a Gmail
API y no sustituye ese permiso SMTP. El alcance concedido incluye permisos amplios de lectura y administración del
correo, aunque Ticketyn solo conecta a SMTP y no implementa esas operaciones.
No se añaden otros scopes ni llamadas a Gmail API, IMAP, POP o contactos. La
verificación y restricciones de aplicaciones en modo prueba dependen de Google.
[Documentación SMTP OAuth2](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol),
[flujo web](https://developers.google.com/identity/protocols/oauth2/web-server).

### Google Workspace, aplicación

Solo cuentas de organización. Crear una cuenta de servicio, habilitar delegación
de dominio y autorizar su client ID con `https://mail.google.com/` en Administración
de Workspace. Introducir el JSON de la cuenta de servicio y el buzón que se va a
suplantar como Usuario SMTP. Se retienen cifrados únicamente client_email y la clave
privada RSA (mínimo 2048 bits); no se confía en token_uri ni otros URLs del JSON.
La aserción JWT RS256 usa el endpoint fijo de Google, sub=buzón, iat y exp de una
hora, firmada mediante cryptography. No se crean cuentas ni permisos automáticamente.
[Delegación de dominio](https://developers.google.com/identity/protocols/oauth2/service-account).
No se presenta esta modalidad para Gmail personal.

### Outlook.com y Microsoft 365, delegado

Registrar una aplicación Entra compatible con las cuentas elegidas y la URI web
de retorno. Configurar client ID y secreto. Outlook.com utiliza el tenant
`consumers`; Microsoft 365 requiere el UUID del tenant de la organización. El flujo
solicita `https://outlook.office.com/SMTP.Send` y `offline_access`, con PKCE. Deben
permitirse consentimiento y SMTP AUTH según las políticas externas de la cuenta.
No solicita permisos Graph ni OpenID/User.Read: no es un login de usuarios.

### Microsoft 365, aplicación

Solo organización: configurar tenant, client ID y secreto; obtener consentimiento
administrativo para Exchange Online `SMTP.SendAsApp`, registrar el service principal
en Exchange y autorizar los buzones correspondientes según las instrucciones de
Microsoft. Habilitar SMTP AUTH para el buzón y revisar las políticas del tenant.
El token se solicita con client_credentials y `https://outlook.office365.com/.default`.
No se solicitan permisos IMAP/POP/Graph. La aplicación no ejecuta comandos de
administración del tenant. Microsoft permite distintos mecanismos externos de
asignación a buzones; seguir su guía vigente para la instalación concreta.
[Guía oficial de SMTP OAuth2](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth),
[asignación SMTP con App RBAC](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/smtp-app-rbac-onboarding).
No se ofrece client_credentials para Outlook.com personal. Esta etapa usa secreto
de cliente para Microsoft; no implementa certificados de aplicación Microsoft.

Los proveedores mantienen requisitos propios de consentimiento, licencias y SMTP
AUTH. Que el perfil pueda guardarse no prueba que la administración externa esté
completa. Los tokens rechazados/revocados producen Error de autenticación sin
exponer la respuesta del proveedor. Desconectar elimina tokens locales; **no revoca
el consentimiento externo ni el secreto de la aplicación**. La revocación global se
realiza desde Google/Entra/Exchange sin pedir permisos adicionales a Ticketyn.
Para aplicación, desconectar elimina el token cacheado: una prueba deliberada
posterior puede solicitar otro mientras las credenciales externas sigan vigentes.

## Persistencia, pruebas y recuperación

`0028_mail_transport` depende de `0027_mail_templates`. Añade al singleton existente:

- `oauth_settings`: client ID, tenant y banderas de credenciales; nunca secretos.
- `oauth_status`: estado técnico de conexión.
- `test_not_before`, `test_lease_until`, `test_lease_token`: coordinación temporal.

El contenedor `oauth_credentials_encrypted` de la etapa 3 almacena secretos,
tokens, caducidad y estado OAuth2 pendiente bajo AES-256-GCM con contexto
`mail:transport:1:oauth-credentials`. La vinculación método/proveedor/buzón se
comprueba antes de usarlo. No se requieren nuevas tablas ni mensajes históricos.
La migración conserva transporte, contraseñas, eventos y plantillas. El downgrade
rechaza configuración OAuth2 o pruebas activas para evitar perder datos: desconectar,
cambiar a un perfil sin OAuth2 y esperar a que terminen las pruebas antes de revertir.

Una prueba permite una dirección temporal y contenido fijo. Rechaza body/subject,
servidores o destinatarios adicionales enviados por el cliente. La coordinación es
global para el singleton: una prueba simultánea como máximo, con 30 segundos entre
solicitudes aceptadas y lease de 10 minutos para recuperación tras caída. Se usan
bloqueos de fila y commits, por lo que procesos y pestañas comparten el límite. No
se mantiene bloqueado ningún circuito. SMTP comienza después de liberar el bloqueo
de configuración. Las modificaciones del transporte durante la prueba se rechazan.
La lease se limpia al terminar o caduca tras reinicio; no se reanuda ni repite un envío.
Si falla la limpieza de lease en PostgreSQL, se conserva el resultado SMTP conocido
y el bloqueo vence por tiempo. La dirección temporal no se almacena.

El estado OAuth pendiente sobrevive en el contenedor cifrado. Tras consumir state,
una interrupción durante el intercambio de código requiere nueva autorización,
no un reintento automático. El marcador de intercambio caduca a los 10 minutos;
también puede limpiarse con Desconectar. El refresh se serializa con bloqueo del
singleton y se guarda cifrado; no se reintenta si el proveedor devuelve error.

El resultado de prueba distingue aceptación SMTP, conexión, TLS, autenticación,
rechazo del destinatario/mensaje y resultado incierto. Una desconexión o timeout
durante DATA se clasifica conservadoramente como incierto; no se reintenta. Una
falla de QUIT posterior a la aceptación no cambia el resultado ya conocido. SMTP
aceptado **no garantiza llegada al buzón**. No se promete entrega exactamente una vez.

El dump de PostgreSQL conserva únicamente credenciales cifradas. La clave externa
se respalda/restaura independientemente según [Gestión de secretos](secrets-v0.6.0.md).
Sin la clave correspondiente las consultas sin secretos funcionan, pero no se
pueden descifrar credenciales ni iniciar conexiones que las necesiten. Nunca se
genera una clave sustitutiva automáticamente. Preservar también el override con la
URI pública y las inscripciones externas OAuth2 al recuperar una instalación.
La etapa 5 no modificó los scripts ni systemd. La etapa 6 incorporó la exclusión
del control de autorización del dump y la pausa del correo antes del cutover de
restauración; consulta [recuperación del procesador](mail-jobs-v0.6.0.md#reinicio-y-restauración).
La unidad systemd conserva sus protecciones originales.

Las pruebas automatizadas usan SMTP simulado, endpoints OAuth simulados, claves
sintéticas y PostgreSQL descartable. No usan credenciales reales ni envían a externos.
La aceptación real por cada proveedor y la configuración del proxy requieren una
prueba manual autorizada en DEV; no equivalen a las pruebas automatizadas.
