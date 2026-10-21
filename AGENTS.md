# Ticketyn — Instrucciones del Proyecto y Mecanismo de Continuidad Multagente

Este documento define las reglas operativas y el protocolo de colaboración continua entre **Codex CLI** y **Antigravity GUI** para el desarrollo del proyecto Ticketyn.

Ambos agentes deben cumplir estrictamente estas directrices.

---

## 1. Protocolo de Traspaso Continuo (`AGENT_HANDOFF.md`)

Para garantizar que cualquier agente pueda retomar el trabajo del otro sin repetir tareas, sobrescribir código ni perder cambios:

1. **Lectura obligatoria al iniciar:** Al comenzar cada sesión o turno de trabajo, el agente DEBE leer `/AGENT_HANDOFF.md` en la raíz del repositorio para conocer el estado dejado por el agente anterior.
2. **Contraste con la realidad:** No asumir ciegamente lo que indica el documento. Contrastar SIEMPRE su contenido con el estado real de Git (`git status`, `git branch`, últimos commits, diffs) y el código en disco.
3. **Actualización obligatoria:** Actualizar `/AGENT_HANDOFF.md` después de completar cada tarea significativa y antes de finalizar el turno de trabajo.
4. **Reemplazo sin acumulación:** Al actualizar, sobrescribir el estado anterior con la fotografía actualizada y vigente del proyecto. No acumular un registro histórico extenso en este archivo.
5. **Estructura requerida de `AGENT_HANDOFF.md`:**
   * Agente que trabajó por última vez.
   * Fecha y hora de actualización.
   * Rama Git activa.
   * Tarea actual.
   * Cambios relevantes realizados.
   * Archivos principales afectados.
   * Estado: completado, en proceso y pendiente.
   * Pruebas ejecutadas y pruebas pendientes.
   * Problemas o riesgos conocidos.
   * Próximo paso concreto.

---

## 2. Reglas Generales de Operación para Ambos Agentes

1. **Respeto al trabajo previo:** No modificar ni descartar trabajo o archivos creados por el otro agente sin revisarlos y justificarlos técnicamente.
2. **Control de cambios e integraciones:**
   * No realizar `git commit` ni `git push` sin autorización expresa del usuario.
   * No aplicar migraciones Alembic sobre bases compartidas o entornos operativos sin autorización expresa.
   * No ejecutar comandos destructivos (`git reset --hard`, `git checkout --`, `rm`, etc.).
3. **Aislamiento estricto de entornos:**
   * No modificar ni conectar a entornos de **TEST** ni **PRODUCCIÓN** durante el desarrollo.
   * Las pruebas automatizadas utilizan clústeres efímeros de PostgreSQL (`tmp_path_factory` en `conftest.py`) y nunca deben tocar la base de datos de desarrollo ni productiva.
4. **Procedimiento de Releases:**
   * Mantener el procedimiento manual de releases documentado en el proyecto.
   * Antes de dar por finalizada una versión o preparar una entrega, ejecutar `npm run build` en `frontend/` y verificar que el directorio `frontend/dist/` se genere correctamente y esté sincronizado.

---

## 3. Principios Arquitectónicos de Ticketyn (v0.7.0+)

1. **Identidad única de personas y cuentas:**
   * La tabla `responsibles` representa la identidad única de las personas en Ticketyn.
   * **Responsables son los Usuarios de Ticketyn.** No debe crearse un catálogo paralelo ni una tabla duplicada de usuarios.
   * El acceso al sistema se habilita o inhabilita directamente sobre el registro existente en `responsibles`.
2. **Dimensiones de estado independientes:**
   * `active`: Estado operativo de la persona. Si se da de baja (`active=false`), sus sesiones se invalidan de inmediato.
   * `access_granted`: Autorización administrativa persistente. Al reactivar operativamente a una persona, solo recupera acceso si `access_granted` ya era verdadero.
   * `operational_selectable`: Disponibilidad para nuevas asignaciones operativas. Permite que usuarios administrativos (ej. `admin-dev`) tengan cuenta y rol sin figurar en selectores de nuevos tickets u operaciones.
   * **Históricos preservados:** Los registros y asignaciones históricas jamás deben alterarse ni eliminarse por cambios de disponibilidad o acceso.
3. **Autorización y Seguridad:**
   * Todas las comprobaciones de seguridad se realizan en el **backend** (`SafeAuthRoute`, `routes.py`, `permissions.py`). Ocultar botones en React es solo una mejora de experiencia de usuario y no constituye seguridad suficiente.
   * Denegación por defecto: cualquier ruta no declarada explícitamente en el inventario cerrado se deniega con 403.
   * Las mutaciones de cuentas, roles y sesiones deben ejecutarse bajo bloqueo transaccional de seguridad (`lock_security(session)`).
   * **Protección del último Superadministrador:** Está estrictamente prohibido eliminar, desactivar o retirar facultades al último Superadministrador activo.
4. **Sesiones y Despliegue Monoproceso:**
   * Las sesiones utilizan tokens opacos y metadatos alojados en **memoria RAM** del backend (`SecurityMemory`).
   * No existen tablas de sesiones en base de datos ni servicios de caché como Redis.
   * La aplicación está diseñada para operar como **un único trabajador HTTP** (`--workers 1`). No levantar múltiples instancias o procesos worker simultáneos.
