# Arquitectura de Ticketyn

Esta guía describe la implementación actual del sistema (v0.7.0+).
El [README](../README.md) presenta el proyecto y el [Mapa del Sistema](SYSTEM_MAP.md) indexa los archivos de cada dominio.

## Componentes

- `src/ticketyn/main.py` integra FastAPI, middleware de sesión y rutas de la API.
- `src/ticketyn/security/` gestiona autenticación (Argon2id), sesiones opacas en memoria RAM (`SecurityMemory`), autorización por ruta (`SafeAuthRoute`), matriz de permisos y auditoría de seguridad.
- `src/ticketyn/notifications/` implementa el subsistema de correo: plantillas HTML/texto, transporte SMTP/OAuth2 (Google/Microsoft) y procesamiento de cola en segundo plano (`mail_jobs`).
- `src/ticketyn/api/` contiene endpoints, validaciones operativas, coordinación transaccional y exportaciones.
- `src/ticketyn/models/` define entidades SQLAlchemy; `schemas/` define contratos Pydantic; `core/` y `db/` configuran el entorno y las sesiones de base de datos.
- `alembic/` conserva la evolución incremental del esquema PostgreSQL.
- `frontend/src/` contiene la SPA en React 18, TypeScript, Tailwind CSS y Vite. React Router gestiona la navegación bajo el control de acceso de `auth/AuthGate.tsx`. Recharts representa estadísticas.
- ReportLab y openpyxl generan documentos PDF y hojas Excel directamente en el backend.

En producción, Nginx sirve `frontend/dist/` y canaliza `/api/` y `/health` a Uvicorn local. En desarrollo, Vite proporciona el frontend y el proxy hacia el backend.
PostgreSQL es el único motor de base de datos soportado; no hay alternativa SQLite.

## Configuración y transacciones

`DATABASE_URL` es obligatoria y utiliza `postgresql+psycopg`. El entorno tiene prioridad sobre `.env`, localizado respecto al directorio de trabajo. La aplicación no crea tablas ni aplica migraciones al arrancar.

Las operaciones coordinan sus escrituras dentro de transacciones de base de datos. La numeración utiliza configuraciones independientes, bloqueo transaccional (`SELECT ... FOR UPDATE`) y referencias únicas almacenadas. La vista previa no consume números y cambiar la configuración no reescribe referencias anteriores.

Las mutaciones de seguridad (roles, asignación de cuentas, restablecimiento de contraseñas y retención) se ejecutan bajo bloqueo de seguridad explícito (`lock_security(session)`).

## Relaciones principales

| Entidad | Relación y criterio principal |
|---|---|
| Responsables y Usuarios | `responsibles` representa la identidad única de personas y usuarios. Tres estados independientes: `active` (operativo), `access_granted` (autorización de acceso) y `operational_selectable` (disponible en selectores operativos). |
| Roles y permisos | Catálogo cerrado en `security/permissions.py`. Roles predeterminados: Superadministrador, Administrador, Operador y Auditor, más roles personalizados. Denegación predeterminada (403) en backend. |
| Cliente y circuito | Un cliente tiene varios circuitos; el ticket de cliente se vincula con un circuito de ese cliente. |
| Sector y nodo | Catálogos independientes. Sector es una agrupación lógica configurable; no hay relación directa que permita filtrar todos los nodos por sector. |
| Ticket de cliente | Conserva clasificación y tiempos propios; puede vincularse opcionalmente con un ticket interno. |
| Ticket interno | No tiene cliente ni circuito propios. Puede reunir varios tickets de clientes; sus estados y seguimientos son independientes. |
| Operaciones FMS | Activaciones, capacidad y bajas/reactivaciones se relacionan con circuitos y conservan información técnica histórica. |
| Cambio | Planificación de ventanas de mantenimiento con encargado, apoyo y seguimiento; relación opcional con múltiples tickets internos. |
| Notificaciones | Disparadas por eventos operativos (ej. activaciones); utilizan perfiles SMTP/OAuth2 y cola persistente. |
| Catálogos | Clasifican y permiten nuevas asignaciones activas, conservando referencias históricas a registros desactivados. |

Los catálogos de tipos de incidencia de clientes e internos son diferentes. Proveedores corresponde a tickets internos. Los tipos de cambio y de finalización clasifican el trabajo y su resultado, respectivamente.

## Datos actuales e históricos

El sector y nodo almacenados en un ticket no se recalculan al consultarlo desde el circuito actual. Existe una excepción deliberada: al cambiar el sector del circuito se sincronizan sus tickets creados en las últimas 168 horas, incluidos los cerrados, únicamente cuando su sector difiere. La corrección y su entrada interna de bitácora son transaccionales. Los tickets anteriores permanecen intactos. Véase la [regla de sincronización reciente](recent-ticket-sector-sync-v0.5.0.md).

Las activaciones conservan datos técnicos capturados al registrarse (tipo de servicio, capacidad inicial y CPE). Los valores históricos ausentes se presentan como «Sin registrar», sin reconstruirlos silenciosamente desde el circuito.

Control de cambios conserva departamento y nombres de participantes históricos, así como la elegibilidad para eficiencia del tipo de finalización al finalizar. Modificar el catálogo no cambia retroactivamente esa elegibilidad. Los cambios anteriores al catálogo de tipos de cambio pueden conservar clasificación nula.

No existen cierres automáticos entre tickets vinculados ni entre cambios y tickets internos. La fecha de creación se distingue de las fechas operativas manuales. Las conversiones operativas utilizan `America/Guatemala`; la interfaz no debe reinterpretarlas según la zona horaria del navegador.

## Seguridad, sesiones y trazabilidad

El sistema incorpora autenticación y control de acceso basado en roles (RBAC) granular:

- **Sesiones en memoria:** Los tokens de sesión son opacos y se validan en memoria RAM (`SecurityMemory`). No existen tablas de sesiones en base de datos ni caché Redis. La aplicación debe ejecutarse con **un único proceso trabajador** (`--workers 1`).
- **Contraseñas:** Almacenadas con hash Argon2id seguro.
- **Autorización backend:** Implementada en `security/routes.py` y `security/permissions.py`. Toda ruta requiere una sesión activa salvo excepciones públicas explícitas (`/health`, `/api/auth/login`, callback OAuth2). Denegación por defecto (403) ante rutas o permisos no inventariados.
- **Protección del Superadministrador:** No es posible eliminar, desactivar ni retirar facultades al último Superadministrador activo del sistema.
- **Auditoría de seguridad:** Registro persistente en `security_audit` de inicios de sesión, cambios de permisos, cuentas y configuraciones. Política configurable de retención de registros de auditoría entre 1 y 3650 días.
- **Configuración CPE:** Texto plano técnico; no ejecuta comandos ni constituye una bóveda cifrada de credenciales ni sincronización con routers/switches.
- **Límites:** No existe portal público de clientes, autorregistro ni segundo factor de autenticación (MFA).

## Lecturas complementarias

- [Mapa técnico del sistema](SYSTEM_MAP.md).
- [Módulos y reglas funcionales](modules.md).
- [Seguridad y autorización](security-authorization-v0.7.0.md).
- [Administración de seguridad y cuentas](security-administration-v0.7.0.md).
- [Auditoría de seguridad](security-audit-v0.7.0.md).
- [Transporte de correo y notificaciones](mail-transport-v0.6.0.md).
- [Instalación y despliegue](deployment.md).
