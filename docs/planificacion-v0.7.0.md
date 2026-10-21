# TICKETYN v0.7.0 — Documento maestro de implementación

**Estado:** Planificación funcional cerrada
**Destino:** Desarrollo e Implementación
**Versión base:** v0.6.x
**Versión objetivo:** v0.7.0
**Objetivo principal:** Incorporar autenticación, autorización, administración de accesos y auditoría de seguridad, preservando el funcionamiento operativo actual de Ticketyn.

---

> **Actualización aprobada — 20/10/2026:** la fase 4 se limita a **Auditoría de seguridad**. Esta decisión posterior sustituye su alcance anterior: incluye logins correctos e incorrectos, consulta básica, retención única de 365 días ajustable solo por Superadministrador y limpieza automática. Excluye auditoría operativa, exportaciones de auditoría, estadísticas/dashboard, configuración general de seguridad y limpieza manual. Las sesiones permanecen fijas en 30 minutos de inactividad y cinco simultáneas. Las demás decisiones de v0.7.0 conservan vigencia. Esta actualización documental no autoriza implementación.

## 1. Principios generales

Ticketyn es una plataforma de gestión operativa orientada a NOC de ISP y telecomunicaciones.

La versión 0.7.0 debe incorporar seguridad sin transformar el producto en un sistema ITSM genérico ni modificar innecesariamente sus flujos actuales.

### Reglas obligatorias

- Conservar la información histórica existente.
- No alterar la lógica de tickets, circuitos, activaciones, cambios de capacidad, bajas, reactivaciones ni ventanas de mantenimiento salvo lo necesario para aplicar permisos.
- Reutilizar el catálogo existente de **Responsables** para administrar cuentas.
- No crear un catálogo paralelo de usuarios o personas.
- Mantener separada la identidad del usuario autenticado del responsable operativo seleccionado en un registro.
- Validar permisos en el backend; ocultar botones en React no constituye una medida de seguridad suficiente.
- No publicar v0.7.0 con endpoints operativos parcialmente protegidos.
- Mantener compatibilidad con PostgreSQL, SQLAlchemy, Alembic, FastAPI y React/Vite.

---

## 2. Bloque I — Autenticación

### 2.1 Cuentas

Los accesos se administrarán desde los registros existentes de **Responsables**.

Cada responsable podrá tener o no acceso al sistema.

Agregar al formulario existente:

- **Habilitar acceso a Ticketyn:** casilla desactivada de forma predeterminada.
- Nombre de usuario.
- Contraseña inicial.
- Rol asignado.

Los responsables existentes no recibirán acceso automáticamente durante la migración.

El nombre de usuario será independiente del nombre visible del responsable y único sin distinguir mayúsculas y minúsculas.

El nombre de usuario permanecerá reservado mientras exista la cuenta, incluso cuando esté deshabilitada.

### 2.2 Contraseñas

- Almacenamiento mediante **Argon2id**.
- Nunca almacenar contraseñas en texto plano.
- No imponer complejidad, longitud mínima ni vencimiento periódico obligatorio.
- Permitir reutilización de contraseñas anteriores.
- La contraseña inicial será temporal y requerirá cambio en el primer acceso.
- El administrador autorizado podrá generar una contraseña aleatoria segura o establecer una manualmente.
- Las contraseñas temporales se mostrarán una sola vez.
- No habrá recuperación de contraseñas existentes.
- El restablecimiento administrativo obligará a cambiar la contraseña e invalidará todas las sesiones.
- El cambio voluntario desde Mi perfil requerirá la contraseña actual e invalidará las demás sesiones, conservando la actual.

### 2.3 Inicio de sesión

Implementar una pantalla de inicio de sesión con usuario y contraseña.

Los errores de credenciales utilizarán un mensaje genérico:

**«Usuario o contraseña incorrectos».**

No revelar si un nombre de usuario existe.

Si una cuenta está deshabilitada, no podrá autenticarse.

Si el usuario ya está autenticado y accede a la pantalla de login, será redirigido al primer módulo autorizado.

### 2.4 Protección contra intentos fallidos

- Aplicar limitación progresiva después de 5 intentos fallidos.
- Considerar cuenta e IP de origen.
- Evitar bloqueos permanentes.
- Considerar entornos NOC donde múltiples usuarios comparten IP.
- Proteger también frente a intentos con usuarios inexistentes.
- Mantener contadores temporales en memoria del backend.
- Agrupar eventos fallidos por usuario, IP y período para evitar registros excesivos.

---

## 3. Bloque II — Sesiones

### 3.1 Arquitectura

Se utilizarán tokens opacos, aleatorios y criptográficamente seguros.

- Envío mediante encabezado `Authorization`.
- Almacenamiento en `sessionStorage` del frontend.
- No utilizar cookies ni `localStorage`.
- El backend almacenará únicamente hashes de tokens y metadatos de sesión en memoria RAM.
- No crear tablas PostgreSQL para sesiones.
- No introducir Redis.
- Arquitectura prevista para un único proceso trabajador de FastAPI.

**Consecuencia aceptada:** reiniciar el backend invalidará todas las sesiones.

### 3.2 Duración

- Tiempo de inactividad fijo: **30 minutos**.
- No configurable en v0.7.0; sustituye la propuesta anterior de configuración por Superadministrador.
- Advertencia 2 minutos antes del vencimiento.
- Permitir continuar la sesión.
- La actividad válida del usuario renovará el período de inactividad.
- No establecer una duración máxima absoluta.
- El backend limpiará periódicamente las sesiones vencidas.

Actualizar la actividad únicamente de forma controlada para evitar que consultas automáticas mantengan indefinidamente una sesión.

### 3.3 Sesiones simultáneas

Máximo fijo de **5 sesiones activas por cuenta**, sin opción de configuración en v0.7.0.

Al intentar crear una sexta sesión, rechazar el acceso sin cerrar automáticamente ninguna de las anteriores.

El usuario podrá administrar sus sesiones existentes.

### 3.4 Administración de sesiones

**Mi perfil:**

- Consultar sesiones propias.
- Identificar sesión actual.
- Consultar navegador, sistema operativo, IP y última actividad.
- Cerrar sesiones individuales.
- Cerrar todas las demás sesiones.

**Administración → Sesiones activas:**

- Disponible para administradores autorizados.
- Consultar sesiones según los límites de administración de cuentas.
- Filtrar por responsable, usuario, IP y actividad reciente.
- Cerrar sesiones autorizadas.
- Registrar en auditoría las terminaciones administrativas.

La implementación deberá considerar que algunos navegadores pueden duplicar `sessionStorage` al duplicar pestañas. No asumir independencia absoluta sin validarlo.

### 3.5 Manejo de errores

- **401:** sesión inexistente, inválida o vencida. Redirigir al login mostrando una explicación.
- **403:** usuario autenticado sin permiso. Mostrar pantalla de acceso denegado.
- Intentar preservar temporalmente formularios sin guardar ante una expiración, sin crear un mecanismo de autoguardado en el servidor.

---

## 4. Bloque III — Roles y permisos

### 4.1 Roles predeterminados

| Rol | Alcance |
|---|---|
| Superadministrador | Acceso completo y administración de seguridad |
| Administrador | Gestión administrativa autorizada, sin control total de roles |
| Operador | Gestión operativa según permisos |
| Auditor / Solo lectura | Consulta y reportería autorizada |

Los cuatro roles predeterminados serán fijos y definidos en código.

No podrán eliminarse ni editarse como roles personalizados.

### 4.2 Roles personalizados

Solo el Superadministrador podrá:

- Crear roles.
- Editar sus permisos.
- Duplicar roles predeterminados o personalizados.
- Eliminar roles personalizados sin responsables asignados.
- Comparar permisos de dos roles.
- Consultar el historial de cambios de roles.

Cada responsable con acceso tendrá exactamente un rol.

Los nombres de roles serán únicos sin distinguir mayúsculas y minúsculas.

Se admitirá una descripción opcional.

Los roles nuevos comenzarán sin permisos.

Los roles duplicados copiarán los permisos de origen, pero podrán modificarse independientemente.

### 4.3 Matriz de permisos

Definir permisos granulares por módulo y acción, por ejemplo:

- Consultar.
- Crear.
- Editar.
- Eliminar.
- Cerrar o escalar tickets.
- Ejecutar operaciones.
- Enviar notificaciones manuales.
- Consultar reportes.
- Exportar reportes.
- Administrar catálogos específicos.

Contemplar los módulos actuales:

- Dashboard.
- Tickets de clientes.
- Tickets internos.
- Activaciones.
- Cambios de capacidad.
- Bajas y reactivaciones.
- Control de cambios.
- Circuitos.
- Clientes.
- Sectores.
- Nodos.
- Responsables y puestos.
- Catálogos restantes.
- Reportería.
- Configuración de notificaciones.
- Administración de accesos y seguridad.

La matriz deberá corresponder a las rutas y acciones reales del repositorio.

### 4.4 Reglas de dependencia

- Editar requiere consultar.
- Crear requiere el acceso contextual necesario.
- Deshabilitar consulta debe retirar los permisos dependientes.
- La interfaz agrupará permisos por módulo, con secciones desplegables y selección conjunta.
- Advertir al abandonar un formulario con cambios sin guardar.

### 4.5 Aplicación de permisos

Los cambios de rol o permisos surtirán efecto inmediatamente, incluso en sesiones activas.

Cuando corresponda, mostrar:

**«Tus permisos han sido actualizados».**

Si el usuario pierde acceso al módulo actual, redirigirlo a uno permitido.

Si no tiene permisos sobre módulos operativos, podrá acceder únicamente a Mi perfil.

Los módulos, botones, enlaces, menús y resultados de búsqueda no autorizados deberán ocultarse.

Los endpoints del backend deberán comprobar autorización independientemente de React.

### 4.6 Reportería y datos relacionados

Los permisos de consulta y exportación de reportes serán independientes.

Un reporte autorizado mostrará todos sus datos necesarios, aunque algunos provengan de catálogos que el usuario no pueda administrar o consultar de manera independiente.

La información contextual relacionada con un registro autorizado no otorgará acceso completo a otros módulos.

El Dashboard tendrá permiso propio, pero sus datos respetarán las autorizaciones de los módulos de origen.

### 4.7 Administración de roles y cuentas

El Administrador podrá asignar roles existentes únicamente dentro de sus facultades, sin elevar privilegios por encima de los propios.

No podrá administrarse a sí mismo para elevar permisos ni modificar cuentas de administradores equivalentes o superiores.

Los roles personalizados con permisos operativos sobre responsables no obtendrán automáticamente facultades de administración de credenciales.

Solo los administradores autorizados podrán habilitar cuentas o gestionar contraseñas.

Siempre deberá permanecer al menos un Superadministrador activo.

### 4.8 Compatibilidad futura

Los módulos nuevos no otorgarán automáticamente permisos a roles personalizados.

Los permisos de los roles predeterminados se definirán explícitamente en cada versión.

Las migraciones de permisos deberán ser seguras e idempotentes.

---

## 5. Bloque IV — Responsables y perfil

### 5.1 Integración con Responsables

Modificar el formulario y las rutas existentes, evitando duplicar entidades.

Permitir habilitar, deshabilitar y administrar el acceso desde el responsable correspondiente.

Al deshabilitar una cuenta:

- Invalidar sus sesiones.
- Conservar nombre de usuario, rol, contraseña y antecedentes.
- Permitir reactivación posterior sin restablecimiento obligatorio.

La eliminación definitiva de un responsable seguirá las restricciones de integridad histórica existentes y no podrá eliminar al último Superadministrador activo.

Si la eliminación es válida, también deberán invalidarse las sesiones y retirarse las credenciales.

### 5.2 Mi perfil

Mostrar:

- Nombre del responsable.
- Nombre de usuario.
- Puesto operativo.
- Rol asignado.
- Cambio de contraseña.
- Sesiones activas.

El encabezado de Ticketyn mostrará el responsable autenticado y ofrecerá **Mi perfil** y **Cerrar sesión**.

No permitir autoasignación de roles ni edición de privilegios desde Mi perfil.

---

## 6. Bloque V — Auditoría de seguridad

**Alcance definitivo aprobado el 20/10/2026.** Sustituye el bloque anterior de auditoría operativa, resúmenes, exportaciones y limpiezas manuales.

### 6.1 Ubicación y acceso

**Administración → Auditoría**.

Consulta por Administrador y Superadministrador. Los roles personalizados pueden recibir `audit.view` conforme a los acuerdos sobre permisos administrativos específicos. Operador y Auditor / Solo lectura no reciben Administración automáticamente.

Los registros son de solo lectura. No hay edición, eliminación individual, exportación ni limpieza manual desde esta pantalla o su API. El historial de definiciones de roles sigue reservado al Superadministrador; la consulta general no debe permitir eludir esa restricción.

### 6.2 Eventos incluidos

- Inicio de sesión correcto e incorrecto; esta regla sustituye expresamente la exclusión anterior de logins exitosos.
- Cambios y restablecimientos de contraseñas.
- Habilitación y deshabilitación de acceso.
- Cambios de roles, permisos y asignación de roles.
- Cierres y revocaciones explícitas de sesiones.
- Bootstrap, recuperación administrativa y demás eventos críticos de autenticación/autorización ya contemplados en la arquitectura.
- Modificación del período de retención, sin convertirla en configuración general de seguridad.

Los intentos fallidos pueden conservar la agrupación por usuario, IP y período ya prevista, sin atribuir a los grupos un conteo no registrado. No auditar consultas ordinarias, clics, comprobaciones automáticas de permisos ni expiraciones normales de sesión.

**Excluido:** instrumentar auditoría de tickets, circuitos, activaciones, cambios de capacidad, bajas/reactivaciones de circuitos o ventanas de mantenimiento. Sus históricos y bitácoras operativas permanecen separados e intactos. No ampliar esta fase a la configuración de correo ni crear historial de envíos.

### 6.3 Integridad y protección de secretos

Reutilizar `SecurityAudit`, `SecurityConfig` y los permisos existentes cuando corresponda. Registrar el actor autenticado, distinto del responsable operativo seleccionado.

En las mutaciones críticas, evento y cambio comparten transacción; si falla la auditoría obligatoria, no completar la modificación. No crear un evento por cada persona afectada al modificar un rol. El diseño técnico debe preservar la coherencia entre un login auditado y la sesión RAM emitida.

Nunca guardar contraseñas, hashes, tokens, credenciales, claves ni secretos en registros nuevos, respuestas de auditoría, logs o metadatos de auditoría. Registrar que se cambió un secreto, nunca su valor. No confundir esta prohibición con los hashes necesarios para autenticación y sesiones, que siguen en sus componentes actuales.

### 6.4 Consulta

Tabla con fecha/hora, usuario o identificador disponible, tipo de evento, resultado e información relevante permitida de la acción. Orden de más reciente a más antiguo por fecha e id, con paginación PostgreSQL de 50 registros por página.

Filtros básicos combinables: fecha o período, usuario/Responsable o identificador disponible, tipo de evento y resultado. No exigir los filtros operativos avanzados del alcance sustituido. No agregar dashboard, estadísticas, resumen ni exportaciones PDF/XLSX de auditoría.

Guardar fechas UTC y mostrarlas según la zona Ticketyn. Si falta información histórica, mostrar que no está disponible; no reconstruir usuarios, fechas, cantidades ni acciones a partir de suposiciones. Mantener los grupos fallidos antiguos como registros de grupo, sin fingir que contienen todos sus intentos individuales.

### 6.5 Retención y limpieza automática

Una única retención predeterminada de **365 días para todos los registros de auditoría de seguridad**, incluidos logins fallidos y grupos anteriores. Sustituye los períodos separados de 365/7 días del alcance anterior.

Solo el Superadministrador puede ajustar el período, con advertencia y confirmación al reducirlo. El rango técnico está propuesto en el diseño, pendiente de revisión; no habilitar retención ilimitada ni borrado inmediato por valor cero.

Limpieza automática de registros vencidos desde el backend existente, con lotes y transacciones cortas, sin infraestructura externa ni procesos nuevos. Si falla, registrar un error técnico saneado y reintentar sin detener las operaciones normales. Conservar registros exactamente en el límite de retención. No borrar durante una migración ni cambiar históricos operativos.

No ofrecer limpieza manual, edición o eliminación individual de registros en la interfaz ni endpoints equivalentes.

---

## 7. Ajuste de retención, sin panel general de Seguridad

La propuesta anterior de **Administración → Seguridad** queda sustituida para v0.7.0.

En Administración → Auditoría, mostrar exclusivamente al Superadministrador un control sencillo del período de retención. No ofrecer configuración de inactividad, número de sesiones, política de intentos fallidos, contraseñas ni otros parámetros generales de seguridad.

Las políticas de sesiones siguen fijas: **30 minutos de inactividad y máximo 5 sesiones simultáneas**. Se conservan advertencia de dos minutos, sesiones en RAM, renovaciones por actividad real y comprobaciones de permisos que no renuevan la sesión. La protección actual de intentos fallidos no se vuelve configurable en esta fase.

Los campos o permisos históricos que ya existan en código no autorizan a habilitar funcionalidades excluidas. No modificar destructivamente su esquema para eliminar definiciones sin uso. La configuración de correo mantiene sus secciones y permisos existentes.

---

## 8. Migración inicial

### 8.1 Alembic

Crear migraciones para:

- Incorporar los campos de acceso necesarios a Responsables.
- Crear estructuras persistentes de roles personalizados y asignaciones.
- Incorporar estructuras de auditoría y configuración de seguridad.
- Crear los cuatro roles predeterminados.
- Preservar todos los responsables y registros operativos existentes.

No habilitar automáticamente ninguna cuenta existente.

Las migraciones deberán ser reproducibles e idempotentes cuando corresponda.

### 8.2 Primer Superadministrador

Implementar un comando CLI ejecutado directamente en el servidor para crear el primer Superadministrador.

No crear:

- Registro público.
- Cuenta administrativa predeterminada.
- Contraseña fija.
- Endpoint público de bootstrap.

Hasta completar la configuración inicial, los módulos operativos deberán permanecer protegidos.

---

## 9. Integración técnica

### Backend

- Dependencias de autenticación y autorización reutilizables.
- Validación de sesión y permisos en endpoints.
- Gestión segura de contraseñas y tokens.
- Administración de sesiones en memoria.
- Gestión de roles y permisos.
- Auditoría transaccional.
- Limpieza de registros vencidos.
- Manejo uniforme de errores 401 y 403.

### Frontend

- Pantalla de login.
- Gestión de token en `sessionStorage`.
- Protección de rutas.
- Navegación y acciones condicionadas por permisos.
- Gestión de roles.
- Integración de acceso en Responsables.
- Mi perfil y sesiones.
- Auditoría de seguridad con filtros básicos y paginación.
- Ajuste exclusivo de retención dentro de Auditoría, sin panel general de Seguridad.
- Manejo de expiración de sesión y cambios inmediatos de permisos.

No duplicar componentes o servicios cuando existan alternativas reutilizables en el proyecto.

---

## 10. Orden de implementación

### Fase 1 — Autenticación
Modelos, migraciones iniciales, bootstrap, contraseñas, login, tokens y sesiones.

### Fase 2 — Roles y permisos
Roles predeterminados, personalizados, matriz de autorización, dependencias y validaciones backend.

### Fase 3 — Responsables y perfil
Integración en formularios existentes, administración de cuentas, Mi perfil y sesiones activas.

### Fase 4 — Auditoría de seguridad
Eventos de autenticación y seguridad, consulta con filtros básicos y paginación, retención única de 365 días ajustable solo por Superadministrador y limpieza automática. Sin auditoría operativa, exportaciones, estadísticas, limpieza manual ni panel general de configuración. Diseño vigente: [diseno-fase-4-v0.7.0.md](diseno-fase-4-v0.7.0.md).

### Fase 5 — Integración y pruebas
Proteger todos los módulos, revisar navegación, probar permisos, ejecutar pruebas completas y preparar release.

**Importante:** Aunque la auditoría tenga una fase específica, los eventos críticos deberán incorporarse progresivamente desde las fases anteriores.

---

## 11. Pruebas y criterios de aceptación

Validar como mínimo:

- Login correcto e incorrecto.
- Usuarios inexistentes y cuentas deshabilitadas.
- Cambio obligatorio de contraseña inicial.
- Restablecimiento administrativo.
- Vencimiento y renovación de sesiones.
- Límite de cinco sesiones.
- Invalidación por cambios de contraseña y deshabilitación.
- Cambios inmediatos de permisos.
- Restricciones entre Administrador y Superadministrador.
- Prevención de escalación de privilegios.
- Protección de endpoints por acceso directo.
- Acceso correcto a reportes y datos relacionados.
- Integridad de históricos.
- Auditoría de eventos relevantes de seguridad, incluidos login correcto e incorrecto.
- Ausencia de contraseñas, hashes, tokens y secretos en registros y respuestas de auditoría.
- Retención única, ajuste exclusivo por Superadministrador y limpieza automática.
- Ausencia de rutas o acciones de exportación, estadísticas, limpieza manual y configuración de sesiones dentro de auditoría.
- Compatibilidad con los módulos existentes.
- Errores 401 y 403.
- Migraciones sobre una copia de datos reales.

Agregar pruebas automatizadas de backend y frontend.

No considerar terminada la versión únicamente porque el login funcione.

---

## 12. Entrega y despliegue

1. Trabajar en rama de desarrollo, sin modificar directamente la versión estable.
2. Inspeccionar el estado real del repositorio antes de cambiar archivos.
3. Implementar y probar cada bloque.
4. Ejecutar pruebas backend y frontend.
5. Ejecutar `npm run build`.
6. Verificar que `frontend/dist/` esté incluido correctamente.
7. Validar migraciones y funcionamiento en TEST.
8. Respaldar PostgreSQL antes de migrar PRODUCCIÓN.
9. Publicar manualmente siguiendo el procedimiento de releases existente.
10. Validar login, roles, permisos y módulos operativos después del despliegue.

**Rollback:** restaurar conjuntamente la versión anterior del aplicativo y el respaldo de base de datos previo a la migración. Advertir que los registros creados después de ese respaldo podrían perderse.

---

## 13. Restricciones de alcance

No incorporar en v0.7.0 sin aprobación adicional:

- Registro público de usuarios.
- Autenticación con proveedores externos.
- Recuperación por correo.
- MFA.
- Redis o almacenamiento persistente de sesiones.
- Jerarquías nuevas de responsables.
- Rediseño completo de Ticketyn.
- Nuevos módulos operativos ajenos a seguridad.
- Automatización del procedimiento de releases.

---

## 14. Instrucción para iniciar desarrollo

**Implementar Ticketyn v0.7.0 siguiendo esta especificación como alcance funcional aprobado.**

Antes de modificar código:

1. Inspeccionar la estructura actual del repositorio, modelos, migraciones, rutas, componentes y pruebas.
2. Comparar la especificación con las funcionalidades reales de v0.6.x.
3. Identificar dependencias técnicas y posibles incompatibilidades.
4. Proponer el desglose de implementación por archivos y migraciones.
5. No modificar código hasta validar el plan técnico.
6. Mantener los cambios acotados a la versión 0.7.0.

Las decisiones funcionales de este documento están cerradas. Las decisiones técnicas que requieran adaptación al código real deberán justificarse antes de implementarse.

**Fin del documento maestro — Ticketyn v0.7.0.**