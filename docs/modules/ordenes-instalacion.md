# Órdenes de instalación

Antecedente documental del servicio, independiente del circuito y de su activación.
Una recepción de correo crea una solicitud pendiente; únicamente una validación
humana crea una orden definitiva. No hay estados de ejecución de instalaciones.

## Invariantes

- Toda orden nueva es `NORMAL` o `EXTRAORDINARY` (`installation_orders.order_type`).
  **El tipo es permanente**: ni la API (`PATCH` lo rechaza con 422) ni la base de
  datos (trigger `installation_order_type_immutable`) permiten cambiarlo, y nunca
  se deduce solo de `circuit_id`.
- `NORMAL`: circuito existente obligatorio y del mismo cliente; relación 1:1 con
  `installation_orders.circuit_id` (UNIQUE). Los datos técnicos (servicio, nodo,
  sector, equipo, puerto, CPE) se leen del circuito en cada consulta
  (`technical` en la respuesta); la orden no guarda copias.
- `EXTRAORDINARY`: sin circuito; descripción más servicio, nodo y sector de los
  catálogos existentes (FK activas). Equipo, puerto y CPE no aplican.
- La restricción `ck_installation_orders_order_type_shape` impone ambas formas.
- `order_type NULL` = orden anterior a las modalidades cuyo circuito no existía:
  nunca se clasifica automáticamente. Conserva `service` y `location` (columnas
  heredadas, nulas en órdenes nuevas). Solo vincularla a un circuito
  (`PUT /{id}/circuit`) la convierte en `NORMAL`; las órdenes tipadas rechazan
  vincular, crear circuito o desvincular con 409.
- Creación rápida de cliente y circuito en el formulario de orden normal: reutiliza
  `QuickCatalogCreate` de Tickets y sus permisos (`customers.create` o
  `context.customers.create`; `circuits.create` o `context.circuits.create`);
  `installation_orders.create` no los concede. No guarda la orden.
- El cliente debe existir. El autor procede de la sesión y referencia a
  `responsibles`. La referencia `OI-000001` se genera en PostgreSQL; puede tener
  saltos y no debe interpretarse como un contador de registros.
- Una solicitud genera como máximo una orden. Procesarla bloquea la solicitud y
  crea orden, vínculo, estado y evento en una única transacción.
- Los estados de solicitud son Pendiente, En revisión, Procesada y Descartada.
  Un borrador incompleto no constituye una orden. Su versión impide sobrescribir
  silenciosamente cambios concurrentes; los conflictos devuelven HTTP 409.
- Los originales conservan su origen después de procesar la solicitud. El
  historial no se borra al desvincular un circuito.
- Crear circuito y vincularlo es atómico y conserva las validaciones y permisos
  existentes. Nunca registra una activación automáticamente.

## Arquitectura

| Área | Archivos |
|---|---|
| Persistencia | `src/ticketyn/models/installation_orders.py`, `alembic/versions/0042_installation_orders.py` |
| API | `src/ticketyn/api/installation_orders.py`, `installation_requests.py`, `installation_documents.py`, `incoming_mail.py` |
| Validación | `src/ticketyn/schemas/installation_orders.py` |
| Recepción y documentos | `src/ticketyn/incoming/` |
| Permisos | `src/ticketyn/security/permissions.py`, `routes.py` |
| Interfaz | `frontend/src/pages/Installation*.tsx`, `frontend/src/api/installationOrders.ts`, `frontend/src/components/installation/` |

## Autorización

Los permisos nuevos se conceden inicialmente solo a Administración y
Superadministración. Los roles personalizados no se amplían automáticamente.
Consultar una orden no concede administración del buzón. Acceder a un archivo
requiere autorización sobre su origen o sobre la orden que lo incorpora; conocer
su ID o su ruta no concede acceso.

La interfaz no sustituye las comprobaciones del backend. La creación de circuito
desde orden exige vinculación y la facultad existente de creación de circuitos.

## Correo y documentos

El receptor entrante es independiente de las notificaciones salientes de FMS.
La ausencia de configuración IMAP no impide el registro manual.
La identidad de recepción incluye buzón, carpeta, UIDVALIDITY y UID; Message-ID y
checksum son evidencia adicional y no permiten descartar correos por semejanza.

El directorio de originales es privado, persistente y ajeno a las releases y al
frontend. No debe publicarse mediante un alias de Nginx. Las imágenes y PDF se
obtienen con autorización para su visualización; Office se descarga, no se
ejecuta ni se incrusta. El cuerpo del correo se muestra como texto, sin imágenes
remotas ni HTML activo. No se incluyen tokens de sesión en URLs.

La operación y recuperación se documentan en
[la guía del módulo](../installation-orders.md).

## Fuera de alcance

Técnicos, visitas, materiales, cuadrillas, estados de ejecución, OCR, inteligencia
artificial, automatización de activaciones y compromisos contractuales de tiempo.
