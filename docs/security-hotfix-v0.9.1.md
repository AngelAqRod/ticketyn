# Hotfix de seguridad v0.9.1 — RL-01 y SEC-02

Propuesta para revisión sobre la etiqueta v0.9.0. No aplica migraciones ni cambia
autenticación, contraseñas, roles o permisos. La numeración/publicación de la
release permanece como paso manual después de aprobar el hotfix.

## Exportaciones PDF masivas de tickets

Las cuatro rutas siguientes comparten los controles:

- `/api/tickets/export/pdf`
- `/api/internal-tickets/export/pdf`
- `/api/reports/export/pdf`
- `/api/reports/internal-tickets/export/pdf`

| Control | Límite y respuesta |
|---|---|
| Registros | Máximo 2.000 tickets coincidentes; HTTP 413 al superarlo |
| Texto | Máximo 2.000.000 de caracteres de presupuesto; HTTP 413 al superarlo |
| Concurrencia | Una generación masiva entre las cuatro rutas; HTTP 429 y `Retry-After: 5` si está ocupada |
| Frecuencia | Una solicitud admitida cada 30 segundos por ID de usuario, compartida entre rutas y sesiones; HTTP 429 con espera restante redondeada hacia arriba |

Los límites de registros y texto siguen el precedente de los PDF estadísticos
FMS. El presupuesto se calcula en PostgreSQL antes de traer los registros y
crear párrafos/tablas: incluye referencia, título, descripción, resolución,
nombres de catálogos relacionados y, en clientes, códigos y descripción de
circuito. Cuenta conservadoramente narrativas aunque el listado no las muestre,
los valores de filtros y 256 caracteres adicionales por ticket para fechas y
etiquetas. No limita bytes de salida ni pretende medir exactamente la RAM.

El filtro se evalúa sobre todos los resultados: `limit` y `offset` de pantalla
no recortan ni el documento ni las comprobaciones. Los presupuestos se leen en
el mismo snapshot de exportación. Un exceso devuelve un error explícito, nunca
un PDF parcial. El usuario debe acotar fechas o filtros.

El control de concurrencia se adquiere antes de la validación/consulta del
documento, es atómico entre hilos y se libera incluso ante excepciones. Termina
cuando el archivo está generado; no espera a que el cliente termine de descargar.
Se conserva la limpieza existente del archivo temporal en errores y descargas.
Una solicitud admitida consume su intervalo aunque falle o exceda volumen;
una rechazada por concurrencia no consume intervalo adicional.

El estado pertenece a la aplicación, en memoria del único proceso HTTP admitido
por Ticketyn. Se eliminan entradas de frecuencia caducadas al admitir solicitudes;
el reinicio elimina los intervalos. No se añaden tablas, Redis ni cambios al
almacén de sesiones. Los 30 segundos permiten uso habitual del NOC sin que una
misma cuenta pueda lanzar continuamente trabajos costosos; la exclusión global
limita la presión simultánea de distintas cuentas.

Consultas, resúmenes en pantalla, XLSX, PDF individuales, FMS y Control de Cambios
conservan sus flujos y permisos. Este hotfix no es un limitador general de API ni
una protección DDoS. Las agregaciones PostgreSQL aún consumen trabajo proporcional
al conjunto filtrado.

## Logging OAuth

El sitio Nginx usa `ticketyn_no_args` y escribe en
`/var/log/nginx/ticketyn-access.log`: IP, fecha, método, ruta normalizada sin
argumentos, protocolo, estado HTTP, bytes y duración. Se excluyen query strings
y Referer en todo el sitio, ya que un Referer también puede transportar parámetros
sensibles. El registro de accesos sigue habilitado.

El callback tiene una ubicación exacta dentro de `/api/`, con el mismo
`proxy_pass` y las cabeceras/timeouts heredados. Solo sus errores Nginx se envían
a `/dev/null`, porque `error_log` puede incluir la solicitud completa y no admite
el formato redactado de `access_log`. Los fallos del callback siguen visibles
por su estado y duración en el access log seguro. Los errores del resto del sitio
conservan su destino previo. El filtro existente de `uvicorn.access` se mantiene.

No se cambia la petición enviada al backend: necesita recibir `code`, `state`
y los demás parámetros originales. PKCE, cookies, sesión y autorización permanecen
intactos. La protección cubre las peticiones normales que alcanzan esta ubicación;
los rechazos tempranos de protocolo y cualquier captura/debug externo requieren
revisión de infraestructura.

## Despliegue manual después de revisión

1. Seguir el procedimiento manual de release; no publicar estos cambios de forma
   automática. Mantener `--workers 1`. El cambio backend requiere reinicio para
   cargar el limitador; como siempre, un reinicio invalida sesiones en RAM.
2. Integrar las directivas de logging en el sitio Nginx realmente instalado,
   conservando TLS, dominio, puerto y configuración local. Definir `log_format`
   una sola vez en contexto `http` y revisar permisos/rotación del nuevo log.
   No asumir que actualizar el código reemplaza el sitio existente.
3. Validar la configuración efectiva con `nginx -t` antes de una recarga manual
   autorizada. No se ejecutó ninguna recarga durante el desarrollo.
4. Aplicar la misma exclusión de query strings/Referer a balanceadores, WAF,
   proxies TLS, colectores y trazas anteriores a Nginx; sus logs de error tampoco
   deben capturar la URL completa del callback. No eliminar parámetros del proxy.
5. Revisar la retención y acceso a logs antiguos: el hotfix no borra datos que
   pudieran haberse registrado anteriormente.

## Validación local

`tests/test_ticket_pdf_limits.py` cubre volumen, límites inclusivos, filtros,
concurrencia entre hilos, frecuencia por identidad entre rutas/sesiones y limpieza
tras errores. Las regresiones de exportaciones comprueban documentos completos,
consulta normal, XLSX y PDF individuales.

`tests/test_nginx_oauth_logging.py` comprueba el formato permitido, la conservación
del proxy y el tratamiento de errores del callback. Ejecuta `nginx -t` sobre una
configuración aislada en un directorio temporal si Nginx está instalado; no lee
ni modifica el servicio activo. Las pruebas de callback/PKCE existentes verifican
el comportamiento backend. PostgreSQL de pruebas es efímero y no usa Alembic.
