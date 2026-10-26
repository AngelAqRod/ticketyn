# Mi perfil — Electric Blue 2.0 + LCD Operator Identity

## Alcance

Implementación en `features/v0.9.0`; sin cambiar la versión oficial del proyecto. La identidad única continúa en `Responsible` / `responsibles`. No se crea catálogo de usuarios paralelo, fotografías, almacenamiento de avatares ni módulo Mis tickets.

La pantalla sigue `DESIGN.md`: superficies NOC oscuras, bordes de 12 px, controles compartidos y Electric Blue como acento. Sustituye el banner de degradado azul y las tarjetas claras de la primera implementación. Cabecera compacta con LCD, nombre, usuario, puesto operativo, rol de seguridad y acceso efectivo; contenido de ancho máximo 1120 px. Datos personales y preferencias comparten una superficie, Seguridad conserva el formulario visible en tres columnas cuando hay espacio y una columna en anchos reducidos. Los estilos se acotan al perfil y al avatar/menú de usuario; no se modifican tokens globales ni otros módulos.

## LCD auténtico de 14 segmentos

`frontend/src/components/LcdOperatorAvatar.tsx` define **14 polígonos geométricos independientes por carácter**, seis exteriores, centro dividido, cuatro diagonales y dos verticales centrales. Siempre dibuja 28 segmentos para dos caracteres, diferenciando activos cian e inactivos tenues sobre fondo oscuro. No utiliza texto SVG ni una fuente de imitación.

El mapa contiene A–Z, 0–9 y `?`; letras como M, N, K, X o I utilizan segmentos interiores específicos. NFKD normaliza acentos y Ñ. Para nombres de varios componentes usa la primera inicial y la del último componente. Si no hay dos palabras, toma los dos primeros caracteres alfanuméricos del usuario; si este tampoco alcanza, utiliza los disponibles del nombre y rellena con `?`. Sin información representa `??`, conservando una etiqueta accesible legible.

Variantes `large` para el perfil y `compact` para `UserControls`. Las iniciales derivan directamente de props: no solicitan datos al backend ni necesitan persistencia. Los contadores de siete segmentos no se modifican.

## Identidad y datos personales

El contrato previo de Mi perfil era de lectura y cambio de contraseña; no existía edición personal autorizada. Continúa de solo lectura para nombre, usuario, departamento, puesto, rol y estado. No se crea una excepción para editar esos campos desde el perfil.

No existe correo personal en Responsible; no se inventa un campo ni se usa el correo de clientes. La modificación de identidad/asignaciones sigue exclusivamente en la administración autorizada de Responsables. Las preferencias rechazan campos adicionales mediante `extra='forbid'`; PATCH genérico de `/api/auth/profile` sigue sin estar autorizado. No se muestran hashes, tokens, identificadores internos o secretos.

El cambio de nombre recibido en la identidad autenticada actualiza el avatar del encabezado sin peticiones adicionales para dibujarlo. El perfil vuelve a consultar sus datos cuando cambia la identidad relevante (persona, nombre/usuario o revisión del rol), además de su consulta inicial y reintento explícito.

## Seguridad y sesiones

Se reutilizan `PasswordChangeForm` y `SessionsPanel`, sin cambiar su implementación ni sus contratos:

- Contraseña actual, nueva y confirmación; misma validación de 1–4096 bytes UTF-8 y Argon2id del backend. No se añaden requisitos de complejidad/caducidad.
- Error accesible, bloqueo de doble envío y conservación de campos ajenos al formulario.
- Cambio correcto cierra las demás sesiones mediante el mecanismo previo; no genera logins para comprobarlo.
- Sesiones propias en RAM, identificación de la actual, consulta y revocación autorizada. Sin Redis ni persistencia de sesiones.

## Preferencias persistentes

Única ampliación de datos: `responsibles.preferred_home_page`, VARCHAR(20), NOT NULL, predeterminado `DASHBOARD`, CHECK de valores `DASHBOARD` y `MY_TICKETS`. El segundo valor reserva el contrato futuro, pero **la API rechaza seleccionarlo mientras no exista el módulo**.

- `GET /api/auth/profile` añade `preferences: {home_page: ...}` al contrato de perfil propio. El catálogo operativo de Responsables no añade este dato.
- Nuevo `PATCH /api/auth/profile/preferences`, autenticado y de autoservicio, cuerpo estricto `{ "home_page": "DASHBOARD" }`. No acepta ID de destino ni datos personales/administrativos. Un parámetro de otro Responsable no cambia la identidad objetivo: siempre proviene de la sesión autenticada.
- Valida cuenta vigente bajo `lock_security` y bloqueo de fila; guarda solo la preferencia del propietario. No modifica revisión de acceso, rol, puesto, credenciales, actividad ni sesiones.
- No se crean permisos nuevos. Usuarios sin permisos operativos también conservan su perfil propio.
- Formulario con Dashboard / Inicio y Mis tickets deshabilitado con «Próximamente». Guardar utiliza el endpoint real, muestra éxito/error y evita doble envío.

No se cambia el enrutamiento autorizado existente: Dashboard sigue siendo el inicio cuando tiene permiso; usuarios sin él mantienen el primer destino autorizado o el perfil. Nunca se navega a Mis tickets. Cuando se implemente ese módulo será necesario habilitar su elección y resolución de ruta respetando permisos; no rehacer el almacenamiento de la preferencia.

## Mi actividad y encabezado

Mi actividad se reduce a un único aviso sobre la futura integración de Mis tickets, **sin cuatro accesos deshabilitados, enlaces, botones operativos, contadores ni consultas**. No duplica el Dashboard ni crea listas de tickets personales.

`UserControls` conserva nombre, Mi perfil y Cerrar sesión en su zona actual y añade el LCD compacto. En tablet y móvil (hasta 1023 px) utiliza el disclosure existente de usuario en esa misma zona, con acciones reales, foco visible, cierre con Escape/devolución de foco y cierre al pulsar fuera. No cambia sidebar ni la ubicación de la API. La etiqueta de versión puede elidirse si falta espacio, conservando el título completo del indicador existente.

## Migración

`0041_profile_preferences` → `0040_escalation_recommend_ack` → `0039_device_templates`. Aditiva, agrega exclusivamente preferencia y CHECK en responsibles; los registros previos empiezan con Dashboard. No modifica migraciones anteriores ni identidades/históricos.

Upgrade/downgrade/upgrade probado en PostgreSQL efímero con datos de Responsable preexistentes, verificando que nombre, usuario, hash, estado e identidad quedan intactos. La reversión elimina únicamente la preferencia y su restricción: ese ajuste personal se pierde si se revierte. **No aplicada a DEV persistente, TEST ni PROD**. Debe aplicarse con autorización antes de ejecutar el código contra una base persistente.

## Archivos y comprobaciones

- UI: `pages/Profile.tsx`, `components/LcdOperatorAvatar.tsx`, `components/UserControls.tsx`, `styles/operatorProfile.css`.
- Backend: `models/responsible.py`, `api/security_accounts.py`, inventario `security/routes.py` y migración `0041`.
- Pruebas: `tests/test_profile_preferences.py`, `frontend/src/components/LcdOperatorAvatar.test.tsx`, `frontend/src/pages/Profile.test.tsx`; regresiones de administración, autenticación y Layout.
- Refinamiento visual validado con componentes reales y fixtures ficticios en Firefox headless a 1920, 1366, 768 y 390 px. Capturas `/tmp/ticketyn-profile-refined-{1920,1366,768,390}.png`; mediciones JSON con el mismo prefijo y ancho. Sin desbordamiento horizontal de página ni controles; la tabla de sesiones conserva scroll interno. No se usan sesiones ni bases reales.
- Pruebas enfocadas del refinamiento: Profile, LcdOperatorAvatar/UserControls, SecurityAdministration, Layout y AuthGate: 63 aprobadas en 5 archivos. TypeScript y `git diff --check` correctos. No se repitieron pruebas backend por tratarse de una corrección de presentación.
- La composición se adapta al ancho disponible del perfil mediante una consulta de contenedor a 700 px, incluyendo cuando el sidebar reduce el espacio en tablet. Se conserva geometría/mapa del LCD; solo se ajustan dimensiones del avatar en el perfil.
- Resultados finales y alcance exacto en `AGENT_HANDOFF.md`.

No hay builds, commits, despliegues, cambios SMTP/PDF, migraciones persistentes ni modificaciones del trabajo paralelo de plantillas, distribución, FMS, recomendaciones/ACK o catálogos de puestos.
