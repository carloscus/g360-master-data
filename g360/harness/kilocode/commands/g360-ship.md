---
description: Full G360 pipeline to get a project ready to present and deploy
agent: code
---

# G360 Ship

1. `g360 audit` — G360 compliance (skill.json, signature, structure).
2. `g360 lint` — naming, duplicates, syntax.
3. `g360 review` — tokens, hierarchy, components. Target >= 90/100.
4. `g360 clean --dead --orphans --dry-run` — inspect, then run without `--dry-run` using `--force`.
5. `g360 present` — verify final repo structure.
6. `g360 pptx .` — generate the user manual inside the repo.
7. `g360 docs --level all` — README, architecture, business rules.
8. Report: audit/lint/review scores, cleaned files, PPTX and docs paths.
