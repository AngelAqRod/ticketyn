# Auditoría de notificaciones v0.6.0 — etapa 9

Auditoría realizada en DEV el 19 de octubre de 2026, sobre el trabajo acumulado
de las etapas 1–8, todavía sin publicar. No equivale a una certificación de seguridad
ni autoriza la publicación. Se conservan versión, rama, migraciones históricas,
configuraciones reales y datos operativos. No se generan builds ni mensajes externos.

## Diagnóstico y correcciones

No se identificó un defecto crítico confirmado en la revisión y los escenarios
automatizados ejercitados. La ausencia de autenticación es una decisión de alcance,
no una autorización para exponer Ticketyn a Internet.

| Severidad | Archivo o componente | Riesgo y reproducción | Corrección o tratamiento | Verificación |
|---|---|---|---|---|
| Medio — corregido | `notifications/smtp.py` | En Python 3.11, construir SMTP sin host y llamar después a `connect()` deja `_host` vacío; STARTTLS y TLS implícito no tienen el nombre de servidor necesario para verificar TLS/SNI. Arch/Python 3.14 no reproducía esta diferencia. | Conservar el host antes de conectar, sin relajar TLS ni cambiar el cierre explícito de conexiones. | Emulación de `connect()` de Python 3.11 en ambos modos, con hostname obligatorio. No sustituye ejecutar toda la aplicación en cada versión de Python. |
| Medio — corregido | `notifications/smtp.py` | Respuesta 454 al comando STARTTLS se presentaba como error de conexión en lugar de TLS. | Clasificar el rechazo como `TLS_ERROR`; no autenticar, enviar ni reintentar. | SMTP simulado con rechazo 454; cierre de conexión y error sin secretos. |
| Bajo — corregido | `MailTransportControls.tsx` | Después de AUTH_ERROR, guardar credenciales o desconectar mantenía el error anterior por encima del estado OAuth2 actual. También podía quedar un resultado de prueba de un perfil SMTP anterior. | Limpiar el resultado al actualizar configuración/credenciales y descartar respuestas tardías de pruebas de otra configuración. | Guardado, desconexión, actualización del transporte y respuestas tardías ACCEPTED/AUTH_ERROR. |
| Bajo — corregido | `MailNotifications.tsx` y guías de correo | Dos textos afirmaban que crear una activación aún no solicitaba envíos; algunas guías describían capacidades actuales como futuras. | Explicar Automático, Manual y Desactivado; distinguir el alcance histórico de cada etapa del funcionamiento actual. | Prueba de mensajes vigentes y revisión de enlaces/documentación. |
| Alto — riesgo de despliegue | APIs SMTP/OAuth2, eventos, procesador y reenvíos | Cualquier persona con acceso puede cambiar destinatarios, detener/reanudar el procesador o solicitar envíos. Cambiar el servidor SMTP conservando una credencial también permite usarla contra el servidor elegido, que podría capturarla al autenticar. El cifrado en reposo no evita ese uso. | Mantener el modelo aprobado, sin inventar autorización. Restringir acceso por red/proxy y el acceso del servicio a destinos SMTP autorizados mediante infraestructura. | Contratos sin secretos y sin envío de contenido arbitrario; la eficacia de los controles de red debe comprobarse en la instalación concreta. |
| Alto — riesgo de despliegue | Nginx/proxies y callback OAuth2 | La plantilla de Nginx no excluye la query del callback del access log. Un código OAuth2 puede aparecer allí o como Referer si un proxy sustituye la política de la respuesta. | Mantener el filtro de Uvicorn y documentar sanitización/omisión de query y Referer en todos los proxies; conservar `Referrer-Policy: no-referrer` del callback. No modificar automáticamente infraestructura. | Prueba del filtro Uvicorn y callback; revisión manual de la configuración efectiva de logs antes de habilitar OAuth2. |
| Medio — límite operativo | Restore externo a `backup.sh`/`restore.sh` | Un dump externo que incluya autorización, restaurado sobre el mismo OID, no se distingue de un reinicio normal por esos datos. PENDING pudo enviarse después de tomar un backup. | Usar el procedimiento soportado, detener Ticketyn, marcar pausa/cuarentena y revisar pendientes antes de reanudar. No prometer deduplicación de restauraciones externas. | Dump/restore PostgreSQL reales, exclusión de control, hook de pausa, cuarentena y pruebas de fallos antes del cutover. |
| Mejora futura fuera de alcance | Secretos, proveedores y transporte | No hay rotación completa/recifrado; OAuth2 depende de permisos y políticas externas. El timeout SMTP de 20 s es por socket, no un plazo total del mensaje; la reserva de transporte vence a los 10 min. | Conservar los límites actuales documentados. Revisar un plazo total si se admiten servidores lentos o volúmenes elevados; un intercambio que exceda la reserva puede solaparse con una prueba SMTP explícita. Validar cada proveedor con autorización aparte. | Claves sintéticas, OAuth2/SMTP simulados y concurrencia PostgreSQL. No se certifica integración real con Google/Microsoft durante esta auditoría. |

La diferencia de `connect()` se contrastó con el
[código oficial de CPython 3.11](https://github.com/python/cpython/blob/3.11/Lib/smtplib.py).
La compatibilidad mantiene el peer utilizado internamente por `smtplib` sin introducir
criptografía, conexiones o bibliotecas alternativas.

## Integridad, coordinación y recuperación verificadas

- La creación FMS obtiene ID mediante flush y registra la intención automática antes
  del mismo commit. Un fallo de persistencia revierte activación, numeración y
  asignaciones; un fallo SMTP posterior no modifica la operación.
- Solo `fms.activation.created` está habilitado. Consultas, intervenciones y otras
  operaciones FMS no solicitan correo. Notas históricas e inmutables, sin edición nueva.
- Restricción UNIQUE por evento/activación; fila reutilizable y revisión observada.
  PENDING/PREPARING/SENDING bloquean la acción manual. UNCERTAIN exige confirmación.
- Advisory lock de sesión, conexión AUTOCOMMIT, selección con SKIP LOCKED y sesiones
  independientes. No hay transacción FMS ni transacción de trabajos abierta durante SMTP.
- PREPARING interrumpido vuelve a PENDING sin posibilidad de SMTP; SENDING interrumpido
  pasa a UNCERTAIN. FAILED, PARTIAL y UNCERTAIN no se reenvían automáticamente.
- Se añaden pruebas para caída después de aceptación SMTP, persistencia indisponible,
  terminación real de la conexión PostgreSQL del worker y parada durante preparación.
  No se necesita cambiar la arquitectura del procesador para esos casos.
- Los estados y mensajes distinguen solicitar, aceptar por SMTP y entregar al buzón.
  No hay garantía de entrega exactamente una vez, ni historial individual o mensajes almacenados.

## Credenciales, plantillas y superficie de acceso

AES-256-GCM usa clave de 256 bits, nonce aleatorio de 96 bits, autenticación de
versión/identificador/contexto y límites de tamaño. La lectura comprueba permisos,
propietario, ACL, tipos de archivo y enlaces. No se regenera una clave ausente.
Las API públicas de configuración nunca devuelven contraseña, token, ciphertext ni
clave privada; los errores de validación omiten entradas crudas. Las pruebas usan
solo material sintético. No se leyeron ni rotaron claves reales.

SMTP verifica certificados y nombres; STARTTLS no se degrada, y sin cifrado no se
admiten credenciales. CCO queda fuera de las cabeceras. Las plantillas usan una
lista permitida de campos, sin expresiones ejecutables. Se mantienen mayúsculas
Unicode solo para etiquetas predeterminadas, etiquetas personalizadas literales,
notas multilínea, orden y separación aprobados. Preview, MIME y worker comparten
el renderizador, sin persistir su resultado.

OAuth2 mantiene state, PKCE, cookie de vinculación y consumo del callback previo al
intercambio. Tokens y claves privadas se cifran; los endpoints de proveedor son
fijos y el tenant se valida. Renovar un token es una operación externa: si el
proveedor rota un refresh token y falla después su persistencia, puede ser necesaria
una nueva autorización. Desconectar localmente no revoca el consentimiento externo.

La red restringida no equivale a autorización individual ni protección completa
frente a un navegador comprometido. Las rutas POST sin cuerpo, como pausa o
desconexión, tampoco son una frontera contra solicitudes desde sitios externos.
Revisar los controles de origen y acceso del proxy según el despliegue; no se
agregan sesiones, roles, banners ni middleware de autorización en esta etapa.

## Migraciones, backup y restore

La cadena es lineal:
`0024_default_change_types_upper → 0025_activation_notes → 0026_mail_configuration
→ 0027_mail_templates → 0028_mail_transport → 0029_mail_requests`.
No se crean ni modifican migraciones en la etapa 9. Los downgrades que perderían
notas, configuración, tokens, plantillas o solicitudes se rechazan con datos presentes.

El backup conserva ciphertext pero no las claves externas ni la autorización para
procesar correo. Restore pausa el staging y convierte trabajos iniciados en
UNCERTAIN antes del cutover. Los fallos preservan DB anterior y artefactos de
recuperación; no se hace rollback destructivo automático. La clave requiere una
copia independiente, permisos correctos y comprobación de correspondencia con los
secretos cifrados. Recuperarla no autoriza reanudar el procesador.

Referencias operativas: [claves](secrets-v0.6.0.md),
[transporte y OAuth2](mail-transport-v0.6.0.md),
[configuración y plantillas](mail-configuration-v0.6.0.md),
[trabajos, pausa y reanudación](mail-jobs-v0.6.0.md).

## Validación

Comandos: `.venv/bin/pytest -q --tb=short`, `npm test` desde `frontend/`,
`npx tsc --noEmit`, `git diff --check` y `alembic heads/history`.
Las pruebas PostgreSQL crean sus propios clústeres y bases, sin leer la conexión
operativa. Backup/restore se ejercitan con dobles controlados y bases descartables.
SMTP/OAuth2 utilizan mocks; no se envían mensajes externos.

La ejecución inicial de frontend dentro del sandbox tuvo errores EPERM al crear
subprocesos Node de zonas horarias y un fallo transitorio de espera en NewTicket.
Al repetir la suite completa con permisos de ejecución, pasaron las 638 pruebas
anteriores, sin modificar Tickets ni sus expectativas. Las regresiones nuevas
reprodujeron los defectos antes de aplicar las correcciones.

La primera suite backend completa pasó sus **1.929 pruebas**. La pasada final,
con todas las correcciones cargadas y los ocho casos nuevos, pasó **1.937 pruebas
en 597,40 segundos**, sin fallos. Los casos nuevos son tres SMTP y cinco del
procesador. El entorno backend utilizado fue Python 3.14.8; la diferencia de
`connect()` de Python 3.11 se reproduce con un doble controlado, no con otra instalación.

| Comprobación final | Resultado |
|---|---|
| Backend completo | 1.937 correctas; una advertencia preexistente Starlette/httpx. |
| Frontend completo | 644 correctas en 57 archivos; seis regresiones nuevas. |
| TypeScript | `npx tsc --noEmit`, sin errores. |
| Migraciones | Un HEAD `0029_mail_requests`; dependencias 0025–0029 válidas. Upgrade/downgrade y rechazo de pérdida de datos cubiertos en PostgreSQL descartable. |
| Recuperación | Dump/restore reales, pausa/cuarentena, recuperación de claves, revisión/reanudación y fallos parciales cubiertos en la suite completa. |
| Scripts y documentación | `bash -n backup.sh restore.sh`, enlaces locales y `git diff --check`, correctos. También se revisó whitespace de los archivos no rastreados modificados en esta etapa. |
| Exclusiones | Sin build ni cambios en dist, migraciones, Nginx, systemd o scripts administrativos durante la etapa 9. Sin commits, tags, releases, despliegues ni cambios operativos. |

La advertencia Starlette/httpx ya existía; no se sustituyen dependencias en esta etapa.

Archivos intervenidos en esta etapa: `src/ticketyn/notifications/smtp.py`,
`frontend/src/components/MailTransportControls.tsx`,
`frontend/src/pages/MailNotifications.tsx`, sus tres archivos de pruebas
(`tests/test_mail_transport.py`, `MailTransportControls.test.tsx`,
`MailNotifications.test.tsx`), `tests/test_mail_jobs.py`, esta auditoría y las guías
`mail-configuration-v0.6.0.md`, `mail-transport-v0.6.0.md` y `secrets-v0.6.0.md`.
El resto del trabajo acumulado de las etapas 1–8 se conserva.

## Condiciones antes de producción

1. Verificar acceso de red/proxy y destinos SMTP permitidos; no exponer administración,
   pruebas, callbacks y reenvíos a usuarios o sitios no confiables.
2. Verificar que logs de proxy no retengan códigos OAuth2 ni Referer del callback.
3. Comprobar la copia independiente de claves y ensayar recuperación con el procesador
   pausado, revisando incluso los PENDING antes de autorizar la reanudación.
4. Validar manualmente en DEV cada perfil OAuth2 que se vaya a utilizar. Las pruebas
   reales Gmail con contraseña de aplicación fueron comunicadas por el operador;
   no se repitieron ni se utilizaron credenciales reales durante la auditoría.
5. Reservar para la validación de release el build y la prueba visual en navegador.
   No se ejecutan en esta etapa ni se modifica `frontend/dist/`.
