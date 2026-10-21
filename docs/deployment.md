# Instalación y administración

El aprovisionamiento y recuperación independientes de claves se describen en
[Gestión de secretos](secrets-v0.6.0.md). El backup general no contiene esas claves.

Esta guía describe las herramientas existentes. No implica que una versión esté
lista para tu entorno: revisa el código, la versión elegida y valida en laboratorio.
Los comandos administrativos modifican servicios o datos cuando se ejecutan;
no forman parte de una simple consulta de documentación.

## Entorno soportado

El instalador admite Debian 12/13 y Ubuntu 24.04 con systemd. Puede ejecutarse en
una máquina física, VM o contenedor compatible; no instala una imagen completa.
Un entorno de desarrollo en otra distribución no implica soporte del instalador.

Nginx sirve el frontend compilado y dirige `/api/` y `/health` a Uvicorn en
`127.0.0.1:8000`. PostgreSQL es local. La instalación usa `frontend/dist/`
versionado: no necesita Node/npm en producción.

| Ruta | Uso |
|---|---|
| `/opt/ticketyn/releases/<version>` | Código y entorno de cada release instalada. |
| `/opt/ticketyn/current` | Enlace a la release activa. |
| `/etc/ticketyn/ticketyn.env` | Configuración privada, root y modo 0600. |
| `/var/backups/ticketyn` | Backups privados, directorio modo 0700. |
| journald | Registros del servicio. |

Ticketyn v0.7.0 incorpora inicio de sesión y autorización granular en el backend,
con denegación por defecto. Los Responsables son los usuarios: el acceso se
habilita sobre su identidad existente, sin crear un catálogo paralelo de personas.
Restringe además el acceso mediante red controlada, VPN, firewall o proxy; la
autenticación no sustituye esos controles. El instalador configura HTTP, no HTTPS:
configura TLS y la protección del entorno antes de exponer el servicio.
Ocultar Swagger no protege los endpoints.

Las sesiones utilizan tokens opacos y se mantienen en RAM del backend, no en
PostgreSQL. Es obligatorio un único trabajador HTTP y una sola instancia del
backend; la unidad systemd del código actual utiliza `--workers 1`. No aumentes
workers ni despliegues réplicas para escalar. Reiniciar el backend invalida las
sesiones y exige iniciar sesión nuevamente. Se mantienen treinta minutos de
inactividad y un máximo de cinco sesiones simultáneas por Responsable.

## Primera instalación

Utiliza una copia de confianza del instalador y sus auxiliares. El instalador
actual consulta `/releases/latest` del repositorio público oficial en GitHub,
rechaza borradores y prereleases, y anuncia el tag estable exacto `vX.Y.Z` elegido.
Descarga el archivo fuente asociado a ese tag y comprueba su identidad contra
`pyproject.toml`, su contenido y el frontend precompilado. No instala la rama del
checkout desde el que se ejecuta ni sus cambios locales sin publicar.

```bash
git clone https://github.com/AngelAqRod/ticketyn.git
cd ticketyn
# Revisar el instalador y sus auxiliares antes de ejecutarlos con privilegios.
sudo ./install.sh
```

La selección requiere Python 3.11 o posterior instalado previamente y acceso
HTTPS a GitHub; después se requiere acceso a paquetes y dependencias. Errores de
red, HTTP, rate limiting, metadatos inválidos o descarga incompleta detienen el
flujo: no hay fallback a una rama ni a otra versión. La selección automática no
significa que v0.7.0 ya esté publicada: se instala la release estable pública que
GitHub indique en ese momento, que puede ser anterior y no incorporar autenticación.

Crea servicio y usuario del sistema, base y rol PostgreSQL locales, configuración
privada y frontend estático. Solicita el puerto HTTP (80 por defecto), valida
conflictos y reserva los puertos de backend y PostgreSQL.

Las credenciales de PostgreSQL se generan y conservan fuera del repositorio; las
del primer Superadministrador se solicitan al operador cuando corresponde. La base utiliza
UTF-8 y las convenciones de colación requeridas por el proyecto. Python instala
las dependencias fijadas en `requirements.lock` y el paquete no editable.

El instalador no sobrescribe indiscriminadamente instalaciones, releases ni sitios
Nginx desconocidos. Una instalación completada se actualiza con el updater, no
repitiendo `install.sh`. Solo puede reanudarse una instalación interrumpida cuando
las evidencias de identidad y estado permiten hacerlo de forma segura. En ese caso
descarga de nuevo el tag registrado de la instalación parcial, no otra release
más reciente; verifica que su identidad y contenido sigan coincidiendo.

### Inicialización del primer Superadministrador

El instalador y el updater utilizan `deploy/install_security.py` para verificar
las capacidades del paquete: conexión de la seguridad y del login en el código,
dependencias de las migraciones 0030–0032 y contratos del bootstrap ejecutable.
No deciden solo por el número de versión o por la existencia de un archivo.
Una release antigua sin autenticación omite el bootstrap; un paquete de seguridad
incompleto se rechaza, sin degradarse a una instalación sin protección.

En una instalación nueva con autenticación, el orden es:

1. Preparar código, entorno Python, PostgreSQL y configuración privada.
2. Aplicar Alembic y comprobar que la base alcanzó el HEAD de la release elegida.
3. Publicar `current` y ejecutar el bootstrap de esa release con
   `--config /etc/ticketyn/ticketyn.env`, antes de configurar e iniciar los nuevos servicios.
4. Consultar `--check`: si no existe Superadministrador, abrir el asistente en una
   terminal interactiva; si ya existe uno válido, no solicitar nuevas credenciales.
5. Repetir la comprobación administrativa, iniciar servicios y verificar la instalación.

El asistente solicita nombre de usuario, nombre para el catálogo de Responsables
y contraseña con confirmación, sin mostrarla en la terminal ni pasarla por argumentos.
Conserva Argon2id y exige cambiar la contraseña temporal en el primer inicio de
sesión. El Superadministrador inicial queda activo, con acceso y
`operational_selectable=false`; no necesita aparecer en asignaciones operativas.
Una cuenta válida existente no se duplica ni cambia su contraseña. Las
inconsistencias se rechazan sin reparación automática ni promoción de históricos.

Un error o interrupción conserva la instalación parcial y distingue preparación
técnica de inicialización administrativa. No se anuncian servicios listos ni se
inician los nuevos servicios si falta confirmar el Superadministrador. Utiliza la
ruta exacta de bootstrap indicada en el diagnóstico; si `current` ya apunta a la
release preparada, puedes comprobar e inicializar manualmente así:

```bash
sudo /opt/ticketyn/current/bootstrap-superadmin.sh --config /etc/ticketyn/ticketyn.env --check
# Solo si la comprobación indica que no existe Superadministrador (código 3):
sudo /opt/ticketyn/current/bootstrap-superadmin.sh --config /etc/ticketyn/ticketyn.env
sudo /opt/ticketyn/current/bootstrap-superadmin.sh --config /etc/ticketyn/ticketyn.env --check
```

Después reejecuta el mismo instalador confiable para completar servicios y
verificaciones. Un administrador creado antes de un fallo posterior permanece;
la reejecución lo comprueba sin recrearlo. Ante errores de base o migraciones,
resuelve primero la preparación técnica; no omitas validaciones ni borres estado.

No borres bases, releases ni `/etc/ticketyn/install-state` para eludir un bloqueo.
Si la identidad de un recurso es ambigua, diagnostica antes de continuar. Evita
operaciones administrativas simultáneas y modificaciones concurrentes de servicios.

Después de instalar, verifica servicio, interfaz, una consulta real a PostgreSQL
y revisión Alembic. `/health` solo confirma respuesta HTTP; no certifica la base.
El instalador exige el JSON `{"status":"ok"}`, compara frontend y assets y
comprueba que Uvicorn solo escuche en `127.0.0.1:8000`. Con autenticación exige
HTTP 401 en `/api/customers` sin credenciales y repite `bootstrap --check` para
validar el estado administrativo y la conexión PostgreSQL. Sin autenticación
espera una lista JSON de clientes. No crea sesiones para estas comprobaciones.
Comprueba además manualmente login, cambio inicial de contraseña y una consulta
autorizada desde la interfaz.
La documentación FastAPI del backend está en `/docs`, `/redoc` y `/openapi.json`,
protegidas por autenticación y permisos en v0.7.0; esas rutas no se publican por
defecto mediante el proxy de producción.

## Migraciones

La aplicación no migra al arrancar. El instalador y actualizador coordinan las
migraciones correspondientes a la versión elegida. No ejecutes Alembic manualmente
sobre una instalación operativa como sustituto de esos flujos.

El HEAD del código local revisado es `0032_responsible_selectable`, posterior a
`0029_mail_requests`, `0030_security_foundation` y `0031_role_permissions`.
La revisión 0030 añade seguridad a los Responsables existentes con acceso
deshabilitado inicialmente; no crea automáticamente un Superadministrador.
La 0032 conserva la disponibilidad operativa de los registros previos con
`operational_selectable=true`. Las referencias e identidades históricas se conservan.
Compara siempre la base con el HEAD del paquete realmente instalado: una release
anterior puede tener otro HEAD. Las guías antiguas describen su versión.

Los upgrades antiguos pueden incluir recuperaciones puntuales de datos. Por ejemplo,
la recuperación histórica de Nodo en v0.4.1 se apoyaba en que el nodo del circuito
no hubiera cambiado: no debe interpretarse como una regla actual para reconstruir
historial desde el circuito. Revisa las notas de la versión de origen y destino.

## Copias de seguridad

Como root, desde una fuente administrativa de confianza:

```bash
./backup.sh
```

Usa PostgreSQL local y no detiene la aplicación. Publica atómicamente un TAR privado
con dump PostgreSQL, configuración, metadatos, manifiesto y sumas de comprobación.
No incluye el código: conserva también la release compatible.
En v0.7.0 el dump incluye identidades, hashes de contraseña, roles y auditoría;
no incluye sesiones RAM. Protege esos datos como información sensible y respalda
las claves de correo por separado, como indica la guía de secretos.

- El archivo contiene credenciales y **no está cifrado**. Protégelo dentro y fuera
  del servidor; las sumas detectan alteraciones, no autentican su procedencia.
- No incluye roles globales, Nginx, systemd, WAL ni recuperación a un instante (PITR).
- No hay retención ni eliminación automática. Reserva espacio para dump, TAR y
  copias de trabajo, y comprueba periódicamente una restauración en laboratorio.
- No ejecutes migraciones simultáneamente. Un backup fallido o temporal no equivale
  a un archivo publicado correctamente.

Inspecciona únicamente archivos confiables en un directorio privado: verifica
manifiesto y sumas; `pg_restore --list` permite revisar el índice del dump sin
restaurarlo. No publiques el contenido de `ticketyn.env` ni sus credenciales.

## Restauración

La restauración requiere la release compatible ya activa: comprueba versión,
identidad del paquete y revisión Alembic, además de compatibilidad de versiones
mayores PostgreSQL. No descarga código, cambia `current` ni aplica migraciones.
Para recuperar una versión anterior, utiliza primero un entorno compatible,
no un restore directo sobre código de otra versión.

```bash
./restore.sh /ruta/absoluta/backup-confiable.tar
# Solo si se pretende reemplazar una base existente:
./restore.sh --replace /ruta/absoluta/backup-confiable.tar
```

Una base existente, aunque esté vacía, requiere `--replace` y confirmación explícita
`REEMPLAZAR ticketyn`. Antes de detener el servicio, el flujo exige un backup previo
correcto. Valida estructura y contenido del archivo; restaurar un dump ejecuta SQL,
por lo que la confianza en su procedencia sigue siendo necesaria.

El proceso detiene Ticketyn, restringe conexiones, restaura en una base temporal
y valida antes de intercambiar nombres. Conserva la base anterior como
`ticketyn_previous_<id>` con conexiones bloqueadas. Normaliza propiedad al rol de
Ticketyn; no promete conservar ACL personalizadas. El formato de backup v1 no
registra toda la información de colación original.

Reserva espacio para las bases anterior y restaurada, además de los backups.
Si falla después del intercambio, el servicio puede quedar detenido: conserva
`restore-state` y sus evidencias. No borres el estado, intercambies bases a mano
ni supongas que repetir el comando equivale a rollback.

Cuando existen tablas de notificaciones, el restore marca el procesador pausado
y convierte solicitudes interrumpidas PREPARING/SENDING a UNCERTAIN antes del
intercambio. Revisa pendientes y autoriza la reanudación por los controles
operativos existentes; no se deben reenviar automáticamente resultados ambiguos.

**Limitación confirmada en el código actual:** `restore.sh::restore_check_http`
todavía exige éxito anónimo y una lista en `/api/customers`, también al finalizar.
El 401 correcto de v0.7.0 hace fallar esa comprobación. No interpretes ese fallo
como prueba de pérdida de datos ni como restauración completada; conserva estado
y evidencias y resuelve la compatibilidad en laboratorio antes de usar este flujo
con autenticación. No desactives la protección para eludirlo.

### Finalizar una restauración verificada

Después de comprobar datos, interfaz y servicio:

```bash
./restore.sh --finalize
```

Revalida identidad de bases, release y backup; exige `FINALIZAR RESTAURACION`.
Elimina **solo la base anterior registrada** cuando existe, conserva los backups
y archiva el estado en `restore-history`. No migra, reinicia ni fuerza conexiones.
También permite cerrar un restore verificado que no tenía base previa.
Un restore fallido o incoherente requiere diagnóstico, no finalización forzada.

## Actualizaciones

En una instalación administrada, utiliza como root:

```bash
ticketyn-update <tag-revisado>
# Alternativa desde una fuente de confianza:
./update.sh <tag-revisado>
```

Sustituye el marcador por un tag explícito y aprobado para tu entorno. No existe
selección `latest` ni actualización mediante `git pull` de la release activa.
Se admiten avances de versión compatibles dentro de la misma versión mayor;
se rechazan downgrade, misma versión y destinos ya ocupados.

El comando instalado se vincula a herramientas administrativas verificadas en
`/opt/ticketyn/admin/updater/`, independientes de `current`. Para provisionarlo
en una instalación anterior compatible, desde fuentes confiables:

```bash
python3 -I -B deploy/install_updater.py /ruta/absoluta/a/fuentes-confiables
```

Ese paso publica herramientas; no actualiza la aplicación, migra ni reinicia.
Para actualizar desde v0.6.2 a una release con autenticación, utiliza el updater
corregido y todos sus auxiliares de una fuente confiable, incluido
`deploy/install_security.py`. El bundle previamente instalado no se actualiza
solo por elegir un tag nuevo; no copies únicamente `update.sh` o un auxiliar.
El provisionador valida los inventarios antiguos y actuales y conserva los bundles
anteriores. Alternativamente, ejecuta `./update.sh` desde la copia confiable completa.
El updater requiere instalación administrada o adoptada válida, servicio saludable
y ausencia de operaciones pendientes de actualización o restauración.

Prepara la release y entorno Python, verifica artefactos y crea backup obligatorio.
Luego detiene/deshabilita temporalmente el servicio, aplica migraciones hacia delante,
activa `current` y comprueba API, base y archivos del frontend antes de concluir.
Conserva checkpoints en `/etc/ticketyn/update-state` y archiva operaciones completadas.
La confianza en repositorio y tags no equivale a verificación de firmas digitales.

### Actualización a una release con autenticación

El updater conserva `bootstrap-superadmin.sh` del paquete seleccionado, incluidos
sus bytes y permiso ejecutable; rechaza enlaces y distribuciones de seguridad
incompletas. Las releases antiguas no están obligadas a incluir ese script.

La actualización sigue dividida en dos fases:

1. **Actualización técnica:** dependencias, migraciones, activación y verificaciones.
   Comprueba `/health` con `{"status":"ok"}` y HTTP 401 anónimo en `/api/customers`
   cuando detecta autenticación; para releases anteriores espera una lista JSON.
   También valida servicios, frontend, assets, socket local y `current`. No inicia
   sesión ni ejecuta el bootstrap, tampoco `--check`.
2. **Inicialización administrativa manual:** después de confirmar el éxito técnico,
   ejecuta los comandos de comprobación y bootstrap indicados arriba. Código 0
   significa que ya existe un Superadministrador válido; código 3, que debe crearse.
   Código 1 indica inconsistencias y código 2 errores de configuración o conexión:
   requieren diagnóstico, no modificaciones improvisadas de roles o contraseñas.

El mensaje «inicialización administrativa pendiente de comprobación manual» no
afirma que falte la cuenta: el updater no la consulta. Su ausencia no es por sí
sola un fallo técnico de actualización, pero impide considerar el sistema listo
para los operadores. Los Responsables históricos no reciben credenciales ni
acceso automáticamente; después del primer login se administran los accesos
autorizados desde su pantalla existente. Verifica el cambio de contraseña temporal,
las consultas permitidas y los rechazos de operaciones no autorizadas.

### Si una actualización falla

No hay rollback automático. Después de comenzar una migración, **no cambies a
ciegas al código anterior**, no ejecutes downgrade ni edites los archivos de estado.
El servicio puede quedar detenido y deshabilitado para evitar código/esquema incompatibles.
Esto incluye un fallo de salud después de migrar a autenticación: revertir solo
`current` no revierte PostgreSQL. Volver a código sin autenticación puede exponer
operaciones sin protección y no constituye una recuperación segura demostrada.

- Un fallo previo a migración puede admitir reintento con el mismo tag si las
  evidencias son coherentes. Un proceso interrumpido de estado ambiguo requiere diagnóstico.
- `ticketyn-update --abort` abandona únicamente un fallo confirmado previo al
  límite de migración y con checkpoints seguros. Archiva evidencia, no restaura
  ni modifica datos y no reinicia un servicio detenido. No elimina releases o backups.
- `ticketyn-update --recover <tag-posterior-revisado>` permite recuperación hacia
  delante bajo sus comprobaciones: servicio detenido, identidad consistente,
  backup nuevo y conservación de la operación fallida. No es una opción de fuerza.
- [Reintento administrativo de migración](migration-retry.md) explica
  `--retry-migration`: exige demostrar que revisión **y DDL** siguen en el origen,
  conserva la operación anterior y crea otro backup. No basta con mirar Alembic.

No borres evidencias ni uses un restore como supuesto paso automático de actualización.

## Adopción de una instalación manual antigua

`adopt.sh` es una herramienta restringida a la instalación manual histórica
**v0.1.0**, commit `5d478abc97ffa18bb5293b96dfedc8649e89a013`, con Alembic
`0004_nodes_responsibles` y layout compatible en `/opt/ticketyn`.
No es un importador genérico de instalaciones manuales actuales.

Comprueba identidad del código, servicio, Nginx, base local, permisos y configuración
antes de registrar la adopción. Se ejecuta como root desde fuentes confiables;
no descarga código, migra ni reinstala. No existe una opción para ignorar esas
verificaciones. Conserva su recibo y utiliza después el flujo administrado.

## Referencias

- [Selección e instalación de releases](installer-latest-stable.md).
- [Bootstrap del primer Superadministrador](bootstrap-superadmin-v0.7.0.md).
- [Updater y autenticación](updater-authentication-v0.7.0.md).
- [Responsables, acceso y sesiones](security-administration-v0.7.0.md) y
  [autorización](security-authorization-v0.7.0.md).
- [Desarrollo local](development.md): comandos para bases de desarrollo.
- [Módulos](modules.md): reglas y exportaciones disponibles.
- [Actualización v0.3.0](upgrading-v0.3.0.md): referencia específica histórica,
  no procedimiento general para cualquier versión.
