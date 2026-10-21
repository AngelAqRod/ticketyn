# Ticketyn v0.7.0 — Acuerdos complementarios de seguridad y permisos

**Estado:** Decisiones funcionales aprobadas durante la revisión del diagnóstico técnico
**Documento principal:** `docs/planificacion-v0.7.0.md`
**Naturaleza:** Complemento del documento maestro, no sustitución
**Implementación:** Fases 1–3 completadas según el handoff; fase 4 redefinida y pendiente de autorización. Este documento no autoriza modificar código, migrar ni desplegar.

> **Decisión posterior aprobada — 20/10/2026:** la fase 4 queda limitada a Auditoría de seguridad. La sección 8 actualizada sustituye el alcance anterior de esa fase, incluida la exportación de auditoría. Se mantienen las demás decisiones que no entren en conflicto.

## 1. Alcance y precedencia

Este documento registra las decisiones tomadas tras la inspección técnica de v0.7.0. Debe leerse junto con el documento maestro. Cuando precise o cambie una regla del documento maestro, prevalece **esta decisión posterior para ese punto específico**. El resto de la especificación original permanece vigente.

No implementar nuevas funcionalidades operativas para justificar permisos. La seguridad debe adaptarse a los flujos que Ticketyn ya ofrece.

## 2. Operador: operaciones y reportería, no Administración

El rol predeterminado **Operador** tiene acceso a las áreas de **Operaciones** y **Reportería**, con las acciones operativas permitidas, pero **no tiene acceso a ninguna sección de Administración**.

- Puede consultar, crear, editar y eliminar registros operativos **donde esas acciones ya existan y respetando las restricciones de integridad y permisos específicos**.
- Puede consultar y exportar reportes operativos.
- No puede administrar cuentas, contraseñas, roles, permisos, seguridad, SMTP, OAuth2, configuración administrativa ni controles administrativos del procesador de correo.
- La autorización debe aplicarse en el backend, no solo ocultando navegación.

### Catálogos existentes

Los catálogos que actualmente se administran desde **Administración** permanecen allí y no serán accesibles al Operador por esa vía.

Si un formulario operativo **ya permite** crear o modificar un dato relacionado —por ejemplo, agregar un nodo cuando esa función exista—, se conserva esa capacidad para el Operador en ese contexto. Si el formulario **no ofrece** esa función, el Operador no podrá agregar ese dato por otra vía administrativa.

No agregar nuevas acciones rápidas, formularios ni endpoints contextuales únicamente para ampliar los permisos del Operador.

**Distinción importante:** la edición operativa de un Responsable, si existe fuera de Administración, jamás otorga acceso a sus credenciales o privilegios.

## 3. Control de cambios

El módulo **Control de cambios** es una excepción expresa al acceso operativo amplio del Operador.

| Acción | Operador | Administrador | Superadministrador | Rol personalizado |
|---|---|---|---|---|
| Consultar ventanas, detalles e historial | Sí | Sí | Sí | Según permisos |
| Crear ventanas | No | Sí | Sí | Según permisos |
| Editar ventanas | No | Sí | Sí | Según permisos |
| Iniciar, ejecutar y finalizar cambios | No | Sí | Sí | Según permisos |
| Exportar reportes | Sí | Sí | Sí | Según permisos |

No crear un rol predeterminado «Operador de cambios». Un Superadministrador podrá configurar, por ejemplo, un rol personalizado «Operador N3» con facultades sobre Control de cambios sin otorgarle automáticamente toda la Administración.

## 4. Roles predeterminados y personalizados

Se mantienen los cuatro roles predeterminados: Superadministrador, Administrador, Operador y Auditor / Solo lectura.

- **Superadministrador y Administrador no pueden duplicarse.**
- **Operador y Auditor / Solo lectura sí pueden duplicarse.**
- Los roles personalizados también pueden duplicarse.
- Los roles personalizados pueden recibir **permisos específicos de Administración**, según configuración del Superadministrador. No quedan limitados exclusivamente a Operaciones y Reportería.
- Las facultades exclusivas del Superadministrador siguen reservadas y no pueden obtenerse mediante duplicación ni asignación indirecta.
- Un rol personalizado con permisos sobre datos operativos de Responsables no adquiere por ello facultades para administrar credenciales o accesos.
- Los roles nuevos siguen comenzando sin permisos, conforme al documento maestro.

El Administrador predeterminado tiene acceso completo a la gestión de **Control de cambios**, sin que eso le conceda las facultades exclusivas del Superadministrador.

## 5. Baja y reactivación de Responsables: efecto doble

Se aprueba que la baja y reactivación operativa del Responsable también afecten su acceso a Ticketyn.

**Al desactivar un Responsable:**
- Queda inactivo como Responsable operativo.
- Su acceso queda deshabilitado.
- Se invalidan inmediatamente sus sesiones.
- Se conservan identidad de cuenta, credenciales, rol e historial.

**Al reactivar un Responsable:**
- Recupera su estado operativo activo.
- Recupera automáticamente el acceso **solo si ya estaba habilitado antes de la baja**.
- Si no tenía acceso habilitado previamente, no se le crea cuenta ni se le habilita acceso.
- Se conservan credenciales y rol; no se obliga a un restablecimiento por la mera reactivación.

**Requisito técnico:** conservar el estado previo de habilitación de acceso, de modo que una reactivación no habilite por error cuentas que ya estaban deshabilitadas. No permitir desactivar al último Superadministrador activo.

Se mantienen los controles de seguridad independientes que correspondan a una suspensión administrativa de acceso, sin alterar accidentalmente el estado operativo.

**Eliminación de Responsables:** no incorporar eliminación física ni endpoint DELETE nuevo en v0.7.0. Se mantiene el comportamiento actual de desactivación/reactivación para preservar históricos.

## 6. Contraseñas y recuperación administrativa

- No aceptar contraseñas completamente vacías.
- No imponer longitud mínima adicional, complejidad ni vencimiento periódico.
- Conservar el uso de Argon2id y las reglas de contraseña temporal, cambio inicial, restablecimiento e invalidación de sesiones del documento maestro.
- Establecer un límite técnico razonable de tamaño de entrada para evitar abuso, sin introducir requisitos de complejidad no aprobados.

**Recuperación del único Superadministrador:** implementar un comando CLI ejecutado directamente en el servidor por un administrador del sistema, capaz de restablecer su contraseña **sin crear otra cuenta ni modificar su rol**. Debe invalidar sus sesiones y registrar el restablecimiento en auditoría, sin registrar secretos. Distinguir este comando de la creación inicial del primer Superadministrador.

## 7. Sesiones, OAuth2 y actualización de permisos

- Las sesiones normales de Ticketyn utilizan tokens opacos transportados por `Authorization` y almacenados en `sessionStorage`, según el documento maestro.
- Se conserva **exclusivamente para el callback OAuth2 de correo** la cookie técnica temporal que ya existe, sin convertirla en cookie de sesión Ticketyn. El callback debe quedar vinculado a un flujo autorizado y protegido.
- Los cambios de permisos tienen efecto inmediato en el backend.
- React actualiza la interfaz al navegar, recuperar foco y mediante comprobaciones ligeras y controladas; no se requieren WebSockets.
- Las consultas automáticas de permisos no deben renovar artificialmente la actividad de sesión.

## 8. Alcance definitivo de fase 4 — Auditoría de seguridad

**Decisión posterior aprobada el 20/10/2026.** Esta sección sustituye expresamente la anterior autorización de exportación PDF/XLSX de auditoría y las disposiciones incompatibles del documento maestro y del diseño anterior.

### Incluido

- Logins correctos e incorrectos; se sustituye la exclusión anterior de logins exitosos.
- Cambios/restablecimientos de contraseñas, habilitación/deshabilitación de acceso, cambios de roles y permisos, revocaciones de sesiones y otros eventos críticos de autenticación/autorización existentes.
- Tabla de solo lectura con fecha/hora, usuario o identificador disponible, tipo de evento e información relevante, filtros básicos combinables y paginación.
- Una única retención predeterminada de **365 días**, también para los fallos de autenticación y grupos históricos; ajustable únicamente por Superadministrador.
- Limpieza automática de registros vencidos desde el backend actual, sin infraestructura externa ni procesos innecesarios.
- Reutilización de `SecurityAudit`, `SecurityConfig` y permisos existentes, excluyendo contraseñas, hashes, tokens y secretos de los registros nuevos.

### Excluido

- Auditoría de tickets, circuitos, activaciones y ventanas de mantenimiento, y ampliaciones de auditoría a otros flujos operativos.
- Exportaciones PDF/XLSX de auditoría.
- Dashboard, estadísticas y resúmenes de auditoría.
- Panel general de configuración de Seguridad.
- Configuración de duración o cantidad de sesiones, y de la política de intentos fallidos.
- Limpiezas manuales y edición/eliminación individual de registros desde la interfaz o endpoints equivalentes.

Las políticas de sesiones permanecen **fijas en 30 minutos de inactividad y cinco sesiones simultáneas**. No cambia la administración de sesiones activas completada en fase 3 ni la advertencia de dos minutos.

### Permisos, retención e históricos

Se mantiene consulta por Administrador/Superadministrador y por personalizados con `audit.view` concedido expresamente. No se otorga Administración al rol Auditor / Solo lectura. El historial de definiciones de roles conserva su exclusividad de Superadministrador.

El ajuste de retención será un control limitado dentro de Auditoría, protegido con el permiso exclusivo existente `security.configure`; no habilita el antiguo panel general. Los permisos ya declarados `audit.export` y `audit.clean` no dan lugar a rutas o botones nuevos: quedan sin operación de fase 4. No renombrar ni eliminar por ello la matriz existente de 147 permisos.

Los anteriores períodos separados de 365/7 días quedan sustituidos por la política única de 365 días. Conservar los campos históricos de esquema que no se utilicen y los registros existentes; no ejecutar borrados durante una migración. No alterar bitácoras operativas.

Cuando un grupo fallido anterior carezca de usuario identificable o de conteo de intentos, indicarlo sin inventar datos. No convertir una huella histórica en una identidad, no duplicar el grupo como eventos individuales y no exponer hashes en la consulta.

### Propuestas técnicas pendientes de revisión

El diseño propone retención entera entre **1 y 3650 días**, con 365 iniciales, y una limpieza diaria por lotes dentro del ciclo de vida del backend. Estos detalles técnicos se revisarán antes de implementar. No se mantiene pendiente aprobar exportaciones, limpieza manual o configuración de sesiones: están excluidas.

Diseño de continuidad: [diseno-fase-4-v0.7.0.md](diseno-fase-4-v0.7.0.md). Su actualización y esta decisión no autorizan implementación, migraciones ni despliegues.

## 9. Corrección del indicador de versión

Se mantiene para **v0.7.0** la corrección pendiente del indicador de versión:

- `pyproject.toml` será la referencia del proyecto.
- El mecanismo debe funcionar en desarrollo editable y en despliegues por releases.
- No confiar ciegamente en metadatos obsoletos de `importlib.metadata`.
- `FastAPI.version` y `/api/system/version` deben ser coherentes.
- No cambiar innecesariamente el frontend, que ya muestra el valor recibido.
- No modificar ni reutilizar la etiqueta oficial v0.6.2.

Esta tarea debe figurar explícitamente en el plan de implementación y sus pruebas.

## 10. Próximos pasos y límites

1. Revisar el diseño actualizado de Auditoría de seguridad y sus propuestas técnicas de retención y limpieza.
2. Esperar autorización explícita para implementar la fase 4. Las fases 1–3 ya completadas deben conservarse; no reiniciarlas.
3. No adelantar fase 5, publicación o despliegue; mantener pendiente la corrección centralizada del indicador de versión.
4. No modificar DEV, TEST ni PRODUCCIÓN durante esta tarea documental.
5. No crear código, pruebas o migraciones, ejecutar builds ni realizar commits/pushes.

Las reglas aprobadas de contraseñas, Argon2id, protección de intentos y sesiones de las fases anteriores continúan vigentes. La nueva fase no debe convertirlas en opciones configurables. Solo los detalles técnicos identificados en el diseño necesitan revisión; no volver a plantear decisiones funcionales ya resueltas.
