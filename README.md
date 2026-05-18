# G360 Master Data

Sistema centralizado de datos maestros para proyectos G360.

Genera JSONs de catálogo consolidado que alimentan:
- `g360-order-xlsx` - Sistema de pedidos
- `g360-stock-reporter` - Reportes de stock
- `g360-return-form` - Devoluciones
- `comparador_de_precios` - Cotizaciones

## 📁 Estructura

```
g360-master-data/
├── data/                           ← Fuentes de datos (manuales)
│   └── plantilla_precios.xlsx      ← Catálogo + descuentos + precios fijos
├── scripts/                        ← Scripts de generación
│   ├── generar_catalogo.py         ← Genera catálogo consolidado
│   ├── leer_plantilla_precios.py   ← Lee precios con mapeo sku_cliente
│   └── tests/                      ← Tests unitarios
│       └── test_generar_catalogo.py
├── output/                         ← JSONs generados
│   └── catalogo_productos.json     ← Catálogo consolidado v2.0.0
└── actualizar_catalogo.bat         ← Automatización de actualización
```

## 🚀 Uso

```bash
# Crear entorno virtual (primera vez)
uv venv

# Instalar dependencias
uv pip install openpyxl

# Generar catálogo consolidado
.venv\Scripts\python scripts/generar_catalogo.py -i data/plantilla_precios.xlsx -o output/catalogo_productos.json
```

## 📋 Estructura del Excel

La plantilla `plantilla_precios.xlsx` contiene 4 hojas:

### Hoja 1: PRODUCTOS (principal)
| Columna | Descripción | Obligatorio |
|---------|-------------|-------------|
| `orden` | Índice para interface | ✅ |
| `sku` | Identificador único | ✅ |
| `nombre` | Descripción completa | ✅ |
| `ean13` | Código de barras | ❌ |
| `categoria` | VINIBALL/VINIFAN/REPRESENTADAS | ✅ |
| `subcategoria` | Subclasificación | ❌ |
| `linea` | PELOTAS, FORROS, ARCHIVO, etc. | ✅ |
| `grupo` | IMPORTADA VINIBALL, ROCHELLE, etc. | ❌ |
| `tipo` | PU, CUERO TERMOSELLADA, etc. | ❌ |
| `familia` | FUTBOL, VOLEY, BASQUET, etc. | ❌ |
| `unidad_medida` | UND | ❌ |
| `peso_kg` | Peso en kg | ❌ |
| `un_bx` | Unidades por caja | ❌ |
| `precio_lista` | Precio de lista | ❌ |
| `moneda` | PEN | ❌ |
| `imagen_url` | URL de imagen | ❌ |

### Hoja 2: DESCUENTOS
| Columna | Descripción |
|---------|-------------|
| `sku` | Código de producto |
| `desc1` | Descuento 1 (decimal, ej: 0.13 = 13%) |
| `desc2` | Descuento 2 |
| `desc3` | Descuento 3 |
| `desc4` | Descuento 4 |

### Hoja 3: PRECIOS_FIJOS
| Columna | Descripción |
|---------|-------------|
| `sku` | Código de producto |
| `precio_fijo` | Precio de remate/liquidación |

### Hoja 4: SKU_CLIENTES (opcional)
| Columna | Descripción |
|---------|-------------|
| `sku` | Código interno |
| `sku_cliente` | Código del cliente |

## ✅ Validaciones

### Campos Obligatorios
- `sku` - No puede estar vacío
- `nombre` - No puede estar vacío
- `categoria` - No puede estar vacío
- `linea` - No puede estar vacío

### Campos Opcionales (valor por defecto)
- `precio_lista` → 0.00 si está vacío
- `un_bx` → 1 si está vacío
- `ean13` → "" (no es error, solo observación)

### SKUs Repetidos
- Solo se considera el primero
- Los duplicados se ignoran

## 📊 JSON Generado

```json
{
  "metadata": {
    "version": "2.0.0",
    "generated_at": "2026-03-24T20:00:00",
    "source_file": "plantilla_precios.xlsx",
    "total_productos": 1088,
    "estadisticas": {
      "sin_ean13": 148,
      "con_descuento": 339,
      "con_precio_fijo": 129
    },
    "changelog": [
      "v2.0.0: Descuentos dinámicos (N columnas)",
      "v2.0.0: Validaciones mejoradas (SKU/nombre/categoria/linea obligatorios)",
      "v2.0.0: SKUs duplicados ignorados",
      "v2.0.0: un_bx vacío asigna 1",
      "v2.0.0: nombre_corto generado con regex",
      "v2.0.0: Consolidación de descuentos y precios fijos"
    ]
  },
  "productos": [
    {
      "orden": 1,
      "sku": "016763",
      "nombre": "FUTBOL PU FUTURE #5",
      "nombre_corto": "Futbol Future #5",
      "ean13": "",
      "categoria": "VINIBALL",
      "subcategoria": "",
      "linea": "PELOTAS",
      "grupo": "IMPORTADA VINIBALL",
      "tipo": "PU",
      "familia": "FUTBOL",
      "unidad_medida": "UND",
      "peso_kg": 0.4,
      "un_bx": 18,
      "precio_lista": 70.0,
      "moneda": "PEN",
      "imagen_url": "",
      "keywords": ["FUTBOL", "FUTURE", "PELOTAS", "VINIBALL"],
      "descuentos": [0, 0, 0, 0],
      "descuento_pct": 0.0,
      "precio_fijo": null,
      "precio_final": 70.0,
      "es_remate": false
    }
  ]
}
```

## 📁 Copiar a proyectos

```bash
# Order XLSX
cp output/catalogo_productos.json ../g360-order-xlsx/public/

# Stock Reporter
cp output/catalogo_productos.json ../g360-stock-reporter/public/

# Devoluciones
cp output/catalogo_productos.json ../g360-return-form/public/
```

## 🛠️ Scripts

### `generar_catalogo.py`
Genera el catálogo consolidado desde el Excel.

**Funcionalidades:**
- Lee hoja PRODUCTOS (datos base)
- Lee hoja DESCUENTOS (descuentos por SKU)
- Lee hoja PRECIOS_FIJOS (remates/liquidaciones)
- Genera `nombre_corto` con regex
- Genera `keywords` automáticamente
- Calcula `precio_final` (descuentos o precio fijo)
- Valida campos obligatorios
- Ignora SKUs duplicados

**Uso:**
```bash
.venv\Scripts\python scripts/generar_catalogo.py -i data/plantilla_precios.xlsx -o output/catalogo_productos.json
```

### `leer_plantilla_precios.py`
Lee precios con mapeo de códigos de cliente.

**Uso:**
```bash
.venv\Scripts\python scripts/leer_plantilla_precios.py -i data/plantilla_precios.xlsx -o output/precios_productos.json
```

## 🧪 Tests Unitarios

### `scripts/tests/test_generar_catalogo.py`
Tests unitarios para validar funcionalidades críticas.

**Ejecutar tests:**
```bash
.venv\Scripts\python -m pytest scripts/tests/ -v
```

**Funciones testeadas:**
- `generar_nombre_corto()` - Validación de regex y reglas
- `validar_ean13()` - Validación de códigos de barras
- Cálculo de descuentos consecutivos
- Validaciones de campos obligatorios

## 🤖 Automatización

### `actualizar_catalogo.bat`
Script batch para automatizar la actualización del catálogo.

**Funcionalidades:**
- Verifica entorno virtual
- Genera catálogo consolidado
- Copia automáticamente a proyectos G360
- Muestra resumen de operación

**Uso:**
```bash
./actualizar_catalogo.bat
```

**Proyectos actualizados automáticamente:**
- g360-order-xlsx
- g360-stock-reporter
- g360-return-form
- comparador_de_precios

## 📝 Notas

- Los descuentos se aplican de forma consecutiva (no acumulativa)
- Si un producto tiene `precio_fijo`, este prevalece sobre los descuentos
- El campo `es_remate` indica si el producto está en liquidación
- El campo `nombre_corto` se genera automáticamente con regex
- El campo `keywords` se genera automáticamente para búsquedas

---
*G360 Ecosystem - CCUSI 2026*