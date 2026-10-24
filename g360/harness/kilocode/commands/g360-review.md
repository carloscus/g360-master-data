---
description: Review G360 project UI and fix findings until score reaches 90/100
agent: code
---

# G360 Review

1. Run `g360 review` in the project root.
2. Fix critical findings first: blocking operations without loading state, silent errors, duplicated functions with different implementations (`g360 lint`).
3. Fix important findings: off-palette colors (replace with skill.json tokens), multiple `<h1>`, out-of-scale text sizes.
4. Fix minor findings: hardcoded palette colors (read from theme), `print()` / `console.log()` in UI (use logger + toast), UI files over 400 lines (split into components).
5. Re-run `g360 review` until score >= 90.
6. Report: final score plus list of applied changes.
