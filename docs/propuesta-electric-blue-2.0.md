# Ticketyn — Propuesta Electric Blue 2.0 + Capsule NOC

**Estado:** propuesta conceptual para aprobación; no implementada.

**Método:** Impeccable `shape`, modo **Operate**.

**Rama inspeccionada:** `development/v0.7.0`. **Fecha:** 20/10/2026.

## 1. Brief confirmado

Evolucionar integralmente la interfaz de Ticketyn manteniendo el azul eléctrico, las cápsulas y su identidad técnica NOC/ISP. La nueva autorización permite replantear la composición de sidebar, encabezado y pantallas: las geometrías actuales son antecedentes, no una obligación de reproducirlas exactamente.

El personal del NOC debe poder reconocer un registro, entender su contexto y estado y ejecutar la acción autorizada con claridad. La identidad gráfica debe ayudar a orientarse sin competir con datos, formularios o mensajes.

**Confirmado por el propietario:** escritorio NOC de **1440–1920 px** como entorno principal, con adaptación a portátil y móvil. **Piloto: Tickets — listado, detalle y formulario**. Se conservan las acciones y datos disponibles; no se modifica el modelo operativo.

Las prioridades son legibilidad, consistencia, densidad útil, accesibilidad, adaptación y reducción de ruido. El diseño se plantea como una aplicación de trabajo, sin recursos de una página comercial ni simulaciones de consola de monitoreo.

## 2. Evidencia y límites de la inspección

Se revisaron AGENTS, handoff, PRODUCT y documentación vigente, junto con `styles.css`, Layout, PageHeading, navegación, AuthGate, Dashboard, Tickets, TicketTable, TicketFilters, FormField, SearchableSelect, OperationModal, ActivationDetail y patrones de Administración. Las rutas citadas de frontend son relativas a `frontend/src/`.

| Hecho comprobado en código | Implicación de diseño que conviene validar |
|---|---|
| Hay 21 entradas principales; el menú utiliza Operación, Análisis y Administración. | Los grupos FMS y correo pueden mejorar la orientación sin crear nuevas rutas o módulos. |
| Layout muestra contexto; PageHeading repite grupo, número y título; el menú también numera módulos. | La jerarquía contiene señales redundantes. Una numeración ornamental no debe competir con correlativos operativos. |
| Sidebar, cabeceras, títulos de panel y paginación acumulan superficies oscuras, cápsulas, gradientes y motivos de red. | La identidad se reparte por demasiadas zonas de atención similar; conviene concentrarla. |
| Coexisten estilos base y tratamientos `noc-*`, paneles blancos y azulados, con excepciones locales. | Un lenguaje compartido debe reducir diferencias de controles y superficies entre módulos. |
| TicketTable tiene once columnas y `min-w-[1350px]`; el sidebar consume otros 224–240 px. | Incluso un escritorio de 1440 px puede necesitar scroll horizontal: no se debe resolver reduciendo todo el texto. |
| La escala incluye etiquetas de 9–11 px y títulos con Oxanium; formularios y datos usan otras convenciones. | Revisar la escala para lectura prolongada, manteniendo la tipografía de marca separada del trabajo con datos. |
| El login es un panel funcional sencillo y AuthGate contiene además los estados de sesión y contraseña temporal. | Integrar visualmente esos estados sin reescribir autenticación ni cambiar cómo se conserva el formulario al expirar. |
| Existen controles reutilizables, permisos React, estados de petición, filtros en URL y diálogos nativos con gestión de foco. | Se puede evolucionar la presentación conservando comportamiento y pruebas. |

Estas son observaciones de código e hipótesis de mejora, **no un resultado de pruebas de usabilidad ni una certificación de accesibilidad**. No se inspeccionaron sesiones autenticadas ni datos DEV, no se arrancó el servicio y no se hicieron capturas del renderizado. No se encontraron capturas de referencia que permitan declarar verificada la apariencia en navegador. La aprobación visual requerirá esa comprobación en un hito autorizado posterior.

## 3. Dirección propuesta: orientación de servicio

**Tesis: marco reconocible, trabajo despejado.** El azul organiza el espacio; las cápsulas señalan ubicación, selección y estado; la información conserva una estructura estable y fácil de recorrer.

La referencia conceptual es la jerarquía de la cartografía técnica: distintos niveles de información y una señal inequívoca de dónde se está. Se traduce a navegación web convencional, tipografía, densidad y un gesto propio: **una cápsula azul identifica el contexto activo, mientras los datos se alinean sobre superficies claras**. No introduce un mapa de red, topologías inventadas ni otro módulo.

La primera pantalla del piloto debe mostrar Ticketyn y el contexto en un marco compacto; título Tickets y su acción principal; búsqueda/filtros que delimitan la consulta; tabla y paginación. El registro y sus datos son el foco. La transición al detalle conserva una posición reconocible para correlativo, estado, contexto y acciones.

### Exploración y alternativas

Se exploraron siete referencias: manual técnico, ficha de servicio, cartografía técnica, señalética de centros técnicos, registro de turno, rejillas de programación y etiquetado de infraestructura. Se toman criterios de lectura y organización; ninguna convierte la aplicación en una imitación literal de esos objetos.

| Dirección | Aporte | Riesgo / decisión propuesta |
|---|---|---|
| **Orientación de servicio — propuesta principal** | Marco azul, selección en cápsula y relaciones visualmente claras; sirve a listados, fichas y administración. | Evitar convertir los vínculos en un grafo o asignar colores sin semántica. |
| Ficha técnica editorial — alternativa | Jerarquía vertical muy legible, etiquetas estables y superficies sobrias. | Puede perder personalidad si elimina demasiadas señales de marca; sigue disponible si se prefiere mayor sobriedad. |
| Índice compacto de operaciones — alternativa estructural | Navegación más compacta y mayor anchura para tablas. | Un menú basado solo en iconos o códigos perjudicaría descubrimiento y teclado; no se recomienda como configuración inicial. |

Impeccable aportó además referencias externas de catálogo industrial, listados temporales, secuencias comparables, notación y catálogos de personajes. Se descartaron sus traducciones literales por menor claridad e identificación con el trabajo NOC. Sus exigencias útiles refuerzan la propuesta: jerarquía inequívoca de identificadores, alineación de tiempos, posiciones estables de lectura y distinción consistente de estados. No se incorporan nombres codificados por color, gráficos decorativos, texturas de papel, personajes o movimientos de exhibición.

La dirección sigue pendiente de aprobación. No se ha fijado un contrato de implementación, creado DESIGN.md, generado una maqueta HTML o seleccionado automáticamente una alternativa. Referencia técnica de exploración Impeccable: `seed:393dfb66ece5b695`; no representa una preferencia del propietario.

## 4. Lenguaje visual transversal

| Elemento | Propuesta |
|---|---|
| Electric Blue | Azul eléctrico reconocible en el marco superior, selección de navegación y acciones principales. La aplicación debe seguir siendo identificable al ocultar el nombre. |
| Superficies | Sidebar azul profundo; espacio de trabajo gris azulado muy claro; contenido blanco; superficies secundarias suaves. Reducir gradientes, motivos de red y grandes fondos oscuros dentro del contenido. |
| Cápsulas | Reservarlas para navegación activa, estados breves y controles segmentados. El título completo de una pantalla, cada etiqueta y cada panel no necesitan una cápsula. |
| Tipografía | Sans legible para títulos de trabajo, etiquetas y contenido. Evaluar conservar Oxanium como firma de marca limitada. Monoespaciada solo en correlativos/códigos cuando facilite distinguir caracteres; cifras tabulares en fechas y cantidades. |
| Escala | Base de trabajo de 14 px; datos compactos de 13–14 px; etiquetas normalmente de 12 px o más; títulos de 22–26 px. Valores orientativos para validar en prototipo, no tokens aprobados. |
| Bordes y volumen | Paneles con radios moderados, separadores discretos y sombra reservada para elementos superpuestos. Evitar contenedores anidados y tarjetas para cada dato. |
| Color semántico | Azul para acción/selección; rojo, ámbar y verde solo cuando representen estados reales. Siempre acompañar con texto; no inventar severidades o urgencias ausentes del dominio. |
| Iconos y movimiento | Reutilizar Lucide y convenciones actuales. Animación breve solo para cambios de estado/visibilidad, con movimiento reducido; sin secuencias decorativas de entrada. |

Como punto de partida, mantener el azul existente cercano a `#1E60D8`, con azul profundo cercano a `#0B1B33`, fondo `#F2F5FA`, blanco y texto oscuro. La selección final de tonos depende de comprobar contraste en todos los estados; esta propuesta no declara cumplimiento ni incorpora estilos.

## 5. Marco, navegación y encabezado

Proponer un encabezado eléctrico más compacto, de aproximadamente 56–60 px, con marca a la izquierda, orientación breve y controles de usuario junto al estado de API. La versión y la conectividad mantienen su significado y quedan subordinadas al trabajo. No confundir «API conectada» con salud de la red o entrega de correo.

Sidebar azul profundo con enlaces identificables por texto e icono, cápsula clara de selección y grupos con separación discreta. Retirar la numeración decorativa repetida; conservar íntegramente referencias y numeraciones de registros. Puede evolucionar la curva que conecta sidebar y header, sin sostener máscaras complejas si entorpecen el contenido o el responsive.

Agrupación propuesta, con enlaces existentes y filtrado por permisos:

- **Operación:** Dashboard, tickets de clientes, tickets internos, FMS —activaciones, capacidad, bajas/reactivaciones—, Control de cambios, clientes y circuitos.
- **Reportería:** acceso actual a reportes de tickets/internos/cambios y los reportes FMS existentes; no crear nuevas páginas o indicadores para completar el menú.
- **Administración:** Responsables, Roles y permisos, Sesiones, Auditoría de seguridad, correo —configuración y plantillas—, Catálogos y configuración de numeraciones.

Anidar visualmente FMS y correo sirve para orientar, no para cambiar rutas o introducir otra matriz de autorización. Los grupos sin enlaces autorizados desaparecen. La cápsula activa y el estado expandido deben ser distinguibles y accesibles; no depender de hover ni de conocer números de módulo.

```text
┌ Ticketyn ─ contexto de trabajo ───────── usuario · perfil · API ┐
│ Operación      Tickets                         [Nuevo ticket] │
│  Tickets       Buscar · Estado · filtros principales           │
│  Internos      Filtros activos / filtros adicionales           │
│  FMS           Referencia · contexto · estado · fechas         │
│  …             Tabla de resultados                            │
│ Reportería     Tabla de resultados                            │
│ Administración                         Anterior · página · sig.│
└───────────────────────────────────────────────────────────────┘
```

Esquema de jerarquía, sin datos ni geometría final. No es un prototipo validado.

## 6. Cambios por superficie

| Superficie | Evolución propuesta y límites |
|---|---|
| Login y contraseña temporal | Composición sobria con marca/cápsula, jerarquía clara y formulario protagonista. Conservar mensajes genéricos, autocompletado, foco, validaciones y handlers actuales; sin registro público, recuperación por correo o SSO nuevos. |
| Dashboard | Dar prioridad visual a abiertos, después cerrados y total, usando los tres indicadores actuales y tickets recientes. Sin métricas nuevas, semáforos de red, alarmas o actualizaciones automáticas adicionales. |
| Listados y tablas | Encabezado de página compacto; una acción principal cuando exista permiso; exportaciones/actualizar con menor peso. Tabla con encabezados legibles, alineación estable, hover discreto y estado con texto. Mantener las once propiedades de Tickets, agrupando las relacionadas visualmente cuando permita ganar anchura sin perder información. |
| Filtros | Primera línea con búsqueda y filtros de uso directo; el resto en un desplegable accesible, con activos siempre visibles. Conservar todos los filtros, valores en URL y comportamiento de consulta. No añadir un buscador global ni preferencias persistentes. |
| Detalle de ticket | Correlativo y estado arriba; cliente/circuito y datos de contexto legibles; cuerpo y seguimiento como área principal. Acciones autorizadas cercanas al registro, sin repetir el mismo botón en varios paneles. Mantener visibilidad interna/cliente y vínculos existentes. |
| Formularios | Agrupar identificación, contexto, asignación, fechas y documentación; dos columnas donde ayuden y una para textos largos. Errores junto al campo y resumen comprensible cuando corresponda. Mantener dependencias cliente/circuito y creación rápida actual; no introducir pasos obligatorios o validaciones nuevas. |
| Modales | Un vocabulario coherente para títulos, cuerpo y pie de acciones. Mantener diálogos nativos, Escape según reglas existentes, bloqueo al guardar, restauración de foco y datos sin guardar. Revisar ancho/altura y visibilidad de selectores; no transformar operaciones en otros flujos sin autorización. |
| Circuitos y FMS | Separar visualmente información actual y snapshots históricos. Notas de activación con lectura multilínea, sin apariencia de campo editable. Mantener el botón/estado de correo existente y las advertencias de resultado incierto. |
| Control de cambios | Aplicar el sistema a calendario, listado, detalle y participantes; conservar fechas, estados, vínculos, evaluación y acciones autorizadas. El Operador continúa sin mutaciones. |
| Reportería | Títulos sencillos, colores consistentes y etiquetas/unidades claras. Reducir cápsulas y paneles oscuros repetidos. No cambiar consultas, bases temporales, fórmulas, series o exportaciones existentes. |
| Administración | Misma estructura de formularios/tablas. Mantener agrupación de los 147 permisos, facultades exclusivas y tres estados independientes de Responsables. No confundir sesión activa con historial de sesiones. |
| Correo y auditoría | Ordenar editor, previsualización y formularios administrativos con las mismas reglas. Conservar iframe aislado, contenido renderizado, estados y conservación de auditoría; sin cambiar SMTP, OAuth2 o limpieza. |

Las salidas de correo HTML/texto, PDF/XLSX y reportes generados conservan su diseño y contenido actuales. Rediseñar el contenedor web de una previsualización no autoriza alterar el documento previsualizado.

## 7. Densidad, contenido y adaptación

Para escritorio, priorizar anchura útil y comparación por filas. No sustituir tablas por tarjetas grandes ni agrandar todos los espacios. Una fila de una línea puede partir de 40–44 px; con dos líneas crecerá lo necesario. Los textos críticos no se cortan sin un modo accesible de leerlos: un tooltip de hover no basta.

Objetivo a contrastar en el piloto: en 1440×900, ver título, búsqueda/filtros principales y alrededor de diez filas de dos líneas sin dedicar la mayor parte de la pantalla a cabeceras. Es una meta de diseño, no una medición del producto actual o una garantía antes de renderizar.

- **1440–1920 px:** navegación visible; listas amplias y formularios con ancho de lectura limitado, sin estirar campos largos de extremo a extremo.
- **1280–1366 px:** reducir espacios y columnas de composición; admitir scroll contenido de tablas cuando los datos lo requieran. No reducir tipografía para forzar once columnas.
- **Tablets:** navegación desplegable y formularios adaptados al espacio disponible; ninguna acción depende del puntero.
- **Móvil, referencia de prueba 390 px:** navegación como panel, acciones esenciales visibles, filtros adicionales plegables y tablas con desplazamiento dentro de su contenedor. Conservar acceso al detalle y a todas las propiedades; evitar overflow de toda la página. No se propone una aplicación nativa.

Probar vacío, un registro, página de 50, nombres/códigos extensos, notas multilínea de hasta 10.000 caracteres, 147 permisos y catálogos con registros históricos. No fijar nuevas restricciones de datos por motivos de composición.

## 8. Estados, accesibilidad y reglas invariables

El diseño debe contemplar reposo, hover, foco, selección, deshabilitado, carga, vacío, error y éxito en cada control pertinente. Distinguir consulta vacía de error, permiso revocado de sesión vencida, y solicitud de correo de aceptación SMTP. Las cargas mantienen contexto y no muestran ceros que parezcan datos confirmados.

Validar teclado, orden de foco, etiquetas asociadas, encabezados semánticos, tablas con relaciones comprensibles, zoom al 200 %, contraste de todos los estados y uso sin percepción de color. Mantener movimiento reducido. Las acciones táctiles dispondrán de área suficiente aunque el icono sea pequeño; el encabezado fijo no ocultará foco o mensajes.

No cambiar autenticación, duración/cupo de sesiones, actualización de permisos, reglas backend, modelo de personas, selección operativa, numeración, snapshots, transacciones, filtros, mensajes técnicos de significado aprobado o reglas de notificación. El rediseño debe reutilizar los handlers y las capacidades reales, evitando inferir permisos por nombres de rol.

## 9. Estrategia incremental propuesta

Estos son **hitos visuales propuestos**, no una autorización para iniciar la fase 5 de v0.7.0 o publicar cambios. Cada implementación requiere aprobación y se valida antes de extenderse.

| Hito | Objetivo y archivos de referencia | Dependencia y salida verificable |
|---|---|---|
| V0 — Confirmar dirección | Aprobar este brief y una composición del piloto con datos de demostración identificados. | Validación visual en escritorio/portátil/móvil; todavía sin modificar contratos ni sustituir DESIGN.md por una especificación no construida. |
| V1 — Base compartida | Definir roles de color, tipografía, radios, espacios y estados; revisar `styles.css`, FormField, botones, badges y RequestState. | Depende de V0; comprobar controles en todos sus estados antes de propagarlos. No introducir dependencias por comodidad. |
| V2 — Marco de aplicación | Layout, UserControls, moduleIdentity y PageHeading; adaptar únicamente la presentación de estados de AuthGate. | Depende de V1; navegación de los cuatro roles y personalizado, Mi perfil, 401/403, foco, expiración y responsive conservados. |
| V3 — Piloto Tickets | Tickets, TicketTable, TicketFilters, TicketDetail, TicketForm, PaginationBar y diálogos relacionados. | Depende de V1/V2; comparar listado/detalle/crear/editar, filtros, exportaciones y acciones autorizadas con el flujo anterior. Aprobación visual antes de continuar. |
| V4 — Operación y análisis | Extender a internos, clientes/circuitos, FMS, CAM, Dashboard y reportería mediante componentes compartidos. | Depende de V3; ninguna propiedad perdida, consulta nueva o cálculo alterado. Validar calendario, históricos y lectura de notas. |
| V5 — Administración | Responsables, roles, perfil/sesiones, auditoría, correo, catálogos y numeraciones. | Depende de V3 y componentes estabilizados; formularios sensibles, permisos, iframe y contratos intactos. Puede prepararse por separado, evitando cambios simultáneos en primitives comunes. |
| V6 — Cierre visual y regresión | Revisar todas las superficies, retirar excepciones temporales, documentar el sistema realmente implementado en DESIGN.md. | Depende de V4/V5; suites completas, TypeScript, accesibilidad, capturas comparables y aprobación del propietario. No equivale a autorizar build, release o despliegue. |

Evitar un reemplazo global de CSS antes del piloto. Aislar temporalmente las variaciones necesarias y retirarlas al consolidar el sistema, sin mantener dos sistemas visuales permanentes o crear preferencias en PostgreSQL. Los cambios compartidos deben tener un único responsable de edición por hito para reducir conflictos.

En cada hito futuro: pruebas dirigidas de componentes/páginas y TypeScript; capturas de escritorio y móvil con datos controlados; comprobación de acciones permitidas/prohibidas y estados vacíos/error/carga. Al cierre: suites completas frontend/backend según integración, más `git diff --check`; pruebas de escritura solo sobre PostgreSQL efímero. No enviar correos reales para validar presentación.

## 10. Riesgos y mitigación

| Riesgo | Mitigación propuesta |
|---|---|
| Cambios globales de CSS afectan módulos no revisados. | Migrar primitives y piloto primero; revisar capturas y estados de cada módulo antes de extender. |
| Ganar anchura ocultando información o reduciendo legibilidad. | Agrupar datos relacionados con etiquetas claras; mantener propiedades accesibles, tamaño legible y scroll contenido cuando haga falta. |
| Nueva navegación oculta enlaces autorizados o expone otros. | Mantener rutas y vocabulario de permisos; probar visibilidad con perfiles y roles personalizados, además del backend existente. |
| Mover formularios desmonta estado y pierde borradores o cambia el submit. | Reutilizar handlers, claves y límites de montaje existentes; probar expiración, cancelación y doble clic. |
| Sidebar, sticky headers y overlays crean clipping o trampas de foco. | Probar teclado, zoom, selectores dentro de diálogos, tamaños reducidos y retorno de foco. |
| Colores de marca sustituyen significado operativo. | Separar selección, acción y semántica de estado; etiquetas textuales y contraste comprobado. |
| La propuesta se interprete como nuevas funciones. | No buscador global, alarmas, SLA, monitorización, métricas o permisos nuevos; solo presentación de capacidades existentes. |
| Un rediseño amplio diluya Electric Blue/Capsule NOC. | Aprobar el piloto y comprobar identidad en una pantalla de datos, otra de formulario y otra administrativa. |

## 11. Aprobación y continuidad

**Confirmado:** identidad Electric Blue/cápsulas/NOC, libertad sobre composición, prioridades operativas, escritorio principal 1440–1920 y piloto Tickets.

**Por aprobar en esta propuesta:** dirección «orientación de servicio» o alternativa, tratamiento del marco/menú, retirada de numeración ornamental, papel de las cápsulas, jerarquía de tabla y el orden de hitos. Los valores tipográficos/cromáticos son puntos de partida para validar, no decisiones ya adoptadas.

**No decidido aquí:** composición final medida, pruebas visuales en navegador y sistema definitivo de tokens. No son dudas de negocio: corresponden al prototipo y a su validación posterior. No se plantea agregar modo oscuro o un selector de densidad como funcionalidades nuevas.

Esta tarea solo produce el brief y actualiza el handoff. No modifica PRODUCT, AGENTS, código, estilos, rutas, pruebas, base de datos o activos visuales existentes; no inicia migraciones, builds, servicios, commits o despliegues. El helper conceptual de Impeccable generó registros locales de exploración bajo `.impeccable/questions/`; no son código de Ticketyn ni una decisión aprobada.

**Siguiente paso:** revisión del propietario y autorización explícita del siguiente hito visual. Detenerse; no implementar ni iniciar publicación o trabajos de fase 5 por inferencia de este documento.
