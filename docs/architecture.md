# Arquitectura de Ticketyn

Esta guía describe la implementación actual, no una arquitectura futura.
El [README](../README.md) presenta el proyecto y sus límites.

## Componentes

- `src/ticketyn/main.py` integra FastAPI y sus rutas.
- `src/ticketyn/api/` contiene endpoints, consultas, coordinación transaccional
  y servicios de datos y exportación de los módulos.
- `src/ticketyn/models/` define entidades SQLAlchemy; `schemas/` define contratos
  y validaciones Pydantic; `core/` y `db/` reúnen configuración y acceso a datos.
- `alembic/` conserva la evolución incremental del esquema PostgreSQL.
- `frontend/src/` contiene páginas React/TypeScript, componentes y utilidades
  compartidas. React Router conecta las pantallas; Recharts representa estadísticas.
- ReportLab y openpyxl generan documentos en el backend. Las exportaciones
  reutilizan consultas y primitivas de presentación, con variantes por dominio.

En producción, Nginx sirve `frontend/dist/` y dirige `/api/` y `/health` a Uvicorn
local. En desarrollo, Vite proporciona el frontend y el proxy hacia el backend.
PostgreSQL es el almacenamiento soportado; no hay alternativa SQLite.

## Configuración y transacciones

`DATABASE_URL` es obligatoria y utiliza `postgresql+psycopg`. El entorno tiene
prioridad sobre `.env`, localizado respecto al directorio de trabajo.
La aplicación no crea tablas ni aplica migraciones al arrancar.

Las operaciones coordinan sus escrituras dentro de transacciones. La numeración
utiliza configuraciones independientes, bloqueo transaccional y referencias
únicas almacenadas. La vista previa no consume números y cambiar la configuración
no reescribe referencias anteriores.

## Relaciones principales

| Entidad | Relación y criterio principal |
|---|---|
| Cliente y circuito | Un cliente tiene varios circuitos; el ticket de cliente se vincula con un circuito de ese cliente. |
| Sector y nodo | Catálogos independientes. Sector es una agrupación lógica configurable; no hay relación directa que permita filtrar todos los nodos por sector. |
| Ticket de cliente | Conserva clasificación y tiempos propios; puede vincularse opcionalmente con un ticket interno. |
| Ticket interno | No tiene cliente ni circuito propios. Puede reunir varios tickets de clientes; sus estados y seguimientos son independientes. |
| Operaciones FMS | Activaciones, capacidad y bajas/reactivaciones se relacionan con circuitos y conservan información histórica propia. |
| Cambio | Tiene planificación, ejecución, encargado, apoyo y seguimiento; admite varios tickets internos mediante una relación opcional. |
| Catálogos | Clasifican y permiten nuevas asignaciones activas, conservando referencias históricas a registros desactivados según las reglas de cada formulario. |

Los catálogos de tipos de incidencia de clientes e internos son diferentes.
Proveedores corresponde a tickets internos. Los tipos de cambio y de finalización
son también catálogos separados: clasifican el trabajo y su resultado, respectivamente.

## Datos actuales e históricos

El sector y nodo almacenados en un ticket no se recalculan al consultarlo desde
el circuito actual. Existe una excepción deliberada: al cambiar el sector del
circuito se sincronizan sus tickets creados en las últimas 168 horas, incluidos
los cerrados, únicamente cuando su sector difiere. La corrección y su entrada
interna de bitácora son transaccionales. Los tickets anteriores permanecen intactos.
Véase la [regla de sincronización reciente](recent-ticket-sector-sync-v0.5.0.md).

Las activaciones conservan datos técnicos capturados al registrarse, incluidos
tipo de servicio, capacidad inicial y CPE. Los valores históricos ausentes se
presentan como «Sin registrar», sin reconstruirlos silenciosamente desde el circuito.

Control de cambios conserva departamento y nombres de participantes históricos,
así como la elegibilidad para eficiencia del tipo de finalización al finalizar.
Modificar el catálogo no cambia retroactivamente esa elegibilidad. Los cambios
anteriores al catálogo de tipos de cambio pueden conservar clasificación nula.

No existen cierres automáticos entre tickets vinculados ni entre cambios y tickets
internos. La fecha de creación se distingue de las fechas operativas manuales.
Las conversiones operativas utilizan `America/Guatemala`; la interfaz no debe
reinterpretarlas según la zona horaria del navegador.

## Acceso y trazabilidad

No existen usuarios, login, roles ni autorización individual. Un responsable es
una persona del catálogo operativo, no una cuenta autenticada. La protección
externa de red no sustituye autorización individual en la API.

Los seguimientos y registros de cambios disponibles conservan información operativa,
pero no constituyen una auditoría completa con identidad autenticada. La visibilidad
para cliente de un seguimiento normal controla su inclusión documental; no habilita
un portal público. Los tickets internos y los cambios no tienen esa visibilidad.

La configuración CPE es texto almacenado: no ejecuta comandos ni constituye una
bóveda cifrada de credenciales. No hay sincronización con equipos de red.

## Lecturas complementarias

- [Módulos y reglas funcionales](modules.md).
- [Tickets internos: diseño y decisiones](internal-tickets-v0.5.0-design.md).
- [Control de cambios: diseño y validaciones históricas](change-control-v0.5.0-design.md).
- [Tipos de cambio y compatibilidad histórica](change-types-v0.5.0.md).
- [Instalación y migraciones](deployment.md).
