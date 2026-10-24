# Mi Proyecto G360 Migracion

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="g360/brand/g360/logotypes/logo-g360-light.svg">
  <img alt="G360" height="64" src="g360/brand/g360/logotypes/logo-g360-dark.svg">
</picture>

> Migracion de tkinter/CustomTkinter a Flet con el ecosistema G360

## Quick Start

```bash
uv sync
uv run python src/main.py
```

## Estructura del Proyecto

```mermaid
flowchart TD
    UI["UI<br/>Flet widgets"]
    Migrate["Migration<br/>migrate_tkinter.py"]
    Core["Core<br/>business logic"]
    Theme["Theme<br/>G360Theme"]

    UI --> Core
    UI --> Theme
    Migrate --> UI
```

## Identidad de Marca

| Elemento | Valor |
|---|---|
| Marca | G360 |
| Color primario | `#00d084` |
| Signature mode | `powered` |
| Signature text | "powered by G360" |

## Footer

```python
from core.components.g360_signature import g360_footer
page.add(g360_footer())
```

---

**Marca**: G360 · **Isotipo**: 3 puntos + chevron `>`
**Signature**: powered by G360 · **Powered by**: [g360-signature](https://github.com/carloscus/g360-signature)