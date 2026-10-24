# Layout: lista-filtros-export

**Uso**: listados grandes con filtros combinables y exportación.
Ideal para: reportes de ventas, logística, inventarios, auditorías.

## Wireframe

```
┌──────────────────────────────────────────────────────────┐
│  Titulo vista                              [Exportar ▾]   │  ~56px
├──────────────────────────────────────────────────────────┤
│  [Busqueda...]  [Fecha ▾] [Estado ▾] [Marca ▾]  Limpiar  │  ~48px
├──────────────────────────────────────────────────────────┤
│  Filas: 234 | Periodo: 01-30 Oct | Mostrando 1-50        │  ~32px
├──────────────────────────────────────────────────────────┤
│  Col ▲ │ Col │ Col │ Col │ Col                           │
│  ──────┼─────┼─────┼─────┼───── (sticky header)          │
│  dato  │ dato│ dato│ dato│ dato                          │
│  dato  │ dato│ dato│ dato│ dato                          │
│  ...   (scroll propio, paginacion abajo)                 │
├──────────────────────────────────────────────────────────┤
│  ◀  1  2  3  ...  9  ▶      Filas por pagina: [50 ▾]     │  ~48px
└──────────────────────────────────────────────────────────┘
```

## Bloques y orden

1. **Header**: título + botón export (dropdown: Excel, CSV).
2. **Barra de filtros**: búsqueda + 2-4 filtros dropdown, chip de "limpiar" solo si hay filtros activos.
3. **Barra de estado**: total de filas + rango visible (contexto inmediato).
4. **Tabla**: sticky header, filas de 40-48px, números alineados a derecha, texto a izquierda.
5. **Paginación**: fija abajo, no scrollea con la tabla.

## Reglas de composición

- Filtros: cambiar un filtro refresca la tabla con loading overlay sutil, no recarga de pantalla.
- Columnas numéricas moneda con fuente monoespaciada (`g360-num`), alineadas a derecha.
- Máximo 8 columnas visibles; el resto se agregan con selector de columnas.
- Export respeta los filtros activos y muestra progreso (`flet-export-progress`).
- Estado vacío (0 resultados): mensaje + botón "limpiar filtros", no tabla vacía.

## Snippets asociados

`flet-search-field`, `flet-datatable`, `flet-pagination`, `flet-export-menu`, `flet-export-progress`, `flet-progress-bar`, `flet-loading-overlay`

## Errores comunes

- Filtros de fecha + estado + sucursal + vendedor en una fila sola → wrap en 2 filas.
- Tabla sin sticky header en 50 filas → pierde contexto.
- Export sin filtros visibles → el usuario no sabe qué exportará.
