# Ticketyn

Ticketyn es un proyecto para gestionar tickets y operaciones
técnicas en proveedores de Internet (ISP) y centros de operaciones de red (NOC).
Nació como una herramienta sencilla de tickets y crece a partir de necesidades
que aparecen durante su uso.

## Estado del proyecto

Está **en desarrollo**. Algunas funcionalidades se utilizan en un entorno
operativo real, pero eso no significa que sea una plataforma terminada ni que
cubra todas las necesidades de un NOC. La versión declarada en este repositorio
es **0.5.0**; revisa y valida cada versión antes de incorporarla a tu entorno.

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
- Control de cambios: planificación, ejecución, calendario, participantes,
  seguimiento, evaluación de duraciones y vínculos con tickets internos.
- Dashboard, reportería, filtros y exportaciones según las capacidades de cada módulo.
- Catálogos administrables y numeraciones independientes configurables.

Consulta el [alcance y las reglas de los módulos](docs/modules.md).

## Flexibilidad y límites actuales

Los sectores son agrupaciones lógicas configurables; no representan necesariamente
zonas geográficas ni anillos de fibra. Los departamentos, responsables y demás
catálogos no obligan a adoptar una estructura N1/N2/N3.

**Actualmente no hay autenticación ni autorización individual.** La aplicación
está pensada para un entorno interno de confianza, protegido mediante controles
externos de acceso. No debe exponerse directamente a Internet. Una VPN, firewall
o proxy no equivale a permisos por usuario dentro del backend.

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
- [Historial de cambios](CHANGELOG.md): notas de evolución; las entradas antiguas
  describen su momento y no sustituyen las guías actuales.

## Licencia

GNU Affero General Public License v3, **AGPL-3.0-only**.
Consulta el texto completo en [LICENSE](LICENSE).
