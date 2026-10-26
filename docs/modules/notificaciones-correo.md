# Ficha Técnica: Notificaciones y Correo

## Responsabilidad del módulo
- **Qué gestiona:** La infraestructura de generación, renderizado, encolado y despacho de correos electrónicos automáticos originados por eventos operativos del sistema.
- **Funcionalidades existentes:**
  - Configuración del transporte de correo mediante SMTP tradicional (servidor, puerto, TLS/STARTTLS y autenticación) o integración OAuth2 para Microsoft 365 y Google Workspace.
  - Flujo de autorización interactiva OAuth2 con generación de `code_challenge` (PKCE) y callback seguro.
  - Prueba interactiva de transporte SMTP para diagnóstico en vivo.
  - Editor visual de plantillas con soporte dual para formato HTML enriquecido y texto plano, con vista previa y sustitución de variables contextuales.
  - Configuración de eventos operativos disparadores (ej. alta de circuito en FMS) con destinatarios y asunto parametrizables.
  - Cola persistente de entrega asíncrona (`MailNotificationRequest`) con contador de reintentos, registro de bitácora y control administrativo de pausa/reanudación del procesador (`MailProcessorControl`).
- **Qué no le corresponde:** No es un agente de transferencia de correo completo (MTA tipo Postfix/Exim), no implementa buzones entrantes para convertir correos en tickets (IMAP/POP3) ni envía boletines masivos comerciales.

## Reglas de negocio críticas
- **Encolado persistente y procesamiento asíncrono:**
  - Toda notificación generada por una acción operativa (ej. activación en FMS) se persiste en la tabla `mail_notification_requests`.
  - El envío físico lo ejecuta un procesador desacoplado en segundo plano; jamás debe bloquearse la solicitud HTTP principal de la operación ni depender el éxito de la transacción de base de datos de la respuesta del servidor de correo.
- **Obligatoriedad del formato dual:**
  - Toda plantilla debe conservar sincronizadas su variante en HTML y su variante en texto plano (`plain_text`) para clientes de correo sin soporte HTML.
- **Seguridad en autorización OAuth2:**
  - El callback OAuth2 exige una sesión administrativa activa del Superadministrador, cotejo de cookie técnica de sesión efímera, coincidencia de `state` y verificación PKCE.
  - Un reinicio del proceso backend invalida cualquier flujo OAuth2 en curso. La cookie técnica OAuth2 no autentica sesiones normales de Ticketyn.
- **Pausa y contingencia operativa:**
  - El procesador de cola puede pausarse mediante `MailProcessorControl.is_paused`. Al estar pausado, las peticiones entrantes continúan acumulándose en estado `pending` sin descartarse, quedando disponibles para su entrega inmediata al reanudar.
- **Confidencialidad de credenciales y aislamiento de gestión:**
  - Las contraseñas SMTP y secretos de cliente OAuth2 se almacenan de forma protegida y jamás se devuelven en texto claro en respuestas API de consulta.
- **Identidad visual Technical Split — Opción 3 (v0.8.0):**
  - **Cabecera dividida:** Encabezado blanco con barra vertical Electric Blue (`#1768D5`) en el extremo izquierdo y línea divisoria inferior gris clara (`#E2E8F0`).
    - *Lado izquierdo:* Identidad tipográfica `Ticketyn` en azul (`#1768D5`) y subtítulo `NOTIFICACIÓN OPERATIVA` en gris discreto.
    - *Lado derecho:* Etiqueta temática del evento (ej. `FMS · ACTIVACIÓN` con acento `#047857` y fondo `#ECFDF5`), correlativo dinámico destacado (`#0F172A`), y descripción breve del evento (`#64748B`).
  - **Cuerpo en dos columnas:** Presentación balanceada al 50% de ancho por columna sin tarjetas individuales ni bordes por celda. Etiqueta discreta superior en gris (`#64748B`) y valor inferior en azul oscuro (`#0F172A`).
  - **Emparejamiento y orden estricto:** Los campos consecutivos se agrupan por parejas respetando rigurosamente el orden de la plantilla; los campos impares ocupan el 50% con celda vacía técnica (`ticketyn-empty`). Los bloques narrativos (`introduction`, `signature`) y notas técnicas ocupan el ancho completo (100%).
  - **Secciones visuales identificadas:**
    - `Información de activación`: Acento verde/esmeralda (`#047857`).
    - `Información técnica de distribución`: Acento cian/azul técnico (`#0284C7`), visible únicamente cuando la plantilla contiene campos de distribución o IP CPE.
    - `Notas técnicas de activación`: Acento verde/esmeralda (`#047857`) en bloque contenedor gris azulado claro (`#F2F6FC`) con barra izquierda esmeralda (`3px solid #047857`).
  - **Pie institucional minimalista:** `Ticketyn · Gestión operativa` en contenedor tenue `#F8FAFC`.
  - **Compatibilidad con clientes de correo:** Tablas de presentación HTML con estilos inline, ancho máximo de 640px, comentarios condicionales MSO para Outlook, y media queries para apilamiento vertical en móviles (`max-width: 480px`). Sin CSS Grid, Flexbox, JavaScript ni recursos remotos.
- **Catálogo cerrado de variables semánticas de plantillas (v0.8.0):**
  - **Equipo de distribución (`activation.distribution_device`, HISTORICAL):** Obtiene el nombre histórico del equipo guardado en la activación. Muestra «No asignado» si la activación se creó sin equipo asignado, o «No registrado» si es una activación legacy anterior a v0.8.0. Nunca consulta el circuito vivo para sustituir datos históricos desconocidos.
  - **Puerto de distribución (`activation.distribution_port`, HISTORICAL):** Mismo comportamiento histórico que el equipo de distribución («No asignado» si no tiene puerto, «No registrado» en registros legacy).
  - **IP de gestión CPE (`circuit.cpe_management_ip`, CURRENT):** Muestra la IP normalizada (IPv4 sin espacios, IPv6 comprimida bajo RFC 5952) del circuito asociado al momento del renderizado/envío. Si el circuito no tiene IP asignada o está vacía, muestra «No asignada».
  - **Notas de activación (`activation.activation_notes`, HISTORICAL):** Texto de notas registradas en la activación. Si está vacío o nulo, resuelve a «Sin notas registradas».
  - **Compatibilidad histórica de plantillas:** Plantillas persistidas en versiones previas continúan renderizándose y cargándose sin migraciones ni alteraciones destructivas.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`mail_notifications.py`, `mail_transport.py`, `mail_jobs.py`), motor central en `src/ticketyn/notifications/` (`smtp.py`, `oauth.py`, `fields.py`, `templates.py`, `processor.py`, `delivery.py`, `html.py`, `requests.py`), modelos en `src/ticketyn/models/` (`mail_notifications.py`, `mail_jobs.py`), esquemas en `src/ticketyn/schemas/` (`mail_notifications.py`, `mail_templates.py`, `mail_transport.py`).
- **Componentes frontend:** Vistas en `frontend/src/pages/MailNotifications.tsx`, componentes en `frontend/src/components/` (`MailTemplateEditor.tsx`, `MailTransportControls.tsx`).
- **Dependencias:** Operaciones FMS (disparador de eventos), Servidores SMTP externos o Proveedores OAuth2 (Google/Microsoft) y Capa de Seguridad (RBAC).
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad

- Hotfix propuesto v0.9.1: Nginx registra método/ruta sin argumentos, estado, bytes y duración; omite query strings y Referer. Los errores de la ubicación exacta del callback se descartan para evitar URLs completas, conservando access log seguro. El proxy y el filtro Uvicorn existentes se mantienen. Proxies externos requieren aplicar la misma política; ver `../security-hotfix-v0.9.1.md`.
- **Endpoints clave:** `GET/PUT /api/mail/transport`, `POST /api/mail/transport/test`, `GET/PUT /api/mail/templates`, `GET/POST /api/mail/oauth/authorize`, `GET/PUT /api/mail/processor/control`, `GET /api/mail/events`, `GET /api/mail-notifications/events/{event_key}/fields`, `GET/PATCH /api/mail-notifications/events/{event_key}/template`, `POST /api/mail-notifications/events/{event_key}/preview`.
- **Permisos requeridos:** `mail.transport.view`, `mail.transport.edit`, `mail.transport.test`, `mail.oauth.view`, `mail.oauth.edit`, `mail.oauth.authorize`, `mail.events.view`, `mail.events.edit`, `mail.templates.view`, `mail.templates.edit`, `mail.templates.preview`, `mail.processor.view`, `mail.processor.control`.
- **Regla de dependencia:** `mail.oauth.view` exige obligatoriamente `mail.transport.view`. Los roles Operador y Auditor no disponen de acceso a este módulo.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_mail_template_variables_v080.py tests/test_mail_templates.py tests/test_mail_notifications.py tests/test_activation_notifications.py tests/test_activation_manual_notifications.py tests/test_mail_html.py tests/test_mail_jobs.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/MailNotifications.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Comprobar que el endpoint de prueba SMTP no sobreescriba la configuración guardada si no se guardan los cambios explícitamente.
  - Asegurar que la cola gestione reintentos con retraso progresivo y que los fallos definitivos se registren en la bitácora sin arrojar excepciones no capturadas.
  - Proteger estrictamente que `cpe_configuration` jamás sea accesible ni inyectable en plantillas.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en el motor de despacho, adición de nuevos disparadores de eventos operativos o modificaciones en las integraciones OAuth2 de Microsoft o Google.
