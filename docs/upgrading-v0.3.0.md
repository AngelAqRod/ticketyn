# Actualización de v0.2.0 a v0.3.0

Este procedimiento se ejecutará **después de publicar y verificar el tag oficial
v0.3.0**, sobre una instalación administrada de confianza. Esta preparación no
actualiza ningún servidor. Probar primero en Debian de laboratorio con datos ficticios.
Ticketyn sigue sin autenticación: mantener acceso restringido a redes confiables.

## Preparación y respaldo

1. Verificar versión activa 0.2.0, servicio saludable, configuración segura y ausencia
   de `update-state`/`restore-state` pendientes. No modificar archivos concurrentemente.
2. Ejecutar como root `/opt/ticketyn/current/backup.sh`. Su TAR privado contiene
   dump lógico PostgreSQL, `ticketyn.env`, metadatos, manifiesto y hashes SHA-256.
   Conservar el backup y comprobar sus hashes en un directorio privado al extraerlo.
3. Conservar la release anterior, el tag correspondiente y los archivos locales
   de despliegue necesarios (unidad systemd y sitio Nginx). Estos últimos no están
   incluidos en el TAR: respaldarlos con permisos restrictivos si fueron personalizados.
   No imprimir ni compartir el env o el contenido del backup.
4. Revisar los ocho catálogos para nombres equivalentes según
   `lower(btrim(name) COLLATE "C.utf8")`; puestos se agrupan por departamento.
   Revisar que PostgreSQL disponga de la collation `C.utf8` para UTF-8.
   No asumir que está disponible en cualquier instalación.

## Actualización administrada

Como root, desde cualquier directorio:

```bash
ticketyn-update v0.3.0
```

El updater obtiene el tag exacto, prepara una release independiente, instala las
mismas dependencias desde `requirements.lock` y el paquete no editable en su venv,
valida imports e integridad y crea **otro backup obligatorio** antes de los cambios.
No usa `git pull` sobre `current`. No sobrescribe releases previas.

El frontend se compila durante la preparación de la release (`npm ci`, `npm run build`)
y se distribuye en `frontend/dist`. Producción consume ese build: **no necesita Node/npm**
ni recompilarlo. No ejecutar un procedimiento manual paralelo que evite el updater.

El updater detiene Ticketyn, ejecuta Alembic con el venv/código nuevo, aplica
`0009 → 0010 → 0011 → 0012`, cambia `current` atómicamente y arranca el servicio.
Valida backend loopback, health, API y frontend antes de habilitar autostart.
Nginx continúa apuntando a `current`; una actualización normal no requiere recargarlo.

## Advertencias de migración

`0012_catalog_name_uniqueness.py` puede detenerse por nombres duplicados o ausencia
de `C.utf8`. Los conflictos indican tabla, IDs, nombres y departamento si corresponde.
No elimina ni fusiona registros ni modifica relaciones. Resolver los conflictos con
revisión y autorización explícita; no inventar renombres ni aplicar merges automáticos.
`0010` y `0011` pueden haber sido aplicadas antes del fallo: consultar estado durable y
revisión real antes de decidir cómo recuperar. No asumir que todo el upgrade se revirtió.
La migración toma locks de catálogos; reservar una ventana de mantenimiento.

## Validación posterior

- `readlink -e /opt/ticketyn/current`: release 0.3.0.
- `systemctl is-active ticketyn` y `systemctl is-enabled ticketyn`: activos/habilitados.
- Mediante Nginx, comprobar `/`, `/health` y `/api/customers` en el puerto configurado.
- Confirmar HEAD `0012_catalog_name_uniqueness` en el historial del updater y, con
  configuración segura verificada, mediante una consulta administrativa read-only.
- Comprobar clientes, circuitos, tickets e intervenciones anteriores; registrar y
  finalizar un escalamiento de prueba, revisar estadísticas y generar PDF/XLSX.
- Confirmar que no quedan estados pendientes y conservar ambos backups y releases.

## Recuperación ante fallos

Conservar diagnóstico, `update-state`, ambas releases y backups. No borrar el estado
ni cambiar `current` a mano para saltarse validaciones.

Antes del límite de migración, `ticketyn-update --abort` permite abandonar únicamente
un estado fallido verificable en `SAFE_RETRY`; archiva el historial y no altera DB ni
servicios. No usarlo si ya se cruzó el límite.

Después de migrar, el updater puede dejar Ticketyn detenido/deshabilitado. No basta
volver al código viejo. Una release posterior compatible puede utilizar
`ticketyn-update --recover <tag-posterior>` tras validar toda la evidencia; requiere
un nuevo backup y preserva la operación original como fallida. No existe `--force`.

No hay downgrade de esquema ni restore automático. `restore.sh` exige compatibilidad
con la versión/revisión del backup: no prometer que un TAR v0.2.0 se restaure directamente
sobre v0.3.0. Una recuperación desde backup requiere un entorno compatible, revisión
administrativa y procedimiento probado, sin descartar los datos posteriores sin autorización.
