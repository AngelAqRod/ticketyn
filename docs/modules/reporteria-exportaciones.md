# Ficha Técnica: Reportería y Exportaciones

## Responsabilidad del módulo
- **Qué gestiona:** El cálculo de métricas agregadas, análisis estadístico y la generación de documentos exportables (reportes ejecutivos en PDF y libros de cálculo en Excel) para todos los dominios de la plataforma.
- **Funcionalidades existentes:**
  - Vistas de reportería estadística especializada para Tickets de Clientes, Tickets Internos, Control de Cambios y Operaciones FMS.
  - Representación gráfica interactiva mediante Recharts (barras, líneas, áreas) y franjas de telemetría operativa (`MetricStrip`).
  - Generación de reportes PDF técnicos consolidados mediante ReportLab (`src/ticketyn/api/documents.py`), con cabeceras institucionales Capsule NOC, paginación y formato industrial.
  - Generación de hojas de cálculo Excel (.xlsx) estructuradas con formato de celdas mediante openpyxl (`src/ticketyn/api/*exports.py`).
  - Exportación de listados completos filtrados directamente desde las vistas operativas.
- **Qué no le corresponde:** No es un motor de Business Intelligence externo ni una consola de consultas SQL ad-hoc para usuarios finales; no altera datos ni recalcula estados al generar un informe.

## Reglas de negocio críticas
- **Bases temporales independientes en incidencias:**
  - *Iniciados:* Tickets cuyo registro o inicio (`created_at`) ocurrió dentro del rango de fechas seleccionado.
  - *Cerrados:* Tickets cuya fecha de finalización (`closed_at`) se ubica en el rango y poseen estado Cerrado.
  - Un ticket cerrado sin fecha de finalización válida no aporta tiempo de resolución. Son conjuntos matemáticos y temporales distintos; no deben mezclarse al calcular tasas de efectividad.
- **Criterios de agregación en Control de Cambios:**
  - La duración promedio y acumulada considera exclusivamente ventanas finalizadas con fechas reales válidas.
  - La métrica de participación cuenta eventos distintos por persona, desagregando funciones de encargado y apoyo por separado, sin calificar desempeño laboral individual.
- **Alcance completo del filtrado tabular:**
  - Las exportaciones PDF y Excel de cualquier listado procesan el conjunto completo de registros que satisfacen los filtros aplicados (búsqueda, cliente, sector, nodo, estado, fechas), no limitándose a la página visible en la paginación de pantalla.
- **Protección de memoria y límites ReportLab:**
  - Los generadores ReportLab procesan el documento en memoria RAM antes de emitir la respuesta HTTP.
  - Para evitar agotamiento de memoria en el proceso Uvicorn (`--workers 1`), se aplican límites de volumen (ej. máximo **2.000 operaciones y 2.000.000 de caracteres** en FMS).
  - Ante volúmenes excesivos, el backend rechaza la solicitud indicando acotar el período; jamás se genera un documento truncado silenciosamente.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`reports.py`, `report_data.py`, `report_exports.py`, `documents.py`, `fms_reports.py`, `fms_report_exports.py`, `change_reports.py`, `internal_ticket_reports.py`, `internal_ticket_exports.py`, `ticket_exports.py`, `ticket_reports.py`), esquemas en `src/ticketyn/schemas/` (`report.py`, `fms_report.py`, `ticket_export.py`).
- **Componentes frontend:** Vistas en `frontend/src/pages/` (`Reports.tsx`, `FmsReports.tsx`, `ChangeReports.tsx`), componentes en `frontend/src/components/` (`ReportCharts.tsx`, `MetricStrip.tsx`, `RankingSection.tsx`).
- **Dependencias:** Modelos y datos de Tickets de Clientes, Tickets Internos, Operaciones FMS y Control de Cambios.
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `GET /api/reports/tickets`, `GET /api/reports/tickets/export`, `GET /api/reports/internal-tickets`, `GET /api/reports/changes`, `GET /api/fms/reports`, `GET /api/fms/reports/export`.
- **Permisos requeridos:** `reports.tickets.view`, `reports.tickets.export`, `reports.internal_tickets.view`, `reports.internal_tickets.export`, `reports.changes.view`, `reports.changes.export`, `reports.activations.view`, `reports.activations.export`, `reports.capacity_changes.view`, `reports.capacity_changes.export`, `reports.lifecycle.view`, `reports.lifecycle.export`, `reports.escalations.view`.
- **Independencia de permisos:** La visualización de métricas (`view`) y la descarga de archivos (`export`) son facultades separadas en la matriz RBAC. El rol Auditor dispone de permisos para consultar y exportar todos los reportes del sistema.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_reports.py tests/test_ticket_exports.py tests/test_fms_exports.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/Reports.test.tsx frontend/src/pages/FmsReports.test.tsx frontend/src/pages/ChangeReports.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Verificar que las consultas respeten la zona horaria institucional `America/Guatemala`.
  - Asegurar que los filtros de exportación coincidan con exactitud con los filtros activos en la interfaz de usuario.
  - Probar que ReportLab libere los buffers de memoria tras la generación del documento binario.

## Mantenimiento
Este documento debe actualizarse ante cualquier cambio en las fórmulas de cálculo de indicadores agregados, modificación de plantillas de ReportLab o incorporación de nuevos reportes operativos.


## PDF individuales Modern Modular — v0.8.0

- Solo los tres informes individuales de tickets adoptan A4 vertical: reporte
  interno de ticket de cliente, reporte para cliente y ticket interno NOC.
- `documents.build_pdf(..., modular=True, reference=..., accent=...)` activa
  cabecera blanca, logotipo gráfico, pie y márgenes propios. El valor por defecto
  conserva A4 horizontal y la composición previa de los demás consumidores.
- Primitivas: `identification`, `metadata_modules`, `ModularHeading` y la opción
  `modern_table(light=True)` para las relaciones tabulares del informe NOC.
  Las dimensiones útiles compartidas contemplan el padding del frame ReportLab.
- `ticket_reports.intervention_block(..., modular=True)` permite continuidad de
  texto largo en el formato vertical; su opción predeterminada sigue siendo la
  horizontal utilizada por activaciones y Control de cambios.
- El PNG oficial `logo_horizontal_claro.png` se busca en los directorios ascendientes
  del módulo resuelto, comprobando `frontend/dist/branding` y luego
  `frontend/public/branding` en cada nivel. Funciona desde `src` y desde el paquete
  instalado en `.venv` del release, sin depender del cwd ni usar HTTP o fuentes del
  sistema. El frontend distribuido debe conservar ese recurso de branding.
- La proyección `CustomerReport` y su consulta positiva no se amplían. Nodos,
  sectores, responsables, departamentos, proveedores, escalamientos, relaciones
  internas y distribución continúan fuera del documento para cliente.
- Pruebas visuales y ejemplos ficticios reproducibles en
  `tests/test_modular_pdf.py`, además de las pruebas existentes de privacidad,
  relaciones, cronología, escalamientos y composición.


### Fidelidad visual Modern Modular

- El bloque azul claro mantiene referencia y título; el estado se representa en
  cápsula con texto: abierto/en curso ámbar y cerrado esmeralda. No se inventan
  estados fallidos o críticos ni se usa rojo sin un estado real que lo justifique.
- Los metadatos son módulos separados mediante `MetadataCard`, con bordes
  redondeados sutiles y espacio entre filas/columnas; los valores siguen siendo
  párrafos divisibles, sin recorte ni pérdida de datos extensos.
- Semántica de secciones: descripción azul, resolución esmeralda, incidencia
  interna relacionada púrpura, seguimiento cian e historial de escalamientos
  ámbar moderado. Los escalamientos activos usan ámbar y finalizados esmeralda.
  La cabecera y clasificación del ticket interno NOC conservan su púrpura.
- Se reducen únicamente reservas y espacios de la composición optativa: el
  tamaño de las fuentes se conserva. `intervention_block(modular=True)` mantiene
  juntos bloques breves de hasta 72 pt y ancla los extensos antes de dividirlos;
  el comportamiento predeterminado de otros generadores no cambia.
- El total de tickets relacionados se mantiene unido al inicio de su tabla para
  evitar un encabezado aislado en la página anterior. No se fuerza una cantidad
  fija de páginas: los documentos extensos continúan donde corresponde.


### Cronología de intervenciones Modern Modular

- `documents.timeline_entry` crea `TimelineEntry`, un Flowable divisible con
  marcador circular, segmento vertical, acento y tarjeta de fondo muy claro.
  Encabezado con fecha destacada, responsable secundario y etiqueta opcionales;
  todo texto se escapa y conserva saltos de línea. Fuente narrativa 10 pt.
- Ticket de cliente, informe interno: usa únicamente la visibilidad real de cada
  seguimiento (INTERNAL cian / PUBLIC esmeralda), con etiquetas Interna/Pública.
  Conserva la referencia de escalamiento cuando ya está autorizada.
- Ticket interno NOC: su columna visibility está restringida a INTERNAL; conserva
  fecha, responsable y escalamiento existentes. Usa cian, sin inventar etiquetas
  públicas ni categorías de sistema. La identidad general NOC sigue púrpura.
- Informe para cliente: variante customer azul, exclusivamente fecha y contenido
  de PublicIntervention. La primitiva rechaza responsable, etiqueta o asociación
  si se pasan a esa variante. CustomerReport y su consulta no cambian.
- La tarjeta mide su contenido y reserva su padding dentro de la altura útil.
  Al dividir, la primera parte conserva marcador y metadatos; las continuaciones
  no los repiten. La sección inicial se integra con el primer fragmento para no
  dejar el encabezado o el marcador aislados. Los segmentos no atraviesan pies.
- Los generadores FMS, estadísticos y de Control de cambios no utilizan esta
  primitiva por defecto. No se altera su composición ni su captura de datos.


## Reportes generales y estadísticos Modern Modular (A4 Horizontal) — v0.8.0

- **Formato y disposición:**
  - Adopción de A4 horizontal (`landscape_mode=True`) mediante `ModularCanvas` en `documents.build_pdf(..., modular=True, landscape_mode=True)`.
  - Margen uniforme de 30 pt, cabecera superior con logotipo institucional gráfico resuelto localmente (`branding_logo()`), título del reporte, línea de acento temática a 68 pt del borde superior y pie de página institucional a 44 pt del borde inferior con «Página N / total» y timestamp con timezone.
  - Paleta cromática estricta: Electric Blue (`#1e60d8`) para reportes generales de tickets de clientes y reportería estadística; Púrpura NOC (`#7c3aed`) para reportes de tickets internos NOC.
- **Primitivas de composición reutilizables (`documents.py`):**
  - `report_identification(title, *, period=None, filters=None, total=None, accent=BLUE, category='REPORTE OPERATIVO', width=None)`: bloque de identificación superior con fondo suave (`SOFT`), barra vertical de acento, categoría, título, período y filtros aplicados.
  - `modular_metric_strip(items, width, *, accent=BLUE)`: franja horizontal de tarjetas KPI con fondo blanco, bordes redondeados sutiles y barras de acento lateral semántico (Azul/Púrpura para totales, Ámbar `#b45309` para abiertos/en curso, Esmeralda `#047857` para cerrados).
  - `modern_table(..., light=True, accent=BLUE, status_colors=True)` y `ticket_pdf_table`: tablas claras con fondo suave en cabecera (`#edf2fe` o `#f5f3ff`), líneas de división sutiles (`0.25 pt`), alternancia de filas blancas/suaves, referencias destacadas en negrita con el color de acento, y coloreado semántico directo del texto de estado (Abierto en ámbar, Cerrado en esmeralda).
  - Adaptación cromática de gráficos analíticos (`TrendGraphic`, `BarsGraphic`, `ActivityGraphic`).
- **Generadores implementados:**
  - `src/ticketyn/api/ticket_exports.py`: `export_ticket_pdf` para listados generales de tickets de clientes con KPIs globales calculados en base de datos (`TOTAL TICKETS`, `ABIERTOS / EN CURSO`, `CERRADOS`).
  - `src/ticketyn/api/internal_ticket_exports.py`: `export_pdf` para tickets internos NOC con KPIs de estado y tickets de cliente vinculados.
  - `src/ticketyn/api/report_exports.py`: `export_pdf` para reportería estadística con bloques modulares (`ModularHeading`), franja métrica y tablas detalladas.
- **Preservación y aislamiento:**
  - Los tres informes individuales aprobados (`ticket_reports.py`, `internal_ticket_reports.py`) permanecen en A4 vertical y no sufren alteraciones.
  - Los reportes de Control de cambios (`change_reports.py`) y las exportaciones en formato XLSX mantienen su formato previo sin modificaciones.


## Reportes y documentos de Operaciones FMS Modern Modular — v0.8.0

- **Identidad cromática compartida y semántica de operaciones:**
  - Identidad visual oficial: **Esmeralda NOC** (`EMERALD = #047857`) conforme a `frontend/src/components/moduleIdentity.ts`.
  - Diferenciación semántica de operaciones y estados sin alertas rojas injustificadas:
    - Incrementos de capacidad: Esmeralda (`#047857`), negrita.
    - Decrementos de capacidad: Azul acero (`#0284c7`), negrita.
    - Reactivaciones de circuito: Esmeralda (`#047857`), negrita.
    - Bajas de circuito: Gris pizarra (`#475569`), negrita.
- **Activación individual (`activation_reports.py`):**
  - Formato A4 vertical Modern Modular.
  - Bloque de identificación superior con cápsula de estado «Activa» en esmeralda (`#047857`), fondo suave esmeralda (`#ecfdf5`) y barra lateral esmeralda.
  - Metadatos organizados en tarjetas (`MetadataCard`): Cliente, Circuito (código, descripción, capacidad actual con unidad legible), Topología (nodo y sector históricos registrados) e Infraestructura de distribución.
  - Preservación histórica de distribución: consulta estricta de `distribution_labels(activation)` sobre las columnas históricas (`distribution_device_name`, `distribution_port_name`, `distribution_recorded`). Muestra «No asignado» si no cuenta con equipo/puerto, o «No registrado» para activaciones anteriores a v0.8.0. Nunca consulta la distribución actual viva del circuito.
  - Sección «Notas de activación» después de los metadatos técnicos y de distribución: utiliza exclusivamente `Activation.activation_notes`, preserva saltos de línea y caracteres especiales y muestra «Sin notas registradas» cuando no hay contenido. Texto escapado, blanco sobre fondo de página, encabezado esmeralda y paginación con `intervention_block(..., modular=True)` para mantener el título con las primeras líneas sin arrastrar todo el texto a otra página. No modifica registros, XLSX ni contratos HTTP.
  - Bitácora cronológica con `TimelineEntry` esmeralda y segmento conector vertical; bloque de metadatos de creación y fecha de emisión.
- **Listados generales de operaciones FMS (`fms_exports.py`):**
  - Formato A4 horizontal Modern Modular.
  - Bloque de identificación con categoría `GESTIÓN DE SERVICIOS · OPERACIONES FMS`, título correspondiente, rango de fechas y filtros activos legibles.
  - Franja horizontal de métricas KPI (`modular_metric_strip`) calculadas en base de datos sobre el conjunto filtrado completo:
    - Activaciones: `TOTAL ACTIVACIONES`.
    - Cambios de capacidad: `TOTAL CAMBIOS`, `INCREMENTOS` (esmeralda), `DECREMENTOS` (azul acero).
    - Bajas y reactivaciones: `TOTAL OPERACIONES`, `REACTIVACIONES` (esmeralda), `BAJAS` (gris pizarra).
  - Tablas claras (`modern_table(light=True, accent=EMERALD, status_colors=True)`) con cabecera repetida en cada página, anchos de columna ponderados para evitar desbordes y coloreado semántico directo de operaciones.
- **Reportería estadística FMS (`fms_report_exports.py`):**
  - Formato A4 horizontal Modern Modular.
  - Identificación y métricas KPI de rendimiento en franja modular.
  - Gráficos vectoriales nativos (`TrendGraphic`, `ActivityGraphic`, `BarsGraphic`) con acento temático esmeralda y colores semánticos en series de actividad (Incrementos vs Decrementos en Esmeralda y Azul acero; Bajas vs Reactivaciones en Pizarra y Esmeralda).
  - Tablas de detalle paginadas con alternancia de filas limpias.
- **Exportaciones XLSX:**
  - Intactas e inalteradas en todos sus endpoints y generadores `openpyxl`.

## Constancia independiente de activación para cliente

`customer_activation_reports.py` genera «Constancia de activación de servicio» mediante una proyección positiva inmutable: referencia, identidad histórica capturada al crear, servicio/fecha/capacidad de la activación y notas públicas explícitas. Nunca recibe el ORM, notas internas, descripción del circuito, topología, distribución, IP de gestión CPE o bitácora. Datos desconocidos anteriores a 0036 no se reconstruyen desde el circuito vivo.

El PDF interno conserva sus campos y distingue «Notas internas de activación» de «Información para el cliente». Ambas rutas siguen autenticadas con `activations.export`, descarga diferenciada y `Cache-Control: no-store`. No hay cambios en listados, XLSX ni otras familias PDF. Véase `docs/customer-activation-certificate-v0.8.0.md` para contratos y validación.
