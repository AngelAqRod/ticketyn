# Ficha Técnica: Control de Cambios

## Responsabilidad del módulo
- **Qué gestiona:** La planificación, seguimiento, ejecución y evaluación de ventanas de mantenimiento sobre la red de telecomunicaciones e infraestructura central.
- **Funcionalidades existentes:**
  - Registro de ventanas con numeración secuencial técnica independiente (`ChangeNumberConfig`).
  - Calendario interactivo en tres vistas con diseño Electric Blue 2.0 / Industrial NOC Rounded: **Mes** (celdas Corner Frame E y tarjetas Technical Cut), **Semana** (Extended Grid a 320 px de altura) y **Día** (Technical Timeline Expandida B2).
  - Listado tabular de cambios con filtros unificados compartidos con la vista de calendario.
  - Flujo de estados estricto: **Agendado**, **En ejecución** y **Finalizado**.
  - Asignación de técnico encargado (con departamento institucional congelado históricamente) y equipo de apoyo técnico múltiple.
  - Clasificación obligatoria por Tipo de Cambio y Tipo de Finalización.
  - Bitácora de seguimiento operativo (`ChangeUpdate`) y auditoría (`ChangeAudit`).
  - Vinculación N:M con múltiples tickets internos de infraestructura (`ChangeTicket`).
  - Reportes PDF individuales, listados tabulares en PDF/Excel y reporte estadístico de duraciones y eficiencia.
- **Qué no le corresponde:** No ejecuta comandos sobre routers ni switches, no programa temporizadores que fuercen cambios de estado automáticamente ni cierra o cancela tickets internos vinculados.

## Reglas de negocio críticas
- **Ciclo de estados y validación temporal:**
  - *Agendado:* Requiere fechas y horas planificadas (`proposed_start`, `proposed_end`). Fechas reales opcionales.
  - *En ejecución:* Requiere fecha/hora de inicio real obligatoria (`actual_start`). Fin real opcional.
  - *Finalizado:* Requiere inicio real y fin real obligatorios (`actual_end`), tipo de finalización y notas finales de cierre.
- **Algoritmo de cálculo de eficiencia operativa:**
  - Compara **duraciones de tiempo transcurrido**, no horas absolutas de reloj:
    $$\text{Duración Planificada} = \text{Fin Propuesto} - \text{Inicio Propuesto}$$
    $$\text{Duración Real} = \text{Fin Real} - \text{Inicio Real}$$
  - Aplica un margen de tolerancia inclusivo de **±15 minutos** ($\lvert \text{Duración Real} - \text{Duración Planificada} \rvert \le 15 \text{ min}$).
  - Solo se evalúan cambios finalizados cuyo tipo de finalización haya sido marcado como elegible para eficiencia. Esta elegibilidad se congela históricamente en el registro al momento del cierre.
  - Los cambios no elegibles se etiquetan como «No evaluable» y se excluyen del denominador del porcentaje global de eficiencia.
  - Un inicio retrasado en más de 60 minutos activa el indicador independiente «Inicio tardío», sin anular por sí solo el cálculo de eficiencia de duración.
- **Reglas de participantes:**
  - El encargado (`responsible_id`) requiere departamento asignado.
  - El equipo de apoyo (`ChangeSupport`) admite cero o varios técnicos; no permite técnicos duplicados y rechaza que el encargado figure como apoyo.
- **Zona horaria y ventanas nocturnas:**
  - Todo cálculo utiliza `America/Guatemala`. Soporta trabajos nocturnos que cruzan la medianoche y ventanas de varios días.
- **Vínculos con Tickets Internos:**
  - La asociación es de tipo N:M sin propagación automática de estados entre la ventana y los tickets internos.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`changes.py`, `change_data.py`, `change_reports.py`), modelo en `src/ticketyn/models/change.py` (`MaintenanceChange`, `ChangeType`, `ChangeCompletionType`, `ChangeSupport`, `ChangeTicket`, `ChangeUpdate`, `ChangeAudit`, `ChangeNumberConfig`), esquemas en `src/ticketyn/schemas/change.py`.
- **Componentes frontend:** Vistas en `frontend/src/pages/` (`Changes.tsx`, `ChangeReports.tsx`), componentes compartidos en `frontend/src/components/ChangeShared.tsx`.
- **Dependencias:** Departamentos, Responsables, Tipos de Cambio, Tipos de Finalización y Tickets Internos.
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `GET/POST /api/changes`, `GET/PUT /api/changes/{id}`, `POST /api/changes/{id}/updates`, `GET /api/changes/{id}/pdf`, `GET /api/changes/export`, `GET /api/changes/reports`.
- **Permisos requeridos:** `changes.view`, `changes.create`, `changes.edit`, `changes.execute`, `changes.link`, `changes.followup`, `changes.export`.
- **Restricción por rol:** El rol predeterminado Operador dispone únicamente de `changes.view` y `changes.export` (modo lectura y descarga); no puede crear, editar ni ejecutar ventanas de mantenimiento.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_change_types.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/Changes.test.tsx frontend/src/pages/ChangeReports.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Verificar que el paso a estado Finalizado exija notas de cierre y tipo de finalización.
  - Comprobar que la validación de participantes impida duplicar al encargado dentro de la lista de apoyo.
  - Asegurar que la fórmula de eficiencia considere duraciones con margen de ±15 minutos y conserve la elegibilidad histórica.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en el modelo `MaintenanceChange`, en los algoritmos del motor de eficiencia o en los contratos de presentación del calendario.
