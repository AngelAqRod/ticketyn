# Auditoría de seguridad v0.7.0 — Fase 4, hitos 1 y 2

Este documento describe el registro y consulta del hito 1 y la retención configurable con limpieza automática del hito 2. El [diseño de fase 4](diseno-fase-4-v0.7.0.md) y los [acuerdos complementarios](acuerdos-complementarios-v0.7.0.md) definen el alcance vigente. La autorización posterior del segundo hito fija el rango 1–3650 días, 365 iniciales y limpieza diaria. No habilita fase 5 ni operaciones en bases existentes.

## Componentes y persistencia

Se conserva la tabla `security_audit` y su modelo `SecurityAudit`, sin migraciones nuevas. `responsibles.id` sigue siendo la identidad única; actor autenticado y Responsable afectado son datos diferentes.

- `security/service.py:audit()` sigue siendo el productor transaccional compartido. Aplica el catálogo y la lista de metadatos permitidos de `security/audit.py` antes de guardar.
- `api/auth.py` registra `LOGIN_SUCCEEDED` antes de devolver un token. Si falla el evento o su commit, elimina la sesión RAM provisional, revierte la transacción y no devuelve el token. No elimina otras sesiones.
- Los fallos conservan la agrupación actual de usuario/IP/período: `LOGIN_FAILED_GROUP`. Los registros nuevos guardan identificador disponible, IP y operación; no guardan la huella de usuario `account_key`. La validación fallida de contraseña propia identifica la operación `PASSWORD_CHANGE`.
- Consultas, polling de permisos y renovación de actividad no generan logins ni nuevos eventos de lectura.
- Las políticas de contraseña, rate limiting, cinco sesiones y treinta minutos no cambian. La API no acepta nuevos parámetros para configurarlas.

No existe una transacción distribuida entre RAM, PostgreSQL y el navegador: un apagado después del commit puede dejar un login auditado cuya respuesta no recibió el cliente. El evento registra la emisión del lado del servidor, no prueba recepción del token ni actividad posterior.

## Eventos cubiertos

| Códigos | Acción |
|---|---|
| `LOGIN_SUCCEEDED`, `LOGIN_FAILED_GROUP` | Inicio de sesión y fallos agrupados de autenticación |
| `PASSWORD_CHANGED`, `PASSWORD_RESET` | Cambio propio y restablecimiento administrativo/CLI |
| `ACCESS_ENABLED`, `ACCESS_DISABLED` | Concesión/retiro de acceso |
| `ACCOUNT_CREATED`, `ACCOUNT_USERNAME_CHANGED`, `ACCOUNT_ROLE_CHANGED` | Configuración del acceso y cambios en el mismo Responsable |
| `ROLE_CREATED`, `ROLE_CHANGED`, `ROLE_DUPLICATED`, `ROLE_DELETED` | Definiciones de roles y permisos |
| `SESSION_CLOSED`, `SESSION_TERMINATED_ADMIN` | Cierre explícito y revocación administrativa |
| `BOOTSTRAP_SUPERADMIN` | Configuración inicial por CLI |
| `RESPONSIBLE_DEACTIVATED`, `RESPONSIBLE_REACTIVATED` | Cambios de estado ya existentes con efecto sobre acceso |
| `AUDIT_RETENTION_CHANGED` | Cambio confirmado de días de conservación; solo valores anterior/nuevo y actor |

Se conserva también el productor de disponibilidad de la fase 3, `RESPONSIBLE_AVAILABILITY_CHANGED`; no se añadieron productores operativos. No se instrumentaron tickets, circuitos, FMS, CAM o configuración de correo.

Los cambios críticos existentes siguen auditándose antes del commit; si falla la auditoría obligatoria, no se completa la mutación. Las revocaciones en RAM mantienen su orden posterior al commit. La lista de metadatos elimina claves no permitidas y datos anidados arbitrarios; de las descripciones de roles solo conserva si cambiaron, no su contenido. No registra contraseñas, hashes, tokens ni secretos.

## Consulta API

**GET `/api/security/audit`**, con sesión definitiva y `audit.view`. Los registros siguen siendo de solo lectura: no hay endpoints de eliminación, edición individual, exportación, estadísticas o limpieza manual. Los únicos contratos adicionales del hito 2 son los de configuración limitada de retención descritos abajo.

Filtros combinables, aplicados en PostgreSQL:

| Parámetro | Regla |
|---|---|
| `from_at` / `to_at` | Fecha con zona, inicio incluido y fin excluido; período coherente |
| `username` | Búsqueda literal sin distinción de mayúsculas por nombre/usuario actual de actor o afectado y por identificador registrado disponible; máximo 100 caracteres |
| `actor_id` | Id positivo del actor, distinto de un Responsable operativo asignado |
| `event` | Código del catálogo disponible; `LEGACY` representa códigos anteriores desconocidos |
| `result` | `ALL`, `SUCCESS` o `FAILURE` |
| `offset` / `limit` | Offset no negativo; limit fijo en 50 |

Respuesta: `{items, total, limit, offset, events}`. `events` contiene únicamente las opciones de filtro autorizadas; no es una estadística. Cada registro incluye fecha UTC, actor y afectado mínimos cuando existen, identificador disponible, evento/etiqueta, procedencia, resultado y detalles de presentación expresamente permitidos. No devuelve `details` JSONB en bruto.

Orden: fecha descendente e id descendente para desempate. El total sirve exclusivamente para paginar y aplica el mismo alcance que las filas. Una consulta nueva puede ver eventos incorporados entre páginas; no se mantiene un snapshot entre peticiones.

Administradores y personalizados con `audit.view` pueden consultar. Operador/Auditor predeterminados no adquieren Administración. Los eventos `ROLE_*`, incluso códigos históricos desconocidos de esa familia, quedan fuera de resultados, total y opciones sin `roles.manage`. Intentar filtrar explícitamente una definición de rol sin esa facultad devuelve 403. La asignación de rol a Responsable es una acción distinta.

Errores: 401 sin sesión válida; 403 sin facultades; 422 filtro inválido; 503 error de persistencia saneado. `SafeAuthRoute` conserva la protección existente que evita incluir valores de entrada o excepciones SQL en respuestas de validación/persistencia. La cobertura de rutas incluye el nuevo GET y conserva denegación por defecto.

## Información histórica y seguridad de lectura

Los registros anteriores no se modifican al consultarlos. Las huellas de usuario u otros metadatos no permitidos de registros antiguos se ocultan; no se intentan descifrar, asociar por suposición ni convertir en identidades.

Si falta el identificador de un grupo histórico, mostrar «Usuario no identificado» y que la cantidad de intentos no está disponible. Los grupos nuevos tampoco afirman un conteo que no se persiste. No duplicar el grupo como intentos individuales.

Los eventos desconocidos muestran una etiqueta histórica y no exponen su código o contenido arbitrario. Los filtros no buscan huellas ni estructuras JSON libres; los identificadores de formato incorrecto o fuera del límite no permiten inferir metadatos ocultos mediante los conteos.

Los nombres/usuarios resueltos desde relaciones son sus valores actuales, identificados así en pantalla; no son snapshots históricos. La procedencia CLI sin actor no inventa una persona autenticada.

## Interfaz

**Administración → Auditoría de seguridad**, ruta React `/security-audit`. Reutiliza encabezado, navegación, campos `form-input`, tabla `operation-table`, mensajes y paginación de Ticketyn. La tabla permite desplazamiento horizontal en móvil y muestra fechas según `America/Guatemala`.

Filtros de usuario/Responsable, período, tipo y resultado; acciones «Aplicar filtros», «Limpiar filtros» y «Actualizar». Limpiar filtros no borra registros. No hay acciones de edición individual, borrado, exportación ni configuración de sesiones. El Superadministrador dispone además de «Conservación de registros», sin rediseñar la página.

La navegación y la página verifican `audit.view`; la autorización final sigue en backend. El catálogo de eventos de filtros proviene de la API. Se cancelan consultas anteriores y se retiran datos al recargar o cambiar permisos. La página no renueva actividad ni consulta periódicamente por su cuenta; conserva el mecanismo de permisos de la fase 1/2.

## Validación y continuación

Pruebas nuevas: `tests/test_security_audit.py` y `frontend/src/pages/SecurityAudit.test.tsx`. Se actualizó la expectativa de navegación para la nueva opción, preservando las rutas anteriores.

Validación de cierre del hito:

- Backend dirigido de auditoría y fases 1–3: **98 aprobadas, 0 fallidas y 0 omitidas**, 99,64 segundos. Incluye pruebas existentes de migraciones y CLI en PostgreSQL descartable; no se aplicaron a DEV.
- Frontend dirigido: **57 aprobadas en 6 archivos**. Tras el ajuste final de clases visuales se repitió la suite completa: **692 aprobadas en 61 archivos, 0 fallidas**, 70,95 segundos.
- TypeScript `npx tsc --noEmit` y `git diff --check`: correctos. No se ejecutó la suite backend completa en este hito.
- Única advertencia backend: deprecación Starlette/TestClient con httpx, sin fallos funcionales. Los errores de sandbox para socket PostgreSQL/subprocesos Node se resolvieron repitiendo fuera del sandbox, sin cambiar fixtures ni expectativas operativas.

Comandos de reproducción, usando exclusivamente las fixtures descartables/mocks existentes:

```bash
.venv/bin/pytest -q tests/test_security_audit.py tests/test_security_foundation.py tests/test_security_authorization.py tests/test_security_administration.py
cd frontend
npm test -- --maxWorkers=2 src/pages/SecurityAudit.test.tsx src/pages/SecurityAdministration.test.tsx src/auth/permissions.test.tsx src/auth/AuthGate.test.tsx src/components/Layout.test.tsx src/components/SevenSegmentNumber.test.tsx
npx tsc --noEmit
```

PostgreSQL efímero necesita crear un socket local y las pruebas de fechas de la suite frontend completa requieren subprocesos Node; un bloqueo del sandbox no se corrige cambiando las reglas o expectativas operativas.

El segundo hito se implementa sobre el esquema existente, sin `0033`, cambios de versión/login ni preparación de publicación. Los resultados de su validación se registran al final de este documento y en el handoff; los números anteriores corresponden exclusivamente al cierre histórico del hito 1.

## Conservación de registros — Hito 2

Persistencia: `SecurityConfig.audit_retention_days` (fila singleton id 1), valor inicial 365. Se mantiene después de reiniciar. `failure_retention_days` permanece como campo histórico sin uso en esta política; los fallos y grupos también se conservan según el valor único. No se modifica `idle_minutes`, el máximo de cinco sesiones, credenciales, permisos ni revisiones de acceso.

| Método y ruta | Acceso | Contrato |
|---|---|---|
| GET `/api/security/audit/retention` | `security.configure` y rol Superadministrador | `{retention_days}` |
| PATCH `/api/security/audit/retention` | Misma exclusividad | Entrada `{retention_days, expected_days, confirm_reduction?}`; salida `{retention_days}` |

Los días son enteros estrictos entre 1 y 3650. No se aceptan booleanos, cadenas, fracciones, nulos o campos adicionales. `expected_days` es obligatorio: compara bajo `lock_security()` el valor visto en pantalla con el persistido. Una discrepancia devuelve 409 y requiere actualizar la conservación. Reducir días exige `confirm_reduction: true`, de tipo booleano; omitirlo equivale a falso. La interfaz explica la pérdida potencial y exige marcar la confirmación para esos valores concretos.

El servicio revalida la autoridad después de tomar el lock compartido por las mutaciones de seguridad. Solo confirma el valor si puede persistir `AUDIT_RETENTION_CHANGED` en la misma transacción; error de auditoría/commit revierte el cambio. Un guardado sin cambio no genera un evento. Los detalles permitidos son únicamente `before_days` y `after_days`, nunca estructuras de configuración o secretos.

Guardar no ejecuta limpieza, no programa un borrado dentro del request y no elimina registros. La interfaz muestra progreso, evita doble clic, informa éxito/error y recarga la consulta para mostrar el evento. Un Administrador o personalizado con `audit.view` conserva la tabla sin recibir el formulario ni acceso a estos dos endpoints. Las respuestas mantienen 401/403/422/409/503 saneados.

## Limpieza automática — Hito 2

`security/retention.py:AuditRetentionMaintenance` se integra en `security.http.cleanup_loop()` y el lifespan FastAPI existente. El mantenimiento RAM continúa cada minuto; el SQL se ejecuta en un hilo mediante `asyncio.to_thread`, sin bloquear el event loop ni agregar servicios externos. El despliegue systemd conserva `--workers 1`, `Restart=on-failure`; no se modifican instalación, backup o restore.

- Primera evaluación al minuto de iniciar; tras completar vencidos, próxima pasada a las 24 horas. El calendario se guarda en RAM: reiniciar adelanta una evaluación segura al primer minuto, sin necesitar otra tabla o historial de limpiezas.
- Lotes de hasta 500 filas en sesiones independientes, con commit por lote. Presupuesto cooperativo de 30 segundos entre lotes y máximo 60 lotes por pasada; si quedan vencidos, continúa al minuto siguiente. No se mantiene una transacción abierta entre lotes o durante esperas.
- Corte de cada lote: hora PostgreSQL convertida a UTC menos los días vigentes de 24 horas. Borra exclusivamente `security_audit.occurred_at < corte`. El registro exactamente igual al corte permanece hasta una evaluación posterior. Cambios manuales grandes del reloj del servidor afectarían el corte; mantener su reloj correctamente sincronizado.
- `pg_try_advisory_xact_lock(7807004)` serializa cada lote entre conexiones/procesos; no espera ni utiliza locks SMTP. Otra instancia puede alternar lotes, nunca borrarlos simultáneamente. El bloqueo libera al commit/rollback o desconexión, también después de un apagado. Esto no habilita múltiples workers HTTP para las sesiones RAM.
- La política se relee por lote con `FOR SHARE` sobre `security_config`; el PATCH usa `FOR UPDATE`. Un aumento de días espera a que termine el lote previo o se aplica antes del siguiente. No se borra con un corte obsoleto después de confirmar un aumento.
- Cada transacción limita esperas de lock a 250 ms y cada sentencia a cinco segundos. El modo normal usa un pool dedicado de una conexión, sin overflow, espera de pool de un segundo y conexión de tres segundos. La sesión devuelve la conexión después de cada lote; el pool puede conservar una conexión inactiva, pero ninguna transacción o lock durante las pausas.
- Error de PostgreSQL, configuración ausente/fuera de rango o contención: rollback del lote, ninguna suposición destructiva y reevaluación tras cinco minutos. El log de error es genérico, sin SQL, excepciones, parámetros ni metadatos de eventos. Los lotes ya confirmados se conservan; el resto vuelve a evaluarse tras reinicio. No se generan eventos de auditoría por cada lote.
- Al cerrar se cancela la programación, se señala parada y se espera al lote en curso antes de liberar recursos. El presupuesto de 30 segundos es cooperativo, no un deadline que interrumpe una sentencia; fallos severos de red/servidor pueden prolongar una espera más allá de los timeouts de consulta.

No toca tickets, circuitos, activaciones, ventanas, sus bitácoras, Responsables, roles o solicitudes de correo. No implementa endpoints de limpieza manual ni borrado individual. No realiza operaciones SMTP.

Para pruebas, `create_app(start_notifications=False)` mantiene el mantenimiento de auditoría deshabilitado salvo habilitación explícita. Para probarlo aisladamente usar `start_audit_retention=True, audit_retention_session_factory=factory_efimera`. Cada prueba de escritura utiliza las fixtures PostgreSQL descartables; nunca ejecutar `clean_batch` contra DEV. El desarrollo no reinicia el servicio existente ni activa esta programación en DEV; iniciar una instancia normal con este código sí activa la política y requiere revisión operativa previa.

## Archivos del hito 1 (referencia histórica)

Nuevos:

- `src/ticketyn/security/audit.py`
- `src/ticketyn/schemas/security_audit.py`
- `src/ticketyn/api/security_audit.py`
- `tests/test_security_audit.py`
- `frontend/src/api/securityAudit.ts`
- `frontend/src/pages/SecurityAudit.tsx`
- `frontend/src/pages/SecurityAudit.test.tsx`
- `docs/security-audit-v0.7.0.md`

Integraciones modificadas sobre el trabajo previo:

- `src/ticketyn/api/auth.py`
- `src/ticketyn/security/service.py`
- `src/ticketyn/security/routes.py`
- `src/ticketyn/main.py`
- `frontend/src/App.tsx`
- `frontend/src/auth/permissions.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/components/Layout.test.tsx`
- `frontend/src/components/moduleIdentity.ts`
- `docs/diseno-fase-4-v0.7.0.md`
- `AGENT_HANDOFF.md`

Los documentos maestros, migraciones, modelos y demás cambios acumulados de fases anteriores no se modificaron en este hito.

## Archivos y validación del hito 2

Nuevos: `src/ticketyn/security/retention.py`, `tests/test_security_retention.py`, `frontend/src/components/AuditRetentionSettings.tsx` y su prueba `AuditRetentionSettings.test.tsx`.

Modificados sobre el cierre del hito 1: `src/ticketyn/main.py`, `security/http.py`, `security/routes.py`, `security/audit.py`, `api/security_audit.py`, `schemas/security_audit.py`, `frontend/src/api/securityAudit.ts`, `frontend/src/pages/SecurityAudit.tsx`, `tests/test_security_audit.py`, este documento, el diseño y `AGENT_HANDOFF.md`. La prueba previa de solo lectura sigue rechazando borrado/exportación/limpieza manual; los nuevos contratos de retención se comprueban por separado.

Validación final repetida después del último ajuste:

- Backend dirigido ampliado: **193 aprobadas, 0 fallidas y 0 omitidas**, 145,44 segundos. Incluye 25 casos nuevos de retención y regresiones de consulta, fases 1–3, trabajos de correo e integración FMS. No es la suite backend completa.
- Frontend dirigido: **51 aprobadas en 6 archivos, 0 fallidas**, 6,35 segundos; incluye seis casos nuevos del formulario de conservación y regresiones de navegación, permisos, autenticación y administración. No se ejecutó la suite frontend completa en este hito.
- TypeScript `npx tsc --noEmit`: salida 0. `git diff --check`: correcto.
- Única advertencia backend: deprecación Starlette/TestClient con httpx, sin impacto funcional observado. Los resultados corresponden a ejecuciones completas con PostgreSQL efímero; un intento interrumpido antes de producir su diagnóstico completo no se incluye en los totales. No se modificaron pruebas para eludir restricciones del entorno.

Cobertura específica: 365 iniciales y persistencia tras reiniciar la aplicación, tipos/rango/extremos, confirmación y conflicto, facultad exclusiva, rollback de configuración si falla su evento, corte exacto y grupos fallidos, lotes 500/500/1, concurrencia entre conexiones reales, locks recuperados, cambio de retención durante limpieza, rollback de lote fallido, continuación/reprogramación diaria, parada ordenada y lifespan con fábrica efímera. Se comparan conteos de todas las tablas ajenas a auditoría y se comprueba contenido histórico de tickets sin cambios.

```bash
.venv/bin/pytest -q tests/test_security_retention.py tests/test_security_audit.py tests/test_security_foundation.py tests/test_security_authorization.py tests/test_security_administration.py tests/test_mail_jobs.py tests/test_activation_notifications.py
cd frontend
npm test -- --maxWorkers=2 src/components/AuditRetentionSettings.test.tsx src/pages/SecurityAudit.test.tsx src/auth/permissions.test.tsx src/auth/AuthGate.test.tsx src/pages/SecurityAdministration.test.tsx src/components/Layout.test.tsx
npx tsc --noEmit
```

No se aplicaron migraciones ni se ejecutaron cambios de configuración o limpiezas en DEV, TEST o PRODUCCIÓN. No se reinició el servicio existente. Sin correos externos, builds, commits, pushes, tags o despliegues. El HEAD sigue en `0032_responsible_selectable`. Detenerse para revisión del propietario; la fase 5 no está autorizada.
