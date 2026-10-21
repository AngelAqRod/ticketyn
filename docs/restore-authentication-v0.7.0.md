# Restauración y autenticación — Ticketyn v0.7.0

## Alcance y estado

Adaptación del procedimiento de restauración (`restore.sh` y `deploy/restore_support.py`)
para garantizar compatibilidad posterior al restablecimiento tanto con versiones
históricas sin autenticación (v0.6.2 e inferiores) como con Ticketyn v0.7.0 y
versiones posteriores con autenticación, roles, permisos y auditoría.

Se conservan intactos la selección y validación de respaldos, la restauración de
PostgreSQL (formato custom `pg_dump`, OIDs, revisiones Alembic, sincronización de
contraseñas SCRAM, cluster identity), el manejo de servicios systemd monoproceso,
la conmutación atómica de enlaces simbólicos (`current`), los permisos restrictivos
y la política de recuperación y no-rollback automático ante fallos posteriores al cutover.

La versión oficial del proyecto continúa en **0.6.2** en `pyproject.toml`. Estos
cambios no autorizan ni ejecutan restauraciones destructivas en entornos operativos
(DEV, TEST o PRODUCCIÓN).

---

## Causa raíz de la incompatibilidad

1. **Supuesto de acceso anónimo en legacy:**
   En versiones históricas (v0.6.2 y previas), `restore.sh` ejecutaba `curl -fsS "$base/api/customers"`
   esperando una respuesta HTTP 200 con una lista JSON de clientes (`http-valid` verificaba `isinstance(data, list)`).
2. **Rechazo obligatorio en v0.7.0+:**
   Al incorporar autenticación mediante `SecurityBoundary` y `SafeAuthRoute`, el endpoint
   `/api/customers` exige una sesión válida o token Bearer. Cualquier solicitud anónima
   es rechazada de inmediato con HTTP **401 Unauthorized** y cabecera `WWW-Authenticate: Bearer`.
3. **Falso fallo en corte:**
   Al utilizar `curl -f` contra `/api/customers`, curl interpretaba el HTTP 401 esperado
   como un error fatal (código de salida 22). Esto provocaba que una restauración
   técnicamente perfecta de v0.7.0 fuera marcada como fallida tras conmutar la base
   de datos y activar los servicios.

---

## Detección compartida de capacidades

Para determinar el modo de comprobación de forma determinista y sin duplicar lógica,
`deploy/restore_support.py` reutiliza el detector estático de capacidades ya
establecido para el instalador y el updater (`deploy/install_security.py`):

- **Inspección de código mediante AST:**
  Examina el código de la release a restaurar (`src/ticketyn/main.py`, routers de
  seguridad, presencia de migraciones Alembic 0030–0032 con sus dependencias y
  contrato de `bootstrap-superadmin.sh`).
- **Independiente de la versión declarada:**
  No confía ciegamente en el string de versión de `pyproject.toml` ni en un archivo
  aislado.
- **Sin acceso a base de datos para detección:**
  No requiere consultar PostgreSQL ni ejecutar código arbitrario del candidato.
- **Rechazo temprano de distribuciones incompletas:**
  Si una release presenta indicios parciales de seguridad pero carece de migraciones
  o componentes esenciales, el detector genera un fallo temprano en la fase de
  validación (`restore_validate` o `restore_finalize_validate`), abortando antes de
  mutar el clúster o conmutar enlaces.

---

## Comprobaciones HTTP según el modo

El script `restore.sh` y la función auxiliar `http_valid` en `deploy/restore_support.py`
operan con la siguiente matriz:

### 1. Release con autenticación (`auth_mode == required`)

- **`/health` (público):**
  - Se consulta con `curl -fsS "$base/health"`.
  - Debe responder HTTP 200 con cuerpo JSON idéntico a `{"status":"ok"}`.
- **`/api/customers` (protegido):**
  - Se consulta con `curl -sS --max-time 3 -o /dev/null -w '%{http_code}' "$base/api/customers"`.
  - Debe responder exactamente con código HTTP **401**.
  - **No se descargan ni almacenan cuerpos de respuesta ni credenciales.**
  - Cualquier otro código (200, 403, 500, 502) se rechaza como violación de contrato.
- **Sin requerir credenciales administrativas:**
  La comprobación no requiere sesión, usuario ni contraseña. La presencia del 401
  certifica que el cortafuegos de seguridad de la aplicación está activo y protegiendo
  los recursos de la instalación restaurada.

### 2. Release histórica (`auth_mode == legacy`)

- **`/health`:**
  - Debe responder HTTP 200 con `{"status":"ok"}`.
- **`/api/customers`:**
  - Se consulta con `curl -fsS "$base/api/customers"`.
  - Debe responder HTTP 200 con una lista JSON válida.

En ambos casos, las comprobaciones cuentan con hasta 30 reintentos de 1 segundo
para tolerar demoras normales de inicio del worker de Uvicorn tras conmutar systemd.

---

## Preservación del procedimiento de recuperación

Se mantiene la integridad de la arquitectura de respaldo y restauración existente:

1. **Integridad de PostgreSQL intacta:**
   - Verificación de formato binario custom (`pg_restore -l`).
   - Comprobación de OIDs de base de datos para prevenir colisiones.
   - Alineación estricta de la revisión Alembic (`restore_revision`) contra el HEAD
     declarado en los metadatos del backup y en la release.
   - Verificación de propiedad de tablas en esquema `public`.
   - Sincronización de credenciales SCRAM en `/etc/ticketyn/ticketyn.env`.
2. **Sin rollback automático destructivo tras cutover:**
   Si las comprobaciones HTTP fallan después de haber conmutado la base de datos
   (`CUTOVER_ATTEMPTED=1`):
   - Se detiene `ticketyn.service` para evitar inconsistencias operativas.
   - Se preserva el archivo de estado de restauración (`restore-state`).
   - Se conserva la base previa (`$PREVIOUS`) y el backup de seguridad (`$SAFETY_BACKUP`).
   - No se intenta un rollback automático ni se destruyen datos; se informa al operador
     para que intervenga con el diagnóstico completo.
3. **Flujo `--finalize`:**
   Soporta tanto versiones legacy como autenticadas, verificando la salud con el mismo
   criterio determinista antes de purgar bases temporales o archivar snapshots.

---

## Pruebas y validaciones ejecutadas

La suite completa de pruebas automatizadas garantiza la compatibilidad:

1. **`tests/test_restore_authentication.py` (16 pruebas):**
   - Detección de capacidades `required` vs `legacy`.
   - Rechazo de paquetes de seguridad incompletos o manipulados.
   - Validación unitaria de `http_valid` (salud y códigos API).
   - Restauración exitosa de releases v0.7.0 (401 en API, 200 en health).
   - Rechazo de códigos HTTP no conformes (200 en release autenticada, 403, 500, 502).
   - Manejo de servicios caídos o timeout de red.
   - Aborto temprano en fase de validación antes de mutar base de datos.
   - Compatibilidad conservada para releases legacy (200 en API).
   - Operaciones de finalización (`--finalize`) en ambos modos.
2. **`tests/test_restore.py` (73 pruebas):**
   - Comportamiento completo de restauración legacy, validaciones de seguridad,
     permisos, OIDs, SCRAM y manejo de errores.
3. **`tests/test_restore_finalize.py` (44 pruebas):**
   - Ciclos de vida de finalización, historiales y rotación de snapshots.
4. **`tests/test_backup.py` (33 pruebas):**
   - Generación de respaldos, cálculo de sumas SHA256 e integridad de metadatos.
5. **Pruebas de actualización cruzadas (`test_update.py`, `test_update_authentication.py`, `test_installed_updater.py`):**
   - 140 pruebas aprobadas sin regresiones.
