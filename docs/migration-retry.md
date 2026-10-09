# Reintentar una actualización fallida durante migración

`ticketyn-update --retry-migration` es una autorización administrativa explícita.
No es un force, un downgrade, un restore ni un mecanismo para saltarse evidencia.
Su destino es exclusivamente la candidata ya registrada y preparada por el updater.
No necesita otro checkout para ejecutarse.

## Alcance y condiciones

Solo admite una operación v2 normal (o un reintento enlazado) con fase `migrating`
y resultado `interrupted_or_failed`, checkpoints íntegros, DB en la revisión de
origen, `current` original y releases intactas. Comprueba también instalación
administrada/adoptada, OID, cluster, propietario/UTF8, configuración, unidad y Nginx,
backup y linaje único Alembic. No basta con coincidir `alembic_version`.

El servicio debe estar detenido y deshabilitado, sin listener en 8000. **Invocarlo
con Ticketyn funcionando rechaza la operación sin detenerlo ni deshabilitarlo.**
No realizar cambios administrativos concurrentes en DB, configuración, releases,
servicios o evidencias. El lock serializa los scripts, no acciones externas de root.

Compara el DDL del dump original con un dump schema-only read-only de PostgreSQL
actual, renderizados con pg_restore. Solo normaliza las cabeceras generadas de
versión y claves restrict del prólogo/pie: conserva SQL, propietarios, ACL, tipos,
constraints, índices, vistas, funciones, triggers, comentarios y definiciones de
secuencias. Se exige el mismo major de pg_dump que produjo el backup.

La primera implementación solo admite la extensión integrada `plpgsql` versión
1.0. Extensiones adicionales tienen objetos internos omitidos por pg_dump y se
rechazan. Diferencias de formato o herramientas no reconocidas también se rechazan;
no se añade ninguna opción para ignorarlas. La comparación mide equivalencia del
DDL, no identidad física de cada objeto/OID, contenido de filas ni valores actuales
de secuencias. Los datos posteriores al backup pueden permanecer y **no se restauran**.
No puede demostrar ausencia de efectos externos o transformaciones de datos de una
migración arbitraria: revisar el diagnóstico y las migraciones antes de autorizar.

## Provisionar la herramienta aprobada

Después de revisar, probar y distribuir por un canal de confianza esta versión
completa del updater, ejecutar **como root** en el servidor de destino:

```bash
python3 -I -B /ruta/absoluta/fuente-aprobada/deploy/install_updater.py \
  /ruta/absoluta/fuente-aprobada
```

Este paso publica atómicamente el bundle completo root-owned y el lanzador instalado;
no migra la DB ni cambia current, configuración o servicios. No ejecutar install.sh
para reparar una instalación existente ni modificar el bundle a mano. No sustituir
archivos de la release activa con el código del updater nuevo.

## Procedimiento durante una ventana autorizada

1. Conservar diagnóstico, `update-state`, `update-evidence`, releases y backup original.
   Revisar fase/resultado, target y revisión real; validar hashes del respaldo.
2. Revisar la causa de fallo y las migraciones. Si hay duplicados, resolverlos mediante
   una decisión autorizada, sin merges, borrados ni reasignaciones automáticas.
3. Detener/deshabilitar explícitamente el servicio, solo cuando se autorice mantenimiento:

```bash
systemctl disable ticketyn
systemctl stop ticketyn
systemctl show --property=ActiveState --property=UnitFileState ticketyn
ss -H -ltn 'sport = :8000'
ticketyn-update --retry-migration
```

4. Escribir sin comillas la confirmación `REINTENTAR MIGRACION`; Enter cancela.
5. El comando verifica las evidencias, genera y valida **otro backup obligatorio**,
   revalida el esquema y publica una operación hija `kind=migration_retry` con
   `parent_operation_id`. La operación original se archiva como fallida exactamente
   como estaba, con su checkpoint y diagnóstico. No se sobrescriben backups ni releases.
6. Solo entonces vuelve a migrar mediante el código/venv de la candidata. Activa current
   atómicamente y verifica servicio, loopback, frontend/assets, health y API mediante
   Nginx. Habilita autostart únicamente después de todas las verificaciones.
7. Confirmar current, HEAD previsto, registros existentes, API/UI y reportes. Revisar
   `update-history`: padre fallido e hijo completo. Conservar todos los backups/releases.

La provisión y estos comandos son instrucciones para un despliegue posterior;
las pruebas de desarrollo no ejecutan nada en producción.

## Interrupciones y fallos

La transición tiene una intención privada durable en
`/etc/ticketyn/migration-retry-transitions/<operación-padre>.json`, con hashes e inodes.
Se prepara/valida el estado hijo y se intercambia atómicamente con `update-state`;
nunca existe una ventana sin estado activo. Los estados intercambiados se conservan
privados como evidencia; no hay retención ni eliminación automática.

- Antes del intercambio: el padre sigue bloqueando; otra llamada verifica y utiliza
  la transición preparada. Puede haber backups/temporales privados huérfanos si se
  corta antes de publicar la intención; no se borran artefactos persistentes a ciegas.
- Después del intercambio, antes de DDL: se reconoce el hijo `prepared` y se repiten
  las comprobaciones y confirmación. Se conserva el segundo backup ya validado.
- Después de registrar una migración fallida: solo otro esquema de origen demostrado
  permite un nuevo reintento enlazado. Si hay DDL parcial, rechaza.
- Después de migración completada registrada: puede reanudar únicamente la activación
  del mismo candidato con DB/identidades/checkpoints demostrados y servicio detenido.
  No repite migraciones. Una release posterior puede usar forward recovery existente.
- Después del checkpoint `complete`, antes del archivado: una nueva llamada verifica
  la instalación saludable y completa el archivado sin migrar ni reiniciar servicios.
- Después de archivar: otra llamada informa que no hay operación pendiente, sin cambios.
- SIGKILL/pérdida de energía en `migrating` con resultado `pending` no se interpreta
  como fallo confirmado: requiere diagnóstico administrativo. No editar checkpoints
  ni cambiar result/fase manualmente para permitirlo.

Un nuevo fallo sensible deja Ticketyn detenido/deshabilitado y conserva el estado.
Ante ambigüedad, no cambiar current a mano ni ejecutar downgrade. Las credenciales
no aparecen en argumentos, salida o estado; el acceso a PostgreSQL usa peer local.
La evidencia protegida no pretende resistir a un administrador root malicioso capaz
de alterar a la vez los archivos y PostgreSQL.
