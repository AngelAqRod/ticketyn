# Seguridad v0.7.0 — Fase 1 en desarrollo

Esta fase incorpora autenticación y sesiones. No constituye una versión publicable: la matriz granular, administración visual de cuentas/roles/sesiones y la administración de auditoría pertenecen a fases posteriores. Se conserva la versión declarada de v0.6.x y el indicador pendiente de corrección en la Fase 5.

La política provisional descrita abajo corresponde al cierre histórico de la Fase 1. La autorización vigente de la Fase 2 se documenta en [Roles y permisos](security-authorization-v0.7.0.md).

## Política provisional

Todos los endpoints, incluidos OpenAPI, documentación, exportaciones y administración, requieren una sesión válida. Solo el Superadministrador con contraseña definitiva puede utilizar los módulos existentes. Los demás roles disponen únicamente de las operaciones personales de autenticación; no reciben permisos operativos por tener una sesión. La Fase 2 sustituirá esta política restrictiva por la matriz aprobada.

Excepciones públicas: `GET /health`, `POST /api/auth/login` y el callback OAuth2 de correo, que requiere un flujo vinculado a una sesión Superadministrador vigente y conserva las verificaciones anteriores de cookie técnica, state y PKCE. Reiniciar el backend invalida también esta vinculación. La cookie OAuth2 no autentica sesiones normales de Ticketyn.

## Persistencia

`0030_security_foundation` depende de `0029_mail_requests`. Incorpora en Responsables usuario único sin distinción de mayúsculas, hash Argon2id, autorización administrativa persistente, rol, obligación de cambiar contraseña y revisión de acceso. Los registros existentes conservan sus datos y no reciben acceso.

La autorización administrativa (`access_granted`) es independiente de `active`: la baja operativa invalida las sesiones sin olvidar la autorización previa; la reactivación solo restaura acceso si esa autorización continúa vigente. Una suspensión administrativa no se revierte por reactivar el Responsable. No se permite suspender o dar de baja al último Superadministrador activo. Las mutaciones de seguridad se serializan mediante la fila de configuración y auditan dentro de la misma transacción.

Las tablas iniciales de roles, permisos, asignaciones, configuración y auditoría preparan las fases siguientes. No existen tablas de sesiones. La configuración inicial establece 30 minutos de inactividad y retenciones de 365/7 días; los editores y limpieza de auditoría se implementarán en su fase correspondiente.

## API mínima

| Endpoint | Contrato |
|---|---|
| `POST /api/auth/login` | Usuario y contraseña; devuelve token opaco y datos no sensibles de sesión. |
| `GET /api/auth/me` | Identidad, revisión de rol, restricción provisional, contraseña temporal y tiempo restante. No renueva actividad. |
| `POST /api/auth/activity` | Renueva actividad por una acción explícita del usuario. |
| `POST /api/auth/password` | Contraseña actual y nueva; invalida otras sesiones y conserva la actual. |
| `POST /api/auth/logout` | Audita el cierre y revoca el token actual. |

Errores: 401 sesión ausente/inválida o credenciales incorrectas; 403 acceso restringido; 409 cinco sesiones existentes; 422 datos inválidos; 429 espera progresiva; 503 recurso criptográfico ocupado o persistencia no disponible. No se devuelven entradas de validación que contengan contraseñas. No se reciben contraseñas mediante query strings.

La API valida la revisión persistente y el estado actual de la cuenta en cada solicitud, con una sesión SQLAlchemy independiente de la operación solicitada. Un restablecimiento CLI invalida sesiones del servidor activo sin reiniciarlo. Una revisión antigua no ocupa el cupo de cinco sesiones al iniciar sesión nuevamente.

## Bootstrap y recuperación local

Ejecutar con el Python del checkout/release que corresponda. Las contraseñas se solicitan interactivamente, sin argumentos ni salida del secreto:

```bash
.venv/bin/python -m ticketyn.security.cli --config /ruta/privada/ticketyn.env bootstrap --responsible-id 42 --username administrador
.venv/bin/python -m ticketyn.security.cli --config /ruta/privada/ticketyn.env recover-superadmin
```

En una instalación sin personas, puede crearse explícitamente el primer registro del catálogo existente:

```bash
.venv/bin/python -m ticketyn.security.cli --config /ruta/privada/ticketyn.env bootstrap --responsible-name 'Responsable inicial' --username administrador
```

Preferir `--responsible-id` cuando la persona ya exista. No se crea un catálogo paralelo ni un endpoint público de bootstrap. El bootstrap se rechaza si ya existe una cuenta Superadministrador, incluso deshabilitada. La recuperación es independiente, requiere exactamente una cuenta Superadministrador existente, no cambia su rol ni habilitación y exige cambio posterior de contraseña.

Sin `--config`, la CLI utiliza únicamente variables de entorno; no carga implícitamente `.env` desde el directorio de trabajo. El archivo explícito debe ser regular, privado (0600), sin enlace simbólico final y propiedad del ejecutor o root. La cuenta de servicio no debe obtener permisos innecesarios sobre archivos administrativos. No ejecutar estos comandos sobre bases compartidas durante el desarrollo.

## Sesiones y recursos

Tokens de 256 bits generados criptográficamente; el backend conserva hashes SHA-256 y metadatos, no tokens originales. React usa `sessionStorage`, adjunta `Authorization: Bearer` también a exportaciones y comprueba permisos al navegar, recuperar foco y cada 15 segundos. Estas consultas no renuevan actividad. Solo las acciones reales de teclado/puntero, limitadas a una renovación por minuto, o «Continuar sesión» renuevan el plazo. Se advierte a dos minutos del vencimiento.

Las sesiones duplicadas mediante la función del navegador para duplicar pestañas pueden compartir token: cerrar esa sesión afecta ambas pestañas. Reiniciar el backend elimina todas las sesiones. Los borradores operativos pueden conservarse en memoria del componente durante una expiración; cerrar sesión o cambiar de identidad los elimina. No se guardan contraseñas ni borradores en almacenamiento persistente.

Límites por proceso:

- Cinco sesiones por cuenta; 10 000 sesiones globales. No se expulsan sesiones válidas para admitir una sexta.
- Dos operaciones Argon2id simultáneas: 64 MiB por operación, tres iteraciones, paralelismo cuatro. Si están ocupadas, se devuelve 503 sin crear una cola criptográfica ilimitada.
- 20 000 claves de contadores temporales y 256 flujos OAuth2 pendientes. Los contadores más antiguos se descartan al alcanzar su límite; los vencidos se limpian periódicamente y durante las operaciones.
- Seguimiento de fallos por cuenta y por pareja cuenta/IP durante 15 minutos. Después de cinco fallos se inicia espera progresiva, hasta 60 segundos. La protección agregada por IP tiene un umbral de 100 fallos para reducir afectación de operadores tras una NAT compartida.
- Limpieza periódica cada minuto, además de las comprobaciones durante las operaciones.

Medición orientativa en DEV: verificación Argon2id mediana 191 ms (cinco muestras); pico de RSS del proceso con dos verificaciones simultáneas 149,1 MiB; 1 000 sesiones, aproximadamente 0,42 MiB según `tracemalloc`. El máximo de 20 000 contadores y 256 vínculos OAuth2 ocupó 6,53 MiB; con esa carga, diez comprobaciones promediaron 2,82 ms por operación. Son mediciones del entorno de desarrollo, no garantías de capacidad. Los límites globales permiten acotar memoria; el consumo total incluye Python, SQLAlchemy, HTTP y el procesador de correo.

## Operación y trabajo posterior

Mantener **un solo trabajador HTTP**. La unidad systemd declara `--workers 1` y la aplicación rechaza `WEB_CONCURRENCY` distinto de 1. No ejecutar múltiples instancias/réplicas del backend para una misma instalación: la memoria de sesión no se comparte. No se introduce Redis ni persistencia de tokens.

El acceso debe continuar restringido mediante infraestructura de red y HTTPS. No confiar en encabezados de proxy provenientes de orígenes no confiables. No imprimir credenciales, hashes o tokens en logs; la auditoría registra el cambio de un secreto, nunca su contenido.

Antes de publicar será necesario completar las fases posteriores, adaptar las sondas administrativas que todavía esperan datos operativos sin autenticación, probar el despliegue sin ventana pública, corregir el indicador de versión, ejecutar build y verificar `frontend/dist/`. No aplicar esta fase incompleta a TEST/PRODUCCIÓN.

La reversión operativa futura debe recuperar conjuntamente el código y el respaldo de base anterior, manteniendo el acceso cerrado durante la transición. El downgrade de pruebas elimina datos de seguridad y no es un procedimiento seguro de rollback en vivo.


## Archivos de la fase y validación DEV

Archivos nuevos: `alembic/versions/0030_security_foundation.py`, `src/ticketyn/models/security.py`, `src/ticketyn/api/auth.py`, `src/ticketyn/security/{__init__,passwords,memory,service,http,cli}.py`, `frontend/src/auth/{session.ts,AuthGate.tsx,AuthGate.test.tsx}`, `tests/security_helpers.py`, `tests/test_security_foundation.py` y esta guía.

Integraciones: `src/ticketyn/{main.py,models/__init__.py,models/responsible.py,api/responsibles.py,api/mail_transport.py}`, `frontend/src/{App.tsx,api/client.ts}`, `deploy/systemd/ticketyn.service`, `pyproject.toml` y `requirements.lock`.

Las fixtures backend se autentican con una cuenta real y sesiones procesadas por la misma frontera de seguridad; no desactivan el middleware. Se ajustaron las comprobaciones de catálogos para reconocer esa cuenta y los presupuestos de consultas para distinguir los dos SELECT de autenticación de las consultas operativas originales. Las pruebas de rutas React aíslan la autenticación, mientras el grupo AuthGate comprueba el flujo real, incluida la aplicación completa sin sesión. Una prueba de candidato contenía expectativas obsoletas de v0.6.1: ahora las contrasta con la versión declarada, sin cambiar la versión del proyecto ni el indicador FastAPI pendiente.

Se ejecutó inicialmente la suite backend completa: 1 987 aprobadas y 19 fallos de adaptación de fixtures, presupuestos de consultas y la expectativa de versión obsoleta. Se corrigieron esos casos y se repitieron todos los grupos afectados: **679 pruebas aprobadas**. Después, el grupo final de seguridad ampliado obtuvo **29 pruebas aprobadas**, incluyendo migración upgrade/downgrade, CLI con servidor activo, concurrencia del último Superadministrador, límite de contraseña con escape JSON y denegación anónima sobre los contratos OpenAPI. La validación final posterior repitió la suite backend completa con `.venv/bin/pytest -q --junitxml=/tmp/ticketyn-phase1-backend-final-complete.xml`: **2 023 aprobadas, 0 fallidas, 0 errores y 0 omitidas**, en 673,31 segundos. Las 29 pruebas de seguridad pasaron también dentro de esa ejecución. No fue necesario corregir código adicional. Se utilizaron exclusivamente PostgreSQL descartable y recursos temporales de la suite; no se aplicaron migraciones a bases compartidas u operativas.

La única advertencia de la ejecución completa es `StarletteDeprecationWarning`: Starlette 1.7.0 utiliza su ruta de compatibilidad con httpx 0.28.1 al no estar instalado httpx2. Esa ruta continúa funcionando; la advertencia no produjo fallos ni omisiones y no afecta al servidor de producción. No se cambiaron dependencias para silenciarla.


La suite frontend final obtuvo **656/656 pruebas aprobadas** con `npm test -- --maxWorkers=2`; TypeScript (`npx tsc --noEmit`) y `git diff --check` finalizaron correctamente. Las pruebas de zonas horarias necesitan permiso para crear subprocesos Node: sus errores `EPERM` dentro del sandbox desaparecieron al ejecutarlas con ese permiso, sin cambiar expectativas de fechas.

Al retomar la ejecución se corrigió una carrera adicional: si el token se invalida mientras termina de crearse la sesión, el login responde 401 de forma controlada, sin una respuesta 500 ni acceso a metadatos inexistentes. Una prueba de regresión cubre el caso.

Se conservaron los documentos funcionales aportados por el usuario. No se ejecutaron builds, no se modificó `frontend/dist/`, no se crearon commits/tags/releases y no se aplicaron migraciones a bases compartidas ni operativas.
