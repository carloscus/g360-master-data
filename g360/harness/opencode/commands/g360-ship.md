# G360 Ship — Comando

Pipeline completo para dejar un proyecto listo para presentar y desplegar.

## Pasos

1. `g360 audit` — compliance G360 (skill.json, firma, estructura).
2. `g360 lint` — naming, duplicados, sintaxis.
3. `g360 review` — tokens, jerarquia, componentes. Objetivo >= 90/100.
4. `g360 clean --dead --orphans --dry-run` — revisar, luego sin `--dry-run` con `--force`.
5. `g360 present` — verificar estructura final del repo.
6. `g360 pptx .` — generar manual de usuario dentro del repo.
7. `g360 docs --level all` — README, arquitectura, reglas de negocio.
8. Reporta: puntajes (audit/lint/review), archivos limpiados, rutas del PPTX y docs.
