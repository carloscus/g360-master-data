# Layout: sidebar-panels

**Uso**: app de múltiples vistas donde cada vista es un panel completo.
Ideal para herramientas con módulos (analítica, catálogos, ajustes, procesamiento).

## Wireframe

```
┌────────┬──────────────────────────────────────────────────┐
│  logo  │  Vista activa: titulo + acciones contextuales    │  ~56px
├────────┼──────────────────────────────────────────────────┤
│ 🏠 KPI │                                                  │
│ 📦 Cat.│  Contenido de la vista activa                    │
│ ⚙ Ajust│  (usa otro layout interno: dashboard-kpi,       │
│        │   master-detail, lista-filtros-export...)        │
│        │                                                  │
│        │                                                  │
├────────┤                                                  │
│ firma  │                                                  │
└────────┴──────────────────────────────────────────────────┘
  ~72-88px              rest
```

## Bloques y orden

1. **NavRail izquierdo**: icono + label corto, ancho 72-88px; badge de notificación opcional.
2. **Header de vista**: titulo de la vista + 1-2 acciones principales (no más).
3. **Contenido**: delega en otro layout; sidebar-panels solo define el marco.
4. **Footer firma** (opcional, dentro del rail): texto muted pequeño.

## Reglas de composición

- NavRail: máximo 7 entradas visibles; si hay más, agrupa en submenú.
- La vista activa se marca con accent + fondo accent-soft, no solo color (accesibilidad).
- Cambiar de vista NO destruye el estado de la vista anterior (mantener scroll/datos en memoria si es posible).
- Cada vista puede tener su propio layout interno — composición jerárquica.
- Header de vista con buscador global opcional (Ctrl+K si aplica, ver `flet-search-field`).

## Snippets asociados

`flet-nav-rail`, `flet-tabs`, `flet-search-field`, `flet-footer-signature`, `flet-tooltip`

## Errores comunes

- Rail con 12 entradas → usa un submenu o reubica en la vista.
- Título duplicado en header de vista y header de app → ruido.
- Vistas sin estado preservado → el usuario pierde contexto al navegar.
