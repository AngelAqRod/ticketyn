# Tickets internos — Ticketyn v0.5.0

## Decisión de acceso confirmada

Ticketyn sigue siendo una aplicación interna de confianza, sin usuarios, login,
roles, sesiones, JWT ni autorización individual en backend. Esta decisión es
intencional para v0.5.0. No hay identidades ficticias ni campos de usuario
obligatorios. Responsible continúa siendo un catálogo operativo, no una cuenta.

Se conservan las protecciones externas existentes. No se modifican Nginx, proxy,
red ni infraestructura. La protección externa **no equivale a autorización por
usuario en backend**. Los servicios no dependen de una identidad inexistente;
una futura autenticación podrá introducirse sin sustituir las reglas de dominio.
La evidencia de cambios y auditoría conserva actor desconocido, conforme a las
convenciones actuales. No se atribuye la edición al responsable del ticket.

## Arquitectura implementada

FastAPI y Pydantic conservan contratos separados y estrictos; SQLAlchemy utiliza
entidades especializadas en `models/internal_ticket.py`. Se mantienen NOT NULL y
las relaciones de cliente/circuito de los tickets actuales.

Tablas nuevas: `internal_tickets`, `internal_ticket_number_config`,
`internal_incident_types`, `providers`, `internal_ticket_updates`,
`internal_escalations`, `internal_escalation_audit`.

- Sector obligatorio; nodo, proveedor y responsable opcionales. Departamento y
  tipo de incidencia interna obligatorios. OPEN/CLOSED, fechas y duración siguen
  el comportamiento de Tickets: un estado cerrado no inventa una fecha de fin.
- Sin cliente, circuito o contenido autorizado para cliente en los contratos
  internos. No se añaden rutas de documentos destinados a clientes.
- CRUD de catálogos reutiliza los servicios existentes, estados activos/inactivos
  e índices de nombre normalizado con la collation ya utilizada `C.utf8`.
- `ticket_update_data.py` y `escalation_data.py` admiten contexto de modelos con
  valores por defecto idénticos al dominio actual. Ambos módulos utilizan las
  mismas reglas de intervención, cursores, fechas, destino y auditoría.
- Seguimiento interno: contrato que rechaza PUBLIC y CHECK de BD que exige
  INTERNAL. La UI elimina el selector de visibilidad. El contrato acepta INTERNAL
  explícito para reutilizar el transporte del componente existente.
- Cambio/retirada de proveedor y resolución registran evidencia antes/después
  dentro de la misma transacción. El proveedor se puede corregir tras cerrar,
  sin cambiar estado, fechas o relaciones.
- La consulta de internos carga sus catálogos por joins y cuenta vínculos en una
  agregación por página, evitando una consulta por catálogo y registro.

### Numeración

`InternalTicketNumberConfig` es un singleton independiente, inicializado de forma
segura con INSERT ON CONFLICT y SELECT FOR UPDATE. Reutiliza formateo y validación
de configuración; valores iniciales INT, separador -, número 1 y padding 7.
Número y referencia son únicos. Ticket y contador se confirman en una transacción.
La vista previa no consume correlativos ni cambia referencias emitidas.

### Relación con Tickets

`tickets.internal_ticket_id` es una FK nullable e indexada, sin cascada destructiva.
Un ticket normal referencia cero o un interno; un interno puede tener muchos
normales. La migración deja NULL en los tickets anteriores. No se exige
coincidencia de sector/nodo. No se sincronizan estados, fechas o resoluciones.
No hay endpoint de eliminación de internos.

El formulario de Tickets conserva sus campos y añade un selector opcional basado
en `SearchableSelect`. Consulta el backend por referencia/título/descripción,
con debounce de 300 ms, cancelación y páginas de 20. Resuelve el seleccionado por
ID aunque no esté en la página. Admite internos cerrados y permite limpiar/cambiar.
El detalle inverso pagina de 50 en 50 con total explícito.

## API

- GET/POST `/api/internal-tickets`; GET/PATCH `/api/internal-tickets/{id}`.
- GET `/api/internal-tickets/{id}/related`, con limit/offset y total.
- GET/POST `/api/internal-tickets/{id}/updates`, con cursor y límite.
- GET/POST `/api/internal-tickets/{id}/escalations`;
  PATCH `.../{escalation_id}`, POST `.../{escalation_id}/finish`, GET `.../audit`.
- GET/PATCH `/api/settings/internal-ticket-number`.
- GET/POST y GET/PATCH por ID para `/api/internal-incident-types` y `/api/providers`.

El listado permite search, status, sector_id, node_id, department_id,
responsible_id, incident_type_id, provider_id, without_provider, from/to, limit y
offset. `from` es inclusivo y `to` exclusivo; timestamps con zona horaria.
El frontend utiliza los períodos existentes y America/Guatemala mediante
`reportPeriod`. Orden estable por creación e ID descendentes, como Tickets.
La búsqueda de texto utiliza icontains escapado como Tickets; no se introduce
una extensión PostgreSQL adicional para búsqueda.

## Frontend reutilizado

`PageHeading`, `SevenSegmentNumber`, `StatusBadge`, `PaginationBar`,
`PeriodShortcuts`, `FilterHeading`, `FormField`, `SearchableSelect`,
`RequestState`, `FeedbackMessage`, `TicketFollowUp`, `TicketInterventionModal`,
`TicketEscalations`, `EscalationModal`, `CatalogAdmin` y numeración de Settings.
Los formularios internos tienen sus campos propios, compartiendo controles y
utilidades de fecha. La navegación agrega Tickets internos después de Tickets y
recalcula sus números visuales. Los formularios internos abren rutas propias,
por lo que no requieren scroll de apertura de formularios expandibles.

## Migración y actualización

`0021_internal_tickets` depende de `0020_activation_cpe`. Es aditiva: siete tablas,
FK nullable en tickets e índices. No modifica migraciones publicadas, datos
históricos, FMS ni contadores de otros módulos. No precarga tipos ni proveedores.
Requiere PostgreSQL y la collation `C.utf8`, igual que los catálogos existentes.

Antes de actualizar una instalación: respaldo verificable, revisión Alembic y
prueba de la actualización en laboratorio. Usar el actualizador oficial existente
con sus protecciones; este desarrollo no las modifica ni aplica migraciones a
instalaciones operativas. El downgrade se rechaza explícitamente porque eliminar
estas tablas perdería evidencia operativa. Recuperar requiere revisar impacto y
respaldo; no se promete una reversión segura automática.

## Prueba local, exclusivamente con una base de laboratorio

Preparar una base PostgreSQL vacía o una copia autorizada en un entorno aislado.
Configurar DATABASE_URL a esa base (no a TEST/PRODUCCIÓN):

```bash
export DATABASE_URL='postgresql+psycopg://USUARIO:CLAVE@127.0.0.1:5432/ticketyn_v050_lab'
.venv/bin/alembic upgrade head
.venv/bin/uvicorn ticketyn.main:app --host 127.0.0.1 --port 8000
```

En otra terminal:

```bash
cd frontend
npm ci
npm run dev
```

Abrir http://127.0.0.1:5173. En Catálogos crear sector, departamento y tipo interno;
crear proveedor solo si corresponde. En Configuración comprobar la numeración de
Tickets internos. Registrar uno sin nodo/proveedor, registrar seguimiento y
escalamiento, cerrarlo y corregir proveedor sin reabrir. Desde un ticket normal,
buscar el interno por referencia/descripción, vincular y consultar ambos detalles;
probar múltiples tickets vinculados, cambio y retiro del vínculo. Comprobar que
el cierre de uno no altera los demás y que no aparecen opciones de cliente en el
interno. Revisar filtros, períodos, páginas y estados vacíos.

## Validaciones y límites

Las pruebas backend crean PostgreSQL descartable en /tmp; no leen DATABASE_URL de
la instalación para ese clúster. Incluyen numeración concurrente y migración real
0020→0021 conservando íntegro un ticket anterior, con ejecución de upgrade head
repetida. Las pruebas frontend cubren contratos visibles, navegación, catálogos,
búsqueda remota y la regresión de Tickets/FMS. El build no sustituye esas pruebas.

No se implementan Control de cambios, autenticación, nuevas reporterías internas,
PDF de cliente para internos, adjuntos ni auditoría con usuario identificado.

### Resultado de validación de esta implementación

- Suite backend completa: 1494 pruebas aprobadas; aviso de deprecación ya existente
  de Starlette/httpx, sin introducir dependencias nuevas.
- Suite frontend completa: 515 pruebas aprobadas (46 archivos, dos workers).
- Pruebas específicas de migración, concurrencia, reactivación de proveedores,
  cambio de vínculo, búsqueda paginada y seguimiento interno aprobadas.
- TypeScript y `npm run build` correctos; `frontend/dist/` actualizado.
- Compilación Python, HEAD único `0021_internal_tickets` y `git diff --check`
  correctos.
- Revisión de 20 combinaciones de pantalla/resolución con API simulada entre
  320 y 1440 px, sin desbordamiento horizontal de página.
- No se ejecutaron migraciones operativas, commits, tags, releases o despliegues.

### Reportería de incidencias internas

Se integra en la página existente `/reports`, mediante la selección «Tickets internos»
(`?scope=internal`), sin añadir una entrada al sidebar. Comparte `Reports`, períodos,
KPIs, gráficos Capsule NOC, rankings y generadores estadísticos PDF/XLSX.
Los endpoints son `/api/reports/internal-tickets/summary` y
`/api/reports/internal-tickets/export/{pdf|xlsx}`.

El motor `report_summary` recibe el contexto interno y utiliza sus modelos y catálogo
de tipos, sin consultar tickets de clientes salvo para agregar los vínculos explícitos.
Iniciadas, distribuciones y detalle utilizan Inicio; cierres y duración utilizan Fin,
estado Cerrado y los mismos filtros de clasificación. Los contadores de abiertos y
cerrados por estado se identifican como pertenecientes a la cohorte iniciada.
Las fechas, agrupaciones y duraciones conservan las reglas de la reportería de Tickets.

La atribución distingue Todos, proveedor específico y Ninguno (`without_provider`).
Los proveedores inactivos con incidencias se conservan en las distribuciones.
Los vínculos se cuentan mediante una agregación por ticket interno: una incidencia
con cinco tickets relacionados aporta una incidencia y cinco vínculos. La fecha del
vínculo o del ticket de cliente no sustituye el inicio de la incidencia interna.
No se interpreta esta asociación como afectación confirmada ni se sincronizan estados.

Las exportaciones estadísticas contienen resumen, evolución, distribuciones,
duraciones y todos los detalles filtrados, sin columnas propias de clientes/circuitos.
Conservan el mecanismo de documentos y archivos temporales existente; los PDF de
volumen muy grande requieren memoria proporcional a sus tablas, sin truncamiento.
No se necesitan migraciones ni cambios al modelo de acceso de red de confianza.

El resumen visual interno conserva seis indicadores: iniciadas, cerradas, duración
promedio y acumulada, tickets de clientes vinculados e incidencias con vínculos,
en una sola cápsula con seis columnas en escritorio amplio, tres en tamaños
medianos y dos en móviles. «Incidencias cerradas» utiliza estado Cerrado y Fin en
el período, aunque Inicio sea anterior. Difiere de «Cerrados (iniciados)», que cuenta
los actualmente cerrados dentro de la cohorte con Inicio en el período. Esta última
métrica, abiertos de la cohorte e incidencias sin vínculos se mantienen en el contrato
y exportaciones existentes, pero no se presentan en el resumen visual. No se cambian
los cálculos ni se agregan consultas para esta simplificación.
