# Updater y autenticación — Ticketyn v0.7.0

## Alcance y estado

Corrección preparatoria del updater para releases con autenticación. Mantiene
la selección manual del tag público, origen oficial, validación de identidad,
backup previo, Alembic, activación atómica de `current` y recuperación existente.
No selecciona automáticamente la última release: esa función es del instalador.

La versión oficial del repositorio continúa en **0.6.2**. Estos cambios no publican
v0.7.0 ni autorizan instalaciones o actualizaciones reales. Los comandos de esta
guía son instrucciones para una futura operación expresamente autorizada.

## Incompatibilidades corregidas

1. `Updater.healthy` utilizaba `curl -f` y esperaba una lista de clientes mediante
   acceso anónimo. En v0.7.0 ese acceso devuelve 401 por diseño y provocaba un
   falso fallo después de aplicar migraciones y activar la release.
2. La lista positiva de extracción no incluía `bootstrap-superadmin.sh` en la
   raíz. El módulo Python sí podía estar instalado, pero faltaba el script
   administrativo documentado.

## Detección compartida y paquete

El updater reutiliza `deploy/install_security.py`, el mismo detector del
instalador, sin modificarlo. Se utiliza el helper de la herramienta confiable que
se ejecuta, no se importa el helper descargado del candidato.

Analiza el código mediante AST: instalación de seguridad y router de login,
metadatos de las migraciones 0030–0032 con sus dependencias y contratos de la CLI
bootstrap. No accede a PostgreSQL ni depende únicamente del nombre de un archivo
o del número de versión. Las releases anteriores sin autenticación conservan su
tratamiento; las distribuciones parciales se rechazan sin fallback inseguro.

La extracción permite opcionalmente el archivo raíz `bootstrap-superadmin.sh`.
Mantiene los controles contra rutas inseguras, enlaces simbólicos y duros, tipos
especiales y duplicados. Conserva los bytes originales y el permiso ejecutable:
0700 durante preparación privada y 0755 tras la publicación de permisos. El
script participa en `release_hashes`, verificación del destino y snapshots de
recuperación. Una release autenticada sin script compatible se rechaza antes de
backup, migración y activación; las antiguas no están obligadas a incluirlo.

Se vuelve a comprobar la capacidad al verificar el destino y la salud; no se
ejecuta el bootstrap para decidir compatibilidad.

### Bundle administrativo independiente

`deploy/install_updater.py` incorpora el detector compartido al bundle del updater.
Era una dependencia indispensable: el comando administrativo debe funcionar sin
el checkout original ni depender del contenido de `current`.

La validación admite exactamente dos inventarios conocidos del manifiesto v1:
los cinco archivos originales o los seis actuales, incluido el detector. Esto
permite verificar y reemplazar un bundle anterior sin desconocer su identidad.
Los bundles anteriores se conservan; las sumas y las comprobaciones de permisos
siguen aplicándose y no se aceptan listas arbitrarias de archivos.

**Una herramienta v0.6.2 ya instalada no obtiene estas correcciones por elegir
un tag v0.7.0.** Debe ejecutarse la copia revisada del updater que contiene esta
corrección, con todos sus auxiliares. No copiar solamente `update.sh` o
`update_support.py`. Tampoco asumir que el comando `ticketyn-update` previamente
instalado se actualiza solo.

## Verificaciones técnicas

- Servicio Ticketyn y Nginx activos.
- `GET /health` público: HTTP exitoso y JSON exactamente `{"status":"ok"}`.
- Release autenticada: `GET /api/customers` anónimo debe devolver **401**. Se
  descarta su cuerpo y se comprueba el código; un 200, 403 o 5xx no cumple el
  contrato. Los errores transitorios siguen los reintentos existentes.
- Release anterior: se conserva HTTP exitoso con lista JSON de clientes.
- Frontend y assets corresponden a la release; backend solo en 127.0.0.1:8000 y
  `current` apunta al destino verificado.

No se inicia sesión, no se pasan contraseñas ni tokens y no se ejecuta el
bootstrap, ni siquiera en modo `--check`. `/health` no certifica por sí mismo la
base: la revisión Alembic y las migraciones se validan en el flujo técnico previo.
El estado de la cuenta administrativa queda para el paso manual independiente.

## Dos fases de operación

### 1. Actualización técnica

Cuando se publique y autorice v0.7.0, desde la copia confiable revisada que
contiene este updater y sus auxiliares:

```bash
sudo ./update.sh v0.7.0
```

La herramienta obtiene ese tag exacto, prepara dependencias y esquema, activa y
verifica la release. No solicita credenciales ni crea un Superadministrador. La
ausencia de la primera cuenta no causa un fallo de salud: el 401 anónimo esperado
permite completar técnicamente la actualización.

Al terminar con autenticación se informa:

- Actualización técnica completada.
- Inicialización administrativa **pendiente de comprobación manual**: no implica
  que se haya consultado la base ni que se haya demostrado ausencia de la cuenta.
- Comandos para comprobar y, solo cuando corresponda, inicializar.

El aviso también se conserva al cerrar un checkpoint ya completado o una
recuperación/reintento de migración exitoso. No agrega estados, tablas o acciones
automáticas sobre cuentas.

### 2. Inicialización administrativa manual

Después de una actualización técnica confirmada:

```bash
sudo /opt/ticketyn/current/bootstrap-superadmin.sh --check
```

- Código 0: existe un Superadministrador válido; no se necesita creación.
- Código 3: no existe; ejecutar explícitamente el asistente:

  ```bash
  sudo /opt/ticketyn/current/bootstrap-superadmin.sh
  sudo /opt/ticketyn/current/bootstrap-superadmin.sh --check
  ```

- Código 1 o 2: revisar inconsistencias/configuración/DB; no reparar ni promover
  cuentas mediante SQL o automatismos.

El script original localiza el venv de la release y la configuración privada
`/etc/ticketyn/ticketyn.env`. Las contraseñas se solicitan sin argumentos CLI.
Una cuenta válida existente no se modifica. Se mantiene la identidad única en
`responsibles`, Argon2id, cambio obligatorio inicial y disponibilidad operativa
desactivada para el Superadministrador inicial. Ver la [guía del bootstrap](bootstrap-superadmin-v0.7.0.md).

Estos comandos no se ejecutaron sobre instalaciones reales en esta tarea. Una
reejecución normal del updater con la misma versión ya instalada no es un reenvío
del bootstrap: se conservan las restricciones de avance y checkpoints existentes.

## Fallos después de migrar

El límite durable `migrating` sigue registrándose antes de cualquier DDL. Si la
actualización falla desde ese límite, el manejo existente intenta detener y
deshabilitar Ticketyn, conserva release origen/destino, backup y `update-state`.
No aplica downgrade, no restaura la base automáticamente y no revierte `current`
como si eso restaurara el esquema.

Un fallo de salud posterior puede dejar `current` en la nueva release y la base
en 0032. También puede existir una interrupción anterior con `current` todavía
en la release vieja y la DB ya migrada. **No habilitar el servicio ni cambiar el
enlace a código anterior sin demostrar compatibilidad con la base.** No se
garantiza que v0.6.2 sea compatible con cualquier estado posterior de seguridad.

Los reintentos normales desde fases ambiguas permanecen rechazados. Diagnosticar
el checkpoint, esquema y backups y elegir una recuperación compatible conforme
a los procedimientos existentes (`--recover` / `--retry-migration` cuando cumplan
sus condiciones). No borrar el estado ni improvisar una restauración/downgrade
en una instalación existente. Un cambio de enlace no es recuperación completa.

## Validación y límites

`tests/test_update_authentication.py` cubre paquetes autenticados y legacy,
bootstrap original/ejecutable, paquetes incompletos y enlaces, salud 401,
reintentos transitorios y separación de la inicialización manual. Incluye
migraciones reales 0029 → 0032 sobre PostgreSQL descartable, preservación del
Responsable histórico, ausencia de cuentas creadas por el updater y fallo
posterior a migración con servicio detenido y DB nueva conservada. En esos
escenarios se simulan servicios, red, preparación Python y archivo de backup;
no equivalen a una actualización real completa de producción.

Las regresiones existentes cubren backup, identidad, recuperación y reintentos;
se ejecutan también las pruebas del instalador. Los resultados finales se
registran en `AGENT_HANDOFF.md`.

Antes de publicar falta un ensayo integral autorizado en VM descartable
Debian/Ubuntu con el artefacto definitivo, updater corregido, unidad monoproceso,
backup/restauración y bootstrap manual. No se modifican instalador, autenticación,
bootstrap, versión oficial ni migraciones en esta corrección. No se incorpora
soporte de repositorios privados.
