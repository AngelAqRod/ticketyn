# Ticketyn v0.7.0 — Diseño de fase 4: Auditoría de seguridad

**Actualización:** 20/10/2026. **Agente:** Codex CLI.
**Estado:** hitos 1 y 2 implementados: registro, consulta, retención configurable y limpieza automática; validación del hito 2 en la guía de implementación.
**Rama comprobada:** `development/v0.7.0`. **Commit base:** `6620dc6`.

## 1. Decisión posterior y precedencia

**Estado por hito:** la implementación efectiva se documenta en [Auditoría de seguridad](security-audit-v0.7.0.md). Una autorización posterior habilitó el segundo hito, fijando el rango **1–3650 días**, 365 iniciales y limpieza diaria por lotes. Esta autorización sustituye los pendientes de rango y ejecución del diseño anterior. El diagnóstico de la sección 3 conserva expresamente su carácter histórico, anterior al hito 1.

**Decisión aprobada:** la fase 4 se limita a **Auditoría de seguridad**. Esta revisión sustituye expresamente el diseño anterior de auditoría operativa, exportaciones, estadísticas, limpieza manual y configuración general de seguridad. No son trabajos pendientes de esta fase ni deben trasladarse automáticamente a fase 5.

Referencias obligatorias:

1. [AGENTS.md](../AGENTS.md) y [AGENT_HANDOFF.md](../AGENT_HANDOFF.md).
2. [Documento maestro actualizado](planificacion-v0.7.0.md).
3. [Acuerdos complementarios actualizados](acuerdos-complementarios-v0.7.0.md), con precedencia cuando modifican expresamente el maestro.
4. Guías históricas de [fase 1](security-foundation-v0.7.0.md), [fase 2](security-authorization-v0.7.0.md) y [fase 3](security-administration-v0.7.0.md).

Las menciones incompatibles al alcance anterior en guías históricas quedan sustituidas por la decisión posterior documentada aquí y en los dos documentos funcionales. No modificar esas otras guías en esta tarea. **Aprobado** identifica reglas resueltas; **propuesta técnica** identifica detalles pendientes de revisión, no funcionalidades ya implementadas.

## 2. Alcance vigente

### Incluido y aprobado

- Inicio de sesión correcto e incorrecto.
- Cambio y restablecimiento de contraseñas.
- Habilitación/deshabilitación de acceso; cambios de roles y permisos.
- Cierre/revocación explícita de sesiones; bootstrap, recuperación y eventos críticos de autenticación/autorización ya existentes.
- Consulta de solo lectura con fecha/hora, usuario o identificador disponible, tipo de evento e información relevante de la acción.
- Filtros básicos combinables y paginación.
- Retención única de **365 días**, ajustable solo por Superadministrador; limpieza automática de registros vencidos.
- Reutilizar `SecurityAudit`, `SecurityConfig` y permisos pertinentes; separar auditoría de seguridad de históricos operativos.

### Excluido y aprobado

- Auditoría de tickets, circuitos, activaciones, capacidad, bajas/reactivaciones de circuitos y ventanas de mantenimiento.
- Exportaciones PDF/XLSX de auditoría; dashboard, estadísticas o resúmenes de auditoría.
- Panel general de Seguridad; edición de política de intentos, duración o número de sesiones.
- Limpieza manual por UI o API, edición de eventos o eliminación individual.
- Cambios al motor SMTP/OAuth2, historial de correos o instrumentación de sus ajustes operativos.

Las sesiones siguen **fijas en 30 minutos de inactividad y cinco simultáneas por Responsable**, con advertencia dos minutos antes. No modificar Argon2id, contraseñas, rate limiting, roles o sesiones para habilitar configuración general. Mantener los contadores temporales y hashes de sesión en RAM donde corresponden; la prohibición de hashes en auditoría no elimina los hashes necesarios para la seguridad actual.

## 3. Base contrastada antes de implementar el hito 1

| Componente | Existe | Falta dentro del nuevo alcance |
|---|---|---|
| Identidad | `Responsible` / `responsibles.id`; identidad única, sin otra tabla de usuarios | Nada que requiera duplicar personas |
| Seguridad | Autenticación, Argon2id, RAM, revisiones de acceso, roles y 147 permisos | Registrar login exitoso y ajustar metadatos de fallos sin secretos |
| `SecurityAudit` | Id, fecha UTC, actor/Responsable afectado, evento, procedencia, resultado y JSONB `details` | Lista permitida de metadatos, proyección segura y consulta paginada |
| Productores | Bootstrap, contraseña/acceso, roles, cierres de sesión, cambios de estado de Responsable | Mantener transacciones y completar eventos de seguridad, sin ampliar a NOC |
| Login fallido | Primer evento `LOGIN_FAILED_GROUP` de un grupo; detalles con IP y huella `account_key` | Presentación honesta de legacy; no generar ni exponer hashes en registros nuevos |
| Login correcto | Se emite sesión RAM; no genera actualmente evento de auditoría | Nuevo evento de login correcto, coherente con emisión/invalidez de sesión |
| `SecurityConfig` | `audit_retention_days=365`, `failure_retention_days=7`, `idle_minutes=30` | Usar solo `audit_retention_days` para retención única; API limitada de retención |
| Mantenimiento | `security.http.cleanup_loop()` limpia RAM cada minuto | Evaluación periódica de auditoría vencida con sesiones SQL independientes |
| Consulta/UI | Administración existente; no página de auditoría | Una página Auditoría y ajuste limitado de retención para Superadministrador |

Las fases 1–3 están completadas y validadas según el estado aprobado y el handoff de Antigravity. Permanecen Departamento en Mi perfil y las pruebas del rol personalizado de 73 permisos. No reiniciar esas fases.

El único HEAD en archivos es `0032_responsible_selectable`, posterior a `0031_role_permissions`; su aplicación a DEV fue confirmada por el propietario y Antigravity, no reconsultada a la base durante estas tareas documentales. Los cambios locales acumulados siguen sin commit.

**Guías históricas:** la de fase 3 todavía menciona DEV en `0031` y perfil sin Departamento. La de fase 1 describe una política provisional de autorización ya sustituida por fase 2. Su información desactualizada no autoriza repetir migraciones, bootstrap o funcionalidades eliminadas de este diseño.

## 4. Arquitectura implementada

```text
Autenticación / mutación crítica de seguridad / CLI
  → servicio actual y evento permitido, misma transacción cuando corresponda
  → security_audit

Consulta autenticada
  → permiso y alcance → filtros PostgreSQL → DTO seguro → tabla

Superadministrador → ajuste limitado de retención → security_config + evento
Ciclo de vida actual → limpieza de vencidos por lotes → security_audit
```

No crear un motor de auditoría operativa, una segunda tabla de eventos, tablas nuevas de grupos fallidos o mantenimiento, colas, exportadores ni otro proceso. El esquema actual cubre este diseño inicial.

### Modelo de datos

- Conservar `SecurityAudit` y sus FK `actor_id`/`target_id` a `responsibles`; `target_id` sigue significando Responsable afectado, no un id genérico de ticket o circuito.
- Reutilizar `event`, `source`, `success`, `occurred_at` y detalles permitidos. Diferencias no sensibles de roles/permisos se conservan en metadatos ya existentes.
- Reutilizar `SecurityConfig.audit_retention_days`; no agregar una retención separada de fallos. `failure_retention_days` permanece como campo legado sin uso en la nueva política: no borrarlo ni aplicarlo a los registros de fase 4.
- `idle_minutes` permanece en el esquema existente, sin endpoint ni formulario para modificarlo; la política vigente sigue siendo 30 minutos. No usar su existencia para ofrecer configuración de sesiones.
- No agregar campos de recurso operativo, índices genéricos JSONB, snapshots masivos ni contadores estadísticos.

**Migraciones:** con estos contratos no se identifica una nueva migración indispensable. La propuesta anterior `0033_security_audit_management` queda retirada. No crearla por continuidad del diseño viejo. Si durante la implementación autorizada aparece una necesidad demostrada de esquema/índice, justificarla antes, sin tocar migraciones históricas ni aplicar cambios a DEV. Esta tarea no crea ni ejecuta ninguna migración.

## 5. Registro de eventos y protección de datos

### 5.1 Productores y reglas

| Familia | Comportamiento implementado |
|---|---|
| `LOGIN_SUCCEEDED` (nuevo) | Una entrada por inicio de sesión real que emite sesión; no por `/auth/me`, actividad, foco, navegación o polling |
| `LOGIN_FAILED_GROUP` | Conservar agrupación usuario/IP/período existente, sin afirmar conteos que no se guardan; identificar que es un grupo de fallos |
| `PASSWORD_CHANGED`, `PASSWORD_RESET` | Mantener transacciones y revisión de acceso; nunca guardar contraseña/hash anterior o nuevo |
| `ACCESS_*`, `ACCOUNT_*` | Mantener habilitación, suspensión, usuario y asignación de rol sobre el mismo Responsable |
| `ROLE_*` | Mantener cambios de definiciones y diferencias de permisos; un evento por operación, no por persona afectada |
| `SESSION_CLOSED`, `SESSION_TERMINATED_ADMIN` | Registrar cierre explícito antes de retirar RAM, sin token/hash de token ni historial persistente de sesiones |
| `BOOTSTRAP_SUPERADMIN` y recuperación CLI | Mantener procedencia segura y actor disponible; no reconstruir una identidad ausente |
| Estado operativo de Responsable que afecta acceso | Conservar trazabilidad crítica de bloqueo/reactivación de acceso e independencia administrativa |
| `AUDIT_RETENTION_CHANGED` (nuevo) | Diferencia de días anterior/nueva y actor; no otros parámetros de seguridad |

No ampliar productores a servicios de tickets, circuitos, FMS, CAM o correo. Las entradas anteriores de disponibilidad u otras acciones ajenas al nuevo alcance no se borran ni reclasifican como acciones de acceso que no ocurrieron; mostrar su condición histórica si aparecen, sin crear nueva auditoría operativa. La retención de `SecurityAudit` nunca se extiende a tablas de bitácoras operativas.

No agregar un middleware que registre cuerpos HTTP, cada 401/403 o cada consulta. Las solicitudes rechazadas por el rate limiter con 429 no generan por sí mismas un evento individual adicional: no hubo otra verificación de contraseña. Conservar respuestas de credenciales genéricas y protección para usuarios inexistentes.

### 5.2 Login exitoso y atomicidad

Las mutaciones críticas conservan `security.service.audit()` antes del commit. Si la escritura obligatoria falla, rollback de la modificación; revocaciones RAM solo tras confirmar la auditoría, como en la arquitectura existente.

El hito 1 integró el evento de login correcto antes de responder con el token, conservando la revalidación bloqueada de credenciales en `api/auth.py`. Si se crea una sesión RAM provisional y falla el commit del evento, se revoca esa sesión y no se devuelve su token. No se crea `LOGIN_SUCCEEDED` si se rechaza el cupo de sesiones. El hito 2 no modifica ese flujo.

RAM y PostgreSQL no tienen transacción distribuida: un apagado después del commit puede dejar auditado un login cuya respuesta no recibió el navegador. El evento no prueba entrega del token al cliente ni actividad posterior; documentar esta limitación. No introducir una tabla de sesiones para resolverla.

### 5.3 Metadatos permitidos

- Usuario/identificador disponible, actor y afectado; procedencia técnica e IP cuando ya se obtiene de forma confiable y es relevante.
- Evento, resultado, ids de roles y diferencias permitidas de permisos/acceso/retención.
- Nunca contraseñas, hashes, tokens, encabezados Authorization, cookies técnicas, códigos OAuth2, secretos SMTP, claves o datos de CPE.

Definir lista de claves y tipos permitidos por evento, validar tamaños y usar DTO de salida explícito. No devolver `details` en bruto, incluso para Superadministrador. Escapar textos en React; no renderizar metadatos como HTML.

Para nuevos fallos, conservar únicamente el identificador de usuario introducido si está disponible y permitido, con tamaño acotado, e IP pertinente; no copiar la huella `account_key` a los registros nuevos. No transformar contraseñas ni cambiar comparaciones de identidad para presentar auditoría. Un usuario introducido no demuestra que exista una cuenta.

## 6. Intentos fallidos anteriores: información incompleta

**Regla:** no inventar ni completar retrospectivamente información desconocida.

1. Mantener las filas `LOGIN_FAILED_GROUP` existentes y su timestamp real. Representan el evento observado al comenzar un grupo, no una lista completa de intentos.
2. Si solo hay huella de usuario y no actor, afectado ni identificador legible, mostrar «Usuario no identificado» o «Identificador no disponible». No intentar revertir hashes, compararlos masivamente contra usuarios actuales o asignarles identidades actuales.
3. No exponer `account_key` ni otras huellas en pantalla, filtros o respuestas. No duplicarlas en registros nuevos. Son metadatos legados ya presentes, no un formato a perpetuar; este encargo no autoriza sanear o modificar esas filas en la base.
4. No asignar un conteo ficticio de 1 ni mostrar un total estimado de intentos. Basta la etiqueta «Inicio de sesión incorrecto (grupo histórico)» y la información efectivamente disponible. No se necesitan estadísticas.
5. Los filtros por usuario solo incluyen filas cuya identidad pueda asociarse sin inferencias. Los grupos desconocidos siguen localizables por fecha/tipo/resultado.
6. Todos los registros de seguridad, incluidos los grupos anteriores, quedan sujetos a la política única de 365 días iniciales cuando se implemente. No mantener siete días para fallos, borrar al actualizar esquema ni reconstruir eventos antes de la instrumentación.

Si fuera imprescindible eliminar metadatos legados que contengan huellas antes de su vencimiento, requiere una autorización específica para modificar datos históricos; no forma parte de esta tarea documental ni se ejecuta automáticamente.

## 7. Consulta, permisos y contratos API previstos

### Permisos existentes

| Acción | Permiso | Alcance |
|---|---|---|
| Consultar tabla y filtros | `audit.view` | Superadministrador, Administrador y personalizado con concesión explícita |
| Consultar/modificar retención | `security.configure` | Exclusivo de Superadministrador, limitado a retención |
| Consultar historial de definiciones de roles | Exclusividad existente de `roles.manage` | No exponerlo indirectamente a Administrador por `audit.view` |
| Exportar / limpiar manualmente | `audit.export`, `audit.clean` ya declarados | Sin operaciones nuevas: no crear rutas ni botones |

Operador y Auditor / Solo lectura no reciben Administración por este cambio. Mantener denegación por defecto, verificación backend y efectos inmediatos de permisos. No renombrar ni eliminar los 147 permisos ni añadir facultades exclusivas a personalizados.

El catálogo existente contiene permisos de funcionalidades ahora excluidas. Su mera presencia no equivale a implementación; no anunciar esas funciones como disponibles. La administración de cuentas y sesiones de fase 3 sigue funcionando con sus permisos actuales.

### API mínima y alcance por hito

| Método y ruta | Permiso | Contrato |
|---|---|---|
| GET `/api/security/audit` | `audit.view` | Hito 1 implementado: `{items, total, limit: 50, offset, events}`; total solo para paginar, `events` para opciones autorizadas |
| GET `/api/security/audit/retention` | `security.configure` y rol Superadministrador | Hito 2: `{retention_days}` |
| PATCH `/api/security/audit/retention` | `security.configure` y rol Superadministrador | Hito 2: ajuste de días con concurrencia y confirmación; respuesta `{retention_days}` |

No endpoints de resumen, exportación, limpieza manual, eliminación individual o configuración general. Registrar cada nueva ruta en `security/routes.py` y la cobertura OpenAPI. No crear excepciones públicas.

Filtros básicos de tabla: `from_at` incluido / `to_at` excluido con zona, `actor_id` o texto de usuario/identificador disponible, `event`, `result=SUCCESS|FAILURE|ALL`, `offset >= 0` y `limit=50`. Consulta parametrizada en PostgreSQL antes de materializar, orden `(occurred_at DESC, id DESC)`. Los identificadores deben poder distinguir actor de Responsable afectado al mostrar la acción. No admitir SQL, columnas, ordenamientos ni rutas JSON arbitrarios.

Proyección: id, fecha UTC, actor/identificador permitido, evento amigable, procedencia, resultado y explicación/diferencias permitidas. Los nombres resueltos desde relaciones actuales son datos actuales; no presentarlos como snapshots históricos. Estado vacío y falta de información son respuestas válidas.

Los eventos `ROLE_*` de definición se excluyen de resultados y total para quien no tiene la facultad exclusiva; los cambios de rol asignado a Responsable (`ACCOUNT_ROLE_CHANGED`) no se confunden con esa definición. No filtrar en React después de paginar.

Errores: 401 sesión ausente/inválida; 403 sin permiso; 422 filtros/cuerpo inválidos; 409 modificación concurrente; 503 persistencia no disponible. Ningún error debe devolver SQL, contraseñas, tokens o datos de validación sensibles.

## 8. Retención configurable, sin panel de Seguridad

**Aprobado:** 365 días por defecto para todas las filas de auditoría; solo Superadministrador puede ajustar. Registros de solo lectura salvo limpieza automática de vencidos; no se toca el historial operativo.

**Rango aprobado e implementado en hito 2:** entero entre **1 y 3650 días**. Rechaza cero, negativos, booleanos, fracciones y cadenas. No constituye una recomendación normativa de conservación. El valor predeterminado persistente sigue siendo 365, sin migración ni cambios de datos existentes.

Control de retención dentro de **Administración → Auditoría**, visible solo al Superadministrador. No añadir Administración → Seguridad. Mantener la misma estética y protección de rutas actuales; no rediseñar sidebar o encabezado.

PATCH implementado: `{retention_days, expected_days, confirm_reduction}` con `extra=forbid`. Los dos valores de días son obligatorios y enteros estrictos en el rango; la confirmación es booleana estricta, opcional con valor falso. `expected_days` compara el valor visto por el usuario con el actual bajo `lock_security()`; si difiere, 409. Se revalida la autoridad después del lock. Omisiones no restablecen valores; guardado idéntico no crea evento. No se añade revisión de esquema.

Si reduce días, mostrar advertencia de que la siguiente limpieza automática puede eliminar más registros y solicitar confirmación de esos valores exactos. El backend exige esa confirmación al reducir. Guardar no ejecuta una limpieza sincrónica ni crea un botón de borrado. Evento `AUDIT_RETENTION_CHANGED` y nuevo valor confirman juntos; fallo de auditoría obliga a rollback. No modificar `access_revision` ni cerrar sesiones por cambiar la retención.

## 9. Limpieza automática implementada para el despliegue actual

Reutilizar el ciclo de vida FastAPI de `src/ticketyn/main.py` y la tarea periódica existente `security.http.cleanup_loop()`. Conservar un solo trabajador HTTP. No añadir cron, Redis, Celery, daemon, proceso independiente ni tabla de trabajos.

Ejecución del hito 2 (`security/retention.py`):

1. El ciclo actual de 60 segundos sigue limpiando RAM. Añadir una comprobación ligera de fecha de próxima limpieza; el trabajo SQL se ejecuta fuera del event loop mediante el pool de hilos existente, sin procesos nuevos.
2. Primera pasada después del primer intervalo del backend, no en una migración. Después, una pasada cada 24 horas; reiniciar puede adelantar una evaluación segura de vencidos, sin repetir efectos sobre filas ya eliminadas.
3. Sesión SQLAlchemy independiente por lote de hasta 500 filas. Leer la retención vigente y calcular el corte UTC en servidor; eliminar solo `occurred_at < corte`. Conservar el registro exactamente en el límite.
4. Presupuesto cooperativo de 30 segundos comprobado entre lotes y máximo adicional de 60 lotes por pasada. El lote en curso puede superar el presupuesto hasta terminar o agotar su timeout. Si quedan vencidos, continuar tras el siguiente minuto, sin esperar otro día. Son constantes técnicas, no opciones administrativas.
5. Advisory lock transaccional dedicado no bloqueante por lote para evitar superposición accidental; nunca usar los locks del correo. Coordinar lectura de retención y borrado con bloqueo compartido breve de la fila de configuración, para que un aumento concurrente no borre filas con un corte ya obsoleto. No sostener locks durante toda la pasada.
6. Commit corto por lote: un apagado deja confirmados solo los lotes completados. El siguiente arranque vuelve a evaluar lo que siga vencido; no necesita restaurar trabajos ni inventar un historial de limpiezas.
7. Si falla PostgreSQL, la configuración es inválida/ausente o no se obtiene el advisory lock, no adivinar un corte ni continuar borrando. Rollback del lote fallido y nueva evaluación después de cinco minutos. El error produce solo un log genérico, sin SQL, excepciones o parámetros. No detener autenticación, NOC o SMTP.
8. No generar un evento de auditoría por cada lote ni mantener estadísticas/dashboard. Un log técnico de resultado basta para diagnosticar mantenimiento. No permitir eliminación individual o manual mediante API.

El lock `pg_try_advisory_xact_lock(7807004)` es exclusivo por lote y no bloqueante. La fila `security_config` se lee con `FOR SHARE`; los ajustes usan `FOR UPDATE`, de forma que un aumento de retención no pueda confirmarse mientras un lote borra con la política anterior. Las transacciones usan `statement_timeout=5s` y `lock_timeout=250ms` locales. Todos los locks se liberan al commit, rollback, desconexión o caída del proceso.

En cierre, cancelar la programación, señalar parada y esperar el lote activo antes de liberar recursos; no dejar un hilo borrando tras cerrar el lifespan. El modo normal utiliza un pool SQLAlchemy adicional de una conexión, sin overflow, espera de pool de un segundo y conexión de tres segundos, sobre la misma URL configurada. No agrega otro servicio ni proceso. El servidor y PostgreSQL siguen siendo locales según el despliegue actual; un fallo severo de red/servidor podría extender la espera más allá de los timeouts SQL.

Reiniciar adelanta la primera evaluación al minuto; no existe un marcador persistente de última limpieza ni se promete ejecución en una hora de calendario exacta. Dos procesos no eliminan simultáneamente: pueden alternar lotes serializados. Esto no habilita despliegue multiworker: las sesiones RAM de Ticketyn siguen requiriendo un único trabajador HTTP.

Pruebas: `create_app(start_notifications=False)` mantiene desactivados los trabajos de fondo por defecto. Para probar solo retención se usa `start_audit_retention=True` con `audit_retention_session_factory` efímera explícita. No se toman conexiones de DEV en pruebas. El corte usa reloj PostgreSQL convertido a UTC y días de 24 horas; `occurred_at == corte` permanece hasta una evaluación posterior.

La política única usa `audit_retention_days` también para `LOGIN_FAILED_GROUP`; ignorar `failure_retention_days` en este limpiador. Borrar únicamente de `security_audit`, no de tablas de bitácora, roles, Responsables, sesiones, solicitudes SMTP o datos operativos. No se modifican backup/restore.

## 10. Archivos de implementación

Los componentes de eventos/consulta pertenecen al hito 1; retención, programación y controles limitados pertenecen al hito 2. No se agregaron modelos ni migraciones.

| Archivo | Responsabilidad |
|---|---|
| `src/ticketyn/api/auth.py` | Login exitoso auditado, coherencia RAM/commit y fallos sin hashes nuevos |
| `src/ticketyn/security/service.py` | Conservar productor y transacciones; lista permitida de detalles en conjunto con servicio dedicado |
| `src/ticketyn/security/audit.py` | Catálogo de eventos, proyecciones seguras y consulta común básica |
| `src/ticketyn/api/security_audit.py`, `schemas/security_audit.py` | Tres contratos mínimos y validaciones de retención/consulta |
| `src/ticketyn/security/retention.py` | Corte UTC, lotes, programación y coordinación; sin borrado manual |
| `src/ticketyn/security/http.py`, `src/ticketyn/main.py` | Integración en programación actual, sesiones independientes y cierre seguro |
| `src/ticketyn/security/routes.py` | Inventario explícito de las tres rutas, sin nuevas facultades |
| `frontend/src/pages/SecurityAudit.tsx`, `api/securityAudit.ts` | Tabla/filtros/paginación y control de retención exclusivo |
| `frontend/src/components/AuditRetentionSettings.tsx` | Formulario limitado, confirmación de reducción, conflictos, carga y prevención de doble clic |
| `frontend/src/App.tsx`, `auth/permissions.tsx`, `components/moduleIdentity.ts` | Una opción Auditoría según permisos; ninguna página general de Seguridad |

Reutilizar API client, `PageHeading`, `RequestState`, `PaginationBar`, filtros en URL y `lib/datetime.ts`. Fechas almacenadas UTC y presentadas según Ticketyn (`America/Guatemala` actualmente). Mantener refresco de permisos al navegar/foco/cada 15 segundos sin renovar actividad. Total de paginación no es un dashboard; no añadir otros agregados.

Carga/error/vacío, 401/403/409, bloqueo de doble clic y etiquetas accesibles siguen los patrones existentes. La pantalla no muestra acciones para editar registros, borrar, exportar o cambiar políticas de sesión. No introducir dependencias nuevas.

## 11. Etapas y criterios de aceptación

Los dos hitos están autorizados e implementados. El control de conservación se integra en la página existente sin modificar tabla, filtros o permisos de lectura del hito 1.

1. **Reconfirmar base y contratos:** leer los cuatro documentos vigentes, rama/diff, modelos y HEAD. Aprobar o ajustar las propuestas técnicas de rango y lotes; descartar el diseño amplio anterior.
2. **Productores y secretos:** completar login correcto sin sesión filtrada, adaptar metadatos de fallos y mantener auditoría crítica de fases 1–3. No instrumentar módulos operativos.
3. **Consulta:** servicio/DTO, filtros PostgreSQL, paginación, alcance de roles y GET protegido.
4. **Retención:** GET/PATCH exclusivo, valor único, comparación concurrente, confirmación y auditoría transaccional.
5. **Limpieza:** integrar lotes acotados en ciclo actual y probar reinicio/fallos/retención concurrente.
6. **Interfaz:** una tabla y control limitado de días; navegación/acciones según permisos, sin funcionalidades excluidas.
7. **Regresión y documentación:** pruebas dirigidas, suites completas, TypeScript y diff; repetir suite correspondiente si después se corrigen fallos. No comenzar release ni fase 5.

Plan de pruebas de la fase: casos de eventos/consulta del hito 1 y retención/limpieza del hito 2. Consultar la guía de implementación y el handoff para resultados reales:

- Login correcto: evento sin secretos; no evento por polling; límite de sesiones no registra éxito; fallo del audit revoca sesión provisional y no devuelve token; carreras de credenciales/revocación.
- Login incorrecto: respuesta genérica, agrupación coherente, usuario desconocido, IP compartida y rate limiter preservado; ausencia de hashes nuevos.
- Cambios/restablecimientos de contraseña, acceso, roles/permisos y revocación: actor correcto, no duplicación por persona, rollback obligatorio y sin secretos en errores/logs.
- Legacy: huella oculta, identificador desconocido, conteo no inventado, fecha intacta y retención única sin reinterpretar datos.
- Consulta: fecha con zona, filtros combinados, 50 filas, orden estable, vacío, actor/afectado y proyección sin JSON bruto.
- Permisos: anónimo 401; usuario sin facultades 403; Administrador consulta pero no cambia retención; personalizado solo según `audit.view`; solo Superadministrador ve definición de roles y modifica retención.
- Retención: 365 iniciales, rango finalmente aprobado, concurrencia 409, reducción confirmada, no-op y rollback del ajuste si falla auditoría. No endpoints que modifiquen duración/cantidad de sesiones.
- Limpieza con PostgreSQL descartable y reloj controlado: corte exacto conservado, vencidos eliminados, grupos antiguos también 365, lotes, locks, cambio de retención, error/reinicio/cierre y conexiones liberadas. Históricos operativos y solicitudes SMTP intactos.
- React: tabla/filtros/paginación, retención exclusiva, confirmaciones y errores, permisos revocados; ausencia de exportaciones, estadísticas, borrado individual/manual y panel general de seguridad.
- Regresión: suites completas backend/frontend, TypeScript, `git diff --check`, y políticas fijas 30 minutos/cinco sesiones, perfiles, roles, selectores e históricos de fases 1–3.

No crear pruebas que contacten DEV, TEST o PRODUCCIÓN o envíen correos reales. Las fixtures actuales de PostgreSQL efímero y autenticación real deben seguir siendo la base.

## 12. Decisiones resueltas y limitaciones

**Resuelto en hito 2:** rango 1–3650 días, 365 iniciales, lotes de 500 filas, presupuesto cooperativo de 30 segundos/60 lotes, evaluación diaria, continuación al minuto y espera de cinco minutos por contención/error. Se comprueba con PostgreSQL descartable; no se ejecutan limpiezas ni cambios de retención en DEV, TEST o PRODUCCIÓN durante el desarrollo. La validación operativa en una instalación real queda a cargo del propietario y requiere autorización.

**Resuelto:** eventos de login correcto/incorrecto incluidos; retención única inicial 365; sesiones fijas 30/cinco; sin exportaciones, estadísticas, auditoría operativa, limpieza manual ni panel general. No reabrir los antiguos pendientes de límites PDF/XLSX o configuración de política fallida: quedaron retirados.

Limitaciones conocidas: los grupos antiguos no contienen todos los intentos; un nombre actual no es identidad histórica; metadata con huellas ya existente no se borra por este encargo; RAM y base no pueden probar que el cliente recibió el token. El despliegue sigue monoproceso y la ausencia de configuración editable de sesiones no cambia su arquitectura.

La corrección centralizada del indicador de versión sigue como tarea explícita de fase 5: `pyproject.toml` como fuente, metadatos fiables en releases/editable, coherencia FastAPI/API/encabezado. No sustituirla por otra versión fija ni iniciar publicación.

## 13. Restricciones de continuidad

La autorización del hito 2 habilita exclusivamente retención y limpieza automática con documentación y pruebas. No habilita exportaciones, estadísticas, auditoría operativa, configuración de sesiones ni ajustes de login/versión. Preservar cambios anteriores y rama; no ejecutar builds de publicación, commits, pushes o despliegues ni tocar TEST/PRODUCCIÓN o bases operativas.

El único HEAD sigue siendo `0032_responsible_selectable`; ningún hito de auditoría requiere migración. No alterar `admin-dev` ni aplicar migraciones a DEV sin autorización. Las pruebas utilizan PostgreSQL descartable.

**Siguiente paso al cerrar el hito 2:** revisión del resultado por el propietario. Esperar autorización explícita antes de iniciar fase 5, reiniciar servicios con este código o preparar una publicación.
