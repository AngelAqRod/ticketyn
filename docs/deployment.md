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

La aplicación no tiene autenticación ni autorización individual. Restringe acceso
mediante red controlada, VPN, firewall o proxy con control de acceso; no la expongas
directamente a Internet. HTTPS y la protección externa son responsabilidades de
la instalación. Ocultar Swagger no protege los endpoints.

## Primera instalación

Desde una copia de confianza del repositorio, selecciona primero el tag revisado
que quieras instalar; no utilices una rama de desarrollo sin validarla.

```bash
git clone https://github.com/AngelAqRod/ticketyn.git
cd ticketyn
# Seleccionar y revisar la versión antes de continuar.
sudo ./install.sh
```

El instalador requiere acceso a los repositorios de paquetes y dependencias.
Crea servicio y usuario del sistema, base y rol PostgreSQL locales, configuración
privada y frontend estático. Solicita el puerto HTTP (80 por defecto), valida
conflictos y reserva los puertos de backend y PostgreSQL.

Las credenciales se generan y conservan fuera del repositorio. La base utiliza
UTF-8 y las convenciones de colación requeridas por el proyecto. Python instala
las dependencias fijadas en `requirements.lock` y el paquete no editable.

El instalador no sobrescribe indiscriminadamente instalaciones, releases ni sitios
Nginx desconocidos. Una instalación completada se actualiza con el updater, no
repitiendo `install.sh`. Solo puede reanudarse una instalación interrumpida cuando
las evidencias de identidad y estado permiten hacerlo de forma segura.

No borres bases, releases ni `/etc/ticketyn/install-state` para eludir un bloqueo.
Si la identidad de un recurso es ambigua, diagnostica antes de continuar. Evita
operaciones administrativas simultáneas y modificaciones concurrentes de servicios.

Después de instalar, verifica servicio, interfaz, una consulta real a PostgreSQL
y revisión Alembic. `/health` solo confirma respuesta HTTP; no certifica la base.
La documentación FastAPI del backend está en `/docs`, `/redoc` y `/openapi.json`,
pero esas rutas no se publican por defecto mediante el proxy de producción.

## Migraciones

La aplicación no migra al arrancar. El instalador y actualizador coordinan las
migraciones correspondientes a la versión elegida. No ejecutes Alembic manualmente
sobre una instalación operativa como sustituto de esos flujos.

El HEAD del código revisado es `0024_default_change_types_upper`, posterior a
`0021_internal_tickets`, `0022_change_control` y `0023_change_types`. Las guías
antiguas que indican otro HEAD describen su versión, no el esquema actual.

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
El updater requiere instalación administrada o adoptada válida, servicio saludable
y ausencia de operaciones pendientes de actualización o restauración.

Prepara la release y entorno Python, verifica artefactos y crea backup obligatorio.
Luego detiene/deshabilita temporalmente el servicio, aplica migraciones hacia delante,
activa `current` y comprueba API, base y archivos del frontend antes de concluir.
Conserva checkpoints en `/etc/ticketyn/update-state` y archiva operaciones completadas.
La confianza en repositorio y tags no equivale a verificación de firmas digitales.

### Si una actualización falla

No hay rollback automático. Después de comenzar una migración, **no cambies a
ciegas al código anterior**, no ejecutes downgrade ni edites los archivos de estado.
El servicio puede quedar detenido y deshabilitado para evitar código/esquema incompatibles.

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

- [Desarrollo local](development.md): comandos para bases de desarrollo.
- [Módulos](modules.md): reglas y exportaciones disponibles.
- [Actualización v0.3.0](upgrading-v0.3.0.md): referencia específica histórica,
  no procedimiento general para cualquier versión.
