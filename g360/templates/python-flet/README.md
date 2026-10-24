# Mi Proyecto G360 Flet

> ⚠️ **LEGACY** — Este template fue reemplazado por `python-flet-polished` (estandar actual).
> Para nuevos proyectos usar: `g360 init <name> --template python-flet-polished --skill flet-desktop-polished`

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="g360/brand/g360/logotypes/logo-g360-light.svg">
  <img alt="G360" height="64" src="g360/brand/g360/logotypes/logo-g360-dark.svg">
</picture>

> Aplicacion de escritorio G360 con Flet (ERP)

## Quick Start

```bash
uv sync
uv run python src/main.py
```

## Estructura del Proyecto

```mermaid
flowchart TD
    UI["UI<br/>Flet widgets"]
    Core["Core<br/>business logic"]
    Theme["Theme<br/>G360Theme"]
    Export["Export<br/>openpyxl"]
    Signature["Signature<br/>g360_signature"]

    UI --> Core
    UI --> Theme
    Core --> Export
    UI --> Signature
```

## Theme y Colores

| Token | Color | Uso |
|---|---|---|
| `bg` | `#0b1220` | Fondo principal |
| `surface` | `#1a2332` | Cards, contenedores |
| `accent` | `#00d084` | Verde G360 primary |
| `text` | `#f0f4f8` | Texto principal |
| `muted` | `#94a3b8` | Texto secundario |

## Lineamientos de Arquitectura

1. **src/core/**: Solo logica de negocio, sin importar flet
2. **src/ui/**: Importa flet y core. Solo presentacion
3. **src/export/**: Importa openpyxl y core. Solo reportes
4. **Colores**: Siempre via G360Theme. Nunca hardcodear

## Identidad de Marca

| Elemento | Valor |
|---|---|
| Marca | G360 |
| Color primario | `#00d084` |
| Signature mode | `own` |
| Signature text | "G360 Desktop" |

## Footer

```python
from core.components.g360_signature import g360_footer
page.add(g360_footer())
```

---

> **Nota**: Este es el template base original. Para proyectos nuevos se recomienda `python-flet-polished` que incluye: dual theme, auto-refresh con hash cache, search debounce, KPI glow cards, G360 signature widget y launcher auto-instalable de 5 pasos.

**Marca**: G360 · **Isotipo**: 3 puntos + chevron `>`
**Signature**: G360 Desktop · **Powered by**: [g360-signature](https://github.com/carloscus/g360-signature)
