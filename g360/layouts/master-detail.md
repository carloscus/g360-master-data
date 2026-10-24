# Layout: master-detail

**Uso**: seleccionar un elemento de una lista y ver/editar su detalle.
Ideal para catálogos (clientes, productos, proveedores), configuración por entidad.

## Wireframe

```
┌───────────────┬───────────────────────────────────────────┐
│ 🔍 buscar     │  Detalle: nombre entidad + acciones       │  ~56px
├───────────────┤  ──────────────────────────────────────── │
│ Item 1      ◀ │  Seccion: datos generales (2 cols)        │
│ Item 2        │  ┌─────────────┬─────────────┐            │
│ Item 3        │  │ campo       │ campo       │            │
│ Item 4        │  └─────────────┴─────────────┘            │
│ Item 5        │  Seccion: datos operativos / historial    │
│ ...           │  Tabs o acordeon si hay >2 grupos        │
│ (scroll)      │                                           │
└───────────────┴───────────────────────────────────────────┘
   ~30%              ~70%
```

## Bloques y orden

1. **Panel izquierdo (lista)**: buscador fijo arriba, lista con scroll propio, item activo con highlight (accent-soft).
2. **Panel derecho (detalle)**: header con nombre + acciones (editar/guardar), luego secciones.
3. **Secciones**: máximo visibles 2; el resto en tabs o acordeón.

## Reglas de composición

- Lista: item compacto (48-56px), nombre primario + estado/subtitulo muted, badge de estado si aplica.
- Detalle: form en 2 columnas para campos cortos; 1 columna para notas/historial.
- Al seleccionar item: actualizar solo el panel derecho (no re-render de la lista completa).
- Estados vacíos: "Selecciona un item" con ícono, no una pantalla en blanco.
- Botón guardar fijo en header del detalle (no al final del scroll).

## Snippets asociados

`flet-search-field`, `flet-card`, `flet-tabs`, `flet-datatable`, `flet-snackbar-error`, `flet-loading-overlay`

## Errores comunes

- Lista sin buscador con 500+ items → imposible navegar.
- Detalle con formulario de 40 campos sin secciones → muro visual.
- Re-cargar la lista completa al cambiar de item → lag percibido.
