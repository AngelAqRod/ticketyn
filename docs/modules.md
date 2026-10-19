# Módulos disponibles

Esta referencia describe capacidades verificadas en las rutas, formularios,
servicios y exportaciones del repositorio. No implica que el proyecto esté terminado.
La [arquitectura](architecture.md) explica las relaciones entre entidades.

## Dashboard

Presenta indicadores globales de tickets, distribuciones y tickets recientes.
No es una consola de monitoreo de equipos ni genera incidencias desde dispositivos.

## Tickets de clientes

Permite crear, consultar y editar tickets asociados a cliente y circuito, con
clasificación, responsable, descripción, resolución y fechas operativas.
Los estados implementados son Abierto y Cerrado; los escalamientos son registros
independientes, no estados adicionales del ticket.

El seguimiento conserva fecha de actividad, fecha de registro, responsable opcional
y contenido. Distingue intervenciones internas y visibles para cliente. Los
escalamientos documentan solicitudes de apoyo a departamentos y responsables;
no obligan a una jerarquía N1/N2/N3 ni reasignan o cierran automáticamente el ticket.

El PDF individual tiene variantes interna y para cliente. Los textos autorizados
para cliente están separados del contenido interno. Una incidencia interna vinculada
solo se incluye en el reporte interno. El listado permite PDF y Excel de los
resultados filtrados, no únicamente de la página visible.

Un ticket puede vincularse, cambiarse o desvincularse de un único ticket interno,
incluso cerrado. No se exige coincidencia de sector o nodo ni se propagan estados.

Guía especializada: [Escalamientos](escalations-v0.3.1.md). Sus referencias de
migración y resultados de pruebas corresponden a la versión indicada en el documento.

## Tickets internos

Gestiona incidencias de infraestructura sin cliente, circuito ni contenido
autorizado para cliente. Sector y tipo de incidencia interna son obligatorios;
nodo y proveedor atribuible son opcionales. Reutiliza departamentos, responsables,
estados, fechas, seguimiento y escalamientos de la operación existente.

«Ninguno» representa ausencia de proveedor. Las asignaciones nuevas usan proveedores
activos; las referencias históricas se conservan. La atribución puede corregirse
incluso con el ticket cerrado, sin reabrirlo ni afirmar responsabilidad definitiva.
Todos los seguimientos son internos.

La numeración es independiente. Listado, búsqueda, filtros y paginación utilizan
campos propios de infraestructura. Hay exportación de listado PDF/Excel, PDF
individual interno y consulta de tickets de clientes vinculados desde ambos detalles.

Véase [Tickets internos](internal-tickets-v0.5.0-design.md), que conserva también
notas de implementación y validaciones de etapas anteriores.

## Clientes y circuitos

Los clientes agrupan circuitos con código, sector, nodo, tipo de servicio,
capacidad inicial y datos administrativos. Se permite eliminar registros únicamente
cuando sus dependencias lo permiten; no es una herramienta de eliminación de historial.

La ficha del circuito reúne información general, activación inicial, operaciones
de capacidad, bajas/reactivaciones y configuración CPE. La capacidad actual se
determina a partir de las operaciones, sin reemplazar la capacidad inicial.

Al corregir el sector de un circuito se aplica la
[sincronización de tickets recientes](recent-ticket-sector-sync-v0.5.0.md).
No se realiza una reclasificación general de tickets antiguos ni de tickets internos.

## Operaciones FMS

Las pantallas de Activaciones, Cambios de capacidad y Bajas/reactivaciones registran
el ciclo de vida técnico del circuito, con consultas, fechas, responsables y
bitácoras según cada operación. No son tickets ni cambios de infraestructura.

Las activaciones capturan valores técnicos históricos del circuito; su detalle
y PDF individual conservan esos datos y su bitácora. La configuración CPE actual
es texto literal consultable y editable: no ejecuta configuraciones ni mantiene
por sí sola un historial de versiones del equipo.

Los listados FMS tienen exportaciones PDF y Excel. Su análisis estadístico utiliza
períodos y agrupaciones con exportación **PDF**; no se debe confundir esa exportación
con el Excel de los listados. Los PDF estadísticos limitan el volumen procesado
(2.000 operaciones y 2.000.000 de caracteres): ante exceso se debe acotar el reporte,
no asumir que el documento contiene un resultado truncado.

## Control de cambios

Permite planificar y documentar trabajos mediante listado paginado y calendario
Mes/Semana/Día. Los eventos se ubican por inicio propuesto. Los filtros se comparten
entre listado y calendario; los estados se cambian manualmente.

- **Agendado:** planificación obligatoria; fechas reales opcionales.
- **En ejecución:** requiere inicio real; fin real opcional.
- **Finalizado:** requiere fechas reales, tipo de finalización y notas finales.

El encargado requiere departamento; este se conserva históricamente. El apoyo
admite cero o varias personas, sin duplicados ni repetición del encargado.
Nodo es opcional y no se filtra por sector, pues no existe esa relación directa.
Las fechas admiten trabajos históricos, cruce de medianoche y varios días.

El tipo de cambio es obligatorio para nuevos registros y al guardar la edición
principal. Los registros históricos nulos se muestran como «Sin clasificar»;
pueden consultarse y recibir seguimiento o vínculos sin clasificarlos previamente.
Un tipo desactivado puede conservarse en un registro existente.

La eficiencia compara **duraciones**, con tolerancia inclusiva de ±15 minutos.
Solo evalúa finalizados elegibles según la copia histórica del tipo de finalización,
con duración planificada positiva y fechas válidas. Los demás son «No evaluable»
y no integran el denominador de eficiencia. Un inicio más de 60 minutos tarde
muestra «Inicio tardío» de forma independiente: no invalida la eficiencia.

El seguimiento admite fechas manuales y nuevas entradas después de finalizar.
Pueden corregirse participantes y notas; los vínculos opcionales con varios tickets
internos no cambian estados en ninguno de los módulos.

Incluye PDF individual, PDF/Excel del listado y PDF/Excel estadísticos.
Guías: [diseño de Control de cambios](change-control-v0.5.0-design.md) y
[catálogo Tipos de cambio](change-types-v0.5.0.md).

## Reportería

La reportería de Tickets, Tickets internos y Control de cambios comparte componentes
visuales, filtros y exportaciones estadísticas PDF/Excel, con consultas específicas
para cada dominio. Los análisis FMS están disponibles en sus apartados correspondientes.

En Tickets e internos, los iniciados se seleccionan por fecha de inicio; los
cerrados del período se seleccionan por fecha de finalización y estado cerrado.
Un ticket cerrado sin fin no aporta una duración de resolución válida. Son bases
temporales diferentes, no cantidades intercambiables.

Tickets internos incorpora clasificación interna, proveedores y vínculos: un interno
con cinco tickets asociados cuenta como una incidencia y cinco tickets vinculados.
Los vínculos no significan por sí solos afectaciones confirmadas a clientes.

Control de cambios incluye estados, tipos, sectores, nodos, departamentos, evolución,
duraciones y eficiencia. La duración promedio y acumulada utiliza finalizados con
fechas reales válidas. La participación tiene gráficas separadas para encargado
y apoyo; el total por persona cuenta cambios distintos, sin calificar desempeño.

Las categorías decorativas comparten la paleta Capsule NOC. Los filtros y los datos
históricos pertenecen a cada dominio; no se mezclan tickets normales e internos
salvo en los indicadores explícitos de relación.

## Administración

Catálogos mantiene sectores, nodos, departamentos, puestos, responsables, tipos
de incidencia de clientes e internos, proveedores, motivos de escalamiento,
tipos de servicio, motivos de baja, modelos CPE y tipos y finalizaciones de cambios.
La desactivación conserva referencias históricas; las validaciones evitan nombres
duplicados según las convenciones del catálogo.

Configuración administra numeraciones independientes de Tickets, Tickets internos,
Activaciones y Control de cambios. Permite prefijo, separador, siguiente número,
longitud y vista previa sin consumir referencias. No configura todos los campos
ni permite definir libremente estados o flujos nuevos.

## Límites y documentación histórica

No hay autenticación, autorización por usuario, portal de clientes, adjuntos ni
motor de SLA. Las funciones disponibles no sustituyen monitoreo, inventario
especializado ni gestión comercial.

[Actualización v0.3.0](upgrading-v0.3.0.md) y
[notas v0.3.0](releases/v0.3.0.md) se conservan como referencias históricas.
Para una instalación actual utiliza [Administración y despliegue](deployment.md).
