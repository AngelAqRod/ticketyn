# Ticketyn — Contexto de producto

<!-- impeccable:product-schema 1 -->

## Platform

web

## Identidad y propósito

Ticketyn es un proyecto en desarrollo para gestionar tickets y operaciones técnicas de proveedores de Internet (ISP) y centros de operaciones de red (NOC). Nació como una herramienta sencilla de tickets y evoluciona a partir de necesidades de uso operativo real. No debe presentarse como una plataforma terminada ni como una solución que cubre todas las necesidades de un NOC.

Su propósito es reunir incidencias, información de clientes y circuitos, seguimiento técnico y operaciones FMS para que el personal autorizado pueda registrar, consultar y comprender el trabajo realizado y sus antecedentes.

**«Ticketyn se adapta a tu operación, no tu operación a Ticketyn».** Los catálogos y opciones existentes permiten adaptar aspectos de la operación manteniendo la integridad de los datos. La filosofía no implica que cualquier campo, procedimiento o flujo pueda configurarse libremente.

## Usuarios y trabajos principales

El público principal es el personal técnico que opera y da soporte a redes de ISP y telecomunicaciones. Los roles de seguridad delimitan acciones; no representan una jerarquía obligatoria N1/N2/N3.

| Perfil de acceso | Trabajo y límites |
|---|---|
| Operador | Registrar y seguir incidencias y operaciones autorizadas, consultar y exportar reportes. Control de cambios es de solo lectura y exportación; no tiene Administración. |
| Administrador | Gestionar operaciones, Control de cambios, catálogos y configuración dentro de sus facultades; administrar accesos y sesiones autorizados sin elevar privilegios. |
| Superadministrador | Administrar el sistema, definir roles personalizados y ajustar la retención de auditoría. Siempre debe quedar uno activo. |
| Auditor / Solo lectura | Consultar información operativa y exportaciones autorizadas, sin modificar registros ni acceder automáticamente a Administración o a la auditoría de seguridad. |
| Rol personalizado | Recibir permisos concretos por módulo y acción, incluidos administrativos permitidos. Comienza sin permisos y nunca obtiene facultades exclusivas del Superadministrador. |

Los clientes y proveedores son entidades de la operación. No existe un portal de acceso para clientes dentro del alcance actual.

## Identidad única y terminología

- **Responsables son los Usuarios de Ticketyn.** `Responsible` y `responsibles.id` identifican a cada persona; no existe una segunda tabla de usuarios vinculada 1:1. Las representaciones administrativas de acceso no son otra persona.
- Un Responsable puede existir sin acceso y participar en operaciones; también puede tener acceso sin estar disponible para asignaciones.
- `active` expresa estado operativo; `access_granted` conserva autorización administrativa; `operational_selectable` determina disponibilidad para nuevas asignaciones. Son dimensiones independientes. La baja operativa bloquea el acceso efectivo, pero conserva la autorización previa; reactivar no levanta una suspensión administrativa.
- Retirar disponibilidad excluye nuevas asignaciones, sin borrar referencias históricas ni impedir conservar una asignación existente al editar otros datos. No se elimina físicamente a Responsables en v0.7.0.
- La identidad autenticada y el Responsable seleccionado en una operación son conceptos distintos. No sustituir automáticamente uno por otro.
- **Sectores** son agrupaciones lógicas configurables; no significan exclusivamente zonas geográficas o anillos de fibra. Departamentos, puestos y roles de seguridad tampoco son equivalentes.

## Flujos existentes

1. **Acceso y perfil:** iniciar sesión, cambiar la contraseña temporal cuando corresponde, consultar Mi perfil —incluidos departamento, puesto y rol—, cambiar contraseña y administrar sesiones propias. La navegación y las acciones responden a permisos efectivos.
2. **Tickets de clientes:** relacionar cliente y circuito, registrar incidencia, consultar y editar datos autorizados, agregar seguimiento, escalar apoyo y documentar resolución. El contenido interno y el autorizado para documentos de cliente se distinguen.
3. **Tickets internos:** documentar incidencias de infraestructura con clasificación propia y proveedor opcional; vincular tickets de clientes cuando corresponda. Los vínculos no propagan cierres o estados automáticamente.
4. **Circuitos y FMS:** consultar el circuito y su configuración CPE, registrar activaciones, cambios de capacidad, bajas y reactivaciones. Distinguir capacidad inicial/histórica de capacidad actual. Las notas de activación son opcionales, históricas e inmutables; las correcciones posteriores se documentan mediante intervenciones existentes.
5. **Control de cambios:** planificar y consultar ventanas, calendario y participantes; ejecutar, finalizar, agregar seguimiento y relacionar tickets internos según permisos. El Operador no realiza mutaciones en este módulo.
6. **Consulta y reportería:** usar Dashboard, búsquedas, filtros, detalles y reportes propios de cada módulo. Consulta y exportación son permisos independientes; las capacidades PDF/XLSX dependen de la operación existente.
7. **Correo de activaciones:** configurar transporte, destinatarios y plantillas en Administración. Automático solicita el envío al registrar; Manual requiere acción desde el detalle; Desactivado no permite envío. Envíos y reenvíos usan el motor persistente y la configuración vigente. La vista previa comparte renderizador con el correo HTML/texto plano; no guarda ni envía mensajes.
8. **Administración y auditoría:** gestionar Responsables y acceso en su pantalla única, roles y permisos, sesiones, catálogos y numeraciones autorizados. Consultar eventos de seguridad con filtros y paginación. Solo Superadministrador ajusta la conservación: 365 días iniciales, rango 1–3650, limpieza automática por lotes y sin borrado manual.

## Capacidades y límites que deben preservarse

- El backend aplica autorización granular y denegación por defecto; ocultar controles en React no constituye seguridad. La información contextual de un registro no concede administración de sus catálogos. Los cambios de permisos tienen efecto inmediato en backend.
- Las sesiones son opacas y viven en RAM del backend, con token en `sessionStorage`: treinta minutos de inactividad, cinco sesiones simultáneas y aviso dos minutos antes. Las consultas automáticas no prolongan la sesión. Reiniciar el backend la invalida; el despliegue requiere un único trabajador HTTP.
- Las contraseñas se protegen con Argon2id. No se recuperan contraseñas guardadas; los restablecimientos son temporales e invalidan sesiones. El primer Superadministrador y su recuperación se administran mediante CLI, sin registro público o contraseña fija.
- Las credenciales de correo se cifran; no se muestran descifradas. OAuth2 de correo no es autenticación externa de usuarios de Ticketyn.
- La notificación funcional se limita al registro de activaciones FMS. Las intervenciones y ediciones no solicitan nuevos envíos. No se almacenan mensajes generados ni historial individual de reenvíos. Un resultado SMTP aceptado no confirma entrega; los fallos y resultados inciertos no se reintentan automáticamente.
- La auditoría de seguridad permanece separada de los históricos NOC. No ofrece exportación PDF/XLSX, estadísticas, edición individual, limpieza manual ni configuración de sesiones. No registra contraseñas, hashes o tokens.
- La configuración CPE es texto; no ejecuta comandos en equipos. Ticketyn no es una consola de monitoreo, CRM, ERP o ITSM genérico, ni sustituye inventario o monitoreo especializados. No incorporar portal de clientes, adjuntos, SLA, SSO o MFA por inferencia de este contexto.

## Contexto operativo

Es una aplicación web React/TypeScript con Vite, backend Python/FastAPI, SQLAlchemy, PostgreSQL y Alembic. El desarrollo local documentado utiliza Arch Linux. El despliegue manual utiliza releases bajo `/opt/ticketyn/releases/` y el enlace `/opt/ticketyn/current`; no es un servicio público de registro abierto.

Las fechas operativas se presentan según `America/Guatemala`, sin depender de la zona del navegador. Los datos actuales y los capturados históricamente no son intercambiables. No reconstruir snapshots ausentes con valores actuales. Conservar las reglas específicas ya existentes, incluida la sincronización transaccional del sector de tickets recientes al corregir un circuito, documentada en su guía.

Este contexto describe el trabajo existente de la rama de desarrollo v0.7.0; no declara publicada esa versión ni valida TEST/PRODUCCIÓN. El estado de cada fase y las autorizaciones vigentes se consultan en `AGENT_HANDOFF.md`. La corrección del indicador de versión está implementada: backend y frontend utilizan `[project].version` de `pyproject.toml` como fuente oficial; Vite incorpora la versión al frontend durante la compilación.

## Identidad de marca y comunicación

Conservar el nombre Ticketyn, el lenguaje visual existente Capsule NOC y la identidad Electric Blue del encabezado y sidebar. Estos compromisos no autorizan un rediseño ni fijan aquí tokens, tipografías o componentes nuevos.

La comunicación del producto debe ser profesional, clara y comprensible en español, con terminología técnica consistente y sin exagerar su madurez. Distinguir solicitud de envío, aceptación SMTP y entrega; acceso, estado operativo y disponibilidad; información actual e histórica. No inventar beneficios medidos, clientes, testimonios o fechas de lanzamiento.

## Principios de producto

1. **Responder a la operación real:** ampliar sobre necesidades verificadas y flujos existentes, sin imponer estructuras organizativas innecesarias.
2. **Preservar identidad y trazabilidad:** reutilizar Responsables y relaciones existentes; los cambios de acceso o disponibilidad no reescriben asignaciones históricas.
3. **Seguridad efectiva:** validar permisos e integridad en backend, proteger secretos y mantener las facultades administrativas delimitadas.
4. **Precisión antes que amplitud:** mostrar estados, límites y datos ausentes honestamente; separar capacidades disponibles de trabajo pendiente.
5. **Simplicidad mantenible:** reutilizar componentes y servicios, sin duplicar catálogos, motores, personas o infraestructura.

## Fuentes y precedencia

Este registro deriva de decisiones ya aprobadas y código existente; no introduce decisiones funcionales nuevas ni sustituye las especificaciones:

- [AGENTS.md](AGENTS.md): identidad y restricciones arquitectónicas.
- [Planificación v0.7.0](docs/planificacion-v0.7.0.md) y [acuerdos complementarios](docs/acuerdos-complementarios-v0.7.0.md): los acuerdos posteriores prevalecen en los puntos que modifican.
- [Autorización](docs/security-authorization-v0.7.0.md), [administración](docs/security-administration-v0.7.0.md) y [auditoría implementada](docs/security-audit-v0.7.0.md): contrastadas con modelos, permisos, rutas, perfil y mantenimiento actuales. El diseño y la guía de fase 4 recogen la aprobación posterior del rango 1–3650 y la implementación de ambos hitos.
- [Módulos](docs/modules.md), [sincronización de sectores](docs/recent-ticket-sector-sync-v0.5.0.md), [notificaciones](docs/mail-jobs-v0.6.0.md) y [despliegue](docs/deployment.md): relaciones y reglas operativas pertinentes.
- Código de contraste: `src/ticketyn/models/responsible.py`, `security/permissions.py`, `security/retention.py`, `api/activation_notifications.py`, `notifications/templates.py`, y `frontend/src/App.tsx`, `components/moduleIdentity.ts`, `pages/Profile.tsx`. Las rutas Python abreviadas son relativas a `src/ticketyn/`.

**Desactualizaciones conocidas:** README y guías generales todavía mencionan ausencia de autenticación y versión 0.5.0; la guía de fase 3 conserva DEV en 0031 y no enumera Departamento en el perfil. El handoff registra 0032 y el código incorpora Departamento. Algunos encabezados de planificación siguen diciendo que fase 4 espera autorización, y el maestro contempla una eliminación de Responsables que los acuerdos posteriores excluyen. No tomar esos pasajes como decisiones vigentes ni corregirlos automáticamente desde una tarea de diseño. `pyproject.toml` declara 0.7.0; las pruebas de versionado y el build de producción finalizaron correctamente.
