# Control de cambios v0.5.0

## Arquitectura y decisiones

Entidades independientes de Tickets y Tickets internos, con servicios en
`change_data`, rutas `changes` y agregaciones/exportaciones `change_reports`.
Se reutilizan numeración con bloqueo transaccional PostgreSQL, catálogos,
componentes Capsule NOC, búsqueda remota de tickets internos y las primitivas
ReportLab/openpyxl, snapshots de lectura y archivos temporales existentes.
No se incorporan identidades, login ni roles. La protección externa de red no
constituye autorización individual; no se modifica el proxy ni su configuración.

El usuario confirmó que Nodo debe permanecer **sin filtro por Sector**: no existe
una relación directa en los catálogos y no se deduce a través de circuitos.
El encargado necesita un departamento en su catálogo para una nueva asignación.
El departamento y los nombres de encargado/apoyo se conservan como snapshots;
las correcciones de participantes, vínculos, notas y demás campos generan registros
`change_audit` con antes/después, sin inventar autores de sistema.
La creación es inmutable a través de los contratos de escritura. No hay endpoints
de eliminación ni cascadas destructivas en las nuevas relaciones.

## Estados y tiempos

Los tres estados son manuales: Agendado, En ejecución y Finalizado. Se permite
crear cambios históricos directamente Finalizados. La planificación es siempre
obligatoria, con fin >= inicio. En ejecución exige inicio real; Finalizado exige
ambos extremos reales, tipo y notas. Las notas y participantes pueden corregirse
sin reabrir. Seguimiento admite fecha manual y registros posteriores al cierre.

Al finalizar se captura nombre y `applies_efficiency` del tipo. Editar las notas o
renombrar/desactivar el catálogo no vuelve a capturar estos valores. Cambiar el
tipo o volver a finalizar tras una reapertura manual captura la clasificación
seleccionada, dejando evidencia de la modificación.

Eficiencia: compara duraciones reales y planificadas. Solo Finalizados con
snapshot elegible y planificación positiva son evaluables. ±900 segundos inclusive
es Tiempo cumplido; más ahorro es Mayor eficiencia y más exceso es Tiempo excedido.
La planificación cero es válida, pero no evaluable; no se divide por cero.
La variación porcentual usa (planificada-real)/planificada y se redondea a dos
 decimales. Puntualidad es independiente: más de 3600 segundos después del inicio
propuesto produce únicamente «Inicio tardío», sin mostrar minutos de retraso.

## Consultas, calendario y reportería

Listado paginado a 50 y calendario comparten filtros en URL; cambiar vista no los
elimina. La última vista se recuerda localmente. Calendario de mes/semana/día por
Inicio propuesto, con navegación por fecha y sin límites de años codificados.
Carga todas las páginas del intervalo visible; nunca se limita silenciosamente
a los primeros 200 eventos. Muestra la ventana propuesta en cada evento.

La reportería está en `/reports?scope=changes`, dentro del selector existente.
Todas las agregaciones y exportaciones usan el mismo predicado por Inicio propuesto.
Duraciones agregadas: reales de cambios Finalizados. Porcentajes de eficiencia:
únicamente evaluables. Participación: unión de encargado/apoyo y conteo distinto
por cambio/persona. Los indicadores no son una evaluación automática de desempeño.

Las exportaciones del listado, estadísticas y PDF individual usan consultas completas
sin el límite de página y no tienen campos comerciales ni de clientes. Las tablas
largas se dividen en páginas físicas; los PDF pueden consumir memoria proporcional
al contenido, como los generadores existentes. XLSX usa escritura incremental.

## Migración y prueba local

Revisión `0022_change_control`, dependiente de `0021_internal_tickets`. Crea siete
tablas e índices, sin actualizar tickets existentes, y precarga cinco tipos de
finalización (solo Finalizado con éxito elegible). No se modifican revisiones previas.
El downgrade se rechaza para evitar borrar historia automáticamente.

En una base local respaldada, aplicar el procedimiento habitual de actualización
con Alembic hasta HEAD. Nunca se ha aplicado durante el desarrollo a bases operativas.
Configurar responsables con departamento, revisar Catálogos → Tipos de finalización,
Configurar numeración de cambios y abrir Operación → Control de cambios.
Probar un cambio de 11:00–15:00 con ejecución 13:00–15:00, finalizado con éxito:
Mayor eficiencia, 50 % de ahorro e Inicio tardío simultáneos.

## Estado de entrega inicial (registro de la sesión anterior)

Se cerró esta etapa sin iniciar funcionalidades adicionales. Implementados listado,
calendario, creación/edición, ficha, seguimiento, historial, vínculos bidireccionales,
catálogo, numeración, reportería y las cinco exportaciones solicitadas.

Validaciones de cierre:
- 51 pruebas backend esenciales aprobadas (cambios, concurrencia, migración nueva,
  despliegue local simulado, Tickets internos, reportería y exportaciones existentes).
- 5 pruebas de migraciones históricas y 1 de migración de Nodos aprobadas tras excluir
  las nuevas tablas de los esquemas históricos reconstruidos por esas pruebas.
- Suite completa frontend: 536 aprobadas; comprobación final de componentes afectados:
  93 aprobadas.
- HEAD único `0022_change_control`, compilación Python y `git diff --check` correctos.
- Build de producción actualizado; aviso no bloqueante de Vite por chunk principal
  ligeramente superior a 500 kB.
- Revisión en navegador con datos simulados: 25 combinaciones de pantalla/ancho,
  desde 320 a 1440 px, sin desbordamientos globales. PDF individual revisado y
  compactado para evitar una primera página casi vacía.

En aquel cierre quedó pendiente repetir la suite backend completa con las
expectativas de migración ya actualizadas; esta tarea se completó en la validación
retomada que se registra a continuación. La corrida iniciada antes de esos ajustes
no se considera aprobada y fue interrumpida al priorizar este cierre; su salida
incluyó un error de teardown de pytest durante la interrupción. También conviene
completar pruebas de estrés de documentos/calendarios de gran volumen y una revisión
operativa con datos reales en una instalación local aislada. No se han realizado
commits, publicaciones, despliegues ni migraciones en bases operativas.

## Validación retomada: cerrada

Se revisó el estado existente en `master` y se conservaron todos los cambios locales.
No se reimplementaron funcionalidades ni se ampliaron los requisitos.

Resultados de la ejecución completa sobre el código recibido:

- **Backend: 1534 pruebas aprobadas**, sin fallos ni errores de teardown, en 516,45 s.
  Incluye migraciones, concurrencia, Tickets, Tickets internos, cambios, reporterías
  y exportaciones. Solo queda la advertencia de deprecación Starlette/TestClient
  sobre httpx; no se cambian dependencias en esta validación.
- **Frontend: 536 pruebas aprobadas** en 50 archivos. Los procesos de las pruebas de
  zonas horarias se ejecutaron fuera del sandbox para evitar la restricción EPERM.
- **Build: correcto**, incluyendo TypeScript. Se conserva el aviso no bloqueante
  conocido de Vite: chunk principal de 500,74 kB minificado.
- **`frontend/dist/`: actualizado y reproducible**. La recompilación generó exactamente
  los mismos contenidos que al iniciar la validación. Comprobadas las referencias
  del HTML y los imports locales de los bundles, sin assets ausentes.
- **Alembic: HEAD único `0022_change_control`**, dependiente de
  `0021_internal_tickets`. Las pruebas validan upgrade en bases descartables,
  conservación de datos y los cinco tipos de finalización iniciales. Ningún archivo
  de migración fue modificado durante esta sesión.
- Compilación Python de `src`, `tests` y `alembic`, y **`git diff --check`: correctos**.

No aparecieron fallos que requirieran corregir código o pruebas. El único archivo
cambiado durante la validación es este documento de traspaso. No se aplicaron
migraciones a bases operativas ni se realizaron commits, tags, releases o despliegues.
La suite backend completa ya no está pendiente; quedan únicamente la revisión
manual y las pruebas de estrés descritas en la lista siguiente.

## Lista de pruebas manuales en Arch Linux

La validación automatizada retomada utiliza Arch Linux, Python 3.14.8,
PostgreSQL 18.6, Node 26.11.1 y npm 12.2.0. Estas pruebas no sustituyen la
revisión operativa siguiente, que debe hacerse en una instalación local aislada:

1. **Preparación local:** respaldar la base de prueba, comprobar su revisión Alembic
   y seguir el procedimiento existente para llegar a `0022_change_control`.
   Confirmar los cinco tipos iniciales de finalización, responsables con departamento
   y la numeración CAM configurable sin consumir números en la vista previa.
2. **Flujo manual e histórico:** registrar Agendado, pasar manualmente a En ejecución
   y Finalizado; crear también un Finalizado histórico. Comprobar campos obligatorios,
   rechazo de fines anteriores al inicio y cambios que crucen medianoche o varios días.
3. **Resultados:** comparar 11:00–15:00 propuesto con 13:00–15:00 real: 2 horas ahorradas,
   Mayor eficiencia 50 % e Inicio tardío simultáneos. Verificar los límites inclusivos
   de ±15 minutos, inicio exactamente 60 minutos después sin aviso y 61 con aviso.
   Planificación cero y tipos no elegibles deben mostrarse No evaluable.
4. **Historia y trazabilidad:** cambiar notas, encargado y apoyos después de finalizar;
   consultar antes/después en el historial. Renombrar o desactivar personas y tipos
   sin reclasificar resultados históricos. Agregar seguimiento con fecha manual.
5. **Vínculos:** vincular varios Tickets internos, impedir duplicados, desvincular y
   navegar en ambos sentidos. Confirmar independencia de estados, sin crear tickets
   ni cerrarlos automáticamente. Nodo permanece sin filtro por Sector por decisión
   explícita del usuario.
6. **Listado y calendario:** comprobar búsqueda, orden, registro 51 y página siguiente, filtros compartidos,
   Limpiar filtros, vistas mes/semana/día y navegación a fechas pasadas/futuras.
   Los eventos deben permanecer en Inicio propuesto aunque cambie el inicio real.
7. **Reportería y documentos:** contrastar KPIs, denominadores de eficiencia y
   participación sin duplicaciones; exportar listado PDF/Excel, reporte PDF/Excel
   y PDF individual. Revisar vacíos, contenido extenso, saltos de página, tildes,
   fechas, filtros y totalidad de registros en archivos descargados.
8. **Interfaz y regresiones:** probar teclado, zoom, escritorio y móvil; revisar
   Tickets normales, Tickets internos, Catálogos, Configuración y Reportería.
   Las pruebas de estrés con grandes volúmenes de calendario/PDF siguen pendientes.
