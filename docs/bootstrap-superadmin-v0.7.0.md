# Ticketyn v0.7.0 — Procedimiento de Bootstrap Seguro del Superadministrador Inicial

## 1. Contexto y Propósito

Ticketyn v0.7.0 introduce autenticación obligatoria, control de acceso basado en roles (RBAC) y gestión granular de sesiones. En las versiones anteriores (v0.6.2 y anteriores), el sistema operaba sin autenticación. Al migrar una instalación en producción, los responsables existentes se preservan en la base de datos pero conservan el acceso desactivado (`access_granted = false`) y sin contraseñas configuradas.

El updater existente (`update.sh` / `deploy/update_support.py`) se encarga exclusivamente de la actualización técnica:
- Desempaquetado del nuevo release en `/opt/ticketyn/releases/v0.7.0`.
- Preparación del entorno virtual Python.
- Ejecución de migraciones Alembic (`0030_security_foundation`, `0031_role_permissions`, `0032_responsible_selectable`).
- Reemplazo atómico del enlace simbólico `/opt/ticketyn/current`.
- Reinicio supervisado de servicios systemd.

El bootstrap del primer superadministrador constituye la **Fase 2 (Inicialización administrativa)**, separada de las migraciones y de la lógica del updater. Puede ejecutarse manualmente mediante el script interactivo y seguro:

```bash
./bootstrap-superadmin.sh
```

**Instalaciones nuevas:** el instalador integra este mismo script después de
verificar las migraciones y antes de iniciar servicios. Comprueba primero con
`--check`; solo solicita creación si no existe un Superadministrador. Las
releases anteriores sin autenticación no ejecutan bootstrap. El flujo y su
recuperación se describen en [Instalador](installer-latest-stable.md).

**Actualizaciones:** el updater corregido incluye el script original y acepta
el 401 anónimo esperado, pero no ejecuta el bootstrap ni crea cuentas. Después
de la actualización técnica se realiza manualmente `--check` y, únicamente si
no existe el primer Superadministrador, el asistente. Es necesario utilizar la
herramienta corregida con todos sus auxiliares; un updater antiguo no adquiere
esta compatibilidad solo por seleccionar un tag nuevo. Ver [guía del updater](updater-authentication-v0.7.0.md)
para los comandos, recuperación y validaciones pendientes antes de publicar.

---

## 2. Principios de Seguridad y Diseño

1. **Uso exclusivo local:** El bootstrap solo puede invocarse desde la consola administrativa del servidor donde corre Ticketyn. No existe endpoint HTTP ni API remota que permita disparar esta inicialización.
2. **Protección de secretos:**
   - Las contraseñas **jamás** se reciben por argumentos CLI (`argv`) para evitar fugas en `ps`, logs del sistema o historial de shell (`~/.bash_history`).
   - Se leen de forma interactiva con eco desactivado (`getpass`).
   - Nunca se persisten ni imprimen contraseñas en claro, hashes Argon2id ni cadenas de conexión a base de datos.
   - En auditoría se registra únicamente el evento `BOOTSTRAP_SUPERADMIN` indicando el ID del responsable afectado y el actor `CLI uid=<UID>`.
3. **Idempotencia y exclusión mutua transaccional:**
   - La operación adquiere un bloqueo exclusivo sobre la fila singleton `security_config(id=1)` (`SELECT ... FOR UPDATE`).
   - Se reevalúa el estado dentro de la transacción bloqueada. Si dos operadores o scripts invocan el bootstrap concurrentemente, solo uno creará el usuario; el segundo detectará inmediatamente que la inicialización ya fue satisfecha, finalizando con código de salida `0` sin duplicar cuentas ni corromper datos.
4. **Respeto a la identidad única de responsables:**
   - No se crean tablas paralelas de usuarios.
   - El superadministrador creado se marca con `active = true`, `access_granted = true`, rol `SUPERADMIN`, `password_change_required = true` y `operational_selectable = false` (para que los usuarios de administración no figuren en selectores operativos de tickets).
   - Los responsables históricos no son alterados ni sus permisos modificados.

---

## 3. Requisitos Previos

Antes de ejecutar `bootstrap-superadmin.sh`, deben cumplirse:

1. **Migraciones Alembic aplicadas:**
   - La base de datos debe contener las tablas creadas por las migraciones de seguridad v0.7.0 (`security_roles`, `security_permissions`, `security_role_permissions`, `security_config`, `security_audit`) y las columnas añadidas a `responsibles`.
2. **Entorno Python disponible:**
   - En producción: `/opt/ticketyn/current/.venv/bin/python`.
   - En desarrollo: `./.venv/bin/python`.
3. **Acceso seguro a configuración:**
   - En producción: `/etc/ticketyn/ticketyn.env` (permisos `0600`, propietario `root:root`).
   - En desarrollo: variable de entorno `DATABASE_URL` o archivo `.env` privado.

---

## 4. Modos de Ejecución

### A. Ejecución en Producción (Instalación Versionada)

Tras ejecutar `./update.sh v0.7.0`, el operador ejecuta como root:

```bash
cd /opt/ticketyn/current
./bootstrap-superadmin.sh
```

El script localiza automáticamente el entorno Python de la release activa y lee la configuración desde `/etc/ticketyn/ticketyn.env`.

#### Flujo interactivo:
```
======================================================================
TICKETYN v0.7.0 — INICIALIZACIÓN DEL SUPERADMINISTRADOR INICIAL
======================================================================
No se encontró ningún superadministrador en el sistema.
Se procederá a crear la cuenta del primer superadministrador.

Nombre de usuario (login): admin
Nombre completo para el catálogo de responsables [Superadministrador (admin)]: Administrador del Sistema
Contraseña del superadministrador: [oculta]
Confirmar contraseña: [oculta]

======================================================================
SUPERADMINISTRADOR INICIAL CREADO EXITOSAMENTE
======================================================================
  ID Responsable:     12
  Nombre en catálogo: Administrador del Sistema
  Usuario (login):    admin
  Rol asignado:       Superadministrador
  Estado:             Activo (access_granted=True)
  Disp. Operativa:    operational_selectable=False
----------------------------------------------------------------------
NOTA: Por seguridad, se requerirá cambiar la contraseña temporal
      en el primer inicio de sesión.
======================================================================
```

### B. Ejecución en Entorno de Desarrollo (Local)

En el repositorio local de desarrollo:

```bash
./bootstrap-superadmin.sh --config .env
```
O bien con `DATABASE_URL` exportada:
```bash
export DATABASE_URL="postgresql+psycopg://ticketyn:secreto@127.0.0.1:5432/ticketyn"
./bootstrap-superadmin.sh
```

También es posible pasar de antemano el nombre de usuario y catálogo para agilizar el asistente (las contraseñas siempre se solicitarán interactivamente):
```bash
./bootstrap-superadmin.sh --username admin --name "Admin Local"
```

### C. Comprobación de Estado No Interactiva (`--check`)

Para tareas de verificación o pipelines de automatización:

```bash
./bootstrap-superadmin.sh --check
```

Códigos de retorno con `--check`:
- `0`: Superadministrador válido y operativo presente.
- `3`: No existe superadministrador (requiere inicialización).
- `1`: Inconsistencias administrativas detectadas.
- `2`: Error de configuración o fallo de conexión a PostgreSQL.

---

## 5. Comportamiento en los Tres Casos

### Caso A: Ya existe un superadministrador válido
Si en la base de datos ya existe un responsable con rol `SUPERADMIN`, activo (`active = true`), con acceso otorgado (`access_granted = true`), credenciales configuradas y capaz de autenticarse:
- El script informa que la inicialización ya está satisfecha.
- Muestra el ID, nombre y nombre de usuario del administrador existente.
- No modifica contraseñas, roles ni registros.
- Finaliza exitosamente con código `0`.

### Caso B: No existe un superadministrador válido
Si no existe ningún registro con rol `SUPERADMIN`:
- Solicita interactivamente el nombre de usuario, nombre para el catálogo y contraseña con confirmación.
- Valida que el nombre de usuario no esté duplicado ni reservado.
- Hashea la contraseña con Argon2id configurado (64 MiB RAM, 3 iteraciones, 4 lanes).
- Crea la cuenta transaccionalmente con `operational_selectable = false` y `password_change_required = true`.
- Genera el registro de auditoría `BOOTSTRAP_SUPERADMIN`.
- Valida que el usuario cumple todas las condiciones de inicio de sesión antes de confirmar la transacción.
- Finaliza con código `0`.

### Caso C: Estado administrativo inconsistente
Si se detecta un superadministrador inactivo, con `access_granted = false`, sin hash de contraseña, sin nombre de usuario o con configuración fundamental faltante:
- El script detalla el problema detectado en `stderr`.
- **No** aplica reparaciones automáticas ni altera contraseñas.
- **No** promueve cuentas existentes sin intervención explícita.
- Finaliza con código `1` indicando la necesidad de revisión manual por el equipo técnico.

---

## 6. Independencia de Alembic y del Updater

El bootstrap no forma parte de las migraciones de Alembic ni de `update.sh` por las siguientes razones de arquitectura:

1. **Alembic no es interactivo:** Las migraciones deben poder ejecutarse desatendidas, sin requerir `stdin` ni bloquearse esperando que un operador introduzca contraseñas.
2. **Sin credenciales predeterminadas:** Ticketyn rechaza tajantemente la inclusión de contraseñas por defecto ("admin/admin") o credenciales preconfiguradas en el código fuente o en scripts SQL de migración.
3. **Separación de responsabilidades:** El updater es un mecanismo técnico de despliegue y rollback automático; la creación del primer superadministrador es un acto administrativo con control y responsabilidad de credenciales.
4. **Idempotencia post-actualización:** Tras cualquier actualización futura (ej. v0.7.0 a v0.7.1), el updater volverá a correr migraciones y servicios, mientras que el bootstrap detectará el superadmin existente y no realizará ninguna acción.
