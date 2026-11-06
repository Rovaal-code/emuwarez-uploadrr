---
name: eMuwarez Uploadrr
description: Consola nocturna para subir la biblioteca del NAS a eMuwarez
colors:
  base-night: "#0a0d14"
  surface-night: "#0f1420"
  sidebar-night: "#080b11"
  panel-solid: "#060e1c"
  hud-fill: "rgba(3, 17, 39, .82)"
  hud-line: "rgba(30, 110, 190, .42)"
  signal-cyan: "#2fd8ff"
  sky-link: "#38bdff"
  ice-text: "#a9ecff"
  azure: "#1c7dff"
  hud-blue: "#1e6ebe"
  action-blue: "#2563eb"
  text-primary: "#e5e7eb"
  text-secondary: "#9ca3af"
  text-muted: "#848c9b"
  ok-green: "#28e394"
  warn-amber: "#ffb930"
  danger-rose: "#ff5470"
  available: "#22c55e"
  missing: "#ef4444"
  uploading: "#a855f7"
  pending: "#f59e0b"
typography:
  page-title:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    letterSpacing: "0.1em"
  section-title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
  stat-value:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 700
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
  nav:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 500
    letterSpacing: "0.03em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "12px"
rounded:
  card: "12px"
  small: "7px"
  control: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.azure}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  button-secondary:
    backgroundColor: "{colors.panel-solid}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  button-small:
    rounded: "{rounded.control}"
    padding: "4px 10px"
  card:
    backgroundColor: "{colors.hud-fill}"
    rounded: "{rounded.card}"
  input:
    backgroundColor: "{colors.panel-solid}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
  badge:
    rounded: "{rounded.control}"
    padding: "2px 8px"
  nav-item-active:
    textColor: "{colors.ice-text}"
    rounded: "{rounded.small}"
---

# Design System: eMuwarez Uploadrr

## Overview

**Creative North Star: "La sala de control"**

Una consola nocturna: todo el estado de la biblioteca, las peticiones y las subidas a la vista, sobre un fondo casi negro
con paneles de vidrio azul oscuro. El cian es la señal: marca lo vivo (la sección activa, el foco, la acción principal, una
barra de progreso) y lo que pide actuar. Es una herramienta de trabajo (modo Operate): manda la lectura rápida de tablas y
cifras, no la expresión.

La densidad es flexible: algo compacta (texto base de 13 px, tablas de 12-13 px, botones de 7×14 px), pero se da aire cuando
mejora la lectura; no hay regla fija. Las esquinas son redondeadas y firmes en todo: la esquina cortada, demasiado
contrastada, se descartó. La tipografía es una sola familia, Inter, con JetBrains Mono para nombres de torrent, rutas y logs.

Este sistema se evoluciona, no se sustituye: nada de un estilo nuevo, ni otra tipografía, ni un segundo acento.

**Key Characteristics:**
- Fondo casi negro con dos halos radiales cian/azur muy tenues en las esquinas superiores.
- Paneles de vidrio azul oscuro con borde azul fino y un filo interior claro.
- Un solo acento, el cian; verde, ámbar y rosa solo para estados.
- Rótulos de página y de navegación en mayúsculas con tracking abierto.
- Esquinas redondeadas en todo, de 6 a 12 px.

## Colors

Noche azulada con un acento cian eléctrico y una paleta de estados saturada que solo aparece en chapas, barras y avisos.

### Primary
- **Cian de señal** (`signal-cyan`): foco (`--color-focus`), sección activa del menú, barras de progreso, el borde del botón
  principal y los puntos de «no leído». Es lo que brilla.
- **Celeste de enlace** (`sky-link`): enlaces y acentos de texto dentro de la aplicación (`--text-accent` bajo `.hud-app`).
- **Azur** (`azure`) y **Azul de acción** (`action-blue`): el relleno del botón principal (degradado cian→azur en el HUD; el
  azul plano fuera de él, en Login y el asistente de primera configuración).

### Neutral
- **Noche base** (`base-night`): fondo de la página, también `theme-color`.
- **Superficie** (`surface-night`) y **Panel opaco** (`panel-solid`): fondos sólidos de modales, campana, paleta y celdas fijas
  de tabla que no pueden transparentar.
- **Vidrio HUD** (`hud-fill`): relleno de tarjetas y paneles, sobre el que va el borde **Línea HUD** (`hud-line`).
- **Hielo** (`ice-text`): títulos de sección, valores destacados y texto de la navegación activa.
- **Texto** principal, secundario y atenuado (`text-primary`, `text-secondary`, `text-muted`): el atenuado es el mínimo para
  texto que se lee (AA sobre la noche base).

### Estados
- **Disponible / Compatible** (`available`), **Faltante / Error** (`missing`), **Subiendo** (`uploading`), **Pendiente /
  Parcial** (`pending`), con sus variantes `-soft` y `-pale` en `globals.css`. En el HUD, `ok-green`, `warn-amber` y
  `danger-rose` para avisos y la banda «Necesita atención».

### Named Rules
**La regla de la única señal.** El cian solo marca lo vivo o lo accionable; no decora. Si todo brilla, nada avisa.

**La regla del estado con nombre.** Un color de estado siempre va con su texto (chapa, etiqueta o `title`): nunca el color solo.

## Typography

**Display Font:** Inter (con system-ui)
**Body Font:** Inter (con system-ui)
**Label/Mono Font:** JetBrains Mono (con ui-monospace) para nombres de torrent, rutas, hashes y logs.

**Character:** una sola sans neutra y legible a tamaños pequeños; la jerarquía la dan el peso, el tamaño, las mayúsculas con
tracking y el color hielo, no otra familia.

### Hierarchy
- **Título de página** (700, 18 px, mayúsculas, tracking .1em): el `h1` de cada sección.
- **Título de sección** (600, 14 px, hielo): cabecera de cada panel, subrayada con una línea degradada.
- **Cifra** (700, 22 px): valores de las tarjetas de estadísticas, con cifras tabulares.
- **Cuerpo** (400, 13 px, interlineado 1.5): texto general, celdas de tabla.
- **Etiqueta** (600, 11-12 px): cabeceras de tabla, chapas, campos de formulario.
- **Navegación** (500, 12.5 px, mayúsculas, tracking .03em): menú lateral.

### Named Rules
**La regla de una familia.** Inter se queda; no se añade una tipografía de display. La mono solo para datos que se copian.

**La regla de las cifras alineadas.** Números en tablas, medidas y contadores con `font-variant-numeric: tabular-nums`.

## Layout

Barra lateral fija de 240 px (plegable) y barra superior de 56 px; el contenido va en `.page-container`, que es el único
scroll de la página (alturas con `--vh100`, nunca `100vh`, porque la interfaz admite escala con `--ui-scale`). Escritorio
manda: las pantallas se diseñan para 1280-1440 px y se adaptan hacia abajo. A ≤768 px la barra lateral pasa a cajón con
hamburguesa y la cuenta baja a su pie; con puntero táctil los objetivos miden `--tap-min` (44 px compensados por la escala)
y los campos 16 px. Las tablas anchas llevan su propio scroll horizontal; en móvil se quedan con las columnas esenciales.
Ritmo de espacios en múltiplos de 4 (4, 8, 12, 16, 24 px).

## Elevation & Depth

Capas tonales: un panel se separa del fondo por su tono (vidrio azul oscuro sobre noche casi negra) y su borde azul fino con
un filo interior claro (`inset 0 0 0 1px` de `--hud-line-inner`). La sombra negra difusa bajo tarjetas y modales es
secundaria (sobre un fondo tan oscuro apenas se ve). Los elementos flotantes (modales, campana, paleta Ctrl+K) llevan
fondo opaco (`panel-solid`) bajo el degradado, para que no se transparente la página.

### Shadow Vocabulary
- **Panel** (`inset 0 0 0 1px var(--hud-line-inner), 0 14px 30px -16px` negro al 70 %): tarjetas y modales.
- **Halo de señal** (`0 0 12px -4px` cian al 70 %): botón principal, sección activa, botones de la barra superior al pasar.

### Named Rules
**La regla del brillo en lo vivo.** El brillo cian (`box-shadow` o `text-shadow` de color) es para lo activo, lo enfocado, la
acción principal y el progreso. Los títulos y las cifras estáticas no brillan: hoy algunos lo hacen (`.page-title`,
`.section-title`, `.stat-card-value`) y en trabajo futuro se les va quitando, sin cambiar el resto del tema.

## Shapes

Esquinas redondeadas firmes en todo: 12 px en tarjetas, paneles y modales (`--radius-card`), 7 px en elementos de navegación
y bloques pequeños (`--radius-small`), 6 px en botones, campos y chapas. Los carriles pegados al borde de la ventana (barra
lateral) no llevan esquinas. Bordes de 1 px; el acento lateral de 2 px solo en la sección activa del menú.

### Named Rules
**La regla de la esquina redonda.** Nada de esquinas cortadas ni rectas en tarjetas o controles.

## Components

### Buttons
- **Shape:** 6 px (`--radius-button`), 7×14 px de relleno, 13 px; `.btn-sm` 4×10 px y 12 px; `.btn-icon` 32 px.
- **Primary:** degradado cian→azur translúcido con borde cian y halo de señal; un solo botón principal por vista o diálogo.
- **Secondary:** vidrio oscuro con borde azul al 50 %; al pasar, borde cian y halo suave.
- **Ghost:** sin borde, texto hielo; al pasar toma el fondo del secundario.
- **Danger:** rojo al 12 % con borde al 25 %.
- **Hover / Focus:** transición corta de borde y halo; `:active` baja 1 px; anillo de foco cian (`--color-focus`).

### Chips
- **Style:** chapa de 6 px, 2×8 px, 11 px y 600, fondo del color de estado al ~15 % y texto en su variante clara.

### Cards / Containers
- **Corner Style:** 12 px.
- **Background:** vidrio HUD en degradado (`hud-fill` → `hud-fill-2`) con un halo cian de esquina muy tenue.
- **Shadow Strategy:** «Panel» (ver Elevation).
- **Border:** 1 px `hud-line`.
- **Internal Padding:** 14-18 px; cabecera de sección `14px 18px 0`.

### Inputs / Fields
- **Style:** pozo oscuro (`--hud-well` al 70 %), borde azul al 45 %, 6 px; etiqueta con `<label for>`.
- **Focus:** borde cian y anillo `--color-focus`.
- **Error / Disabled:** el error se dice en el propio campo; deshabilitado al 45 % de opacidad.

### Navigation
- **Style:** menú lateral en mayúsculas de 12.5 px; al pasar, fondo cian al 6 % y texto hielo; la sección activa lleva
  degradado cian, borde izquierdo de 2 px y su icono con brillo. En móvil, cajón con la cuenta al pie.

### Tablas de datos
- Cabeceras de 12 px y 600 en texto atenuado; filas separadas por una línea celeste al 9 % y resaltadas con cian al 6 % al pasar.
  Las columnas fijas llevan fondo opaco. Filtros en la cabecera de cada columna.

## Do's and Don'ts

### Do:
- **Do** usar los tokens de `styles/globals.css` y `styles/hud-theme.css` y las clases existentes; nada de estilos en línea nuevos
  salvo valores calculados.
- **Do** reservar el cian para lo vivo y lo accionable (La regla de la única señal).
- **Do** dar a cada color de estado su texto.
- **Do** usar `components/Modal.tsx` para todo diálogo, con fondo opaco.
- **Do** diseñar para 1280-1440 px y comprobar 390 px; en táctil, objetivos de `--tap-min`.

### Don't:
- **Don't** cambiar de tipografía ni añadir una de display: Inter se queda.
- **Don't** introducir un estilo nuevo, un segundo acento o una paleta distinta: el HUD oscuro azul/cian se evoluciona.
- **Don't** usar esquinas cortadas o rectas en tarjetas y controles.
- **Don't** añadir brillo a títulos, cifras o decoración estática.
- **Don't** usar `window.confirm`, `100vh` ni nada que dependa solo del hover.
