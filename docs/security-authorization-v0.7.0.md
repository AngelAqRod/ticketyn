# Seguridad v0.7.0 — Fase 2: roles y permisos

Esta guía describe la autorización implementada sobre la base de la [Fase 1](security-foundation-v0.7.0.md). Sustituye su política provisional exclusiva de Superadministrador. Los documentos funcionales maestros se conservan sin cambios. No constituye una publicación ni autoriza despliegues de fases incompletas.

## Aplicación y límites

El backend mantiene un inventario cerrado por método y ruta en `security/routes.py`. Una sesión válida no concede acceso por sí sola. Las rutas nuevas sin regla se rechazan, incluso para el Superadministrador; además, al construir la aplicación se verifica la cobertura de los contratos OpenAPI. La política se evalúa con los permisos vigentes de PostgreSQL en cada solicitud, usando una sesión independiente de la operación.

Los roles predeterminados tienen definición fija explícita en `security/permissions.py`. No se usan comodines para conceder módulos futuros a Administrador, Operador, Auditor ni roles personalizados. Los personalizados comienzan vacíos y reciben asignaciones independientes persistidas. Las facultades exclusivas se descartan incluso ante una asignación inválida introducida directamente en base de datos.

La consulta y exportación son independientes. La creación, modificación y acciones especiales requieren consulta de su módulo. Configuración CPE requiere consulta de circuitos; OAuth2 requiere consulta del transporte porque sus controles utilizan el perfil SMTP guardado. El catálogo de permisos publica estas dependencias. Quitar una consulta elimina las acciones dependientes; seleccionar una acción nueva incorpora sus requisitos.

### Acciones combinadas

- PATCH de tickets distingue edición de datos, cambio de estado y vínculos internos. Cerrar/reabrir requiere `close`; un permiso de cierre sin edición solo puede cambiar estado, fin y resolución.
- PATCH de Control de cambios permite edición, ejecución y vínculos por separado. Estado, fechas reales y tipo de finalización requieren `execute`; participantes y planificación requieren `edit`; relaciones requieren `link`. Las notas finales pueden modificarse con edición o ejecución. La comparación se realiza contra el registro bloqueado y antes de persistir.
- Corregir el sector de un circuito requiere además `tickets.edit`, porque la operación existente sincroniza tickets recientes. Cambiar su estado requiere el permiso de baja/reactivación correspondiente, además de edición del circuito.
- La baja operativa de un Responsable con cuenta también requiere autoridad sobre accesos. Editar su nombre, departamento o puesto no concede esa autoridad. Los esquemas operativos no aceptan credenciales, roles ni permisos.

### Contexto operativo

Se reutilizan los POST existentes para la creación rápida de clientes, circuitos y nodos: permiso específico `context.*.create`, limitado a registros activos. No permite editar/desactivar ni administrar el catálogo, no depende de Referer ni de un encabezado enviado por React. Clientes y circuitos conservan además su CRUD operativo habitual para el Operador.

Los permisos de módulos y reportes derivan únicamente lecturas de los selectores utilizados por sus formularios y filtros. Esos permisos `lookup` no habilitan páginas de Administración. Los GET reutilizados para vincular tickets internos devuelven solo id, correlativo y título cuando no existe permiso de consulta del módulo. Sin facultades de vinculación, la consulta individual exige una relación real con un ticket de cliente o un cambio del módulo autorizado; no basta conocer un identificador. Intervenciones, historial, exportes y ficha completa siguen protegidos. La ficha de circuito oculta la activación inicial sin permiso de activaciones. La consulta de eventos utilizada por el editor de plantillas oculta destinatarios sin `mail.events.view`.

## Contratos de roles

Todos requieren sesión con contraseña definitiva. Solo Superadministrador crea, modifica, elimina o duplica definiciones.

| Método y ruta | Comportamiento |
|---|---|
| GET `/api/security/permissions` | Vocabulario, módulos, dependencias y exclusividad. |
| GET `/api/security/roles` | Roles paginados; un administrador de cuentas solo ve roles dentro de sus facultades. |
| GET `/api/security/roles/{id}` | Definición y permisos; misma restricción de visibilidad. |
| POST `/api/security/roles` | Nombre y descripción opcional; inicia sin permisos. |
| PATCH `/api/security/roles/{id}` | Nombre, descripción y/o lista completa de permisos. |
| POST `/api/security/roles/{id}/duplicate` | Copia independiente; prohibida para Superadministrador y Administrador. |
| DELETE `/api/security/roles/{id}` | Solo personalizado sin Responsables asignados, incluso inactivos. |

Los roles predeterminados son inmutables. Nombres únicos sin distinguir mayúsculas, también para acentos Unicode. La auditoría de cambios de roles es obligatoria y transaccional; si falla, se revierte la modificación. Cambiar una definición genera un evento del rol, no un evento por cada persona afectada.

Las funciones internas de asignación, suspensión y restablecimiento verifican autoridad sobre la cuenta. Administrador y personalizados con `accounts.manage` no pueden administrarse a sí mismos, modificar Superadministradores/Administradores ni cuentas con capacidades equivalentes o superiores. La comparación usa conjuntos de capacidades, sin imponer jerarquías por nombres entre personalizados. El último Superadministrador activo sigue protegido con el bloqueo transaccional de la Fase 1.

Errores: 401 por sesión ausente o inválida; 403 por falta de permiso; 404 por registro inexistente; 409 por nombre duplicado, rol asignado o protección del último Superadministrador; 422 por estructura, permiso desconocido o facultad exclusiva; 503 si no se puede comprobar el acceso.

## React y sesiones

`GET /api/auth/me` y la respuesta de login incluyen rol, identificador, revisión y lista efectiva de permisos. React comprueba al navegar, al recuperar foco y cada 15 segundos, sin renovar actividad. Los cambios se anuncian y se retiran las acciones/rutas no autorizadas. La navegación, formularios, vínculos, exportaciones y secciones administrativas utilizan el mismo vocabulario. La protección definitiva permanece en el backend.

Una expiración no convierte un 403 en 401. Se mantienen las sesiones opacas en RAM, el único trabajador HTTP, las revisiones persistentes de acceso, los límites y la advertencia de inactividad de la Fase 1. El callback OAuth2 conserva cookie técnica, state y PKCE, y vuelve a comprobar `mail.oauth.authorize` en la sesión iniciadora vigente; no es un endpoint público anónimo.

## Migración y revisión

Nueva revisión `0031_role_permissions`, dependiente de `0030_security_foundation`. Registra el vocabulario explícito y refuerza la unicidad Unicode de nombres de roles; no modifica datos operativos, credenciales, plantillas, solicitudes de correo ni históricos. El downgrade restaura el índice previo y conserva permisos/asignaciones existentes: no se destruye configuración de acceso al volver a la base de la Fase 1. No es un procedimiento de rollback de producción.

No se modifican las migraciones históricas. Las validaciones usan PostgreSQL descartable. El acceso de red/HTTPS y el único trabajador siguen siendo requisitos operativos.

## Pendiente de fases posteriores

La administración visual de Responsables, acceso, roles, sesiones y Mi perfil se describe en la [Fase 3](security-administration-v0.7.0.md). Auditoría consultable/exportable, retención y configuración de seguridad pertenecen a la Fase 4. Solo Superadministrador puede recibir `roles.manage`, `security.configure`, `audit.export` y `audit.clean`.

La corrección del indicador de versión, validación del despliegue sin ventana anónima, build y revisión de dist permanecen en la Fase 5. No se prepara una publicación con esta fase.

## Archivos de la fase

- Nuevos: `security/permissions.py`, `security/routes.py`, `security/roles.py`, `security/mutations.py`, `api/security_roles.py`, `alembic/versions/0031_role_permissions.py`, `frontend/src/auth/permissions.tsx`, `frontend/src/auth/permissions.test.tsx`, `frontend/src/test/render.tsx`, `tests/test_security_authorization.py` y esta guía. Las rutas Python son relativas a `src/ticketyn/`.
- Integración backend: `security/http.py`, `security/service.py`, `api/auth.py`, `main.py`, `models/security.py`, y los endpoints de tickets, tickets internos, clientes, circuitos, nodos, FMS, Control de cambios y notificaciones. Los contratos operativos conservan sus datos; las respuestas contextuales reducidas se describen arriba.
- Integración React existente: `AuthGate`, `Layout`, controles operativos y administrativos, formularios, exportaciones y vistas de reportería. No se agregan pantallas de administración de cuentas o roles ni se rediseña la interfaz.
- Pruebas: autorización directa, copia y dependencias de roles, auditoría transaccional, actualizaciones inmediatas, acciones combinadas, contexto y concurrencia PostgreSQL; adaptación de regresiones de rutas y de la fixture de renderizado. Los tests operativos de componentes declaran permisos completos mediante una fixture explícita; las pruebas de seguridad utilizan el proveedor real con permisos específicos y verifican denegaciones.

La migración `0031` ya fue aplicada y verificada en DEV por el propietario. La nueva revisión `0032` de la Fase 3 permanece pendiente de autorización y aplicación; las pruebas automatizadas solo usan bases descartables.

## Matriz efectiva

Leyenda: SA = Superadministrador; A = Administrador; O = Operador; L = Auditor / Solo lectura. Se muestran concesiones explícitas; las lecturas contextuales derivadas están descritas arriba. Los personalizados solo reciben permisos seleccionados y sus requisitos, nunca exclusivos.

| Permiso | SA | A | O | L | Requisitos | Exclusivo |
|---|---|---|---|---|---|---|
| `dashboard.view` | Sí | Sí | Sí | Sí | — | — |
| `tickets.view` | Sí | Sí | Sí | Sí | — | — |
| `tickets.create` | Sí | Sí | Sí | — | `tickets.view` | — |
| `tickets.edit` | Sí | Sí | Sí | — | `tickets.view` | — |
| `tickets.close` | Sí | Sí | Sí | — | `tickets.view` | — |
| `tickets.escalate` | Sí | Sí | Sí | — | `tickets.view` | — |
| `tickets.followup` | Sí | Sí | Sí | — | `tickets.view` | — |
| `tickets.export` | Sí | Sí | Sí | Sí | — | — |
| `tickets.link` | Sí | Sí | Sí | — | `tickets.view` | — |
| `internal_tickets.view` | Sí | Sí | Sí | Sí | — | — |
| `internal_tickets.create` | Sí | Sí | Sí | — | `internal_tickets.view` | — |
| `internal_tickets.edit` | Sí | Sí | Sí | — | `internal_tickets.view` | — |
| `internal_tickets.close` | Sí | Sí | Sí | — | `internal_tickets.view` | — |
| `internal_tickets.escalate` | Sí | Sí | Sí | — | `internal_tickets.view` | — |
| `internal_tickets.followup` | Sí | Sí | Sí | — | `internal_tickets.view` | — |
| `internal_tickets.export` | Sí | Sí | Sí | Sí | — | — |
| `changes.view` | Sí | Sí | Sí | Sí | — | — |
| `changes.create` | Sí | Sí | — | — | `changes.view` | — |
| `changes.edit` | Sí | Sí | — | — | `changes.view` | — |
| `changes.execute` | Sí | Sí | — | — | `changes.view` | — |
| `changes.link` | Sí | Sí | — | — | `changes.view` | — |
| `changes.followup` | Sí | Sí | — | — | `changes.view` | — |
| `changes.export` | Sí | Sí | Sí | Sí | — | — |
| `customers.view` | Sí | Sí | Sí | Sí | — | — |
| `customers.create` | Sí | Sí | Sí | — | `customers.view` | — |
| `customers.edit` | Sí | Sí | Sí | — | `customers.view` | — |
| `customers.delete` | Sí | Sí | Sí | — | `customers.view` | — |
| `customers.lookup` | Sí | Sí | Sí | Sí | — | — |
| `circuits.view` | Sí | Sí | Sí | Sí | — | — |
| `circuits.create` | Sí | Sí | Sí | — | `circuits.view` | — |
| `circuits.edit` | Sí | Sí | Sí | — | `circuits.view` | — |
| `circuits.delete` | Sí | Sí | Sí | — | `circuits.view` | — |
| `circuits.lookup` | Sí | Sí | Sí | Sí | — | — |
| `activations.view` | Sí | Sí | Sí | Sí | — | — |
| `activations.create` | Sí | Sí | Sí | — | `activations.view` | — |
| `activations.followup` | Sí | Sí | Sí | — | `activations.view` | — |
| `activations.notify` | Sí | Sí | Sí | — | `activations.view` | — |
| `activations.export` | Sí | Sí | Sí | Sí | — | — |
| `capacity_changes.view` | Sí | Sí | Sí | Sí | — | — |
| `capacity_changes.execute` | Sí | Sí | Sí | — | `capacity_changes.view` | — |
| `capacity_changes.export` | Sí | Sí | Sí | Sí | — | — |
| `lifecycle.view` | Sí | Sí | Sí | Sí | — | — |
| `lifecycle.deactivate` | Sí | Sí | Sí | — | `lifecycle.view` | — |
| `lifecycle.reactivate` | Sí | Sí | Sí | — | `lifecycle.view` | — |
| `lifecycle.export` | Sí | Sí | Sí | Sí | — | — |
| `cpe.view` | Sí | Sí | Sí | Sí | `circuits.view` | — |
| `cpe.edit` | Sí | Sí | Sí | — | `cpe.view` | — |
| `catalogs.sectors.view` | Sí | Sí | — | — | — | — |
| `catalogs.sectors.create` | Sí | Sí | — | — | `catalogs.sectors.view` | — |
| `catalogs.sectors.edit` | Sí | Sí | — | — | `catalogs.sectors.view` | — |
| `catalogs.sectors.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.departments.view` | Sí | Sí | — | — | — | — |
| `catalogs.departments.create` | Sí | Sí | — | — | `catalogs.departments.view` | — |
| `catalogs.departments.edit` | Sí | Sí | — | — | `catalogs.departments.view` | — |
| `catalogs.departments.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.incident_types.view` | Sí | Sí | — | — | — | — |
| `catalogs.incident_types.create` | Sí | Sí | — | — | `catalogs.incident_types.view` | — |
| `catalogs.incident_types.edit` | Sí | Sí | — | — | `catalogs.incident_types.view` | — |
| `catalogs.incident_types.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.nodes.view` | Sí | Sí | — | — | — | — |
| `catalogs.nodes.create` | Sí | Sí | — | — | `catalogs.nodes.view` | — |
| `catalogs.nodes.edit` | Sí | Sí | — | — | `catalogs.nodes.view` | — |
| `catalogs.nodes.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.responsibles.view` | Sí | Sí | — | — | — | — |
| `catalogs.responsibles.create` | Sí | Sí | — | — | `catalogs.responsibles.view` | — |
| `catalogs.responsibles.edit` | Sí | Sí | — | — | `catalogs.responsibles.view` | — |
| `catalogs.responsibles.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.positions.view` | Sí | Sí | — | — | — | — |
| `catalogs.positions.create` | Sí | Sí | — | — | `catalogs.positions.view` | — |
| `catalogs.positions.edit` | Sí | Sí | — | — | `catalogs.positions.view` | — |
| `catalogs.positions.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.escalation_reasons.view` | Sí | Sí | — | — | — | — |
| `catalogs.escalation_reasons.create` | Sí | Sí | — | — | `catalogs.escalation_reasons.view` | — |
| `catalogs.escalation_reasons.edit` | Sí | Sí | — | — | `catalogs.escalation_reasons.view` | — |
| `catalogs.escalation_reasons.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.service_types.view` | Sí | Sí | — | — | — | — |
| `catalogs.service_types.create` | Sí | Sí | — | — | `catalogs.service_types.view` | — |
| `catalogs.service_types.edit` | Sí | Sí | — | — | `catalogs.service_types.view` | — |
| `catalogs.service_types.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.deactivation_reasons.view` | Sí | Sí | — | — | — | — |
| `catalogs.deactivation_reasons.create` | Sí | Sí | — | — | `catalogs.deactivation_reasons.view` | — |
| `catalogs.deactivation_reasons.edit` | Sí | Sí | — | — | `catalogs.deactivation_reasons.view` | — |
| `catalogs.deactivation_reasons.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.cpe_models.view` | Sí | Sí | — | — | — | — |
| `catalogs.cpe_models.create` | Sí | Sí | — | — | `catalogs.cpe_models.view` | — |
| `catalogs.cpe_models.edit` | Sí | Sí | — | — | `catalogs.cpe_models.view` | — |
| `catalogs.cpe_models.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.internal_incident_types.view` | Sí | Sí | — | — | — | — |
| `catalogs.internal_incident_types.create` | Sí | Sí | — | — | `catalogs.internal_incident_types.view` | — |
| `catalogs.internal_incident_types.edit` | Sí | Sí | — | — | `catalogs.internal_incident_types.view` | — |
| `catalogs.internal_incident_types.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.providers.view` | Sí | Sí | — | — | — | — |
| `catalogs.providers.create` | Sí | Sí | — | — | `catalogs.providers.view` | — |
| `catalogs.providers.edit` | Sí | Sí | — | — | `catalogs.providers.view` | — |
| `catalogs.providers.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.change_completion_types.view` | Sí | Sí | — | — | — | — |
| `catalogs.change_completion_types.create` | Sí | Sí | — | — | `catalogs.change_completion_types.view` | — |
| `catalogs.change_completion_types.edit` | Sí | Sí | — | — | `catalogs.change_completion_types.view` | — |
| `catalogs.change_completion_types.lookup` | Sí | Sí | Sí | Sí | — | — |
| `catalogs.change_types.view` | Sí | Sí | — | — | — | — |
| `catalogs.change_types.create` | Sí | Sí | — | — | `catalogs.change_types.view` | — |
| `catalogs.change_types.edit` | Sí | Sí | — | — | `catalogs.change_types.view` | — |
| `catalogs.change_types.lookup` | Sí | Sí | Sí | Sí | — | — |
| `reports.tickets.view` | Sí | Sí | Sí | Sí | — | — |
| `reports.tickets.export` | Sí | Sí | Sí | Sí | — | — |
| `reports.internal_tickets.view` | Sí | Sí | Sí | Sí | — | — |
| `reports.internal_tickets.export` | Sí | Sí | Sí | Sí | — | — |
| `reports.changes.view` | Sí | Sí | Sí | Sí | — | — |
| `reports.changes.export` | Sí | Sí | Sí | Sí | — | — |
| `reports.activations.view` | Sí | Sí | Sí | Sí | — | — |
| `reports.activations.export` | Sí | Sí | Sí | Sí | — | — |
| `reports.capacity_changes.view` | Sí | Sí | Sí | Sí | — | — |
| `reports.capacity_changes.export` | Sí | Sí | Sí | Sí | — | — |
| `reports.lifecycle.view` | Sí | Sí | Sí | Sí | — | — |
| `reports.lifecycle.export` | Sí | Sí | Sí | Sí | — | — |
| `reports.escalations.view` | Sí | Sí | Sí | Sí | — | — |
| `settings.ticket_number.view` | Sí | Sí | — | — | — | — |
| `settings.ticket_number.edit` | Sí | Sí | — | — | `settings.ticket_number.view` | — |
| `settings.internal_ticket_number.view` | Sí | Sí | — | — | — | — |
| `settings.internal_ticket_number.edit` | Sí | Sí | — | — | `settings.internal_ticket_number.view` | — |
| `settings.activation_number.view` | Sí | Sí | — | — | — | — |
| `settings.activation_number.edit` | Sí | Sí | — | — | `settings.activation_number.view` | — |
| `settings.change_number.view` | Sí | Sí | — | — | — | — |
| `settings.change_number.edit` | Sí | Sí | — | — | `settings.change_number.view` | — |
| `mail.transport.view` | Sí | Sí | — | — | — | — |
| `mail.transport.edit` | Sí | Sí | — | — | `mail.transport.view` | — |
| `mail.transport.test` | Sí | Sí | — | — | `mail.transport.view` | — |
| `mail.oauth.view` | Sí | Sí | — | — | `mail.transport.view` | — |
| `mail.oauth.edit` | Sí | Sí | — | — | `mail.oauth.view` | — |
| `mail.oauth.authorize` | Sí | Sí | — | — | `mail.oauth.view` | — |
| `mail.events.view` | Sí | Sí | — | — | — | — |
| `mail.events.edit` | Sí | Sí | — | — | `mail.events.view` | — |
| `mail.templates.view` | Sí | Sí | — | — | — | — |
| `mail.templates.edit` | Sí | Sí | — | — | `mail.templates.view` | — |
| `mail.templates.preview` | Sí | Sí | — | — | `mail.templates.view` | — |
| `mail.processor.view` | Sí | Sí | — | — | — | — |
| `mail.processor.control` | Sí | Sí | — | — | `mail.processor.view` | — |
| `context.customers.create` | Sí | Sí | Sí | — | `customers.lookup` | — |
| `context.circuits.create` | Sí | Sí | Sí | — | `circuits.lookup` | — |
| `context.nodes.create` | Sí | Sí | Sí | — | `catalogs.nodes.lookup` | — |
| `roles.manage` | Sí | — | — | — | — | Sí |
| `accounts.manage` | Sí | Sí | — | — | — | — |
| `sessions.manage` | Sí | Sí | — | — | — | — |
| `security.configure` | Sí | — | — | — | — | Sí |
| `audit.view` | Sí | Sí | — | — | — | — |
| `audit.export` | Sí | — | — | — | — | Sí |
| `audit.clean` | Sí | — | — | — | `audit.view` | Sí |

## Inventario de endpoints protegidos

Cada fila corresponde a una regla explícita. Las condiciones de campos combinados se aplican además de esta frontera.

| Método | Ruta | Permiso o excepción |
|---|---|---|
| GET | `/health` | Público: salud/login |
| HEAD | `/health` | Público: salud/login |
| POST | `/api/auth/login` | Público: salud/login |
| GET | `/api/auth/me` | Sesión propia |
| POST | `/api/auth/activity` | Sesión propia |
| POST | `/api/auth/logout` | Sesión propia |
| POST | `/api/auth/password` | Sesión propia |
| GET | `/api/system/version` | Sesión propia |
| GET | `/docs` | roles.manage o accounts.manage |
| GET | `/docs/oauth2-redirect` | roles.manage o accounts.manage |
| GET | `/redoc` | roles.manage o accounts.manage |
| GET | `/openapi.json` | roles.manage o accounts.manage |
| GET | `/api/tickets` | tickets.view o reports.tickets.view |
| POST | `/api/tickets` | tickets.create |
| GET | `/api/tickets/{id}` | tickets.view |
| PATCH | `/api/tickets/{id}` | tickets.edit o tickets.close o tickets.link |
| GET | `/api/tickets/export/{format}` | tickets.export o reports.tickets.export |
| GET | `/api/tickets/{id}/updates` | tickets.view |
| POST | `/api/tickets/{id}/updates` | tickets.followup |
| GET | `/api/tickets/{id}/escalations` | tickets.view |
| POST | `/api/tickets/{id}/escalations` | tickets.escalate |
| PATCH | `/api/tickets/{id}/escalations/{escalation_id}` | tickets.escalate |
| POST | `/api/tickets/{id}/escalations/{escalation_id}/finish` | tickets.escalate |
| GET | `/api/tickets/{id}/escalations/{escalation_id}/audit` | tickets.view |
| GET | `/api/tickets/{id}/reports/internal/pdf` | tickets.export |
| GET | `/api/internal-tickets` | internal_tickets.view o reports.internal_tickets.view o tickets.link o changes.link |
| POST | `/api/internal-tickets` | internal_tickets.create |
| GET | `/api/internal-tickets/{id}` | internal_tickets.view o tickets.view o changes.view |
| PATCH | `/api/internal-tickets/{id}` | internal_tickets.edit o internal_tickets.close |
| GET | `/api/internal-tickets/export/{format}` | internal_tickets.export o reports.internal_tickets.export |
| GET | `/api/internal-tickets/{id}/updates` | internal_tickets.view |
| POST | `/api/internal-tickets/{id}/updates` | internal_tickets.followup |
| GET | `/api/internal-tickets/{id}/escalations` | internal_tickets.view |
| POST | `/api/internal-tickets/{id}/escalations` | internal_tickets.escalate |
| PATCH | `/api/internal-tickets/{id}/escalations/{escalation_id}` | internal_tickets.escalate |
| POST | `/api/internal-tickets/{id}/escalations/{escalation_id}/finish` | internal_tickets.escalate |
| GET | `/api/internal-tickets/{id}/escalations/{escalation_id}/audit` | internal_tickets.view |
| GET | `/api/internal-tickets/{id}/reports/internal/pdf` | internal_tickets.export |
| GET | `/api/tickets/{id}/reports/customer/pdf` | tickets.export |
| GET | `/api/tickets/stats` | tickets.view |
| GET | `/api/internal-tickets/{id}/related` | internal_tickets.view |
| GET | `/api/escalations/summary` | reports.escalations.view |
| GET | `/api/escalations/tickets` | reports.escalations.view |
| GET | `/api/customers` | customers.view o customers.lookup |
| GET | `/api/customers/{id}` | customers.view o customers.lookup |
| POST | `/api/customers` | customers.create o context.customers.create |
| PATCH | `/api/customers/{id}` | customers.edit |
| DELETE | `/api/customers/{id}` | customers.delete |
| GET | `/api/circuits` | circuits.view o circuits.lookup |
| GET | `/api/circuits/{id}` | circuits.view o circuits.lookup |
| POST | `/api/circuits` | circuits.create o context.circuits.create |
| PATCH | `/api/circuits/{id}` | circuits.edit |
| DELETE | `/api/circuits/{id}` | circuits.delete |
| GET | `/api/circuits/{id}/operational-detail` | circuits.view o capacity_changes.execute |
| GET | `/api/circuits/{id}/cpe-configuration` | cpe.view |
| PATCH | `/api/circuits/{id}/cpe-configuration` | cpe.edit |
| GET | `/api/sectors` | catalogs.sectors.view o catalogs.sectors.lookup |
| GET | `/api/sectors/{id}` | catalogs.sectors.view o catalogs.sectors.lookup |
| POST | `/api/sectors` | catalogs.sectors.create |
| PATCH | `/api/sectors/{id}` | catalogs.sectors.edit |
| GET | `/api/departments` | catalogs.departments.view o catalogs.departments.lookup |
| GET | `/api/departments/{id}` | catalogs.departments.view o catalogs.departments.lookup |
| POST | `/api/departments` | catalogs.departments.create |
| PATCH | `/api/departments/{id}` | catalogs.departments.edit |
| GET | `/api/incident-types` | catalogs.incident_types.view o catalogs.incident_types.lookup |
| GET | `/api/incident-types/{id}` | catalogs.incident_types.view o catalogs.incident_types.lookup |
| POST | `/api/incident-types` | catalogs.incident_types.create |
| PATCH | `/api/incident-types/{id}` | catalogs.incident_types.edit |
| GET | `/api/nodes` | catalogs.nodes.view o catalogs.nodes.lookup |
| GET | `/api/nodes/{id}` | catalogs.nodes.view o catalogs.nodes.lookup |
| POST | `/api/nodes` | catalogs.nodes.create o context.nodes.create |
| PATCH | `/api/nodes/{id}` | catalogs.nodes.edit |
| GET | `/api/responsibles` | catalogs.responsibles.view o catalogs.responsibles.lookup |
| GET | `/api/responsibles/{id}` | catalogs.responsibles.view o catalogs.responsibles.lookup |
| POST | `/api/responsibles` | catalogs.responsibles.create |
| PATCH | `/api/responsibles/{id}` | catalogs.responsibles.edit |
| GET | `/api/positions` | catalogs.positions.view o catalogs.positions.lookup |
| GET | `/api/positions/{id}` | catalogs.positions.view o catalogs.positions.lookup |
| POST | `/api/positions` | catalogs.positions.create |
| PATCH | `/api/positions/{id}` | catalogs.positions.edit |
| GET | `/api/escalation-reasons` | catalogs.escalation_reasons.view o catalogs.escalation_reasons.lookup |
| GET | `/api/escalation-reasons/{id}` | catalogs.escalation_reasons.view o catalogs.escalation_reasons.lookup |
| POST | `/api/escalation-reasons` | catalogs.escalation_reasons.create |
| PATCH | `/api/escalation-reasons/{id}` | catalogs.escalation_reasons.edit |
| GET | `/api/service-types` | catalogs.service_types.view o catalogs.service_types.lookup |
| GET | `/api/service-types/{id}` | catalogs.service_types.view o catalogs.service_types.lookup |
| POST | `/api/service-types` | catalogs.service_types.create |
| PATCH | `/api/service-types/{id}` | catalogs.service_types.edit |
| GET | `/api/deactivation-reasons` | catalogs.deactivation_reasons.view o catalogs.deactivation_reasons.lookup |
| POST | `/api/deactivation-reasons` | catalogs.deactivation_reasons.create |
| PATCH | `/api/deactivation-reasons/{id}` | catalogs.deactivation_reasons.edit |
| GET | `/api/cpe-models` | catalogs.cpe_models.view o catalogs.cpe_models.lookup |
| GET | `/api/cpe-models/{id}` | catalogs.cpe_models.view o catalogs.cpe_models.lookup |
| POST | `/api/cpe-models` | catalogs.cpe_models.create |
| PATCH | `/api/cpe-models/{id}` | catalogs.cpe_models.edit |
| GET | `/api/internal-incident-types` | catalogs.internal_incident_types.view o catalogs.internal_incident_types.lookup |
| GET | `/api/internal-incident-types/{id}` | catalogs.internal_incident_types.view o catalogs.internal_incident_types.lookup |
| POST | `/api/internal-incident-types` | catalogs.internal_incident_types.create |
| PATCH | `/api/internal-incident-types/{id}` | catalogs.internal_incident_types.edit |
| GET | `/api/providers` | catalogs.providers.view o catalogs.providers.lookup |
| GET | `/api/providers/{id}` | catalogs.providers.view o catalogs.providers.lookup |
| POST | `/api/providers` | catalogs.providers.create |
| PATCH | `/api/providers/{id}` | catalogs.providers.edit |
| GET | `/api/change-completion-types` | catalogs.change_completion_types.view o catalogs.change_completion_types.lookup |
| GET | `/api/change-completion-types/{id}` | catalogs.change_completion_types.view o catalogs.change_completion_types.lookup |
| POST | `/api/change-completion-types` | catalogs.change_completion_types.create |
| PATCH | `/api/change-completion-types/{id}` | catalogs.change_completion_types.edit |
| GET | `/api/change-types` | catalogs.change_types.view o catalogs.change_types.lookup |
| GET | `/api/change-types/{id}` | catalogs.change_types.view o catalogs.change_types.lookup |
| POST | `/api/change-types` | catalogs.change_types.create |
| PATCH | `/api/change-types/{id}` | catalogs.change_types.edit |
| GET | `/api/settings/ticket-number` | settings.ticket_number.view |
| PATCH | `/api/settings/ticket-number` | settings.ticket_number.edit |
| GET | `/api/settings/internal-ticket-number` | settings.internal_ticket_number.view |
| PATCH | `/api/settings/internal-ticket-number` | settings.internal_ticket_number.edit |
| GET | `/api/settings/activation-number` | settings.activation_number.view |
| PATCH | `/api/settings/activation-number` | settings.activation_number.edit |
| GET | `/api/settings/change-number` | settings.change_number.view |
| PATCH | `/api/settings/change-number` | settings.change_number.edit |
| GET | `/api/activations` | activations.view o reports.activations.view o mail.templates.preview |
| POST | `/api/activations` | activations.create |
| GET | `/api/activations/export/{format}` | activations.export o reports.activations.export |
| GET | `/api/capacity-changes` | capacity_changes.view o reports.capacity_changes.view |
| POST | `/api/capacity-changes` | capacity_changes.execute |
| GET | `/api/capacity-changes/export/{format}` | capacity_changes.export o reports.capacity_changes.export |
| GET | `/api/circuit-lifecycle` | lifecycle.view o reports.lifecycle.view |
| POST | `/api/circuit-lifecycle` | lifecycle.deactivate o lifecycle.reactivate |
| GET | `/api/circuit-lifecycle/export/{format}` | lifecycle.export o reports.lifecycle.export |
| GET | `/api/activations/{id}` | activations.view |
| GET | `/api/activations/{id}/reports/pdf` | activations.export |
| GET | `/api/activations/{id}/interventions` | activations.view |
| POST | `/api/activations/{id}/interventions` | activations.followup |
| GET | `/api/activations/{id}/notification` | activations.view |
| POST | `/api/activations/{id}/notification` | activations.notify |
| GET | `/api/fms/reports/{kind}/summary` | reports.{módulo FMS}.view / export según operación |
| GET | `/api/fms/reports/{kind}/details` | reports.{módulo FMS}.view / export según operación |
| GET | `/api/fms/reports/{kind}/export/pdf` | reports.{módulo FMS}.view / export según operación |
| GET | `/api/changes` | changes.view o reports.changes.view |
| POST | `/api/changes` | changes.create |
| GET | `/api/changes/{id}` | changes.view |
| PATCH | `/api/changes/{id}` | changes.edit o changes.execute o changes.link |
| GET | `/api/changes/{id}/updates` | changes.view |
| POST | `/api/changes/{id}/updates` | changes.followup |
| GET | `/api/changes/{id}/audit` | changes.view |
| GET | `/api/changes/export/{format}` | changes.export o reports.changes.export |
| GET | `/api/changes/{id}/reports/pdf` | changes.export |
| GET | `/api/change-reports/summary` | reports.changes.view |
| GET | `/api/change-reports/export/{format}` | reports.changes.export |
| GET | `/api/reports/summary` | reports.tickets.view |
| GET | `/api/reports/export/{format}` | reports.tickets.export |
| GET | `/api/reports/internal-tickets/summary` | reports.internal_tickets.view |
| GET | `/api/reports/internal-tickets/export/{format}` | reports.internal_tickets.export |
| GET | `/api/mail-notifications/smtp` | mail.transport.view |
| PATCH | `/api/mail-notifications/smtp` | mail.transport.edit |
| GET | `/api/mail-notifications/oauth` | mail.oauth.view |
| PATCH | `/api/mail-notifications/oauth` | mail.oauth.edit |
| POST | `/api/mail-notifications/smtp/test` | mail.transport.test |
| POST | `/api/mail-notifications/oauth/authorize` | mail.oauth.authorize |
| GET | `/api/mail-notifications/oauth/callback` | mail.oauth.authorize |
| POST | `/api/mail-notifications/oauth/disconnect` | mail.oauth.authorize |
| GET | `/api/mail-notifications/events` | mail.events.view o mail.templates.view |
| GET | `/api/mail-notifications/events/{event_key}` | mail.events.view o mail.templates.view |
| PATCH | `/api/mail-notifications/events/{event_key}` | mail.events.edit |
| GET | `/api/mail-notifications/events/{event_key}/fields` | mail.templates.view |
| GET | `/api/mail-notifications/events/{event_key}/template` | mail.templates.view |
| PATCH | `/api/mail-notifications/events/{event_key}/template` | mail.templates.edit |
| POST | `/api/mail-notifications/events/{event_key}/preview` | mail.templates.preview |
| GET | `/api/mail-notifications/processor` | mail.processor.view |
| GET | `/api/mail-notifications/requests` | mail.processor.view |
| POST | `/api/mail-notifications/processor/pause` | mail.processor.control |
| POST | `/api/mail-notifications/processor/resume` | mail.processor.control |
| GET | `/api/security/permissions` | roles.manage |
| GET | `/api/security/roles` | roles.manage o accounts.manage |
| GET | `/api/security/roles/{id}` | roles.manage o accounts.manage |
| POST | `/api/security/roles` | roles.manage |
| PATCH | `/api/security/roles/{id}` | roles.manage |
| DELETE | `/api/security/roles/{id}` | roles.manage |
| POST | `/api/security/roles/{id}/duplicate` | roles.manage |

## Validación final de la Fase 2 en DEV

- Backend completo: `.venv/bin/pytest -q --junitxml=/tmp/ticketyn-phase2-final-verified.xml`: **2 046 aprobadas, 0 fallidas, 0 errores y 0 omitidas**, en 1 241,74 segundos. Esta ejecución corresponde al código final, incluida la corrección del alcance contextual.
- Frontend completo: `npm test -- --maxWorkers=2`: **669 aprobadas en 59 archivos**.
- Grupo dirigido final de autorización, tickets internos, reportería y Control de cambios: **76 aprobadas**.
- TypeScript: `npx tsc --noEmit`, correcto. `git diff --check`, correcto.
- Las migraciones se verificaron exclusivamente en PostgreSQL descartable, incluido upgrade/downgrade de `0031_role_permissions`, conservación del registro de permisos y compatibilidad con datos anteriores. La concurrencia de creación de roles se probó con conexiones PostgreSQL independientes.

Al integrar la denegación predeterminada, doce expectativas heredadas de rutas inexistentes o métodos no implementados pasaron de 404/405 a 403. También se adaptó una llamada interna de prueba para proporcionar explícitamente la identidad autorizada. Se repitieron los casos afectados y la suite completa. Las pruebas siguen comprobando que esas acciones no modifican datos.

La revisión final detectó además una lectura contextual demasiado amplia de títulos de tickets internos. Se limitó a relaciones reales para consulta sin facultades de vinculación; los candidatos mínimos para vincular continúan disponibles solo con el permiso correspondiente. Una regresión verifica tanto la denegación de registros no relacionados como la conservación de vínculos autorizados.

La única advertencia backend es `StarletteDeprecationWarning`, por la compatibilidad actual de TestClient con httpx. No produjo fallos ni omisiones; no se cambiaron dependencias para silenciarla.

Se conservaron el trabajo de la Fase 1 y los documentos maestros. No se ejecutaron builds, no se modificó `frontend/dist/`, no se aplicaron migraciones a bases operativas o compartidas y no se crearon commits, tags, releases ni despliegues. La Fase 2 queda preparada para revisión; las fases posteriores no se iniciaron.
