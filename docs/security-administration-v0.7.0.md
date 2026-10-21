# Seguridad v0.7.0 — Fase 3: Responsables, acceso y sesiones

Esta fase amplía la [autorización de la Fase 2](security-authorization-v0.7.0.md). No habilita una publicación ni incluye la administración de auditoría y seguridad de la Fase 4.

## Identidad y disponibilidad operativa

`Responsible` y `responsibles.id` siguen siendo la identidad única. Usuario, hash Argon2id, rol, autorización y revisión de acceso se conservan en la misma fila. Los contratos llamados `Account` son representaciones administrativas de ese Responsable, no otra tabla ni otra persona.

Se distinguen tres propiedades:

| Propiedad | Efecto |
|---|---|
| `active` | Estado operativo; estar inactivo también bloquea la autenticación. |
| `access_granted` | Autorización administrativa persistente de acceso, independiente del estado operativo. |
| `operational_selectable` | Disponibilidad para nuevas asignaciones, independiente del acceso y del rol. |

Desactivar y reactivar operativamente conserva la autorización previa. Retirar el acceso administrativamente impide recuperarlo por una mera reactivación. Desactivar la disponibilidad para asignaciones no modifica credenciales, rol ni sesiones y permite que un administrador use Ticketyn sin aparecer en asignaciones.

La revisión `0032_responsible_selectable`, posterior a `0031_role_permissions`, agrega únicamente el booleano no nulo `operational_selectable`, con valor predeterminado `true`. Todos los Responsables anteriores conservan su disponibilidad. No existen excepciones por nombre de usuario ni cambios automáticos de `admin-dev`. El downgrade elimina únicamente la propiedad nueva; conserva identidades, credenciales y referencias, aunque pierde la configuración de disponibilidad.

La base DEV confirmada por el propietario permanece en `0031`. **La migración nueva no se aplica automáticamente.** Para probar manualmente este código contra DEV hace falta autorizar y aplicar `0032` previamente; el ORM actualizado requiere esa columna. No se debe repetir el bootstrap, recrear la base ni restablecer credenciales.

## Asignaciones e históricos

El backend valida la disponibilidad al asignar Responsables nuevos en tickets de clientes, tickets internos, intervenciones, escalamientos, activaciones FMS, capacidad, bajas/reactivaciones y Control de cambios, incluido el personal de apoyo. Utiliza las lecturas bloqueadas de relaciones existentes.

Conservar un identificador ya asignado no establece una asignación nueva. Se permite editar otros datos y enviar explícitamente el mismo identificador histórico. En personal de apoyo se validan solo las incorporaciones nuevas. Retirar una relación y guardarla impide volver a crearla posteriormente si la persona sigue sin estar disponible.

Los selectores de creación excluyen los no disponibles; los editores retienen las asignaciones originales. Los filtros, reportes y consultas administrativas siguen mostrando los Responsables históricos. `GET /api/responsibles?operational_only=true` ofrece además una consulta explícita de activos y seleccionables, filtrada en PostgreSQL antes de paginar. El comportamiento predeterminado del listado no filtra por disponibilidad.

Modificar disponibilidad requiere `catalogs.responsibles.edit` o `catalogs.responsibles.create` durante la creación. Estos permisos no permiten modificar credenciales. `accounts.manage` no concede por sí solo edición operativa ni disponibilidad. `can_change_active` es una capacidad de acción calculada para la interfaz; no expone credenciales ni sustituye las verificaciones de escritura.

## Administración y perfil

Administración incluye **Responsables**, **Roles y permisos** y **Sesiones**, además de las opciones existentes. Responsables deja de aparecer dentro de Catálogos; se reutiliza `CatalogAdmin` y los registros existentes.

La administración de acceso permite configurar usuario, contraseña temporal manual o generada, autorización y rol sobre un Responsable existente. Las contraseñas temporales se entregan una vez en la respuesta de configuración/restablecimiento y se muestran de forma transitoria. No se pueden recuperar contraseñas guardadas. Las consultas nunca devuelven hashes ni secretos.

Un Administrador o personalizado con `accounts.manage` no administra su propio acceso, Superadministradores, Administradores ni personas con capacidades equivalentes o superiores. Los roles asignables se filtran mediante las reglas de la Fase 2. El último Superadministrador activo permanece protegido. No se agrega eliminación física de personas.

Roles y permisos utiliza el registro de los 147 permisos del backend y sus dependencias. Los nuevos personalizados comienzan vacíos. Solo Superadministrador modifica definiciones; los predeterminados son fijos. Operador, Auditor y personalizados pueden duplicarse; Superadministrador y Administrador no. Las copias son independientes. Se incluye comparación de permisos y advertencia de cambios sin guardar al seguir enlaces o cerrar/recargar la página. La consulta general del historial de auditoría pertenece a la Fase 4; los cambios críticos ya se registran transaccionalmente.

Mi perfil está disponible para cualquier sesión con contraseña definitiva, aunque no tenga permisos operativos. Muestra Responsable, usuario, puesto y rol, sin autoasignación de privilegios. Reutiliza el cambio de contraseña de la Fase 1 y permite consultar/cerrar sesiones propias. El flujo obligatorio de contraseña temporal sigue restringido a autenticación.

Nombre, Mi perfil y Cerrar sesión se integran en el encabezado azul existente, antes del indicador de API. Se elimina la franja de usuario adicional. El encabezado conserva la superficie Electric Blue y las curvas del sidebar, con controles compactos en pantallas pequeñas.

## Contratos nuevos

Todos requieren autenticación y contraseña definitiva. La frontera de seguridad conserva denegación por defecto.

| Método y ruta | Alcance |
|---|---|
| GET `/api/responsibles/access` | Listado paginado de representaciones administrativas dentro de las facultades de `accounts.manage`. |
| GET `/api/responsibles/{id}/access` | Consulta administrativa del acceso del Responsable autorizado. |
| POST `/api/responsibles/{id}/access` | Configura credenciales y rol en la fila existente; no inserta una persona. |
| PATCH `/api/responsibles/{id}/access` | Modifica usuario, rol y/o autorización; no acepta datos operativos ni hashes. |
| POST `/api/responsibles/{id}/access/password` | Restablecimiento temporal, con invalidación de sesiones. |
| GET `/api/auth/profile` | Perfil propio seguro. |
| GET `/api/auth/sessions` | Sesiones propias activas. |
| POST `/api/auth/sessions/close-others` | Cierra las otras sesiones propias. |
| POST `/api/auth/sessions/{session_id}/revoke` | Cierra una sesión propia identificada por su id técnico. |
| GET `/api/security/sessions` | Sesiones dentro de las facultades de `sessions.manage`. |
| POST `/api/security/sessions/{session_id}/revoke` | Cierre administrativo autorizado y auditado. |

Se conservan los endpoints de roles y autenticación previos. Errores: 401 por sesión inválida, 403 por falta de permiso/autoridad, 404 por Responsable inexistente o sesión no accesible/activa, 409 por usuario reservado, acceso ya configurado o protección del último Superadministrador, 422 por datos inválidos o habilitación de un inactivo y 503 ante un fallo de persistencia/verificación.

## Sesiones y efectos inmediatos

Las sesiones siguen en RAM, con máximo de cinco por Responsable y un único trabajador HTTP. Se listan identificadores aleatorios de sesión distintos del token y de su hash, dispositivo inferido del User-Agent, IP y actividad. El dispositivo es orientativo, no una identidad confiable.

La interfaz permite filtrar las sesiones administrativas por Responsable, usuario, IP y actividad reciente. Solo se muestran sesiones activas; no se inventa un historial de revocadas o vencidas. Reiniciar el backend cierra todas. Duplicar una pestaña puede copiar `sessionStorage` y compartir una sesión, en lugar de crear otra independiente.

Las terminaciones se auditan antes de retirar las entradas RAM: si falla la transacción obligatoria no se completa el cierre. La revisión persistente de acceso mantiene la invalidación ante suspensión, baja y restablecimientos, incluidos los realizados por CLI. Cambiar un rol conserva las sesiones y aplica los permisos vigentes en el backend.

React conserva las comprobaciones al navegar, recuperar foco y cada 15 segundos. Consultar perfil, permisos o sesiones no renueva actividad. Se mantienen los 30 minutos iniciales, la advertencia de dos minutos y la renovación explícita por actividad de la Fase 1.

## Validación

Las pruebas utilizan PostgreSQL descartable y sesiones reales; no usan DEV ni envían correos externos. Incluyen preservación de identidad y credenciales al migrar, upgrade/downgrade, disponibilidad e históricos, permisos separados, configuración y suspensión de acceso, contraseñas temporales, último Superadministrador, alcance de sesiones, auditoría obligatoria, formularios y navegación.

Los resultados finales de pytest, Vitest, TypeScript y `git diff --check` se informan al entregar la fase. No se ejecuta build ni se modifica `frontend/dist/`.

## Archivos de integración

- Identidad y migración: `models/responsible.py`, `schemas/responsible.py`, `alembic/versions/0032_responsible_selectable.py`.
- Contratos y servicios: `api/security_accounts.py`, `api/responsibles.py`, `security/accounts.py`, `security/roles.py`, `security/routes.py`, `security/memory.py` y `main.py`.
- Validación operativa compartida: `api/responsible_selection.py`, `api/ticket_data.py`, `api/ticket_update_data.py`, `api/internal_ticket_data.py`, `api/escalation_data.py`, `api/fms_data.py` y `api/change_data.py`.
- React: `auth/context.tsx`, `auth/AuthGate.tsx`, `auth/permissions.tsx`, `api/security.ts`, `lib/responsibles.ts`, `components/ResponsibleAccess.tsx`, `components/PasswordChangeForm.tsx`, `components/SessionsPanel.tsx`, `components/UserControls.tsx`, `pages/Profile.tsx`, `pages/SecurityRoles.tsx` y `pages/SecuritySessions.tsx`.
- Integración visual: `App.tsx`, `components/CatalogAdmin.tsx`, `components/Layout.tsx`, `components/moduleIdentity.ts`, `pages/Catalogs.tsx`, `styles.css` y `types/catalog.ts`.
- Selectores existentes: `components/TicketForm.tsx`, `components/TicketInterventionModal.tsx`, `components/OperationModal.tsx`, `components/EscalationModal.tsx`, `pages/ActivationDetail.tsx`, `pages/InternalTickets.tsx` y `pages/Changes.tsx`.
- Pruebas nuevas: `tests/test_security_administration.py`, `tests/test_responsible_selection.py` y `frontend/src/pages/SecurityAdministration.test.tsx`. Se ajustan las regresiones existentes de contratos, migración/CLI, navegación, autenticación, FMS y Control de cambios.

Las rutas Python de aplicación son relativas a `src/ticketyn/`; las rutas React, a `frontend/src/`. Los cambios acumulados de las fases anteriores se conservan.
