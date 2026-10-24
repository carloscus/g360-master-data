# Layout: wizard

**Uso**: procesos guiados en pasos (ingesta de datos, alta compleja, onboarding).
Ideal para: carga de archivos ERP, asistentes de configuración, multi-formulario.

## Wireframe

```
┌──────────────────────────────────────────────────────────┐
│  ● ━━━━━━━ ● ━━━━━━━ ○ ─────────── ○     (stepper)       │  ~48px
│  Archivo    Mapeo      Validacion    Confirmar           │
├──────────────────────────────────────────────────────────┤
│                                                          │
│              Contenido del paso actual                    │
│              (centrado, max-width 720px)                  │
│                                                          │
│                                                          │
├──────────────────────────────────────────────────────────┤
│       ◀ Atras          (espacio)       Siguiente ▶       │  ~64px
└──────────────────────────────────────────────────────────┘
```

## Bloques y orden

1. **Stepper arriba**: 3-5 pasos máximo, paso actual en accent, completados con check, pendientes muted.
2. **Área de contenido**: un tema por paso, ancho máximo ~720px centrado.
3. **Footer de navegación**: Atras (fantasma) + Siguiente/Siguiente (primario); validar antes de avanzar.

## Reglas de composición

- Un paso = una decisión. Si un paso necesita scroll, se parte en dos.
- Errores de validación inline en el campo, no solo en el footer.
- El paso actual NO se puede visitar hacia atrás si hay datos críticos en curso (confirmar).
- Resumen final antes de ejecutar: clave/valor de todo lo configurado.
- Pasos con carga larga: mostrar progreso real (barra), no spinner infinito.

## Snippets asociados

`flet-progress-bar`, `flet-drop-zone`, `flet-button`, `flet-loading-overlay`, `flet-snackbar-error`

## Errores comunes

- Wizard de 8 pasos → abandono; colapsa a 4 o divide en flujos.
- Validar todo al final en vez de por paso → frustración.
- Permitir saltar pasos sin completar → estados inconsistentes.
