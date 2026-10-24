# G360 Naming Conventions

## UI classes

- Use PascalCase with identifier suffixes: `App`, `Dashboard`, `Card`, `Modal`, `Overlay`, `Badge`, `Chip`, `Table`, `Header`, `Footer`.
- Example: `SalesDashboard`, `KpiCard`, `ExportModal`, `SearchOverlay`.

## Functions and methods

- Python: `snake_case` with semantic prefixes: `_setup_*`, `_build_*`, `_on_*`, `_fetch_*`, `_load_*` / `_save_*`, `_update_*` / `_refresh_*`, `_show_*` / `_hide_*`, `_toggle_*`, `_validate_*`.
- JavaScript: `camelCase` for functions and variables, `PascalCase` for components, `kebab-case` for CSS classes.

## Files

- Entry: `main.py`. Orchestration: `app.py`. Config: `config/*.py`. Business: `core/*.py`. UI: `ui/*.py`. Modals: `ui/modals/*.py`.
- Web components use `kebab-case`: `<g360-signature>`, `<g360-card>`.

## Verification

- Run `g360 lint` to check naming, duplicates and syntax.
- Full reference: `FLET-NAMING-CONVENTIONS.md` and `AGENTS-UIUX.md` in the g360-cli repo.
