# Layout: dashboard-kpi

**Uso**: pantallas de resumen con indicadores + detalle tabular o gráfico.
Ideal para dashboards de ventas, KPIs de ERP, reportes periódicos.

## Wireframe

```
┌──────────────────────────────────────────────────────────┐
│  Header: titulo + periodo selector + boton export        │  ~64px
├───────────┬───────────┬───────────┬──────────────────────┤
│  KPI 1    │  KPI 2    │  KPI 3    │  KPI 4               │  ~120px
│  valor    │  valor    │  valor    │  valor               │
│  delta ▲  │  delta ▼  │  delta ▲  │  delta ▲             │
├───────────┴───────────┴───────────┴──────────────────────┤
│  Grafico principal (linea o barra, 60-70% del ancho)     │  ~280px
│  + panel lateral: top-N o insight (30-40%)               │
├──────────────────────────────────────────────────────────┤
│  Tabla de detalle (scroll propio, paginada)              │  rest
└──────────────────────────────────────────────────────────┘
```

## Bloques y orden

1. **Header** (titulo, rango de fechas, acción de export) — un solo nivel de acciones.
2. **Fila KPIs**: 3-4 tarjetas iguales (`flet-kpi-card`), nunca 5+; si hay más, elige los 4 críticos y mueve el resto al detalle.
3. **Fila análisis**: gráfico principal + panel lateral opcional.
4. **Tabla detalle**: DataTable o ListView paginada, altura restante con scroll propio.

## Reglas de composición

- KPIs: valor grande (`title_style` 24-28px), label muted 12px, delta con color semántico (success/warning).
- Un solo gráfico protagonista; los secundarios van al panel lateral como mini-chart o lista.
- La tabla nunca domina la pantalla arriba del gráfico.
- Espaciado: 16px entre bloques, 12px padding interno de card.

## Snippets asociados

`flet-kpi-card`, `flet-chart-line`, `flet-chart-bar`, `flet-datatable`, `flet-pagination`, `flet-export-menu`, `flet-search-field`

## Errores comunes

- 6 KPIs en fila → ilegible; reduce a 4.
- Tabla sin paginación con 10k filas → congelar UI; usar paginación o virtual scroll.
- Gráfico y tabla con la misma altura → pelea de jerarquía; gráfico domina.
