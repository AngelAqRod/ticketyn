# Ficha Técnica: Catálogos y Configuración

## Responsabilidad del módulo
- **Qué gestiona:** El mantenimiento centralizado de los catálogos maestros operativos del sistema y la configuración técnica de esquemas de numeración secuencial para los documentos y registros de la plataforma.
- **Funcionalidades existentes:**
  - Administración completa (alta, modificación y activación/desactivación lógica) de tablas maestras operativas.
  - Mecanismos de creación rápida en contexto (`QuickCatalogCreate`) desde selectores de formularios operativos.
  - Configuración de numeraciones secuenciales independientes: prefijo, separador, longitud mínima de relleno con ceros (`padding`), siguiente número correlativo y vista previa inmediata.
  - Cuatro dominios con numeración propia: Tickets de Clientes, Tickets Internos, Activaciones y Control de Cambios.
- **Qué no le corresponde:** No permite crear estados operativos nuevos por interfaz (los estados son constantes fijas por código de aplicación) ni admite la eliminación destructiva de registros que cuenten con historial asociado.

## Reglas de negocio críticas
- **Preservación estricta por desactivación lógica:**
  - La eliminación física (`DELETE`) solo se admite para registros que nunca han sido vinculados a una operación.
  - Si un registro de catálogo posee referencias históricas en tickets, cambios u operaciones, debe desactivarse (`active=false`).
  - Un elemento desactivado no aparece en listas desplegables para nuevos registros, pero se conserva intacto en los formularios y reportes históricos.
- **Control de unicidad textual:**
  - Las validaciones aplican normalización estricta (`lower(trim(name))`) para evitar duplicados accidentales (ej. «NOC Central» vs «noc central»).
- **Bloqueo transaccional contra colisiones de numeración:**
  - Cada asignación de un nuevo código correlativo toma un bloqueo exclusivo de fila en PostgreSQL (`SELECT ... FOR UPDATE`).
  - Esto garantiza que dos operaciones concurrentes jamás reciban el mismo número secuencial ni se generen condiciones de carrera.
- **Inocuidad matemática de la vista previa:**
  - La vista previa de numeración en formularios o en la configuración es solo una proyección formateada en memoria; jamás consume, avanza ni reserva números en la secuencia real de base de datos.
- **Inmutabilidad retrospectiva de esquemas:**
  - Modificar el prefijo, separador o longitud de una numeración solo aplica a los registros futuros; los registros creados previamente conservan intacto su código histórico.

## Arquitectura y dependencias
- **Componentes backend:** Endpoints en `src/ticketyn/api/` (`crud.py`, `settings.py`, `ticket_numbers.py`, rutas especializadas por catálogo), esquemas en `src/ticketyn/schemas/`.
- **Distribución de modelos por catálogo:**
  - Sectores: `src/ticketyn/models/sector.py`
  - Nodos: `src/ticketyn/models/node.py`
  - Departamentos: `src/ticketyn/models/department.py`
  - Puestos: `src/ticketyn/models/position.py`
  - Responsables: `src/ticketyn/models/responsible.py`
  - Tipos de Incidencia de Clientes: `src/ticketyn/models/incident_type.py`
  - Tipos de Incidencia Interna y Proveedores: `src/ticketyn/models/internal_ticket.py`
  - Motivos de Escalamiento: `src/ticketyn/models/escalation.py`
  - Tipos de Servicio y Modelos CPE: `src/ticketyn/models/service_type.py` y `cpe_model.py`
  - Motivos de Baja: `src/ticketyn/models/fms.py`
  - Tipos de Cambio y Tipos de Finalización: `src/ticketyn/models/change.py`
  - Configuraciones de numeración: `ticket_number_config.py`, `internal_ticket.py`, `fms.py` y `change.py`
- **Componentes frontend:** Vistas en `frontend/src/pages/` (`Catalogs.tsx`, `Settings.tsx`), componentes en `frontend/src/components/` (`CatalogAdmin.tsx`, `QuickCatalogCreate.tsx`).
- **Dependencias:** Requerido transversalmente por todos los módulos operativos de la plataforma.
- **Referencias:** Consultar `docs/SYSTEM_MAP.md` para la lista completa de archivos.

## Contratos y seguridad
- **Endpoints clave:** `GET/POST/PUT/DELETE /api/{catalogo}`, `GET/PUT /api/settings/{tipo}-numbers`, `POST /api/settings/{tipo}-numbers/preview`.
- **Permisos requeridos:** `catalogs.{catalogo}.view`, `catalogs.{catalogo}.create`, `catalogs.{catalogo}.edit`, `catalogs.{catalogo}.lookup`, `settings.{tipo}_number.view`, `settings.{tipo}_number.edit`, `context.{recurso}.create`.
- **Restricción de acceso:** Los roles Operador y Auditor solo reciben permisos de lectura para selectores (`lookup`) y creación rápida contextual (`context.*.create`). La administración global de catálogos y ajustes de numeración está reservada para Administradores y Superadministradores.

## Validaciones
- **Pruebas backend:**
  ```bash
  .venv/bin/pytest tests/test_catalog_api.py tests/test_catalog_deletion.py tests/test_positions.py tests/test_nodes_responsibles.py -q
  ```
- **Pruebas frontend:**
  ```bash
  npm test -- frontend/src/pages/Catalogs.test.tsx frontend/src/pages/Settings.test.tsx
  ```
- **Consideraciones para evitar regresiones:**
  - Comprobar que el borrado de elementos en uso sea rechazado con HTTP 400/409.
  - Asegurar que la generación de números consecutivos concurrentes mantenga la secuencia estricta sin duplicados.

## Mantenimiento
Este documento debe actualizarse ante cualquier incorporación de nuevos catálogos maestros, cambios en las reglas de unicidad o ampliación de parámetros en la numeración.

## Nomenclaturas de puertos de distribución

- Administración → Catálogos → Nomenclaturas de puertos, mediante `PortNomenclatureAdmin.tsx` y `/api/port-nomenclatures`. Nombre, prefijo literal, formatos N, X/Y, X/Y/Z y W/X/Y/Z, además del estado.
- El prefijo es único sin distinguir mayúsculas. Un registro activo exige formatos; prefijos referenciados y registros referenciados no se cambian/eliminan físicamente. Desactivar conserva puertos y asociaciones.
- Excepción de lectura al catálogo general: Auditor tiene `catalogs.port_nomenclatures.view`. Admin/Superadmin administran; Operador solo lookup y creación de puertos con su permiso operativo existente. No se conceden mutaciones de catálogo por permisos operativos.
- Backend: `src/ticketyn/api/port_nomenclatures.py`, `src/ticketyn/models/distribution.py`, `src/ticketyn/schemas/port_nomenclature.py`. Ver [contratos y pruebas](../port-nomenclatures-v0.8.0.md).
