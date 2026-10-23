# Ficha Técnica: Seguridad y Cuentas

## Responsabilidad del módulo
- **Qué gestiona:** Autenticación de usuarios, autorización granular basada en roles (RBAC), control de sesiones activas en memoria, auditoría de eventos de seguridad y configuración de retención.
- **Funcionalidades existentes:**
  - Inicio de sesión (`login`) y cierre de sesión (`logout`) mediante tokens opacos de cabecera `Authorization: Bearer <token>`.
  - Consulta y actualización de perfil personal (incluyendo cambio voluntario de contraseña).
  - Administración de acceso web sobre el catálogo de Responsables (asignación de usuario, contraseña y rol).
  - Gestión de roles personalizados con asignación granular de permisos sobre un catálogo cerrado.
  - Monitorización y revocación selectiva o masiva de sesiones activas.
  - Bitácora de auditoría de seguridad con filtros por fecha/evento, exportación a PDF y Excel (.xlsx), y purga automática/manual según política de retención (1–3650 días).
- **Qué no le corresponde:** No es un proveedor de identidad OAuth2 externo (no autentica clientes externos), no permite autorregistro público, no incluye MFA/2FA ni recuperación desatendida de contraseñas por correo.

## Reglas de negocio críticas
- **Identidad única de personas y cuentas:** La tabla `responsibles` representa la única identidad en el sistema. No existe ni debe crearse una tabla `users` paralela.
- **Tres dimensiones de estado independientes:**
  1. `active`: Estado operativo. Si `active=false`, la sesión se revoca de inmediato y se bloquea el acceso.
  2. `access_granted`: Autorización administrativa de acceso. Reactivar a una persona no le otorga acceso si esta bandera es falsa.
  3. `operational_selectable`: Disponibilidad en selectores operativos. Permite que cuentas administrativas no saturen listas desplegables operativas.
- **Arquitectura de sesiones en memoria RAM:**
  - Los tokens son opacos y se guardan como hashes SHA-256 en `SecurityMemory` (`memory.py`).
  - Límite de **5 sesiones concurrentes** por usuario y tiempo de inactividad máximo de **1.800 segundos (30 minutos)**.
  - Incompatibilidad con multi-worker: La aplicación debe ejecutarse con **un único proceso Uvicorn (`--workers 1`)** ya que el estado de sesiones no se comparte vía Redis ni base de datos.
  - Invalidación por revisión: Toda sesión almacena un contador de revisión (`responsible.revision`). Cambiar contraseña o revocar acceso incrementa la revisión e invalida instantáneamente todas las sesiones activas del usuario.
- **Argon2id con limitación de concurrencia:**
  - Utiliza `PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)`.
  - Semáforo acotado a 2 hilos paralelos (`_SLOTS = BoundedSemaphore(2)`) limitando la memoria máxima de hashing a 128 MiB por proceso HTTP.
  - Consulta de tiempo constante para cuentas inexistentes mediante `dummy_hash()`.
- **Bloqueo transaccional de seguridad:** Toda mutación sobre credenciales, roles, permisos o políticas de retención debe invocar `lock_security(session)`.
- **Protección del último Superadministrador:** Está prohibido desactivar, degradar o retirar el rol al último Superadministrador activo del sistema.
- **Facultades exclusivas:** `roles.manage`, `security.configure`, `audit.export` y `audit.clean` pertenecen exclusivamente al Superadministrador.

## Arquitectura y dependencias
- **Componentes backend:** `src/ticketyn/security/` (`memory.py`, `routes.py`, `permissions.py`, `passwords.py`, `mutations.py`, `audit.py`, `retention.py`), endpoints en `src/ticketyn/api/` (`auth.py`, `security_accounts.py`, `security_roles.py`, `security_audit.py`).
- **Componentes frontend:** `frontend/src/auth/` (`AuthGate.tsx`, `context.tsx`, `permissions.tsx`), vistas en `frontend/src/pages/` (`SecurityRoles.tsx`, `SecuritySessions.tsx`, `SecurityAudit.tsx`, `Profile.tsx`), componentes en `frontend/src/components/` (`ResponsibleAccess.tsx`, `PasswordChangeForm.tsx`, `SessionsPanel.tsx`).
- **Dependencias:** Tabla `responsibles` (modelo central), `src/ticketyn/core/config.py`.
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `PUT /api/auth/profile/password`, `GET/PUT /api/security/accounts`, `GET/POST/PUT /api/security/roles`, `GET/DELETE /api/security/sessions`, `GET/POST /api/security/audit`, `GET/PUT /api/security/config`.
- **Permisos requeridos:** `accounts.manage`, `roles.manage`, `sessions.manage`, `security.configure`, `audit.view`, `audit.export`, `audit.clean`.
- **Política de denegación predeterminada:** Evaluada por `SafeAuthRoute` en `src/ticketyn/security/routes.py`. Toda ruta no declarada explícitamente en el inventario cerrado se deniega con HTTP 403. Excepciones públicas únicas: `GET /health`, `POST /api/auth/login` y el callback técnico de OAuth2.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_security_foundation.py tests/test_security_authorization.py tests/test_security_administration.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/SecurityAdministration.test.tsx frontend/src/auth/AuthGate.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - No reemplazar la sesión en memoria por almacenamiento en BD sin autorización explícita.
  - Al agregar cualquier ruta HTTP en `src/ticketyn/api/`, declararla obligatoriamente en `src/ticketyn/security/routes.py` para evitar que `SafeAuthRoute` la bloquee con 403.
  - Verificar siempre que los tests corran sobre PostgreSQL efímero y nunca toquen bases operativas.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en el catálogo de permisos en `src/ticketyn/security/permissions.py`, ajustes a las dimensiones de `Responsible`, adición de rutas administrativas o modificaciones en los parámetros de Argon2id o sesiones.
