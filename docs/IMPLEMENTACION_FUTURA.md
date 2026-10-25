# Implementación Futura: Descuentos y Medidas de Caja

> **Estado**: Infraestructura lista, activación pendiente.  
> **Fecha**: 2026-10-24  
> **Trigger**: Cuando se decida incluir descuentos y dimensiones en el catálogo maestro.

---

## Resumen

El ecosistema G360 ya tiene toda la infraestructura para soportar:
- **Descuentos** por SKU (hasta 6 niveles + precio fijo + vigencias)
- **Dimensiones de caja** (largo, ancho, alto, peso, volumen)

Lo único pendiente es **leer los datos de `SKU_PRECIOS.xlsx` y emitirlas en el catálogo**.

---

## Arquitectura Actual

### Archivos existentes

| Archivo | Propósito | Estado |
|---|---|---|
| `scripts/leer_sku_precios.py` | Lee `SKU_PRECIOS.xlsx` (2 hojas unificadas) | ✅ Listo |
| `scripts/contratos.py` | Define `CONTRATO_SKU_LOGISTICA` y `CONTRATO_SKU_PRECIOS` | ✅ Listo |
| `scripts/crear_plantillas.py` | Crea/migra plantillas a `data/` | ✅ Listo |
| `data/plantilla_precios.xlsx` | Plantilla legacy con hojas `DESCUENTOS` + `PRECIOS_FIJOS` | ✅ Existe |
| `data/SKU_BX.xlsx` | Guía comercial sin descuentos ni medidas | ⚠️ Sin datos nuevos |
| `data/SKU_PRECIOS.xlsx` | **Archivo unificado futuro** (no existe aún) | ❌ Crear |

### Estructura esperada de `SKU_PRECIOS.xlsx`

```
Hoja: SKU_LOGISTICA
  Requeridas: ORDEN, SKU, UN_BX
  Opcionales: ESTADO_LINEA, LARGO_CM, ANCHO_CM, ALTO_CM, PESO_CAJA_KG, M3_CAJA, M3_UNIDAD

Hoja: SKU_PRECIOS
  Requerida: SKU, DESC1
  Opcionales: DESC2..DESC6, VIGENCIA_DESC, PRECIO_FIJO, VIGENCIA_PRECIO, OBSERVACION
```

---

## Pasos para Implementar

### Fase 1: Migrar plantilla (1 comando)

```powershell
cd C:\Users\ccusi\Documents\Proyect_Coder\G360-ecosystem\projects\g360-master-data
python scripts/crear_plantillas.py --migrar
```

Esto fusiona las hojas `DESCUENTOS` + `PRECIOS_FIJOS` de `plantilla_precios.xlsx` en una sola hoja `SKU_PRECIOS` dentro de `data/SKU_PRECIOS.xlsx`.

**Nota**: El archivo se crea con estructura vacía; hay que llenarlo manualmente o importarlo desde el ERP/Excel existente.

---

### Fase 2: Actualizar generador (3-4 líneas)

**Archivo**: `scripts/generar_catalogo_base.py`

#### 2.1. Lectura del archivo unificado

En `_leer_guia()`, agregar lectura de precios después de `caja_map`:

```python
# Después de: guia_caja = datos_unificados.caja
# Agregar:
precios_map = datos_unificados.precios
print(f"  SKU_PRECIOS: {len(precios_map)} SKUs con descuento/precio")
```

#### 2.2. Pasar `precios_map` a `generar_output()`

```python
output = generar_output(
    productos,
    unbx_map,
    estado_map,
    orden_map,
    a.output,
    exclusiones=exclusiones,
    universo_stock=universo_stock,
    taxonomia_extra=crayolas_nuevas,
    universo=universo,
    caja_map=guia_caja,
    fuentes=[...],
    erp_todos=erp_todos,
    um_kardex=um_kardex,
    precios_map=precios_map,  # <-- NUEVO
)
```

#### 2.3. Emitir campo `descuentos` en cada producto

En `generar_output()`, dentro del bucle `for p in productos:`, agregar:

```python
# Después de: "precio": float(p.get("precio") or 0.0),
# Agregar:
descuento_info = precios_map.get(p["sku"])
if descuento_info:
    p["descuentos"] = {
        "tipo": descuento_info["tipo"],  # "FIJO" o "DESCUENTO"
        "descuento_pct": descuento_info.get("descuento_total", 0),
        "precio_fijo": descuento_info.get("precio_fijo"),
        "vigencia_inicio": descuento_info.get("vigencia_ini"),
        "vigencia_fin": descuento_info.get("vigencia_fin"),
        "observacion": descuento_info.get("observacion", ""),
    }
else:
    p["descuentos"] = None
```

#### 2.4. Actualizar estadísticas en metadata

```python
estadisticas["con_descuento"] = sum(
    1 for p in productos if p.get("descuentos") and p["descuentos"].get("tipo") == "DESCUENTO"
)
estadisticas["con_precio_fijo"] = sum(
    1 for p in productos if p.get("descuentos") and p["descuentos"].get("tipo") == "FIJO"
)
```

---

### Fase 3: Schema del catálogo (1 línea)

**Archivo**: `scripts/generar_catalogo_base.py` (contrato de salida)

Agregar a la sección de campos validados:

```python
# En VALIDACION_CAMPOS, agregar:
"descuentos": dict,
```

---

### Fase 4: API stock (opcional)

Si se quiere exponer descuentos en el API:

**Archivo**: `app/models/schemas.py`

```python
class ItemStockEnriched(...):
    # ... campos existentes ...
    descuentos: Optional[dict] = Field(None, description="Descuentos aplicables al SKU")
```

**Archivo**: `app/services/s1_service.py`

En `_enriquecer_items()`, propagar el campo desde el catálogo:

```python
# Después de: precio=cat.get("precio", 0.0),
# Agregar:
descuentos=cat.get("descuentos"),
```

---

## Validación

### Tests a agregar

**Archivo**: `scripts/tests/test_generar_catalogo.py`

```python
def test_genera_descuentos_si_existen(self, tmp_path):
    # Mock de precios_map con descuento
    precios_map = {
        "011019": {
            "tipo": "DESCUENTO",
            "descuento_total": 0.15,
            "precio_fijo": None,
            "vigencia_ini": "2026-01-01",
            "vigencia_fin": "2026-12-31",
            "observacion": "Descuento navideño",
        }
    }
    # Generar output y verificar que el SKU tenga descuentos
```

### Comando de verificación

```powershell
python scripts/leer_sku_precios.py -i data/SKU_PRECIOS.xlsx
# Debe mostrar:
#   SKU_LOGISTICA: N filas
#   SKU_PRECIOS: M SKUs con descuento/precio
#   Con caja: K SKUs
#   Con descuento: D SKUs
```

---

## Estimación de Tiempo

| Fase | Tiempo estimado | Complejidad |
|---|---|---|
| Fase 1: Migrar plantilla | 5 min | Automático |
| Fase 2: Actualizar generador | 30-45 min | Baja (copiar patrón existente) |
| Fase 3: Schema | 5 min | Trivial |
| Fase 4: API (opcional) | 15 min | Trivial |
| Tests | 30 min | Moderada |
| **Total** | **~1.5-2 horas** | — |

---

## Checklist Pre-Implementación

- [ ] Definir si los descuentos se aplican **por SKU** o **por cliente** (actual esquema soporta solo por SKU)
- [ ] Confirmar formato de fechas en `VIGENCIA_DESC` / `VIGENCIA_PRECIO` (YYYY-MM-DD recomendado)
- [ ] Decidir si `precio_fijo` reemplaza al `precio` del ERP o se suma como oferta
- [ ] Documentar en `README.md` los nuevos campos `descuentos` y `dimensiones_caja`
- [ ] Correr `python scripts/leer_sku_precios.py --help` para validar que el lector funciona

---

## Notas Históricas

- El "método D" (derivación por parecido) se eliminó en commit `ee2b68b` (2026-09-25).
- `dimensiones_caja` está definido en schema pero nunca poblado porque `SKU_PRECIOS.xlsx` no existía.
- `UM` se pobló desde KARDEX en commit `1037a25` (2026-10-23).
- La estructura `SKU_PRECIOS.xlsx` unificada se diseñó en v3.8 para consolidar `SKU_BX.xlsx` + `plantilla_precios.xlsx`.

---

## Referencias

- `scripts/leer_sku_precios.py` — Lector unificado
- `scripts/contratos.py:CONTRATO_SKU_LOGISTICA` — Contrato de logística
- `scripts/contratos.py:CONTRATO_SKU_PRECIOS` — Contrato de precios
- `scripts/crear_plantillas.py` — Creador/migrador de plantillas
- Commit `1037a25` — Integración UM desde KARDEX
- Commit `8f5f66a` — Orden por línea + corrección key unicode
