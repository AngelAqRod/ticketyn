# Solicitudes administrativas

Bitácora operativa de requerimientos recibidos. No es un CRM, no tiene aprobaciones y nunca crea tickets, tickets internos ni cambios.

## Invariantes

- **Estado** (`status`, manual, inicial `REGISTERED`; las filas existentes migran a `REGISTERED`):
  `REGISTERED` Registrada (recibida y documentada, sin ejecución), `IN_PROGRESS` En ejecución
  (atendida por el NOC), `COMPLETED` Completada, `CANCELLED` Cancelada. Transiciones permitidas
  (`TRANSITIONS` en `api/admin_requests.py`): `REGISTERED`→`IN_PROGRESS`|`CANCELLED`;
  `IN_PROGRESS`→`REGISTERED`|`COMPLETED`|`CANCELLED`; `COMPLETED`|`CANCELLED`→`REGISTERED`|`IN_PROGRESS`
  (reapertura). Otra transición o el mismo estado responde 422. Solo cambia con
  `POST /api/admin-requests/{id}/status` (`PATCH` lo rechaza) y cada cambio crea un evento `STATUS` con
  `detail {from, to}`, el actor y la fecha. Ninguna fecha cambia el estado automáticamente.
- **Período de aplicación** (`application_start`, `application_end`, `DATE` opcionales e informativos):
  pueden faltar uno o ambos; si están los dos, fin ≥ inicio (422 en API, CHECK `period_valid` y
  validación en el formulario). Es independiente del estado: una solicitud puede completarse antes de
  que termine su período.
- **Solicitante:** siempre un `responsibles` activo y seleccionable en operaciones; tenga
  o no acceso al portal. No existe tabla de solicitantes ni texto libre.
- **Fechas:** `request_date` (día, obligatoria y editable) es cuando se recibió el
  requerimiento; `created_at` (automática, inmutable) es cuándo se registró. Se
  conservan por separado. `created_by` sale de la sesión.
- **Cliente y circuito** son opcionales. Un circuito debe pertenecer al cliente
  indicado; si solo se envía circuito se deriva su cliente. Solo se revalidan las
  relaciones que cambian, así los históricos inactivos siguen editables.
- **Numeración:** referencia `SOL-0000001`, configurable en
  `/api/settings/admin-request-number` con el mismo mecanismo que cambios.
- **Tipos:** catálogo `admin_request_types` (sin datos precargados).
- **Asociaciones** (`admin_request_links`): una fila apunta a exactamente un ticket,
  ticket interno o cambio (CHECK `num_nonnulls = 1`); unicidad por solicitud y
  destino (HTTP 409). Cambiar la fecha o el circuito nunca elimina asociaciones.
- **Ventana de búsqueda:** `request_date ± 15 días`, extremos incluidos, calculada en
  backend (zona `America/Guatemala`) sobre `tickets.start_at`,
  `internal_tickets.start_at` y `maintenance_changes.proposed_start`. Los tickets de
  cliente también se filtran por el circuito de la solicitud o, sin circuito, por su
  cliente. Solo limita candidatos nuevos.

## Arquitectura

| Área | Archivos |
|---|---|
| Persistencia | `src/ticketyn/models/admin_request.py`, `alembic/versions/0044_admin_requests.py`, `0047_admin_request_status.py` |
| API | `src/ticketyn/api/admin_requests.py`, `src/ticketyn/schemas/admin_request.py` |
| Permisos | `src/ticketyn/security/permissions.py`, `src/ticketyn/security/routes.py` |
| Interfaz | `frontend/src/pages/AdminRequests.tsx`, `frontend/src/pages/AdminRequestForm.tsx`, `frontend/src/pages/AdminRequestDetail.tsx`, `frontend/src/components/AdminRequestLinks.tsx` |

## Autorización

`admin_requests.view|create|edit|link` (el cambio de estado reutiliza `edit`), `catalogs.admin_request_types.*` y
`settings.admin_request_number.*` se conceden por defecto solo a Administración y
Superadministración; Operador y Auditor conservan sus grants históricos. Buscar
candidatos exige además `tickets.view`, `internal_tickets.view` o `changes.view`
según el tipo. Los selectores (responsables, clientes, circuitos) se habilitan por
contexto desde `admin_requests`.

## Pruebas

`tests/test_admin_requests.py` y `frontend/src/pages/AdminRequests.test.tsx`.
