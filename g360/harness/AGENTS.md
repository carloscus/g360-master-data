# AGENTS.md — G360 Project

Contexto para agentes (OpenCode, Kilo Code o cualquier harness).

## Identidad

- Este proyecto sigue el estandar G360. La fuente de verdad visual es `skill.json` (raiz o `src/core/skill.json`): paleta `colors`, `signature`, `framework`.
- Referencias: `AGENTS-UIUX.md` (patrones por framework), `FLET-NAMING-CONVENTIONS.md` (nombres), `BUSINESS_RULES.md` (reglas de negocio, si existe).

## Politica Less is More

- Colores solo desde `skill.json` (theme / `var(--g360-*)`). Nada hardcodeado.
- `core/` sin imports del framework UI. Un componente por archivo, maximo 400 lineas.
- Loading visible en toda operacion bloqueante. Errores siempre visibles al usuario.
- Una vista = un `<h1>`, sin saltar niveles. Maximo 6 pasos tipograficos.
- 8 esenciales: header, KPI, tabla, drop-zone, loading, firma, export, busqueda.

## Comandos de verificacion

```bash
g360 review   # UI: tokens + jerarquia + componentes (>= 90/100)
g360 lint     # naming, duplicados, sintaxis
g360 audit    # compliance G360
g360 present  # estructura del repo
g360 pptx .   # manual de usuario
```

## Flujo de trabajo

1. Leer `skill.json` antes de tocar UI.
2. Implementar o corregir siguiendo la politica.
3. Verificar con `g360 review` + `g360 lint` hasta puntaje >= 90.
4. Presentar con `g360 present` y documentar con `g360 pptx` / `g360 docs`.
