# G360 Master Data — Manual de operación autónoma

Objetivo de este archivo: que cualquier persona resuelva lo del día a día
**sin depender de nadie**. El catálogo (`output/catalogo_productos.json`) es
el allowlist del API: todo lo que se vende sale de aquí.

## 1. Mapa mínimo

```
KARDEX_BASE.xlsx ──jerarquía (linea/grupo/tipo/familia) + UM──┐
PRODUCTOS.xls ──precio + peso + EAN13/14 + nombre─────────────┤
SKU_BX.xlsx ──un_bx + orden + guía───────────────────────────┼─→ generar_catalogo_base.py
plantilla_precios.xlsx ──precios manuales────────────────────┤         ↓
S1 (API o cache) ──stock + compromiso───────────────────────┘   catalogo_productos.json ─→ g360-stock-api ─→ apps
```

Cada fuente manda **solo en lo suyo**. Si un dato está mal, se corrige en su
fuente, nunca en el JSON (es un artefacto: se regenera).

## 2. Consultar sin ayuda (lo de todos los días)

```powershell
# Oferta por jerarquía: IDs del KARDEX, entrecomillados SIEMPRE en PowerShell
.venv\Scripts\python.exe scripts\consultar_por_taxonomia.py --linea 01 --grupo 01 --tipo 02 --familia '01,02'
# Toda la salida en JSON (para otra app): agregar --json
# Ver todo sin recorte: agregar --limite 0
```

La tabla muestra `SKU_KARDEX -> SKU_JSON` cuando difieren (`1011019 -> 011019`),
más EAN13/EAN14, precio, peso, un_bx, stock, categoría — o `FUERA` con el
motivo si el SKU no está publicado. La fila JSON trae además `sku_catalogo`,
`via_prefijo`, `cotizable`.

## 3. Regenerar el catálogo

```powershell
actualizar_catalogo.bat              # interactivo (pide clave si hace falta)
actualizar_catalogo.bat --auto       # genera + sube a Render sin preguntar
actualizar_catalogo.bat --auto-local # genera sin subir (modo seguro)
actualizar_catalogo.bat --upload     # sube el JSON tal cual está
```

El BAT corre en orden: **paso 0 → pytest → genera → gate taxonomía → upload**.
Si algo frena, el mensaje dice qué bloque y por qué (ver §4).

## 4. Diagnosticar (cuando algo frena o un dato no cuadra)

| Síntoma | Dónde mirar | Qué hacer |
|---|---|---|
| Paso 0 FATAL de contrato | `scripts/contratos.py` (CONTRATO_*) | El archivo fuente cambió columnas: renombrar/reordenar en origen o actualizar el contrato |
| `alerta_caida` / universo raro | `metadata.universo_stock` en el JSON | El S1 vino parcial: reintentar (cold start de Render) o regenerar con cache `--s1-cache` |
| SKU no aparece en consulta | Motivo `FUERA` en la fila | Regla de inclusión: guía ∨ stock>0 ∨ compromiso>0 ∨ (vigente ∧ precio>0). Revisar ERP (precio/inactivo) |
| ID jerarquía con 3 chars (`101`) | `contratos.derecha2` | Se normaliza solo a 2 (`01`); si el paso 0 lo reporta en masa, revisar el KARDEX origen |
| SKU numérico con `1` de más | `contratos.reducir_uno_numerico` | Solo calza si el reducido existe en el maestro; si ambas formas existen, no se fusiona (alerta) |
| Taxonomía distinta ERP↔KARDEX | Bloque `KARDEX vs ERP` del paso 0 | Defecto de registro: corregir en el maestro que esté mal, no en el código |

## 5. Reglas duras (no se negocian con los datos)

1. **SKU exactos**: `03077` ≠ `03077D`, `016763` ≠ `16763`. Sin parecidos ni `difflib`.
2. **Prefijos**: `01CA001`→`CA001`, `1014458`→`014458` solo si el reducido existe
   en el maestro. Len 5 y alfanuméricos: intactos.
3. **Jerarquía a 2 chars** (`derecha2`): `1`→`01`, `101`→`01`, `ad`→`AD`.
   SKU y almacén son TEXTO: se leen sin modificar.
4. **Toda reescritura queda en `meta`** del loader y se muestra en el paso 0.
5. **Línea 98** visible en catálogo pero fuera del semáforo vendible.
6. `data/` no se versiona. Solo `output/*.json` y `plantillas/`.

## 6. Dónde vive cada regla

- Contratos y lectura por nombre: `scripts/contratos.py` (`CONTRATO_ERP`, `CONTRATO_KARDEX`, `emparejar_skus`, `derecha2`, `reducir_uno_numerico`, `leer_kardex`)
- Generador y regla de inclusión: `scripts/generar_catalogo_base.py` (`generar_output`, `decidir_inclusion`)
- Gates: `scripts/validar_encabezados.py` (paso 0), `scripts/validar_taxonomia.py`
- Consulta: `scripts/consultar_por_taxonomia.py`
- Config editable sin código: `config/almacenes.json`, `config/guia_ignorados.json`
- Tests: `scripts/tests/` — 198 verdes a la fecha. Si cambias una regla, cambia su test primero.
