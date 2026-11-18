# Operación de órdenes de instalación

El registro manual no requiere IMAP. El receptor es un proceso independiente del
servidor HTTP y de la cola de notificaciones de activaciones. Un correo crea una
solicitud, nunca una orden definitiva.

## Preparación y migración

1. Respaldar PostgreSQL y el directorio privado de originales como un conjunto.
2. Preparar el directorio persistente y la configuración privada.
3. Detener escrituras del backend y del receptor durante respaldo y migración.
4. Aplicar `alembic upgrade head` con el entorno de la release elegida y su
   `DATABASE_URL` explícitamente revisado. La revisión nueva es
   `0042_installation_orders`, posterior a `0041_profile_preferences`.
5. Iniciar un único trabajador HTTP y, opcionalmente, un receptor entrante.
6. Comprobar permisos con una cuenta administrativa antes de habilitar roles
   adicionales. Validar primero en un laboratorio aislado.

Estos pasos son instrucciones para el operador: la implementación y sus pruebas
no autorizan aplicar migraciones a una base compartida. El downgrade es
estructuralmente reversible, pero elimina los registros del módulo; solo debe
ejecutarse tras respaldar y aceptar explícitamente esa pérdida. No borra por sí
solo los originales del directorio privado. El vocabulario de permisos se conserva
en downgrade, siguiendo la convención histórica de seguridad; no se borran
asignaciones de roles personalizados. Las facultades de los roles integrados se
calculan en el código de la versión activa.

## Variables de entorno

| Variable | Valor predeterminado | Uso |
|---|---|---|
| `INSTALLATION_STORAGE_DIR` | `./var/installation-originals` | Directorio privado de originales; en despliegue usar ruta absoluta persistente. |
| `INSTALLATION_IMAP_HOST` | Vacío | Servidor IMAP con TLS y certificado válido. |
| `INSTALLATION_IMAP_PORT` | `993` | Puerto de IMAP sobre TLS. |
| `INSTALLATION_IMAP_USERNAME` | Vacío | Cuenta autorizada del buzón dedicado. |
| `INSTALLATION_IMAP_PASSWORD` | Vacío | Secreto suministrado fuera del repositorio. |
| `INSTALLATION_IMAP_FOLDER` | `INBOX` | Carpeta de recepción. |
| `INSTALLATION_MAX_BYTES` | `26214400` | Límite de bytes por mensaje o documento. |
| `INSTALLATION_IMAP_INTERVAL` | `60` | Intervalo entre consultas del receptor, en segundos. |
| `INSTALLATION_IMAP_BATCH_SIZE` | `100` | Límite de trabajo de cada consulta. |

Los filtros de recepción (remitentes permitidos y palabras del asunto) se editan en **Configuración → Filtros de recepción** y requieren `incoming_mail.manage`; vacíos aceptan todo. Un correo que no pasa los filtros se registra como solicitud `DISCARDED` con el motivo (sin adjuntos ni cuerpo) para no volver a leerlo. El remitente `From` puede falsificarse: el filtro reduce ruido, no sustituye la autenticación del buzón.

El receptor queda sin configurar si faltan host, usuario o contraseña. Para
desactivar la recepción, detener su proceso y retirar la configuración IMAP;
no es necesario borrar solicitudes ni documentos. El modo manual sigue disponible.
El intervalo es técnico de recepción, no un objetivo contractual de atención.

La configuración entrante se lee del entorno del proceso. Un archivo `.env`
no sustituye la exportación de estas variables al receptor. En systemd se puede
usar `EnvironmentFile=/etc/ticketyn/ticketyn.env`, protegido con modo `0600` y
propietario autorizado. No colocar secretos en argumentos, logs ni en Git.

## Directorio privado

Ejemplo de preparación por el administrador del sistema, ajustando la identidad
del servicio a la instalación real:

```sh
install -d -m 0700 -o ticketyn -g ticketyn /var/lib/ticketyn/installation-originals
```

Configurar `INSTALLATION_STORAGE_DIR=/var/lib/ticketyn/installation-originals`
en backend y receptor. Ambos deben usar **el mismo directorio y base de datos**.
No usar enlaces simbólicos, una carpeta pública, `frontend/dist/` ni un directorio
de release. No conceder lectura a Nginx ni añadir un alias estático. Revisar
capacidad disponible, permisos y política de respaldo antes de habilitar correo.

Los nombres recibidos se conservan como metadatos; no se usan como rutas. Los
originales son inmutables. Una solicitud procesada conserva los documentos en
su origen y la orden los consulta mediante ese vínculo.

## Ejecución del receptor

Con el entorno privado ya cargado y el virtualenv de la release seleccionada:

```sh
python -m ticketyn.incoming --once
python -m ticketyn.incoming
```

La primera forma procesa un lote; la segunda repite periódicamente. Supervisar
el proceso con el gestor de servicios habitual y detenerlo antes de cambiar
release, base o directorio. No añadir trabajadores HTTP ni reutilizar la cola
saliente para este fin. Las pruebas sustituyen el lector IMAP y usan PostgreSQL
efímero; no necesitan credenciales de un buzón real.

La conexión actual usa IMAP con usuario y secreto sobre TLS. Los proveedores
que exigen exclusivamente OAuth necesitan un lector compatible antes de habilitar
recepción; las credenciales OAuth salientes no se reutilizan automáticamente.
No se eliminan ni marcan como procesados los mensajes remotos por recibirlos.

## Respaldo consistente

Un `pg_dump` aislado **no contiene los documentos**. Respaldar también
`INSTALLATION_STORAGE_DIR`; la configuración privada y las claves existentes
siguen su procedimiento independiente de gestión de secretos.

Para una copia consistente:

1. Detener receptor y backend para impedir altas, cargas y procesamiento.
2. Esperar a que terminen sus escrituras.
3. Respaldar PostgreSQL y todo el directorio de originales sin modificar ninguno.
4. Registrar que ambas copias corresponden a la misma ventana y release.
5. Verificar la copia antes de reanudar servicios.

Restaurar ambos componentes del mismo conjunto, con la revisión Alembic
correspondiente y la misma configuración de almacenamiento. No mezclar una base
reciente con documentos de un respaldo anterior.

## Recuperación

Con los servicios detenidos, el entorno revisado y un respaldo disponible:

```sh
python -m ticketyn.incoming --recover
```

La recuperación comprueba documentos referenciados y limpia originales huérfanos
antiguos bajo exclusión mutua. Revisar su resultado y los registros de error;
no reemplaza recuperar un original perdido desde el respaldo. Si falta un
documento, restaurar su contenido original, no marcarlo como disponible ni borrar
su referencia para ocultar la inconsistencia.

Un fallo de recepción puede reintentarse sin crear otra solicitud gracias a la
identidad única del buzón/carpeta/UIDVALIDITY/UID. Message-ID y checksum se conservan
como evidencia; no se fusionan correos similares. Los adjuntos no admitidos se
conservan en el mensaje original y no se ejecutan ni se previsualizan como contenido
activo. Revisar los errores por límites de tamaño y capacidad de disco.

## Permisos iniciales y recomendación

| Capacidad | Administración / Superadministración | Operador (recomendación) | Auditor (recomendación) |
|---|---|---|---|
| Consultar órdenes | Concedido | Sí | Sí |
| Registrar órdenes | Concedido | Según función | No |
| Editar órdenes | Concedido | Según función | No |
| Vincular / crear desde orden / desvincular (solo órdenes sin clasificar) | Concedido | Según función y permisos de circuitos | No |
| Revisar solicitudes y borradores | Concedido | Según función | No |
| Procesar solicitudes | Concedido | Según función | No |
| Descartar solicitudes | Concedido | Según función | No |
| Administrar recepción | Concedido | No | No |

Solo la primera columna se aplica inicialmente. Las otras son propuestas, no
cambios automáticos de rol. Crear un circuito exige además la autorización
existente de creación de circuitos. La consulta de documentos siempre comprueba
acceso al origen o a la orden vinculada.

## Verificación antes de desplegar

- Revisar resultados reales de las suites, typecheck, build y `git diff --check`.
- Probar carga/descarga privada y permisos con cuentas de capacidades distintas.
- Probar un correo del proveedor real en un buzón explícitamente autorizado.
- Comprobar límites, espacio de disco, respaldo y restauración conjunta.
- Validar visualmente escritorio y móvil; una prueba DOM no certifica el render.

No se incluyen asignación de técnicos, visitas, materiales, ejecución de
instalaciones, OCR ni automatización de activaciones.

## Modalidades y migración 0045

`0045_installation_order_types` añade `order_type`, `description`, `service_type_id`,
`node_id` y `sector_id`, relaja `service`/`location` y crea el check y el trigger de
inmutabilidad. Las órdenes con circuito pasan a `NORMAL`; las demás quedan en NULL
("sin clasificar") hasta una decisión humana. Antes de aplicarla, revisar con
`SELECT count(*) FROM installation_orders WHERE circuit_id IS NULL;`. El `downgrade`
se niega si existen órdenes tipadas sin texto heredado.
