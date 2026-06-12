# NexusChain — Guía de estilo visual (Design Style)

Documento de referencia para homologar otras aplicaciones con el look & feel de **NexusChain** (plataforma de pronóstico y cadena de suministro).

**Fuente de verdad en código:** `web/tailwind.config.ts`, `web/app/globals.css`, `web/components/`.

---

## 1. Identidad y tono visual

| Atributo | Valor |
|----------|-------|
| **Marca** | NexusChain |
| **Dominio** | SaaS B2B — pronóstico, inventario, cadena de suministro |
| **Estilo general** | Profesional, denso en datos, inspirado en tableros analíticos (BI) |
| **Densidad** | Alta en tablas y widgets; espaciado generoso en login y formularios |
| **Esquinas** | `rounded-md` (8px) en tarjetas/tablas; `rounded-lg` (12px) en inputs y botones; `rounded-2xl` en modales |
| **Sombras** | Suaves (`shadow-sm` en paneles, `shadow-xl` / `shadow-2xl` en login y modales) |
| **Idioma UI** | Español (México) — `lang="es-MX"`, formato numérico `es-MX` |

---

## 2. Stack de diseño

| Herramienta | Uso |
|-------------|-----|
| **Tailwind CSS 3.4** | Sistema de utilidades y tokens de color/tipografía |
| **Lucide React** | Iconografía lineal, trazo fino, tamaño habitual `h-4 w-4` |
| **clsx + tailwind-merge** | Composición de clases (`cn()` en `web/lib/utils.ts`) |
| **Google Fonts (Next.js)** | Inter, Hanken Grotesk, JetBrains Mono |
| **Dark mode** | `prefers-color-scheme: media` — sin toggle manual |

No hay librería de componentes externa (shadcn, MUI, etc.): los patrones viven en componentes propios bajo `web/components/ui/` y `web/components/data-grid/`.

---

## 3. Paleta de colores

### 3.1 Colores de marca (acción principal)

Usados en login, CTAs y estados activos del shell.

| Token Tailwind | Hex | Uso |
|----------------|-----|-----|
| `primary` | `#0036b9` | Botón principal login, focus ring login, logo icon background |
| `primary.hover` | `#0a3d61` | Hover del botón principal login |
| `brand-500` | `#3b82f6` | Enlaces, ítem activo sidebar, acentos UI |
| `brand-600` | `#2563eb` | Botón primario (`Button` variant primary) |
| `brand-700` | `#1d4ed8` | Hover botón primario, focus inputs, código en tablas, wizard activo |
| `brand-50` / `brand-100` | `#eff6ff` / `#dbeafe` | Fondos de ítem activo, iconos de página |

### 3.2 Superficies y fondos (app autenticada)

El shell principal (`DashboardShell`) usa la escala **slate** de Tailwind más que los tokens Material-like del config.

| Contexto | Light | Dark |
|----------|-------|------|
| Fondo app | `#f1f5f9` (`bg-[#f1f5f9]`) | `#0f172a` (`dark:bg-[#0f172a]`) |
| Sidebar / toolbar | `white` | `slate-800` |
| Header superior | `#0f172a` (slate-900) | igual |
| Borde estructural | `#e2e8f0` | `#334155` |
| Texto principal | `slate-800` / `slate-900` | `slate-100` / `slate-200` |
| Texto secundario | `slate-500` / `slate-600` | `slate-400` |

### 3.3 Superficies (login y tokens semánticos)

| Token | Hex | Uso |
|-------|-----|-----|
| `background-light` | `#f3f4f6` | Fondo login (light) |
| `background-dark` | `#111827` | Fondo login (dark) |
| `surface-light` | `#ffffff` | Panel formulario login |
| `surface-dark` | `#1f2937` | Panel formulario login (dark) |
| `background` / `surface` | `#f7f9fb` | Tokens Material Design 3 (disponibles, poco usados en shell) |

### 3.4 Semánticos (estado y feedback)

| Estado | Colores típicos |
|--------|-----------------|
| **Éxito / activo** | `green-50` fondo, `green-700` texto, `green-200` borde |
| **Error** | `red-600` texto/botón, `red-50` fondo alerta, `error` `#ba1a1a` |
| **Advertencia / pendiente** | `yellow-50`, `yellow-700` |
| **Info / procesando** | `blue-50`, `blue-700` |
| **Validación** | `purple-50`, `purple-700` |
| **Subido** | `indigo-50`, `indigo-700` |
| **Tendencia negativa (KPI)** | `red-500` |
| **Tendencia positiva / disponibilidad** | `emerald-400` |

### 3.5 Gráficos y series de datos

| Serie | Color | Hex aprox. |
|-------|-------|------------|
| Ventas históricas | emerald | `#34d399` |
| Pronóstico | yellow | `#facc15` |
| Línea "Ahora" | slate dashed | `border-slate-400` |
| Grid del gráfico | slate 20% opacidad | `bg-slate-300` |

### 3.6 Acentos por widget (indicador cuadrado 12×12 px)

Cada tarjeta de dashboard lleva un cuadrado de color en el encabezado:

| Widget | Clase |
|--------|-------|
| Categorías | `bg-emerald-500` |
| Familias | `bg-blue-500` |
| Catálogo SKUs | `bg-violet-500` |
| Propuestas de pedido | `bg-red-400` |
| Merma (KPI) | `bg-orange-300` |
| Disponibilidad (KPI) | `bg-yellow-300` |
| Detalle producto | `bg-emerald-600` |

### 3.7 Tokens Material Design 3 (extendidos)

Definidos en `tailwind.config.ts` para futura expansión o login. Incluyen `on-surface`, `surface-container-*`, `tertiary` (`#006242`), `outline` (`#737686`), etc. Priorizar **brand + slate** para nuevas pantallas del shell.

---

## 4. Tipografía

### 4.1 Familias

| Rol | Fuente | Variable CSS | Clase Tailwind |
|-----|--------|--------------|----------------|
| Display / títulos de sección | Hanken Grotesk | `--font-hanken` | `font-display-sm`, `font-headline-md` |
| Cuerpo / labels | Inter | `--font-inter` | `font-body-sm`, `font-body-md`, `font-label-xs` |
| Códigos / datos tabulares | JetBrains Mono | `--font-jetbrains` | `font-data-mono` |

Carga en `web/app/layout.tsx` vía `next/font/google` con `display: swap`.

### 4.2 Escala tipográfica (tokens Tailwind)

| Token | Tamaño | Line-height | Peso | Tracking |
|-------|--------|-------------|------|----------|
| `text-display-sm` | 24px | 32px | 600 | -0.02em |
| `text-headline-md` | 18px | 24px | 600 | — |
| `text-body-md` | 14px | 20px | 400 | — |
| `text-body-sm` | 12px | 16px | 400 | — |
| `text-label-xs` | 11px | 12px | 600 | — |
| `text-data-mono` | 12px | 16px | 500 | -0.01em |

### 4.3 Uso en pantalla

| Elemento | Clases habituales |
|----------|-------------------|
| Título de página (CRUD) | `text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100` |
| Subtítulo / descripción | `text-sm text-slate-500 dark:text-slate-400` |
| Título login | `text-3xl font-bold tracking-tight` |
| Encabezado widget/tabla | `text-sm font-semibold text-slate-800` |
| Labels de formulario | `text-sm font-medium text-gray-700 dark:text-gray-300` |
| Sección sidebar | `text-[10px] font-semibold uppercase tracking-wider text-slate-400` |
| KPI grande | `text-5xl font-light` o `text-3xl font-bold` |
| Celdas de tabla | `text-xs` |
| Código en tabla | `font-data-mono font-medium text-[#1d4ed8]` |

---

## 5. Espaciado y layout

### 5.1 Grid del dashboard

- Contenedor: `grid grid-cols-12 gap-4`
- Widgets ocupan columnas variables (`col-span-12`, `lg:col-span-3`, etc.)
- Altura fija de columna KPI: `h-[400px]`

### 5.2 Padding de contenido

| Zona | Padding |
|------|---------|
| Main (páginas CRUD) | `p-8` |
| Main (home dashboard) | `p-4` |
| Login formulario | `p-8 lg:p-16` |
| Widget / tabla interna | `p-2` (header), `p-4` (cuerpo KPI) |

### 5.3 Shell autenticado

```
┌─────────────┬──────────────────────────────────────┐
│  Sidebar    │  Header (#0f172a, h-12)            │
│  w-52       ├──────────────────────────────────────┤
│  white/     │  Toolbar + FilterBar (solo /dashboard)│
│  slate-800  ├──────────────────────────────────────┤
│             │  Main (scroll, flex-1)               │
└─────────────┴──────────────────────────────────────┘
```

- App: `flex h-screen overflow-hidden`
- Sidebar: `w-52`, borde derecho `#e2e8f0`, `shadow-sm`
- Ítem nav activo: `bg-blue-50 text-[#3b82f6]` (dark: `bg-blue-950/40 text-blue-400`)
- Ítem nav inactivo: `text-slate-600 hover:bg-slate-100`

### 5.4 Login (split screen)

- Desktop: 50% formulario + 50% hero con carrusel
- Formulario: `max-w-md`, centrado vertical
- Hero: overlay `bg-primary/35` + gradiente `from-primary/80`
- Logo: icono `40×40` en `bg-primary rounded-lg` + wordmark `text-xl font-bold tracking-tight`

---

## 6. Componentes UI

### 6.1 Botón (`Button.tsx`)

```tsx
// Base
"inline-flex items-center justify-center gap-1.5 font-medium rounded-lg transition-colors disabled:opacity-50"

// Tamaños
sm: "text-xs px-2.5 py-1.5"
md: "text-sm px-3.5 py-2"  // default

// Variantes
primary:   "bg-brand-600 text-white hover:bg-brand-700"
secondary: "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50"
danger:    "bg-red-600 text-white hover:bg-red-700"
```

Login usa variante custom más prominente: `bg-primary hover:bg-primary-hover shadow-lg hover:shadow-xl w-full py-2.5`.

### 6.2 Inputs y selects (`FormField.tsx`)

```tsx
// Label
"text-sm font-medium text-gray-700"

// Input / Select
"w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent
 disabled:bg-gray-50"

// Error
"text-xs text-red-600"
```

Login añade: icono izquierdo (`pl-10`), `py-2.5`, `focus:ring-primary`, dark `bg-gray-800 border-gray-600`.

Filtros de tabla (compactos): `text-[11px]`, `px-1.5 py-1`, focus `ring-1 ring-[#1d4ed8]`.

### 6.3 Modal (`Modal.tsx`)

- Overlay: `bg-black/40`
- Panel: `bg-white rounded-2xl shadow-xl max-w-lg p-6`
- Título: `text-base font-semibold text-gray-900`
- Cerrar: icono X, `text-gray-400 hover:bg-gray-100 rounded-lg`

### 6.4 Badge de estado (`Badge.tsx`)

```tsx
"inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium"
```

Mapeo semántico por valor (`active`, `failed`, `pending`, etc.) con fondos `-50`, textos `-700`, bordes `-200`.

### 6.5 Chip / pill (tablas)

```tsx
"rounded-full bg-slate-100 px-1.5 py-0 text-[10px] font-medium text-slate-600"
```

### 6.6 Filter chip (dashboard)

```tsx
"rounded border border-slate-200 bg-slate-100 py-0.5 pl-2 pr-1 text-xs font-medium text-slate-700"
```

### 6.7 Wizard stepper

- Círculo: `h-9 w-9 rounded-full`
- Activo/completado: `bg-[#1d4ed8] text-white` + ring `ring-4 ring-blue-100`
- Pendiente: `bg-slate-200 text-slate-500`
- Conector: `h-0.5 w-16` (responsive hasta `w-32`)
- Label: `text-[10px] font-bold uppercase tracking-wider`

### 6.8 Tarjeta contenedora (WidgetCard / DataTable)

```tsx
"flex flex-col overflow-hidden rounded-md border border-[#e2e8f0] bg-white shadow-sm
 dark:border-[#334155] dark:bg-slate-800"
```

Encabezado: borde inferior, `p-2`, indicador de color `h-3 w-3 rounded-sm`.

---

## 7. Tablas de datos (`DataTable`)

Patrón central de las pantallas CRUD (SKUs, ubicaciones, canales, etc.).

| Aspecto | Especificación |
|---------|----------------|
| Tipografía celdas | `text-xs` |
| Header | `sticky top-0`, `bg-slate-50 font-semibold text-slate-500` |
| Filas | `hover:bg-slate-50`, selección `bg-slate-100` |
| Bordes celda | `border-r border-slate-100` (columnas), `divide-y divide-[#e2e8f0]` |
| Checkbox | `text-[#1d4ed8] focus:ring-[#1d4ed8]` |
| Loading | overlay `bg-white/70` + spinner `text-[#1d4ed8]` |
| Vacío | `text-slate-400`, em dash `—` en celdas nulas |
| Paginación | footer `text-xs text-slate-500`, botones `hover:bg-slate-100` |
| Altura default | `calc(100vh - 220px)` |

### Encabezado de página CRUD

```tsx
<div className="flex h-full flex-col gap-5">
  <div className="flex flex-wrap items-start justify-between gap-4">
    <div className="flex items-center gap-2">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-950/50">
        <Icon className="h-5 w-5 text-[#1d4ed8] dark:text-blue-300" />
      </span>
      <div>
        <h1 className="text-xl font-bold tracking-tight">Título</h1>
        <p className="text-sm text-slate-500">Descripción</p>
      </div>
    </div>
    <Button>Acción primaria</Button>
  </div>
  <DataTable ... />
</div>
```

### Acciones de fila

- Editar: `hover:bg-blue-50 hover:text-[#1d4ed8]`
- Eliminar: `hover:bg-red-50 hover:text-red-600`

---

## 8. Iconografía

- **Librería:** Lucide React (`lucide-react`)
- **Tamaños estándar:** `h-4 w-4` (nav, botones), `h-5 w-5` (header, page icon), `h-3 w-3` (indicadores compactos)
- **Color inactivo:** `text-slate-400` / `text-gray-400`
- **Color activo:** hereda del texto del ítem o `text-[#1d4ed8]`
- **Header oscuro:** iconos `text-slate-300 hover:text-white`
- **Filtros:** icono Filter en `text-green-600` (barra de filtros dashboard)

---

## 9. Movimiento y transiciones

| Contexto | Clase |
|----------|-------|
| Global login | `transition-colors duration-300` |
| Botones / links | `transition-colors` o `transition-all duration-200` |
| Hover sidebar/nav | `transition-colors` |
| Carrusel login | `transition-opacity duration-700 ease-in-out` |
| Indicadores carrusel | `transition-all duration-300` |
| FAB asistente | `hover:scale-105` |
| Wizard | `transition-colors` en círculos |

No hay animaciones llamativas; el movimiento es funcional y discreto.

---

## 10. Scrollbars personalizados

Definidos en `web/app/globals.css`:

| Propiedad | Light | Dark |
|-----------|-------|------|
| Ancho/alto | 8px | 8px |
| Track | transparente | transparente |
| Thumb | `#cbd5e1` | `#475569` |
| Thumb hover | `#94a3b8` | `#64748b` |
| Border-radius thumb | 4px | 4px |

Body global: `antialiased`.

---

## 11. Modo oscuro

- Activación: `@media (prefers-color-scheme: dark)` (`darkMode: "media"` en Tailwind)
- Patrón: cada superficie light tiene su par `dark:bg-slate-*`, `dark:text-slate-*`, `dark:border-[#334155]`
- No hay switch de tema en UI; respeta preferencia del SO

---

## 12. Patrones de feedback

### Alerta de error (formulario)

```tsx
"text-sm text-red-600 dark:text-red-400
 bg-red-50 dark:bg-red-950/40
 border border-red-200 dark:border-red-800
 rounded-lg px-3 py-2"
```

### Estado de carga

- Texto: `text-sm text-slate-400` — "Cargando…"
- Spinner: `Loader2 animate-spin text-[#1d4ed8]`

### Enlace de reintento

`text-[#3b82f6] hover:underline`

---

## 13. Checklist para homologar otra aplicación

### Tokens mínimos a replicar

```css
/* CSS custom properties sugeridas */
--color-primary: #0036b9;
--color-primary-hover: #0a3d61;
--color-accent: #2563eb;
--color-accent-hover: #1d4ed8;
--color-accent-light: #3b82f6;

--bg-app: #f1f5f9;
--bg-app-dark: #0f172a;
--bg-surface: #ffffff;
--bg-surface-dark: #1e293b; /* slate-800 */
--bg-header: #0f172a;

--border-default: #e2e8f0;
--border-default-dark: #334155;

--text-primary: #0f172a;   /* slate-900 */
--text-secondary: #64748b;   /* slate-500 */
--text-on-dark: #ffffff;

--radius-sm: 6px;   /* rounded-md */
--radius-md: 8px;   /* rounded-lg */
--radius-lg: 16px;  /* rounded-2xl */

--font-sans: 'Inter', system-ui, sans-serif;
--font-display: 'Hanken Grotesk', system-ui, sans-serif;
--font-mono: 'JetBrains Mono', monospace;
```

### Reglas de composición

1. **Fondo de app** siempre gris azulado (`#f1f5f9`), no blanco puro.
2. **Contenido en tarjetas** blancas con borde `#e2e8f0` y `shadow-sm`.
3. **Acción primaria** azul `brand-600` / `#2563eb`; en marketing/login usar `#0036b9`.
4. **Texto** en escala slate; evitar negro puro (`#000`).
5. **Tablas** compactas (`text-xs`), headers sticky gris claro.
6. **Iconos** Lucide, tamaño 16px por defecto.
7. **Esquinas** más redondeadas en interacción (inputs/botones) que en contenedores de datos.
8. **Espaciado vertical** entre bloques de página: `gap-5`.
9. **Formato locale** `es-MX` para números y fechas.
10. **Antialiasing** activo en todo el body.

### Dependencias recomendadas (paridad con NexusChain)

```json
{
  "tailwindcss": "^3.4",
  "lucide-react": "^0.468",
  "clsx": "^2.1",
  "tailwind-merge": "^2.5"
}
```

### Archivos de referencia para copiar tokens

| Archivo | Contenido |
|---------|-----------|
| `web/tailwind.config.ts` | Paleta completa y escala tipográfica |
| `web/app/globals.css` | Scrollbars y base |
| `web/app/layout.tsx` | Carga de fuentes |
| `web/components/ui/*` | Botón, modal, formulario, badge |
| `web/components/data-grid/DataTable.tsx` | Tabla de datos |
| `web/components/dashboard/DashboardShell.tsx` | Layout autenticado |
| `web/app/login/page.tsx` | Pantalla de autenticación |

---

## 14. Notas de consistencia

- Existe un `Sidebar.tsx` legacy (ancho `w-56`, tokens `brand-*`, labels en inglés) que **no** usa el shell actual. La referencia canónica del área autenticada es **`DashboardShell`**.
- Los tokens Material Design 3 en `tailwind.config.ts` están definidos pero el shell operativo prioriza **slate + brand**.
- `echarts` está en dependencias pero los gráficos visibles usan SVG custom (`SalesForecastChart`); al integrar ECharts, alinear series con `#34d399` (ventas) y `#facc15` (pronóstico).

---

*Generado a partir del código en `web/` — NexusChain small_saas_platform.*
