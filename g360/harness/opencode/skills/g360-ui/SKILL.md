---
name: g360-ui
description: Build symmetric modern corporate UI in any G360 app. Less-is-More policy, design tokens, type hierarchy, 8 essential components, review workflow.
version: 1.0.0
---

# G360 UI — Skill

Skill primario para crear UI frontend simetrica, moderna y corporativa en apps G360
(Flet, React, Solid, Svelte, Lit, CustomTkinter).

## 1. Politica Less is More (leer primero, siempre)

- NO hardcodear colores. Todo color sale de `skill.json` → `theme` / `var(--g360-*)`.
- NO logica de negocio en UI. `core/` nunca importa el framework UI.
- NO mas de 3 niveles de nesting visual (Column > Row > Card, basta).
- SIEMPRE loading visible en operaciones bloqueantes (fetch, threads, exports).
- SIEMPRE error visible al usuario (toast/SnackBar). Nunca `except: pass` ni `catch {}`.
- NO duplicar componentes. Reusar desde `src/assets/snippets/snippets.json`.
- Un componente por archivo. Archivos UI de maximo 400 lineas.
- Una vista = un solo `<h1>`. Nunca saltar niveles (H1 → H3 prohibido).
- Maximo 6 pasos tipograficos (H1, H2, H3, body, caption, mono).
- Toda app incluye los 8 esenciales: header, KPI card, tabla, drop-zone,
  loading, firma G360, menu export, busqueda.

## 2. Verificar antes de presentar

```bash
g360 review            # tokens + jerarquia + componentes, objetivo >= 90/100
g360 review tokens     # solo paleta vs skill.json
g360 review hierarchy  # solo H1-H6 y escala tipografica
g360 review components # solo esenciales + antipatrones
g360 lint              # naming y duplicados
g360 audit             # compliance G360
```

Corrige por severidad: criticos primero, luego importantes, luego menores.
Re-ejecuta `g360 review` hasta alcanzar el puntaje.

## 3. Esenciales por framework

| Esencial | Flet | Web (React/Solid/Svelte/Lit) |
|---|---|---|
| Header | `_build_header()` | `<Header />` / `<g360-header>` |
| KPI Card | `KpiCard` + glow | `<KpiCard />` |
| Tabla | `DataTable` | `<DataTable />` |
| Drop Zone | `FilePicker` | `<input type="file">` / drop-zone |
| Loading | `ProgressRing` + overlay | `<LoadingOverlay />` |
| Firma | `g360_signature` widget | `<g360-signature>` |
| Export | `PopupMenuButton` | dropdown export (xlsx/csv) |
| Busqueda | search + debounce 250ms | search + debounce 250ms |

## 4. Referencias del repo

- `AGENTS-UIUX.md` — patrones por framework, threading, responsive, checklist.
- `FLET-NAMING-CONVENTIONS.md` — sufijos `App/Dashboard/Card/Modal/Overlay/Badge/Chip/Table`.
- `src/assets/snippets/snippets.json` — 40+ snippets listos (flet-*, pandas-*, openpyxl-*).
- `src/assets/config/g360-skills.json` — paletas por skill (corporativo, moderno, cipsa, flet...).
