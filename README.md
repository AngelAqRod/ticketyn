# Ticketyn

Ticketyn es un proyecto para gestionar tickets y operaciones
técnicas en proveedores de Internet (ISP) y centros de operaciones de red (NOC).
Nació como una herramienta sencilla de tickets y crece a partir de necesidades
que aparecen durante su uso.

## Estado del proyecto

Está **en desarrollo**. Algunas funcionalidades se utilizan en un entorno
operativo real, pero eso no significa que sea una plataforma terminada ni que
cubra todas las necesidades de un NOC. La versión declarada en este repositorio
es **0.7.0**, según `[project].version` en [pyproject.toml](pyproject.toml).
Este README describe lo implementado en `development/v0.7.0`, sin implicar que
la versión ya esté publicada o desplegada. Revisa y valida cada versión antes
de incorporarla a tu entorno.

## Filosofía

**«Ticketyn se adapta a tu operación, no tu operación a Ticketyn».**

La intención es organizar información operativa sin imponer jerarquías,
procedimientos o flujos innecesarios. Los catálogos y opciones administrativas
permiten adaptar aspectos del trabajo desde la aplicación, manteniendo reglas
de integridad. Esta es también una dirección del proyecto: no toda configuración
imaginable está implementada.

## Qué busca resolver

Concentrar el registro y seguimiento de incidencias, las relaciones entre clientes
y circuitos y el historial de operaciones técnicas, para facilitar su consulta
y análisis sin depender de registros dispersos.

Ticketyn se centra en la operación. No pretende ser un CRM, un ERP ni sustituir
herramientas especializadas como NetBox o Zabbix.

## Funcionalidades disponibles

- Tickets de clientes: creación, edición, seguimiento, escalamientos, resolución
  y documentos internos o destinados al cliente con contenido autorizado separado.
- Tickets internos de infraestructura, con proveedores, clasificación propia
  y vínculos opcionales con tickets de clientes.
- Clientes, circuitos y operaciones FMS: activaciones, cambios de capacidad,
  bajas y reactivaciones; consulta de configuración CPE.
- Notificaciones por correo para el registro de activaciones FMS: modo Automático
  al crear la activación, Manual desde su detalle y Desactivado sin envíos.
  Incluyen reenvío manual, destinatarios configurados y plantillas con vista previa,
  HTML y texto plano. La aceptación por SMTP no garantiza la entrega al buzón.
- Control de cambios: planificación, ejecución, calendario, participantes,
  seguimiento, evaluación de duraciones y vínculos con tickets internos.
- Dashboard, reportería, filtros y exportaciones según las capacidades de cada módulo.
- Catálogos administrables y numeraciones independientes configurables.
- Inicio de sesión, Mi perfil y cambio de contraseña. Los Responsables son los
  usuarios de Ticketyn: su acceso y disponibilidad para asignaciones se gestionan
  de forma independiente, sin duplicar personas ni alterar sus históricos.
- Roles predeterminados y personalizados, con permisos granulares aplicados en
  el backend para consultas, operaciones, exportaciones y administración.
- Administración de sesiones propias y ajenas según permisos; auditoría de
  seguridad con filtros, paginación y limpieza automática según la retención
  configurada por el Superadministrador.

Consulta el [alcance y las reglas de los módulos](docs/modules.md).

## Flexibilidad y límites actuales

Los sectores son agrupaciones lógicas configurables; no representan necesariamente
zonas geográficas ni anillos de fibra. Los departamentos, responsables y demás
catálogos no obligan a adoptar una estructura N1/N2/N3.

La autenticación y los permisos individuales no sustituyen los controles de
seguridad del entorno. El proyecto sigue en desarrollo: requiere HTTPS, controles
de red y acceso, y una configuración segura antes de cualquier exposición a Internet.
Las sesiones se mantienen en memoria del backend; el despliegue requiere un único
trabajador HTTP y reiniciarlo cierra las sesiones activas.

No hay portal de clientes, adjuntos ni un motor de SLA. La configuración disponible
no permite definir arbitrariamente nuevos campos o flujos de trabajo.

## Tecnologías

Backend Python con FastAPI, SQLAlchemy, PostgreSQL y Alembic. Frontend React y
TypeScript con Vite, Tailwind y Recharts. PDF mediante ReportLab y Excel mediante
openpyxl. La interfaz utiliza el lenguaje visual Capsule NOC.

## Instalación y documentación

- [Instalación y administración](docs/deployment.md): requisitos, actualización,
  copias de seguridad y recuperación.
- [Desarrollo local](docs/development.md): preparación, pruebas y compilación.
- [Arquitectura](docs/architecture.md): componentes, relaciones y decisiones principales.
- [Módulos](docs/modules.md): funcionamiento disponible y guías especializadas.
- [Responsables, acceso y sesiones](docs/security-administration-v0.7.0.md),
  [roles y permisos](docs/security-authorization-v0.7.0.md) y
  [auditoría de seguridad](docs/security-audit-v0.7.0.md).
- [Notificaciones FMS](docs/mail-jobs-v0.6.0.md): modalidades, solicitudes y reenvíos.
- [Historial de cambios](CHANGELOG.md): notas de evolución; las entradas antiguas
  describen su momento y no sustituyen las guías actuales.

## Licencia

GNU Affero General Public License v3, **AGPL-3.0-only**.
Consulta el texto completo en [LICENSE](LICENSE).
