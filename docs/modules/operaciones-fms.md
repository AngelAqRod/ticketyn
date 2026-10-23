# Ficha Técnica: Gestión Operativa FMS

## Responsabilidad del módulo
- **Qué gestiona:** Las operaciones técnicas que rigen el ciclo de vida del servicio de telecomunicaciones sobre los circuitos: altas iniciales (Activaciones), ajustes técnicos de ancho de banda (Cambios de capacidad) y suspensión o restitución operativa (Bajas y Reactivaciones).
- **Funcionalidades existentes:**
  - *Activaciones:* Registro de alta técnica del circuito con código secuencial propio (`ActivationNumberConfig`), congelación de parámetros técnicos iniciales, bitácora de intervenciones (`ActivationIntervention`) y reporte PDF individual de activación.
  - *Cambios de capacidad:* Registro de aumento o reducción de velocidad con trazabilidad de ancho de banda anterior y nuevo (`CapacityChange`).
  - *Ciclo de vida:* Registro formal de baja técnica con motivo obligatorio y registro de reactivación (`CircuitLifecycleOperation`), actualizando el estado `Circuit.active`.
  - Exportaciones tabulares a PDF y Excel (.xlsx) para cada tipo de operación.
  - Disparo de notificaciones de correo para altas de circuitos.
  - Reportería estadística agregada en formato PDF especializado.
- **Qué no le corresponde:** No gestiona tickets de soporte de averías (corresponde a Tickets), no programa ventanas de mantenimiento sobre la red troncal (corresponde a Control de Cambios) ni administra cuentas de facturación ni contratos comerciales.

## Reglas de negocio críticas
- **Tres operaciones formalmente desacopladas:**
  1. *Activación (`activations`):* Registra el inicio productivo del circuito. Sus datos técnicos (nodo, sector, tipo de servicio, capacidad inicial y modelo CPE) son inmutables tras su creación. Si en registros históricos faltan datos, se exponen como «Sin registrar», sin rellenarlos automáticamente con el circuito actual.
  2. *Instantánea de infraestructura de distribución (`distribution_recorded`, `distribution_device_name`, `distribution_port_name`):* Al crear una activación, se congela el nombre del equipo y del puerto de distribución del circuito en ese momento. Si el circuito no tiene equipo ni puerto asignado al momento del alta, se registra `distribution_recorded=true` y se expone como «No asignado». En activaciones históricas previas a esta funcionalidad (`distribution_recorded=false`), la distribución desconocida se expone como «No registrado», sin inferir retrospectivamente la infraestructura actual del circuito. Un puerto requiere obligatoriamente un equipo (`distribution_device_required`). Cambios posteriores en el circuito no alteran la historia de activaciones pasadas.
  3. *Cambios de capacidad (`capacity_changes`):* Registra exclusivamente modificaciones de ancho de banda. La última operación ejecutada determina la velocidad vigente del circuito.
  4. *Ciclo de vida (`circuit_lifecycle`):* Controla la disponibilidad del servicio. Una baja requiere obligatoriamente un motivo de baja (`deactivation_reason_id`) y desactiva el circuito (`Circuit.active=false`). Una reactivación exige que el circuito esté inactivo y restablece `Circuit.active=true` con motivo nulo.
- **Validación de estados en ciclo de vida:**
  - No se permite registrar una baja sobre un circuito que ya se encuentra dado de baja.
  - No se permite registrar una reactivación sobre un circuito que ya está activo.
- **Límites de volumen en generación PDF de estadísticas:**
  - El generador ReportLab aplica un tope de seguridad estricto de **2.000 operaciones y 2.000.000 de caracteres**.
  - Si la consulta sobrepasa estos umbrales, el backend rechaza la solicitud indicando al usuario que debe acotar el período; jamás debe generarse un PDF truncado silenciosamente.
- **Disparo asíncrono de notificaciones:**
  - Las notificaciones de activación encolan una solicitud en `mail_jobs` de forma asíncrona; no deben demorar la confirmación de la transacción en base de datos ni provocar un rollback de la activación si el transporte de correo falla temporalmente.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`fms.py`, `fms_data.py`, `fms_exports.py`, `fms_reports.py`, `fms_report_exports.py`, `activation_reports.py`, `activation_notifications.py`), modelos en `src/ticketyn/models/fms.py` (`Activation`, `CapacityChange`, `CircuitLifecycleOperation`, `ActivationIntervention`, `DeactivationReason`, `ActivationNumberConfig`), esquemas en `src/ticketyn/schemas/fms.py`, migración `alembic/versions/0034_activation_distribution.py`.
- **Componentes frontend:** Vistas en `frontend/src/pages/` (`Operations.tsx`, `ActivationDetail.tsx`, `FmsReports.tsx`), componentes en `frontend/src/components/` (`OperationsTable.tsx`, `OperationModal.tsx`, `ActivationNotificationActions.tsx`).
- **Dependencias:** Circuitos, Responsables (filtro `operational_selectable=true`), Tipos de Servicio, Motivos de Baja, Modelos CPE, Equipos y Puertos de Distribución y Subsistema de Correo.
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `GET/POST /api/fms/activations`, `GET /api/fms/activations/{id}`, `POST /api/fms/activations/{id}/updates`, `POST /api/fms/capacity-changes`, `POST /api/fms/circuit-lifecycle`, `GET /api/fms/reports`, `POST /api/fms/activations/{id}/notify`.
- **Permisos requeridos:** `activations.view`, `activations.create`, `activations.followup`, `activations.notify`, `activations.export`, `capacity_changes.view`, `capacity_changes.execute`, `capacity_changes.export`, `lifecycle.view`, `lifecycle.deactivate`, `lifecycle.reactivate`, `lifecycle.export`.
- **Separación de roles:** El rol Operador tiene facultades completas de ejecución en FMS, mientras que el rol Auditor únicamente puede consultar y exportar.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_fms.py tests/test_fms_exports.py tests/test_activation_reports.py tests/test_activation_distribution.py tests/test_activation_notifications.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/Fms.test.tsx frontend/src/pages/FmsReports.test.tsx frontend/src/pages/ActivationDistribution.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Verificar que el recálculo dinámico de capacidad tome siempre el último registro de `CapacityChange` ordenado por fecha y no la capacidad inicial del circuito.
  - Comprobar que el tope de 2.000 operaciones en el generador de PDF estadístico lance una excepción controlada comprensible para el usuario.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en el modelo `fms.py`, alteraciones en los eventos de notificación de alta o variaciones en las reglas de cálculo del ciclo de vida.

## Constancia de activación para cliente — v0.8.0

- `customer_activation_notes` es independiente de `activation_notes`; nunca se copian notas internas automáticamente. Registro y consulta, sin edición posterior de datos iniciales de la activación.
- Nuevas activaciones capturan nombre del cliente y código del circuito bajo bloqueo; las antiguas conservan `NULL`, sin reconstrucción desde relaciones actuales.
- `GET /api/activations/{id}/reports/customer/pdf` requiere `activations.export`. Renderizador aislado y proyección positiva en `src/ticketyn/api/customer_activation_reports.py`; no recibe ORM. El PDF interno conserva su ruta y añade notas públicas en sección separada.
- Migración aditiva `0036_customer_activation_notes`, posterior a 0035; no aplicada a bases persistentes por esta tarea. Detalles, límites y pruebas en `docs/customer-activation-certificate-v0.8.0.md`.
