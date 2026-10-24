# G360 App Polished

> 🚀 **Plantilla estandar G360 para apps Flet desktop** — La evolucion de `python-flet` con patrones de UI avanzados heredados de produccion.

[![Version](https://img.shields.io/badge/version-1.0.0-blue)]()
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![Flet](https://img.shields.io/badge/Flet-0.28.3-green)](https://flet.dev)

## Quick Start

```bash
# La app auto-instala uv, Python 3.11, dependencias y crea acceso directo
run.bat

# O lanzador minimizado (sin consola visible)
launch.vbs
```

## Caracteristicas

| Caracteristica | Detalle |
|---|---|
| **Dual theme** | Dark/light con toggle y persistencia en `~/.g360/` |
| **Auto-refresh** | Cada 15 min con lock thread-safe |
| **Cache con hash diff** | SHA-256 evita rebuilds si los datos no cambiaron |
| **Search overlay** | Buscador flotante con debounce 250ms, Enter abre, Escape cierra |
| **KPI cards con glow** | Colores semanticos + efecto de luz |
| **G360 Signature** | Isotipo G360 detecta tema automaticamente (dark/light) |
| **Fonts embebidas** | Inter + JetBrains Mono Variable |
| **Launcher 5 pasos** | Auto-instala uv → Python 3.11 → .venv → deps → shortcut |
| **Portable** | `sync_portable.py` + `launch.vbs` para PCs sin Python |
| **Logger rotativo** | `RotatingFileHandler` max 2MB, backupCount=3 |
| **Shutdown limpio** | `page.on_close` detiene threads |

## Estructura

```
g360-app-polished/
├── main.py                    # Entry point (ft.app + logger setup)
├── src/
│   ├── __init__.py
│   ├── app.py                 # G360App base (orquestador)
│   ├── config/
│   │   ├── __init__.py
│   │   └── theme.py           # Paleta dual + rgba() + persistencia
│   ├── core/
│   │   ├── __init__.py
│   │   ├── constants.py       # Rutas, versiones, configuracion global
│   │   ├── processor.py       # BaseProcessor (heredar y extender)
│   │   └── skill.json         # Skill metadata
│   └── ui/
│       ├── __init__.py
│       ├── dashboard.py       # Layout base: sidebar, KPIs, search
│       ├── kpi_card.py        # Card reutilizable con glow
│       └── search_overlay.py  # Buscador flotante con debounce
├── g360_flet/
│   ├── __init__.py
│   └── g360_signature.py      # Widget isotipo G360
├── assets/
│   ├── fonts/                 # Inter + JetBrains Mono Variable
│   ├── images/                # Logo + icono
│   └── data/                  # Sample data + cache runtime
├── skill.json                 # Skill G360 aplicado
├── run.bat                    # Launcher 5 pasos auto-instalable
├── launch.vbs                 # Lanzador minimizado
├── launch_minimized.bat       # Delega a launch.vbs
├── build-portable.bat         # PyInstaller onefile + windowed
├── sync_portable.py           # Sync sincronizacion
├── create_shortcut.vbs        # Acceso directo escritorio
├── requirements.txt           # Dependencias
├── pyproject.toml             # Metadata del proyecto
└── .gitignore
```

## Como extender

### 1. Implementar tu logica de datos

En `src/app.py`, sobrescribe `_fetch_data`:

```python
from src.app import G360App

class MiApp(G360App):
    def _fetch_data(self) -> dict | None:
        """Descarga datos desde tu API/ERP."""
        import requests
        resp = requests.get("https://mi-api.com/data")
        return resp.json() if resp.ok else None
```

### 2. Procesar y renderizar

En `src/core/processor.py`, extiende `BaseProcessor`:

```python
from src.core.processor import BaseProcessor

class MiProcessor(BaseProcessor):
    def calcular_kpis(self, raw_data: dict) -> dict:
        # Tu logica de KPIs
        return {
            "primary": {"value": "100", "subtext": "items"},
            ...
        }
```

### 3. Customizar el dashboard

```python
from src.ui.dashboard import Dashboard

class MiDashboard(Dashboard):
    def _render(self):
        """Renderiza los datos procesados en el UI."""
        kpis = MiProcessor().calcular_kpis(self._raw_data)
        self._kpi_row.controls = self._build_kpi_row(kpis)
        self.page.update()
```

## Theme Colors

Colores semanticos definidos en `skill.json`, accesibles via `get_colors(mode)`:

| Token | Dark | Light | Uso |
|-------|------|-------|-----|
| `bg` | `#0A0F1E` | `#F3F5F9` | Fondo principal |
| `surface` | `#141D33` | `#FFFFFF` | Cards, contenedores |
| `accent` | `#10B981` | `#047857` | Accentos principales |
| KPI cyan | `#06B6D4` | `#0891B2` | Indicador 1 |
| KPI violet | `#8B5CF6` | `#7C3AED` | Indicador 2 |
| KPI red | `#EF4444` | `#DC2626` | Indicador critico |
| KPI amber | `#F59E0B` | `#B45309` | Indicador warning |

### Personalizar Colores

Los colores se leen automaticamente de `skill.json`. Para personalizar:

**Opcion 1: Modificar skill.json**
```json
{
  "colors": {
    "accent": "#2563eb",      // Azul corporativo
    "surface": "#1e293b",     // Gris oscuro
    "success": "#16a34a",     // Verde mas oscuro
    ...
  }
}
```

**Opcion 2: Sobrescribir en runtime**
```python
from src.config.theme import set_brand_colors

set_brand_colors({
    "dark": {
        "accent": "#2563eb",
        "surface": "#1e273e",
    },
    "light": {
        "accent": "#1d4ed8",
    }
})
```

**Opcion 3: Usar paleta existente**
- **Verde esmeralda** (default): `#10B981` — Moderno, fresco
- **Verde corporativo**: `#2563eb` — Azul/verde profesional
- **Verde bosque**: `#059669` — Mas sobrio, enterprise
- **Verde fluorescente**: `#34d399` — Mas vibrante, tech

> **Nota**: Todos los colores deben ser validos hex (`#RRGGBB`). El sistema usa defaults G360 y aplica overrides solo de los colores especificados.

## Arquitectura

```
main.py → G360App ──→ Dashboard ──→ KPICard, SearchOverlay
                    ├──→ theme.py       (colores)
                    └──→ processor.py   (logic)
```

### Capas (Regla G360: Core sin UI, UI con Core)

| Capa | Archivo | Responsabilidad |
|------|---------|-----------------|
| **Entry** | `main.py` | Boot, sys.path, ft.app, logger |
| **App** | `src/app.py` | Page setup, ciclo de vida, cache, auto-refresh, overlay |
| **Core** | `src/core/processor.py` | BaseProcessor (heredar) — KPIs, export |
| **Core** | `src/core/constants.py` | URL, rutas, version |
| **UI** | `src/ui/dashboard.py` | Layout completo, callbacks |
| **Config** | `src/config/theme.py` | Paleta dual, utility rgba, persistencia |
| **Brand** | `g360_flet/g360_signature.py` | Isotipo G360 auto-temado |

## Comandos G360

```bash
g360 init mi-app --template python-flet-polished --skill flet-desktop-polished --portable

# El template se resuelve automaticamente si usas un skill Flet:
g360 init mi-app --skill flet-desktop-polished
# ↓ usa python-flet-polished por defecto
```

---

> **Estandar desde v1.14.0.** El template `python-flet` clasico queda en **legacy** — usa `python-flet-polished` para nuevos proyectos.

**Marca**: G360 · **Isotipo**: 3 puntos + chevron `>` · **Signature**: powered by G360
**Powered by**: [g360-signature](https://github.com/carloscus/g360-signature)
