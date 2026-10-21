---
name: Ticketyn — Industrial NOC Rounded
description: Sistema visual existente Electric Blue 2.0 y Capsule NOC, extraído del frontend actual.
colors:
  primary: "#1e60d8"
  primary-hover: "#164bb0"
  primary-soft: "#172a50"
  primary-border: "#254b8c"
  background: "#091122"
  surface: "#0d172e"
  operational-surface: "#0b1426"
  operational-heading: "#070d1a"
  sidebar: "#070c18"
  header: "#091120"
  border: "#1e2c4a"
  text-primary: "#f8fafc"
  text-secondary: "#94a3b8"
  module-blue: "#38bdf8"
  module-cyan: "#06b6d4"
  module-purple: "#c084fc"
  module-amber: "#fbbf24"
  module-emerald: "#34d399"
  success: "#10b981"
  warning: "#f59e0b"
  error: "#ef4444"
typography:
  display:
    fontFamily: 'Oxanium, "Segoe UI", system-ui, sans-serif'
  title:
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    fontSize: "1.625rem"
    fontWeight: 700
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Segoe UI", system-ui, sans-serif'
  label:
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    fontSize: "0.75rem"
    fontWeight: 700
rounded:
  card: "12px"
  control: "13px"
  capsule: "9999px"
spacing:
  compact: "8px"
  control: "12px"
  panel: "16px"
  workspace: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.capsule}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "#cbd5e1"
    rounded: "{rounded.capsule}"
    padding: "8px 14px"
  input:
    backgroundColor: "{colors.operational-heading}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.card}"
---

# Design System: Ticketyn

## Overview

**Creative North Star: "Industrial NOC Rounded"**

Registro descriptivo del frontend existente el 21/10/2026, contrastado con el handoff de Antigravity, `frontend/src/styles.css`, Layout, PageHeading, Tickets y el branding público. No es la propuesta clara inicial ni una autorización para sustituir el diseño construido. PRODUCT conserva las reglas de producto; este archivo registra su expresión visual actual.

La interfaz utiliza superficies oscuras azuladas, bordes sutiles, cápsulas y acentos técnicos por módulo. El azul eléctrico articula acciones y selección; el cian y los acentos de cada dominio conviven con una tipografía de datos compacta. Los estados y las acciones mantienen etiquetas legibles y permisos reales.

**Key Characteristics:**

- Superficies NOC oscuras y contraste de texto claro.
- Botones, navegación seleccionada y badges en cápsula.
- Encabezados compactos, emblemas numerados y tipografía técnica.
- Identidad de módulo diferenciada de la semántica de éxito/error.
- Branding oficial existente, sin iconos o logotipos sustitutivos.

## Colors

El frontmatter enumera valores extraídos, no una paleta nueva. Los nombres corresponden a roles del CSS o a los acentos ya utilizados por módulo.

### Primary

Azul eléctrico para botones primarios, navegación activa, foco y controles seleccionados. Se conservan sus variantes de hover, fondo tenue y borde.

### Secondary

Cian para Dashboard; azul claro para clientes/circuitos/tickets; morado para internos; ámbar para Control de cambios; esmeralda para FMS. Administración utiliza pizarra. Son identidades de dominio; no equivalen por sí mismas a severidad, permiso o estado.

### Neutral

Fondo, sidebar y consolas se distinguen mediante tonos oscuros, bordes y niveles de superficie. Texto principal claro y texto secundario pizarra; no volver a superficies claras por referencia a una propuesta antigua.

## Typography

Oxanium se carga localmente para display, emblemas y determinadas métricas. El cuerpo utiliza Segoe UI/system-ui; correlativos, encabezados técnicos y etiquetas utilizan la pila monoespaciada disponible. Algunas reglas nombran JetBrains Mono; eso no demuestra que esté instalada o cargada en todos los equipos.

El título de PageHeading tiene una regla específica monoespaciada; no asumir que todos los títulos heredan Oxanium. Conservar tamaños y jerarquías del componente elegido al generar variantes, salvo petición explícita de modificarlos. Los valores de la escala de datos son densos: no se declara accesibilidad validada solo por esta extracción.

## Layout

Aplicación web con header sticky de 56 px y sidebar visible desde el breakpoint md; su ancho cambia de 224 a 240 px. El área de trabajo usa espaciado de 16/24 px. El menú móvil se despliega con controles existentes; la visibilidad de rutas depende de permisos efectivos.

Listados con filtros, acciones, tabla y paginación; fichas operativas con grupos de lectura y bitácora. Se mantienen scrolls contenidos cuando una tabla necesita anchura. Los diálogos y selectores conservan comportamiento y foco. No convertir una variante visual en nuevos pasos, navegación, datos o consultas.

## Elevation & Depth

Capas por tono, borde y sombra oscura. Las superficies compartidas usan la sombra de tarjeta; overlays utilizan la elevada. Algunos acentos y el isotipo tienen un resplandor localizado. Conservar esos tratamientos según el componente, sin extender el glow a todas las superficies.

Las transiciones de controles existentes están aproximadamente entre 140 y 250 ms. Hay una animación orbital del login; las variantes respetan el comportamiento de movimiento reducido disponible y no añaden animaciones ajenas a la petición.

## Shapes

Tarjetas con radio moderado, campos redondeados y acciones/badges en cápsula. El header, sidebar y emblemas actuales sustituyen geometrías de etapas anteriores. No reintroducir curvas o fondos antiguos por documentos históricos.

## Components

### Buttons

Acción principal sólida azul y secundaria oscura con borde; cápsulas, icono breve y texto. Las variantes por módulo conservan su acento. El login utiliza el degradado eléctrico-cian existente. Mantener carga, deshabilitado, foco y protección de doble clic, sin alterar handlers.

### Chips

Píldoras compactas para identidad, filtros y estados. Diferenciar el acento del módulo de la semántica del registro. Abierto/cerrado o fallido/aceptado conservan sus textos y significado; no sustituirlos por un LED sin etiqueta.

### Cards / Containers

Consolas oscuras con borde y radios moderados; métricas independientes y superficies `noc-*` del módulo. La tonalidad y los colores de las métricas provienen del componente actual, no de datos inventados.

### Inputs / Fields

Fondo oscuro, borde tenue y foco azul. Conservar etiquetas, errores, autocompletado y validaciones; selectores usan esquema oscuro. Los menús deben seguir siendo utilizables dentro de diálogos y contenedores con scroll.

### Navigation

Enlaces con icono y texto, selección en cápsula, grupos y controles responsive existentes. No mostrar rutas o acciones sin permiso. El isotipo oficial de la cápsula de marca proviene de `/branding/isotipo_oscuro.svg`; el login utiliza los recursos oficiales existentes. No cambiar branding por ilustraciones nuevas.

### PageHeading

Emblema, etiqueta de módulo, título, contexto/telemetría disponible y acciones. Su color sigue al dominio. La telemetría que muestra una página no se convierte mediante diseño en estadísticas globales nuevas.

## Do's and Don'ts

### Do:

- **Do** conservar la identidad oscura Industrial NOC Rounded construida por Antigravity.
- **Do** extraer los valores y el estado real del elemento seleccionado antes de variar su composición.
- **Do** reutilizar cápsulas, acentos y recursos oficiales existentes.
- **Do** mantener información, interacciones, permisos, foco y estados de carga/error.

### Don't:

- **Don't** tratar la propuesta conceptual anterior como diseño implementado.
- **Don't** introducir otra paleta, fuentes remotas o un logo nuevo sin petición explícita.
- **Don't** cambiar lógica de negocio, autenticación o datos para hacer encajar una variante.
- **Don't** afirmar validación visual o accesibilidad basándose solo en este inventario estático.
