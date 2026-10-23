# Constancia de activación de servicio — v0.8.0

## Funcionalidad

Dos documentos independientes, autenticados con `activations.export`:

- Informe interno existente: `GET /api/activations/{id}/reports/pdf`, nombre de descarga `ticketyn-activacion-{id}.pdf`.
- Constancia para cliente: `GET /api/activations/{id}/reports/customer/pdf`, nombre `ticketyn-activacion-{id}-cliente.pdf`.

Ambos conservan opciones de zona horaria, respuesta PDF y `Cache-Control: no-store`. Los identificadores de descarga siguen la convención HTTP existente; el contenido y los metadatos del PDF público no incluyen identificadores internos de base de datos. No hay acceso anónimo ni envío automático nuevo.

## Notas y reglas de edición

- `activation_notes` continúa intacto: notas internas de activación, sin cambios en sus datos previos ni semántica.
- `customer_activation_notes` es opcional, independiente y destinado expresamente al cliente. Campo PostgreSQL `TEXT`, nullable, sin default ni backfill. La API y el formulario aceptan hasta 10.000 caracteres, como las notas internas; conservan texto, párrafos, espacios exteriores no vacíos y saltos. Solo un valor completamente vacío/blanco se normaliza a `null`.
- Se reciben en `ActivationCreate` y se consultan en `ActivationResponse`, tanto en detalle como en listado. No se crean columnas de listado ni XLSX.
- Los datos iniciales de activaciones ya eran inmutables: **no se agregó un endpoint para editar o limpiar posteriormente las notas públicas**. Se pueden dejar vacías al registrar; una corrección posterior requiere diseñar y autorizar otro flujo. La bitácora sigue siendo independiente y no alimenta la constancia.
- La interfaz advierte que las notas para cliente aparecerán en la constancia y que no deben incluir credenciales ni datos internos.

## Identidad histórica: dependencia indispensable detectada

El esquema anterior conserva servicio/capacidad y topología histórica, pero identificaba cliente y circuito usando relaciones actuales mutables. Para cumplir la prohibición de reconstruir el pasado desde el circuito vivo, se agregan dos instantáneas mínimas:

- `Activation.customer_name_snapshot` (`TEXT`, nullable).
- `Activation.circuit_code_snapshot` (`TEXT`, nullable).

Las nuevas activaciones capturan ambos valores en backend: el circuito ya está bloqueado y el nombre del cliente se consulta bajo bloqueo compartido. No son campos editables ni aceptados en el payload de creación. Tampoco se modifican las instantáneas existentes de sector, nodo, equipo y puerto.

**Sin backfill:** las activaciones anteriores mantienen ambos campos en `NULL`; la constancia muestra «No registrado». No usa el nombre/código actuales como si fueran originales. Para registros nuevos, renombrar al cliente, modificar el código o cambiar posteriormente los datos del circuito no cambia la identidad de la constancia.

## Proyección positiva y confidencialidad

`src/ticketyn/api/customer_activation_reports.py` define `CustomerActivationReport`, dataclass inmutable con exactamente:

1. Referencia de activación.
2. Nombre histórico del cliente.
3. Código histórico del circuito.
4. Tipo de servicio registrado en la activación.
5. Fecha efectiva de la activación.
6. Capacidad inicial y unidad registradas en la activación.
7. Notas para cliente.

La consulta selecciona exclusivamente esas columnas de `activations`. El renderizador público **no recibe sesión SQLAlchemy ni objetos ORM**. No consulta el circuito actual, descripciones operativas, notas internas, bitácoras, responsables, sectores, nodos, distribución ni IP de gestión CPE.

La IP pública y el puerto físico del cliente escritos expresamente en notas públicas sí se imprimen como texto autorizado; nunca se deducen de `cpe_management_ip` ni de `distribution_port_name`. No se interpretan etiquetas, comandos o enlaces: se reutiliza `paragraph()` con escape de contenido.

## Presentación

A4 vertical Modern Modular, fondo blanco, logotipo local, acento Esmeralda NOC de Activaciones, referencia destacada, metadatos en dos columnas y pie con emisión, zona horaria y «Página N / total».

- Constancia: «Información de entrega del servicio» contiene solo notas públicas o un mensaje neutro si no existen.
- Interno: conserva su información previa y distingue «Notas internas de activación» de «Información para el cliente».
- `intervention_block(..., modular=True)` mantiene cada encabezado con el inicio de su texto y permite continuar notas largas entre páginas, sin mover todo el contenido a una página nueva.
- Detalle React: «Descargar PDF interno» y «Descargar PDF para cliente», ambos bajo `activations.export`, con bloqueo de doble clic y gestión de errores existentes.

## Migración y operación

Nueva revisión **`0036_customer_activation_notes`**, depende de **`0035_cpe_management_ip`**. Añade únicamente los tres campos nullable anteriores en `activations`. No modifica migraciones anteriores ni datos existentes. La reversión se detiene si borraría notas públicas o instantáneas de identidad ya registradas.

**No aplicada a DEV persistente, TEST ni PROD por esta tarea.** La validación usa únicamente PostgreSQL efímero. Antes de ejecutar este código sobre una base persistente deberá autorizarse y aplicarse la migración con el procedimiento habitual. Las activaciones nuevas creadas antes de esa actualización no tendrán estas instantáneas; no se inventarán retrospectivamente.

## Archivos de implementación

- `alembic/versions/0036_customer_activation_notes.py` (nuevo).
- `src/ticketyn/models/fms.py`, `src/ticketyn/schemas/fms.py`, `src/ticketyn/api/fms_data.py`.
- `src/ticketyn/api/customer_activation_reports.py` (nuevo), `src/ticketyn/api/activation_reports.py`, `src/ticketyn/api/fms.py`, `src/ticketyn/security/routes.py`.
- `frontend/src/components/OperationModal.tsx`, `frontend/src/pages/ActivationDetail.tsx`, `frontend/src/types/fms.ts`, `frontend/src/api/fms.ts`.
- `tests/test_customer_activation_reports.py` (nuevo), `tests/test_activation_reports.py` (etiqueta interna explícita).
- `frontend/src/pages/ActivationNotes.test.tsx`, `frontend/src/pages/ActivationReport.test.tsx`.
- Esta guía, `docs/SYSTEM_MAP.md`, `docs/modules/operaciones-fms.md`, `docs/modules/reporteria-exportaciones.md`, `AGENT_HANDOFF.md`.

## Validación y muestras

Pruebas específicas: notas independientes, vacío/límite, ambos documentos, proyección SQL sin lecturas sensibles, metadatos sin secretos, permisos/401/403, independencia del generador interno, paginación extensa, identidad histórica no mutable ni falsificable y upgrade/downgrade seguro sobre PostgreSQL efímero.

Muestras completamente ficticias en `/tmp/ticketyn-customer-activation-v080/`:

- `1-entrega.pdf`: IP pública, gateway, prefijo, VLAN y puerto del cliente.
- `2-con-internas-sensibles.pdf`: constancia del caso con datos internos sensibles, sin publicarlos.
- `3-sin-notas-publicas.pdf`: mensaje neutro.
- `4-notas-extensas.pdf`: 120 entradas autorizadas, seis páginas.
- `5-historica.pdf`: identidad histórica desconocida, sin reconstrucción actual.
- `6-interno-ambas-notas.pdf`: control del informe interno con las dos fuentes diferenciadas.

Todas las páginas se rasterizaron y revisaron visualmente. `pdftotext` y `pdfinfo` verificaron texto y metadatos de los documentos públicos sin marcadores `PRIVATE_`, IP CPE ni identificador interno de prueba. También se extrajo y verificó el PDF real generado por el endpoint de confidencialidad (`/tmp/ticketyn-client-activation-privacy.pdf`). Las 120 entradas extensas están completas y comienzan en la primera página.

Resultados comprobados: 24 pruebas específicas de constancia; ejecución de integración/seguridad con 86 aprobadas (incluye 22 de esas 24, las dos de inyección se añadieron y ejecutaron después); 164 pruebas de regresión FMS/notificaciones/XLSX/CPE; 128 pruebas frontend relacionadas; 14 de variables de correo y 12 de MailNotifications para comprobar coordinación; 11 de integridad documental. Todas esas ejecuciones finales aprobaron, sin fallos. TypeScript y `git diff --check` sin errores. No se ejecutó la suite global del repositorio. Se conserva documentado el fallo previo ajeno del subtítulo en `test_cpe_activation_snapshots.py`. No se modifican `documents.py`, exportadores XLSX, `0035_cpe_management_ip` ni `frontend/dist/`. Sin nuevas dependencias, builds, commits ni despliegues.
