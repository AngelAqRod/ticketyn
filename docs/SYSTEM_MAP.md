# Ticketyn — Mapa Técnico Central del Sistema (SYSTEM_MAP)

Este documento es el índice técnico de arquitectura para agentes de programación.
Permite ubicar rápidamente archivos, dependencias y reglas críticas por dominio funcional.

---

## A. Arquitectura General

- **Backend:** FastAPI modular en `src/ticketyn/`. Enrutamiento en `src/ticketyn/api/`, modelos SQLAlchemy 2.0 en `src/ticketyn/models/`, esquemas Pydantic v2 en `src/ticketyn/schemas/` y configuración central en `src/ticketyn/core/config.py`.
- **Frontend:** SPA React 18 + TypeScript + Vite en `frontend/src/`. Enrutador en `frontend/src/App.tsx`, vistas en `frontend/src/pages/`, componentes en `frontend/src/components/` y sistema visual Electric Blue 2.0 (`DESIGN.md`).
- **Persistencia y Migraciones:** PostgreSQL obligatorio (`DATABASE_URL`). Evolución de esquema gestionada exclusivamente con Alembic en `alembic/versions/`.
- **Seguridad y Sesiones:** Tokens opacos en memoria RAM (`src/ticketyn/security/memory.py`). Servidor monoproceso (`--workers 1`). Control de acceso por ruta (`SafeAuthRoute` en `src/ticketyn/security/routes.py`) y permisos en `src/ticketyn/security/permissions.py`. Denegación predeterminada (403). Identidad única en tabla `responsibles`.
- **Notificaciones y Cola:** Subsistema en `src/ticketyn/notifications/` con soporte SMTP y OAuth2 (Google / Microsoft 365). Cola persistente asíncrona en `mail_jobs`.
- **Documentación y Reportes:** Generación de PDF (ReportLab en `src/ticketyn/api/documents.py`) y Excel (openpyxl en `src/ticketyn/api/*exports.py`).

---

## B. Mapa de Dominios Funcionales

### 1. Seguridad y Cuentas
| Campo | Información |
|---|---|
| **Dominio** | Seguridad, autenticación y control de acceso basado en roles (RBAC) |
| **Backend** | `src/ticketyn/api/auth.py`, `src/ticketyn/api/security_accounts.py`, `src/ticketyn/api/security_roles.py`, `src/ticketyn/api/security_audit.py`, `src/ticketyn/security/`, `src/ticketyn/models/security.py`, `src/ticketyn/models/responsible.py`, `src/ticketyn/schemas/security_audit.py` |
| **Frontend** | `frontend/src/auth/`, `frontend/src/api/security.ts`, `frontend/src/pages/SecurityRoles.tsx`, `frontend/src/pages/SecuritySessions.tsx`, `frontend/src/pages/SecurityAudit.tsx`, `frontend/src/pages/Profile.tsx`, `frontend/src/components/LcdOperatorAvatar.tsx`, `frontend/src/components/UserControls.tsx`, `frontend/src/styles/operatorProfile.css` |
| **Dependencias** | `responsibles` (identidad única de personas y cuentas), `src/ticketyn/core/config.py` |
| **Reglas críticas** | Identidad única en `responsibles`. Tres dimensiones: `active`, `access_granted`, `operational_selectable`. Sesiones opacas en RAM (`--workers 1`). `lock_security(session)` en mutaciones. Protección último Superadmin. Retención 1–3650 días. Perfil LCD de 14 segmentos; preferencias propias en responsibles, Dashboard y Mis tickets configurables como inicio; Mi actividad con accesos directos y conteo consolidado (ver `docs/profile-operator-identity.md`). |
| **Pruebas** | `tests/test_security_foundation.py`, `tests/test_security_authorization.py`, `tests/test_security_administration.py`, `frontend/src/pages/SecurityAdministration.test.tsx` |

### 2. Tickets de Clientes
| Campo | Información |
|---|---|
| **Dominio** | Tickets de incidencias y soporte técnico a clientes |
| **Backend** | `src/ticketyn/api/tickets.py`, `src/ticketyn/api/ticket_data.py`, `src/ticketyn/api/ticket_close.py`, `src/ticketyn/schemas/ticket_close.py`, `src/ticketyn/api/ticket_updates.py`, `src/ticketyn/api/escalations.py`, `src/ticketyn/api/escalation_data.py`, `src/ticketyn/api/recommendations.py`, `src/ticketyn/api/recommendation_data.py`, `src/ticketyn/api/my_tickets.py`, `src/ticketyn/api/my_tickets_data.py`, `src/ticketyn/models/ticket.py`, `src/ticketyn/models/ticket_update.py`, `src/ticketyn/models/escalation.py`, `src/ticketyn/models/ack.py`, `src/ticketyn/schemas/ticket.py`, `src/ticketyn/schemas/recommendation.py`, `src/ticketyn/schemas/my_tickets.py` |
| **Frontend** | `frontend/src/pages/Tickets.tsx`, `frontend/src/pages/TicketDetail.tsx`, `frontend/src/pages/NewTicket.tsx`, `frontend/src/pages/MyTickets.tsx`, `frontend/src/components/TicketForm.tsx`, `frontend/src/components/CircuitLink.tsx`, `frontend/src/api/index.ts`, `frontend/src/components/TicketInterventionModal.tsx`, `frontend/src/components/TicketQuickClose.tsx`, `frontend/src/components/TicketEscalations.tsx`, `frontend/src/components/TicketRecommendationNotice.tsx`, `frontend/src/api/recommendations.ts`, `frontend/src/api/myTickets.ts`, `frontend/src/types/recommendation.ts`, `frontend/src/types/myTickets.ts`, `frontend/src/styles/myTickets.css` |
| **Dependencias** | Clientes, Circuitos, Sectores, Nodos, Responsables, Puestos (`positions`), Tickets Internos (vínculo opcional) |
| **Reglas críticas** | Zona horaria `America/Guatemala`. Textos autorizados para cliente separados de bitácora interna. Escalamientos no cambian estado ni responsable. Sincronización de sector en tickets de las últimas 168h. Motor de recomendaciones de escalamiento por etapas (inicial, escalamiento activo determinista, retorno a puesto original al finalizar escalamientos, descuento de tiempo cerrado en reaperturas). Silenciamiento mediante ACK (1H/4H/8H/INDEFINITE) con autorización estricta en backend. Recomendaciones: retorno temprano para cerrados y refresco único de 60 s solo en fichas abiertas visibles; sin N+1 de destinos ni vigilancia global (ver `docs/escalation-recommendation-performance.md`). Módulo «Mis tickets» como espacio personal de trabajo en NOC: cuatro vistas independientes (Asignados a mí, He participado, Mis escalamientos hacia puesto operativo, Por verificar con recomendaciones activas sin ACK). Polling de 60 s en Por verificar con pausa en visibilidad oculta. Principio fundamental: escalamiento no cambia responsable. |
| **Pruebas** | `frontend/src/components/CircuitLink.test.tsx`, `tests/test_ticket_quick_close.py`, `frontend/src/components/TicketQuickClose.test.tsx`, `tests/test_ticket_updates.py`, `tests/test_escalations.py`, `tests/test_ticket_exports.py`, `tests/test_escalation_recommendations.py`, `tests/test_ack_security.py`, `tests/test_recommendation_performance.py`, `tests/test_escalation_recommendation_migration.py`, `tests/test_my_tickets.py`, `frontend/src/pages/Tickets.test.tsx`, `frontend/src/components/TicketRecommendationNotice.test.tsx`, `frontend/src/pages/MyTickets.test.tsx` |

### 3. Tickets Internos
| Campo | Información |
|---|---|
| **Dominio** | Incidencias internas de infraestructura técnica de red y proveedores |
| **Backend** | `src/ticketyn/api/internal_tickets.py`, `src/ticketyn/api/internal_ticket_data.py`, `src/ticketyn/api/ticket_close.py`, `src/ticketyn/schemas/ticket_close.py`, `src/ticketyn/api/recommendations.py`, `src/ticketyn/api/recommendation_data.py`, `src/ticketyn/models/internal_ticket.py`, `src/ticketyn/models/ack.py`, `src/ticketyn/schemas/internal_ticket.py`, `src/ticketyn/schemas/recommendation.py` |
| **Frontend** | `frontend/src/pages/InternalTickets.tsx`, `frontend/src/components/InternalTicketSelect.tsx`, `frontend/src/components/RelatedInternalTicket.tsx`, `frontend/src/components/TicketQuickClose.tsx`, `frontend/src/components/TicketEscalations.tsx`, `frontend/src/components/TicketRecommendationNotice.tsx`, `frontend/src/api/recommendations.ts`, `frontend/src/types/recommendation.ts` |
| **Dependencias** | Sectores, Nodos, Departamentos, Responsables, Proveedores, Puestos (`positions`), Tickets de Clientes (vínculo N:1) |
| **Reglas críticas** | Incidencias sin cliente ni circuito. Todo seguimiento es estrictamente interno. Reatribución de proveedor permitida incluso con ticket cerrado. Numeración independiente. Integración de escalamientos, motor de recomendaciones por etapas y reconocimientos ACK compartida simétricamente con tickets de clientes. |
| **Pruebas** | `tests/test_ticket_quick_close.py`, `frontend/src/components/TicketQuickClose.test.tsx`, `tests/test_internal_tickets.py`, `tests/test_ack_security.py`, `tests/test_escalation_recommendations.py`, `frontend/src/pages/InternalTickets.test.tsx` |

### 4. Clientes y Circuitos
| Campo | Información |
|---|---|
| **Dominio** | Catálogo de clientes, circuitos, CPE y distribución (equipos/puertos; backend, formularios y gestión operativa v0.8.0 bloques 1–3) |
| **Backend** | `src/ticketyn/api/customers.py`, `src/ticketyn/api/circuits.py`, `src/ticketyn/api/circuit_sector.py`, `src/ticketyn/models/customer.py`, `src/ticketyn/models/circuit.py`, `src/ticketyn/models/cpe_model.py`, `src/ticketyn/schemas/circuit.py`, `src/ticketyn/schemas/customer.py`, `src/ticketyn/api/distribution.py`, `src/ticketyn/api/distribution_data.py`, `src/ticketyn/api/device_templates.py`, `src/ticketyn/schemas/device_template.py`, `src/ticketyn/api/port_nomenclatures.py`, `src/ticketyn/schemas/port_nomenclature.py`, `src/ticketyn/models/distribution.py`, `src/ticketyn/schemas/distribution.py` |
| **Frontend** | `frontend/src/pages/CircuitDetail.tsx`, `frontend/src/pages/DistributionDevices.tsx`, `frontend/src/pages/DistributionDeviceDetail.tsx`, `frontend/src/components/CircuitsNavigation.tsx`, `frontend/src/components/DistributionModals.tsx`, `frontend/src/components/CircuitActions.tsx`, `frontend/src/components/CpeConfiguration.tsx`, `frontend/src/components/CatalogAdmin.tsx`, `frontend/src/components/CircuitEditModal.tsx`, `frontend/src/components/QuickCatalogCreate.tsx`, `frontend/src/components/CircuitDistributionFields.tsx`, `frontend/src/components/QuickDistributionCreate.tsx`, `frontend/src/api/distribution.ts`, `frontend/src/components/DeviceTemplateAdmin.tsx`, `frontend/src/components/DeviceTemplateChoice.tsx`, `frontend/src/api/deviceTemplates.ts`, `frontend/src/components/PortCreateDialog.tsx`, `frontend/src/api/portNomenclatures.ts` |
| **Dependencias** | Sectores, Nodos, Tipos de servicio, Modelos CPE, Operaciones FMS |
| **Reglas críticas** | Eliminación permitida solo sin dependencias operativas. CPE es texto técnico. Capacidad actual desde FMS; sync de sector reciente (168h). Distribución opcional con FK compuestas nodo/equipo/puerto; puertos asociados no se trasladan, desactivan ni eliminan. Bitácora operativa transaccional separada de seguridad. Selectores dependientes, altas rápidas y gestión integral de equipos y puertos completada en Bloque 3. Listado/detalle incluyen `unassigned_port_count`, sin circuitos asociados (también inactivos), mediante agregación SQL. Orden natural SQL de puertos antes de paginar, conservado por tabla y selectores. Plantillas reutilizables de equipos: 1–16 grupos y máximo 256 puertos; creación manual o equipo+puertos atómica, sin sincronización retroactiva (ver `docs/distribution-device-templates.md`). Nomenclaturas globales, generación central y lotes atómicos de hasta 256 nombres con vista previa comprobada en servidor. Ver `docs/distribution-v0.8.0.md` y `docs/port-nomenclatures-v0.8.0.md`. |
| **Pruebas** | `tests/test_circuit_ticket_sector_sync.py`, `tests/test_distribution.py`, `tests/test_port_order.py`, `tests/test_distribution_migration.py`, `tests/test_port_nomenclatures.py`, `tests/test_port_nomenclature_migration.py`, `frontend/src/components/PortCreateDialog.test.tsx`, `frontend/src/components/CircuitSectorField.test.tsx`, `frontend/src/pages/DistributionDevices.test.tsx`, `frontend/src/pages/DistributionDeviceDetail.test.tsx` |

### 5. Gestión Operativa FMS
| Campo | Información |
|---|---|
| **Dominio** | Ciclo de vida técnico del circuito (Activaciones, Cambios de capacidad, Bajas y Reactivaciones) |
| **Backend** | `src/ticketyn/api/fms.py`, `src/ticketyn/api/fms_data.py`, `src/ticketyn/api/fms_exports.py`, `src/ticketyn/api/activation_reports.py`, `src/ticketyn/api/customer_activation_reports.py`, `src/ticketyn/api/fms_report_exports.py`, `src/ticketyn/api/activation_notifications.py`, `src/ticketyn/models/fms.py`, `src/ticketyn/schemas/fms.py`, `src/ticketyn/schemas/fms_export.py` |
| **Frontend** | `frontend/src/pages/Operations.tsx`, `frontend/src/pages/ActivationDetail.tsx`, `frontend/src/components/OperationsTable.tsx`, `frontend/src/components/OperationModal.tsx`, `frontend/src/components/ActivationNotificationActions.tsx` |
| **Dependencias** | Circuitos, Responsables, Tipos de servicio, Motivos de baja, Notificaciones |
| **Reglas críticas** | Tres operaciones con bitácoras independientes. Datos técnicos de activación inmutables. Instantánea histórica de distribución (`distribution_recorded`, «No asignado» vs «No registrado»). Notas internas/públicas separadas y constancia de cliente con proyección positiva e identidad capturada en nuevas activaciones (0036, sin backfill). Ver `docs/customer-activation-certificate-v0.8.0.md`. Límites de volumen en PDF estadístico (2.000 operaciones / 2.000.000 caracteres). |
| **Pruebas** | `tests/test_fms.py`, `tests/test_fms_exports.py`, `tests/test_activation_reports.py`, `tests/test_activation_distribution.py`, `tests/test_activation_notifications.py`, `frontend/src/pages/Fms.test.tsx`, `frontend/src/pages/ActivationDistribution.test.tsx` |

### 6. Control de Cambios
| Campo | Información |
|---|---|
| **Dominio** | Planificación, ejecución y seguimiento de ventanas de mantenimiento |
| **Backend** | `src/ticketyn/api/changes.py`, `src/ticketyn/api/change_data.py`, `src/ticketyn/models/change.py`, `src/ticketyn/schemas/change.py` |
| **Frontend** | `frontend/src/pages/Changes.tsx`, `frontend/src/components/ChangeShared.tsx` |
| **Dependencias** | Departamentos, Responsables (encargado y apoyo múltiple), Tipos de cambio, Tipos de finalización, Tickets internos |
| **Reglas críticas** | Flujo manual: Agendado -> En ejecución -> Finalizado. Eficiencia por comparación de duraciones (±15 min) fijada al tipo de finalización al finalizar. Sin cierres cruzados con tickets. |
| **Pruebas** | `tests/test_change_types.py`, `frontend/src/pages/Changes.test.tsx` |

### 7. Notificaciones y Correo
| Campo | Información |
|---|---|
| **Dominio** | Automatización de correos operativos, plantillas dinámicas y transporte SMTP/OAuth2 |
| **Backend** | `src/ticketyn/api/mail_notifications.py`, `src/ticketyn/api/mail_transport.py`, `src/ticketyn/api/mail_jobs.py`, `src/ticketyn/notifications/fields.py`, `src/ticketyn/notifications/templates.py`, `src/ticketyn/notifications/html.py`, `src/ticketyn/models/mail_notifications.py`, `src/ticketyn/models/mail_jobs.py`, `src/ticketyn/schemas/mail_notifications.py`, `src/ticketyn/schemas/mail_templates.py` |
| **Frontend** | `frontend/src/pages/MailNotifications.tsx`, `frontend/src/components/MailTemplateEditor.tsx`, `frontend/src/components/MailTransportControls.tsx` |
| **Dependencias** | Eventos FMS (activaciones), Configuración SMTP, OAuth2 (Microsoft 365 / Google Workspace) |
| **Reglas críticas** | Cola persistente `mail_jobs`. Diseño visual Technical Split (Electric Blue `#1768D5`, cabecera dividida, pares de campos en 2 columnas, secciones con acentos cromáticos esmeralda/cian y bloque exclusivo para notas). Plantillas HTML y texto con render dinámico cerrado (sin evaluación de expresiones). Catálogo cerrado de variables semánticas: equipo (`activation.distribution_device`) y puerto (`activation.distribution_port`) históricos de activación («No registrado» previo a v0.8.0, «No asignado» si no tiene asignación); IP de gestión CPE (`circuit.cpe_management_ip`) en estado actual normalizado RFC 5952 / IPv4 («No asignada» si vacía, sin filtrar configuración técnica interna); notas (`activation.activation_notes`) con fallback «Sin notas registradas». Procesamiento desacoplado sin bloquear la solicitud HTTP principal. |
| **Pruebas** | `tests/test_mail_technical_split.py`, `tests/test_mail_template_variables_v080.py`, `tests/test_mail_templates.py`, `tests/test_mail_notifications.py`, `tests/test_mail_html.py`, `tests/test_mail_jobs.py`, `tests/test_mail_transport.py`, `frontend/src/pages/MailNotifications.test.tsx` |

### 8. Catálogos y Configuración
| Campo | Información |
|---|---|
| **Dominio** | Mantenimiento de tablas maestras y configuración de numeración secuencial |
| **Backend** | `src/ticketyn/api/crud.py`, `src/ticketyn/api/positions.py`, `src/ticketyn/api/settings.py`, `src/ticketyn/api/ticket_numbers.py`, `src/ticketyn/models/` (sector, node, department, position, etc.), `src/ticketyn/schemas/position.py`, `src/ticketyn/schemas/` |
| **Frontend** | `frontend/src/pages/Catalogs.tsx`, `frontend/src/pages/Settings.tsx`, `frontend/src/components/PortNomenclatureAdmin.tsx`, `frontend/src/components/CatalogAdmin.tsx`, `frontend/src/components/QuickCatalogCreate.tsx` |
| **Dependencias** | Entidades operativas de todos los dominios |
| **Reglas críticas** | Desactivación lógica preserva integridad histórica. Puestos con configuración opcional «Escala a» (modalidades General vs Individual con umbrales en minutos), validación de ciclos (BFS) y auto-escalamiento prohibido. Nomenclaturas de puertos globales con prefijos únicos y formatos múltiples; Admin administra, Auditor consulta y Operador usa lookup. Numeraciones con bloqueo de fila `FOR UPDATE`; la vista previa no consume secuencia. |
| **Pruebas** | `tests/test_catalog_api.py`, `tests/test_catalog_deletion.py`, `tests/test_escalation_recommendations.py`, `frontend/src/pages/Catalogs.test.tsx`, `frontend/src/components/CatalogAdmin.test.tsx`, `frontend/src/pages/Settings.test.tsx` |

### 9. Reportería y Exportaciones
| Campo | Información |
|---|---|
| **Dominio** | Informes estadísticos, métricas operativas y exportación de documentos (PDF / Excel) |
| **Backend** | `src/ticketyn/api/reports.py`, `src/ticketyn/api/report_data.py`, `src/ticketyn/api/report_exports.py`, `src/ticketyn/api/documents.py`, `src/ticketyn/api/fms_reports.py`, `src/ticketyn/api/fms_exports.py`, `src/ticketyn/api/fms_report_exports.py`, `src/ticketyn/api/activation_reports.py`, `src/ticketyn/api/change_reports.py`, `src/ticketyn/schemas/report.py` |
| **Frontend** | `frontend/src/pages/Reports.tsx`, `frontend/src/pages/FmsReports.tsx`, `frontend/src/pages/ChangeReports.tsx`, `frontend/src/components/ReportCharts.tsx`, `frontend/src/components/MetricStrip.tsx`, `frontend/src/components/RankingSection.tsx` |
| **Dependencias** | Tickets de Clientes, Tickets Internos, Operaciones FMS, Control de Cambios |
| **Reglas críticas** | Motores ReportLab (PDF) y openpyxl (Excel). Documentos individuales de tickets y activaciones FMS Modern Modular en A4 vertical; reportes generales y estadísticos de tickets y operaciones FMS (activaciones, cambios de capacidad, bajas/reactivaciones, estadísticas) Modern Modular en A4 horizontal con cabecera blanca, logotipo institucional local, franja métrica y tablas claras. Identidad cromática de operaciones FMS en Esmeralda (`#047857`) con estados semánticos diferenciados (Incrementos/Reactivaciones en verde, Decrementos en azul acero, Bajas en gris pizarra). Preservación estricta de infraestructura histórica de distribución en activaciones (sin consultar circuito vivo; «No registrado» previo a v0.8.0, «No asignado» si no tiene). Control de Cambios y XLSX conservan formato propio. Métricas de iniciados vs cerrados usan bases temporales distintas. Filtros compartidos con listados. |
| **Pruebas** | `tests/test_reports.py`, `tests/test_ticket_exports.py`, `tests/test_internal_ticket_exports.py`, `tests/test_report_pdf_composition.py`, `tests/test_modular_pdf.py`, `tests/test_activation_reports.py`, `tests/test_activation_distribution.py`, `tests/test_fms_exports.py`, `tests/test_fms_report_exports.py`, `frontend/src/pages/Reports.test.tsx`, `frontend/src/pages/FmsReports.test.tsx` |

---

## C. Guía de Navegación para Agentes

Para implementar cambios sin reexplorar el repositorio ni consumir tokens en exceso:

1. **Identificar el dominio:** Determinar a cuál de los 9 dominios de la sección B pertenece la tarea.
2. **Localizar los archivos de trabajo:** Consultar las filas correspondientes en la tabla. Todas las rutas indicadas son exactas y relativas a la raíz del repositorio (`src/ticketyn/`, `frontend/src/`, `tests/`).
3. **Respetar las reglas críticas:** Leer la fila «Reglas críticas» antes de proponer cambios estructurales o alterar flujos de datos.
4. **Inspección dirigida:** Abrir exclusivamente los archivos objetivo con `view_file` acotado a las líneas necesarias; evitar listar directorios completos (`ls`, `find`) o leer módulos ajenos.
5. **Verificación focalizada:** Ejecutar la suite de pruebas indicada en la fila «Pruebas» para comprobar que no existan regresiones en el dominio afectado.
