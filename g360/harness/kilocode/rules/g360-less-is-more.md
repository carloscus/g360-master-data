# G360 Less is More

Project UI policy. Apply to every new component and every refactor.

## Colors

- Never hardcode colors. Every color comes from `skill.json` (`colors`) via theme object or `var(--g360-*)`.
- Colors outside the skill palette are defects. Fix with `g360 review tokens`.

## Separation

- Business logic lives in `core/` and never imports the UI framework.
- UI lives in `ui/` (or `components/` / `views/` / `routes/`). One component per file.

## Feedback

- Every blocking operation (fetch, thread, export) must show a visible loading state.
- Every error must be visible to the user (toast / SnackBar). Silent errors (`except: pass`, empty `catch {}`) are defects.

## Simplicity

- Max 3 levels of visual nesting.
- UI files max 400 lines. Split into components (KpiCard, Table, Modal...).
- Max 6 type steps (H1, H2, H3, body, caption, mono). Sizes stay within 10-64.
- One view = one `<h1>`. Never skip heading levels.

## Completeness

- Every app ships the 8 essentials: header, KPI card, data table, drop-zone, loading state, G360 signature, export menu, search.
- Verify with `g360 review` and reach 90/100 or higher before presenting.
