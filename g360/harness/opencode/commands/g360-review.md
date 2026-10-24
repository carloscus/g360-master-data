# G360 Review — Comando

Revisa la UI del proyecto y corrige hasta alcanzar 90/100 o mas.

## Pasos

1. Ejecuta `g360 review` en la raiz del proyecto.
2. Corrige hallazgos criticos primero:
   - Funciones duplicadas con distinta implementacion (`g360 lint`).
   - Operaciones bloqueantes sin loading.
   - Errores silenciosos (`except: pass`, `catch {}`).
3. Corrige hallazgos importantes:
   - Colores fuera de la paleta de `skill.json` → reemplazar por tokens.
   - Multiples `<h1>` o tamanos de texto fuera de escala 10-64.
4. Corrige hallazgos menores:
   - Colores hardcodeados que SI estan en paleta → leer desde theme.
   - `print()` / `console.log()` en UI → logger + toast.
   - Archivos UI de mas de 400 lineas → dividir en componentes.
5. Re-ejecuta `g360 review` y repite hasta puntaje >= 90.
6. Reporta: puntaje final + lista de cambios aplicados.
