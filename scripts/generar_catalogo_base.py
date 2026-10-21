#!/usr/bin/env python3
"""
G360 Catalog Generator — Versión simplificada
Genera catálogo enriquecido desde PRODUCTOS.xls + SKU_BX.xlsx
Autor: CCUSI | v3.5.0

Fuentes:
  - data/PRODUCTOS.xls       → SKU, nombre, ean13, ean14, peso, linea, grupo, tipo, familia, precio
  - data/SKU_BX.xlsx         → SKU, un_bx (cantidad por caja)
  - API de stock (opcional)  → SKUs con stock físico (G360_STOCK_URL / G360_STOCK_API_KEY)

Regla de inclusión (SKU_BX es la guía primaria de lo que se vende):
  - Se muestra el SKU si está vigente en ERP, o si está descontinuado
    pero curado en SKU_BX (con precio > 0 y no inactivo).
  - Los descontinuados incluidos se marcan con descontinuado=true.
  - Un SKU vigente con STOCK FÍSICO también entra aunque no esté en SKU_BX:
    sin catálogo no se conoce su peso/EAN/caja y hay despacho que hacer.

Filtros absolutos (siempre excluyen):
  - Inactivos (FLG_INACTIVO)
  - Sin precio (<= 0)
  - Líneas de proceso
"""

# Versión única del catálogo. El banner, la ayuda del CLI y el metadata del
# JSON salen de acá: antes cada uno declaraba una versión distinta y el
# README terminaba describiendo un producto que no existía.
VERSION = "3.5.0"

# API de stock por defecto. El universo de stock (SKUs con despacho pendiente)
# es parte del catalogo: sin el, el catalogo sale incompleto y nadie lo nota.
URL_STOCK_DEFAULT = "https://g360-stock-api.onrender.com"

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("ERROR: pip install openpyxl")
    sys.exit(1)

try:
    import xlrd
except ImportError:
    print("ERROR: pip install xlrd")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Taxonomía canónica: línea (CÓDIGO) → categoría
#
# Clave por CODIGO de 2 chars, no por nombre: el codigo es estable y el
# nombre puede venir escrito de varias formas. Esta taxonomia es la MISMA
# que aplica el API de stock (g360-stock-api/app/core/constants.py) para que
# /stock y /catalog no se contradigan, y se publica en el metadata del
# catalogo para que ningun consumidor la duplique a mano.
# ─────────────────────────────────────────────────────────────────────────────
CATEGORIA_POR_LINEA: dict[str, str] = {
    # Negocio core
    "01": "VINIBALL",
    "MA": "VINIBALL",
    "14": "VINIBALL",
    "AD": "VINIBALL",
    "02": "VINIFAN",
    "09": "VINIFAN",
    "11": "VINIFAN",
    "72": "VINIFAN",
    "73": "VINIFAN",
    "75": "VINIFAN",
    "76": "VINIFAN",
    "77": "VINIFAN",
    "78": "VINIFAN",
    "79": "VINIFAN",
    "CE": "REPRESENTADAS",
    "CF": "REPRESENTADAS",
    "CA": "REPRESENTADAS",
    "CB": "REPRESENTADAS",
    "CC": "REPRESENTADAS",
    "CD": "REPRESENTADAS",
    "57": "INDUMENTARIA",
    # OJO: "52" estaba DUPLICADO en este dict (INDUMENTARIA arriba y
    # MATERIALES abajo). En un literal de dict la clave repetida no avisa:
    # gana la última y la taxonomía publicada quedaba mintiendo. Se dejó una
    # sola vez, alineada con g360-stock-api/app/core/constants.py.
    "52": "INDUMENTARIA",
    "85": "REPRESENTADAS",
    "80": "PUBLICIDAD",
    "81": "PUBLICIDAD",
    # Areas operativas (no core)
    "20": "INDUSTRIAL",
    "21": "INDUSTRIAL",
    "22": "INDUSTRIAL",
    "23": "INDUSTRIAL",
    "30": "CIPTECH",
    "31": "CIPTECH",
    "32": "CIPTECH",
    "33": "CIPTECH",
    "34": "CIPTECH",
    "35": "CIPTECH",
    "36": "CIPTECH",
    "37": "CIPTECH",
    "38": "CIPTECH",
    "39": "CIPTECH",
    "40": "MATERIALES",
    "41": "MATERIALES",
    "50": "MATERIALES",
    "51": "MATERIALES",
    "53": "MATERIALES",
    "54": "MATERIALES",
    "55": "MATERIALES",
    "60": "DESCARTE Y VARIOS",
    "65": "DESCARTE Y VARIOS",
    "98": "DESCARTE Y VARIOS",
    "70": "PRODUCCION",
    # 99 (VARIOS) la usan ~50 productos del ERP pero no estaba en el mapa:
    # caian en el default OTROS sin que la taxonomia publicada lo dijera.
    # Se declara explicitamente para que /stock y /catalog la resuelvan igual.
    "99": "OTROS",
}

# Prefijos para lineas no listadas (mas especifico primero).
PREFIJOS_CATEGORIA_AUTO: list[tuple[str, str]] = [
    ("20", "INDUSTRIAL"),
    ("21", "INDUSTRIAL"),
    ("22", "INDUSTRIAL"),
    ("23", "INDUSTRIAL"),
    ("30", "CIPTECH"),
    ("31", "CIPTECH"),
    ("32", "CIPTECH"),
    ("33", "CIPTECH"),
    ("34", "CIPTECH"),
    ("35", "CIPTECH"),
    ("36", "CIPTECH"),
    ("37", "CIPTECH"),
    ("38", "CIPTECH"),
    ("39", "CIPTECH"),
    ("40", "MATERIALES"),
    ("41", "MATERIALES"),
    ("50", "MATERIALES"),
    ("51", "MATERIALES"),
    ("52", "MATERIALES"),
    ("53", "MATERIALES"),
    ("54", "MATERIALES"),
    ("55", "MATERIALES"),
    ("60", "DESCARTE Y VARIOS"),
    ("65", "DESCARTE Y VARIOS"),
    ("98", "DESCARTE Y VARIOS"),
    ("70", "PRODUCCION"),
    ("99", "OTROS"),
]

CATEGORIA_DEFAULT = "OTROS"


def asignar_categoria(codigo_linea: str) -> str:
    """Categoría de un código de línea (misma semántica que el API de stock)."""
    if not codigo_linea:
        return ""
    codigo = str(codigo_linea).split(" - ")[0].strip().upper()
    if not codigo:
        return ""
    if codigo in CATEGORIA_POR_LINEA:
        return CATEGORIA_POR_LINEA[codigo]
    for prefijo, cat in PREFIJOS_CATEGORIA_AUTO:
        if codigo.startswith(prefijo):
            return cat
    return CATEGORIA_DEFAULT


# Prefijos de marca Crayola -> REPRESENTADAS.
# Cualquier SKU cuyo codigo empiece con 'C' (CA/CB/CC/CD/CE/CF/CG...) es
# 100% Crayola en el ERP; la marca sobreescribe la categoria de la linea.
PREFIJO_MARCA_A_CATEGORIA = {
    "C": "REPRESENTADAS",
}


def categoria_de_producto(sku: str, codigo_linea: str) -> str:
    """Categoria de un producto: marca sobreescribe a linea.

    Un SKU Crayola (prefijo C) siempre es REPRESENTADAS, incluso si vive en
    una linea VINIFAN (72/76/77). Un SKU no-Crayola cae a la categoria
    canonica de su linea.

    Nota: esta regla asume que todo SKU que empieza con C es Crayola. Si
    existiera un SKU CIPSA interno con prefijo C (ej: CC09150), quedaria
    mal clasificado. Para evitarlo, esos SKUs deben omitirse en el catalogo
    (no tienen precio o no pasan los filtros de inclusion).
    """
    if str(sku or "").upper().startswith("C"):
        return "REPRESENTADAS"
    return asignar_categoria(codigo_linea)


def codigo_linea_crayola(sku: str) -> str:
    """Codigo de linea propio de un SKU Crayola: CA, CB, CC, CD, CE, CF...

    El prefijo de 2 caracteres SOLO es valido si es alfanumerico con al menos
    una letra: un SKU como "C0150" no define la linea "C0" (codigo de linea
    inexistente que terminaba en la taxonomia como categoria vacia). En ese
    caso se devuelve "" y el SKU cae a la linea real del ERP.
    """
    prefijo = str(sku or "").strip().upper()[:2]
    if len(prefijo) != 2:
        return ""
    if not prefijo[0].isalpha() or not prefijo[1].isalnum():
        return ""
    return prefijo


# Mapeo nombre de línea → código corto (2 chars), derivado del reporte de
# stock del API ("0178 - ARCHIVO" → "78", "01MA - MASCOTAS" → "MA").
# Semilla estática: el reporte es la verdad; el funnel lo sobrescribe
# dinámicamente por nombre si la semilla no cubre una línea nueva.
LINEA_NOMBRE_A_CODIGO = {
    "PELOTAS": "01",
    "FORROS": "02",
    "SENSORIALES": "09",
    "METALICA": "11",
    "OTROS": "14",
    "PEGAMENTOS": "72",
    "DIDACTICOS": "73",
    "DIBUJO": "75",
    "ESCRITURA": "76",
    "PINTURA": "77",
    "ARCHIVO": "78",
    "ACCESORIOS": "79",
    "PUBLICIDAD": "80",
    "KITS": "81",
    "REPRESENTADAS": "85",
    "MASCOTAS": "MA",
    "MANUALIDADES": "CE",
    "SET": "CF",
    "ACCESORIOS DEPORTIVOS": "AD",
    "PRODUCTOS INDUSTRIALES": "20",
    "REPRESENTACIONES INDUSTRIALES": "21",
    "SEGURIDAD Y SEÑALIZACION VIAL": "23",
    "CIPTECH ETIQUETAS": "30",
    "CIPTECH CINTAS": "31",
    "CIPTECH CPEI": "32",
    "CIPTECH CIL": "33",
    "CIPTECH SUPPLY CHAIN": "35",
    "MATERIA PRIMA": "40",
    "MATERIA PRIMA CIPTECH": "41",
    "MATERIALES AUXILIARES": "50",
    "REPUESTO PARA MAQUINA": "51",
    "INSUMOS CONSUMIBLES": "53",
    "HERRAMIENTAS - CONSUMIBLES": "54",
    "REPUESTOS,ACCESORIOS Y SUMINIS": "55",
    "INDUMENTARIA Y EPP": "57",
    "SCRAP": "60",
    "MERCADERIAS VARIAS": "65",
    "ECONOMATO": "66",
    "PRODUCTOS EN PROCESO": "70",
    "PRODUCTOS SIN EMBALAJE": "98",
    "SERVICIOS INDUSTRIALES": "22",
    "LICITACION": "LI",
    "VARIOS": "99",
    "CIPTECH INSPECCION": "34",
    "CIPTECH PID": "36",
    "CIPTECH SOFTWARE": "37",
    "CIPTECH SERVICIOS": "38",
    "CIPTECH OTROS": "39",
}

# Desambiguacion de linea por GRUPO cuando el NOMBRE designa a mas de una linea.
# En el ERP, LINEA="ACCESORIOS" agrupa tanto VINIFAN (tijeras, tajadores...) como
# la linea CD (pinceles Crayola, representada). El ERP NO distingue el codigo
# por LINEA: la diferencia esta en el GRUPO. Regla de negocio:
#   ACCESORIOS + grupo PINCELES -> CD  (Crayola, representada)
#   ACCESORIOS + cualquier otro grupo -> 79 (VINIFAN)
LINEA_GRUPO_A_CODIGO = {
    ("ACCESORIOS", "PINCELES"): "CD",
}


def resolver_codigo_linea_grupo(linea, grupo):
    """Codigo de linea desambiguando por GRUPO (ERP PRODUCTOS.xls).

    Orden:
      1. Desambiguacion por (nombre de linea, grupo) -> manda (caso ACCESORIOS).
      2. Nombre de linea conocido -> codigo.
      3. Codigo explicito embebido en el valor ("01CD" -> "CD").
    """
    lin = str(linea or "").strip().upper()
    grp = str(grupo or "").strip().upper()
    amb = LINEA_GRUPO_A_CODIGO.get((lin, grp))
    if amb:
        return amb
    return LINEA_NOMBRE_A_CODIGO.get(lin, "") or _extraer_codigo_linea(lin)


# Mapa nombre de línea → categoría (derivado del canónico por código).
# Se mantiene por compatibilidad con consumidores que lo usan por nombre.
LINEA_A_CATEGORIA: dict[str, str] = {
    nombre: asignar_categoria(codigo)
    for nombre, codigo in LINEA_NOMBRE_A_CODIGO.items()
}

# Lineas que NO son productos de venta
LINEAS_EXCLUIR = {"PRODUCTOS EN PROCESO", "PRODUCTOS EN PROCESO CIPTECH"}


def generar_nombre_corto(nombre):
    """Elimina prefijos y marcas del nombre para generar versión corta."""
    if not nombre:
        return ""
    texto = nombre.upper().strip()
    texto = re.sub(r"^PELOTA(\s+DE)?\s+", "", texto)
    texto = re.sub(r"\b(N|INFLABLE|PELOTA|BALON|JUEGO)\s+", "", texto)
    texto = re.sub(r"\b(GOMA|PVC|CUERO|PU)\b", "", texto)
    texto = re.sub(r"\bVINIFAN\w*\b", "", texto)
    texto = re.sub(r"\bVFAN\w*\b", "", texto)
    texto = re.sub(r"\bN\b", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto.title()


def generar_keywords(nombre, linea, categoria, extra=""):
    """Genera keywords desde nombre, línea y categoría.

    `extra` permite sumar el código de línea (p.ej. "78") para que buscar
    por código también encuentre el producto.
    """
    keywords = set()
    if nombre:
        for p in nombre.upper().replace("#", "").replace(".", " ").split():
            if len(p) > 2:
                keywords.add(p)
    if linea:
        keywords.add(linea.upper())
    if categoria:
        keywords.add(categoria.upper())
    if extra:
        keywords.add(str(extra).upper())
    return sorted(keywords)


def _safe_float(val, default=0.0):
    """Convierte a float de forma segura, retorna default si falla."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _clean_ean(val):
    """Limpia EAN: quita .0 de floats serializados y espacios."""
    if val is None:
        return ""
    s = str(val).strip()
    if not s or s == "0":
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    return s


def motivo_exclusion(
    flg_inactivo,
    flg_discont,
    precio,
    linea,
    en_bx,
    tiene_stock=False,
    force_incluir=False,
):
    """Motivo por el que un SKU del ERP queda FUERA del catálogo (None si entra).

    Única fuente de las reglas de inclusión: `decidir_inclusion` la usa y el
    generador la usa para auditar cuántas filas se quedaron afuera y por qué.
    """
    if flg_inactivo:
        return "inactivo"
    # El precio es un filtro ABSOLUTO: sin precio no se publica, ni siquiera
    # un Crayola (force_incluir solo salta la regla de descontinuado/BX).
    if precio <= 0:
        return "sin_precio"
    if force_incluir:
        return None
    if linea in LINEAS_EXCLUIR:
        return "linea_proceso"
    if flg_discont and not en_bx and not tiene_stock:
        return "descontinuado_sin_bx_ni_stock"
    return None


def decidir_inclusion(
    flg_inactivo,
    flg_discont,
    precio,
    linea,
    en_bx,
    tiene_stock=False,
    force_incluir=False,
):
    """Decide si un SKU del ERP entra al catálogo.

    SKU_BX es la guía primaria de lo que se vende. Además, un SKU que tiene
    STOCK FÍSICO en el almacén entra igual: hay despacho que hacer y sin
    catálogo no se conoce su peso, EAN ni caja (peso/EAN viven en el catálogo).

    Un descontinuado entra si está curado en SKU_BX **o** si tiene stock
    (queda marcado con descontinuado=true para que se negocie).

    Retorna (incluir, descontinuado).
    """
    if motivo_exclusion(
        flg_inactivo,
        flg_discont,
        precio,
        linea,
        en_bx,
        tiene_stock,
        force_incluir,
    ):
        return False, False
    return True, bool(flg_discont)


def _extraer_codigo_linea(linea):
    """Extrae el código de 2 chars de una línea en cualquier formato.

    "0178 - ARCHIVO" -> "78", "01MA - MASCOTAS" -> "MA", "78" -> "78".
    """
    txt = str(linea or "").strip().upper()
    if not txt:
        return ""
    head = txt.split("-")[0].strip() if "-" in txt else txt
    if re.fullmatch(r"[0-9A-Z]{2}", head):
        return head
    if re.fullmatch(r"01[0-9A-Z]+", head):
        return head[2:]
    return ""


def leer_erp(ruta, bx_skus=None, stock_skus=None):
    """Lee PRODUCTOS.xls y retorna (productos, errores, erp_skus, exclusiones).

    bx_skus:    SKUs curados en SKU_BX (guía primaria de lo que se vende).
    stock_skus: SKUs que tienen stock fisico (API de stock). Entran al
                catalogo aunque no esten en SKU_BX: sin catalogo no se conoce
                su peso/EAN/caja y hay despacho que hacer.
    exclusiones: dict {motivo: n} con cuántas filas del ERP quedaron fuera y
                por qué. Sin esto no se puede auditar por qué el catálogo tiene
                N SKUs y no otros.
    """
    productos = []
    errores = []
    skus_vistos = {}
    erp_skus = set()
    bx_skus = bx_skus or set()
    stock_skus = stock_skus or set()
    lineas_desconocidas = set()
    exclusiones: dict[str, int] = {}
    try:
        wb = xlrd.open_workbook(ruta)
        ws = wb.sheet_by_index(0)
        for r in range(1, ws.nrows):
            sku = str(ws.cell_value(r, 0)).strip()
            if not sku:
                continue
            nombre = str(ws.cell_value(r, 1)).strip()
            if not nombre:
                continue
            ean13 = _clean_ean(ws.cell_value(r, 2))
            ean14 = _clean_ean(ws.cell_value(r, 3))
            peso_kg = _safe_float(ws.cell_value(r, 4))
            linea = str(ws.cell_value(r, 5)).strip()
            grupo = str(ws.cell_value(r, 6)).strip()
            tipo = str(ws.cell_value(r, 7)).strip()
            familia = str(ws.cell_value(r, 8)).strip()
            flg_inactivo = str(ws.cell_value(r, 9)).strip().lower() == "checked"
            flg_discont = str(ws.cell_value(r, 10)).strip().lower() == "checked"
            precio = _safe_float(ws.cell_value(r, 11))

            if sku in skus_vistos:
                exclusiones["duplicado_erp"] = exclusiones.get("duplicado_erp", 0) + 1
                continue
            skus_vistos[sku] = r
            erp_skus.add(sku)

            # C* (Crayola) entra sin importar BX/stock (es representada y hay
            # que llevarla), pero el precio sigue siendo filtro absoluto.
            force_crayola = sku.upper().startswith("C")
            motivo = motivo_exclusion(
                flg_inactivo,
                flg_discont,
                precio,
                linea.upper(),
                sku in bx_skus,
                sku in stock_skus,
                force_incluir=force_crayola,
            )
            if motivo:
                exclusiones[motivo] = exclusiones.get(motivo, 0) + 1
                continue
            descontinuado = bool(flg_discont)

            linea_upper = linea.upper()
            # C* usan su prefijo como linea propia (CA, CB, CC, CD, CE, CF)
            # para que cada sub-marca Crayola sea identificable.
            codigo = codigo_linea_crayola(sku) if force_crayola else ""
            if not codigo:
                codigo = resolver_codigo_linea_grupo(linea_upper, grupo)
                if not codigo:
                    lineas_desconocidas.add(linea_upper)
            categoria = (
                categoria_de_producto(sku, codigo) if codigo else CATEGORIA_DEFAULT
            )

            productos.append(
                {
                    "sku": sku,
                    "nombre": nombre,
                    "ean13": ean13,
                    "ean14": ean14,
                    "peso_kg": peso_kg,
                    # `linea` es el CODIGO canonico (2 chars); el nombre legible
                    # va aparte. Antes iba el nombre y el codigo en otro campo:
                    # esa ambiguedad hacia que cada consumidor lo interpretara
                    # distinto y la linea apareciera como nombre o como codigo.
                    "linea": codigo or linea_upper,
                    "linea_nombre": linea_upper,
                    "grupo": grupo,
                    "tipo": tipo,
                    "familia": familia,
                    "categoria": categoria,
                    "precio": round(precio, 2),
                    "descontinuado": descontinuado,
                    "linea_codigo": codigo,
                }
            )
        wb.release_resources()
        if lineas_desconocidas:
            print(
                f"  WARN: {len(lineas_desconocidas)} linea(s) sin codigo conocido: "
                f"{sorted(lineas_desconocidas)[:8]}"
            )
        print(f"  ERP: {len(productos)} productos válidos")
    except Exception as e:
        errores.append(str(e))
    return productos, errores, erp_skus, exclusiones


def leer_unbx(ruta):
    """Lee SKU_BX.xlsx y retorna dict {sku: orden}, {sku: un_bx} y {sku: estado_linea}.
    ORDEN = clave-valor de orden indice maestro (col 0 de SKU_BX.xlsx)."""
    orden_map = {}
    unbx_map = {}
    estado_map = {}
    try:
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            sku = str(row[1] or "").strip()
            un_bx_raw = row[2]
            estado = str(row[3] or "").strip() if len(row) > 3 else ""
            orden = row[0] if len(row) > 0 else None
            if sku:
                try:
                    orden_map[sku] = int(orden) if orden is not None else 0
                except (ValueError, TypeError):
                    orden_map[sku] = 0
            if sku and un_bx_raw is not None and str(un_bx_raw).strip():
                try:
                    unbx_map[sku] = int(un_bx_raw)
                except (ValueError, TypeError):
                    pass
            if sku and estado:
                estado_map[sku] = estado
        wb.close()
        print(f"  SKU_BX: {len(orden_map)} SKUs con orden (indice maestro)")
        print(f"  SKU_BX: {len(unbx_map)} SKUs con un_bx definido")
        print(f"  SKU_BX: {len(estado_map)} SKUs con estado_linea definido")
    except Exception as e:
        print(f"  WARN: No se pudo leer SKU_BX: {e}")
    return orden_map, unbx_map, estado_map


def generar_output(
    productos,
    unbx_map,
    estado_map,
    orden_map,
    ruta_salida,
    exclusiones=None,
    universo_stock=None,
):
    """Genera el JSON de catálogo completo."""
    estadisticas = {
        "sin_ean13": 0,
        "con_ean14": 0,
        "sin_unbx": 0,
        "con_unbx": 0,
        "descontinuados": 0,
        "sin_linea_codigo": 0,
        "por_categoria": {},
        "por_linea": {},
        "por_estado_linea": {},
    }

    productos_final = []
    for p in productos:
        tiene_unbx = p["sku"] in unbx_map
        un_bx = unbx_map.get(p["sku"], 1)
        if tiene_unbx:
            estadisticas["con_unbx"] += 1
        else:
            estadisticas["sin_unbx"] += 1
        if not p["ean13"]:
            estadisticas["sin_ean13"] += 1
        if p["ean14"]:
            estadisticas["con_ean14"] += 1
        if p.get("descontinuado"):
            estadisticas["descontinuados"] += 1
        if not p.get("linea_codigo"):
            estadisticas["sin_linea_codigo"] += 1

        cat = p["categoria"]
        lin = p["linea"]
        estadisticas["por_categoria"][cat] = (
            estadisticas["por_categoria"].get(cat, 0) + 1
        )
        estadisticas["por_linea"][lin] = estadisticas["por_linea"].get(lin, 0) + 1

        est = estado_map.get(p["sku"], "")
        if est:
            estadisticas["por_estado_linea"][est] = (
                estadisticas["por_estado_linea"].get(est, 0) + 1
            )

        productos_final.append(
            {
                "sku": p["sku"],
                "nombre": p["nombre"],
                "nombre_corto": generar_nombre_corto(p["nombre"]),
                "ean13": p["ean13"],
                "ean14": p["ean14"],
                "categoria": p["categoria"],
                # linea = CODIGO canonico | linea_nombre = nombre legible
                "linea": p["linea"],
                "linea_nombre": p.get("linea_nombre", ""),
                "grupo": p["grupo"],
                "tipo": p["tipo"],
                "familia": p["familia"],
                "un_bx": un_bx,
                "orden": orden_map.get(p["sku"], 0),
                "estado_linea": est,
                "peso_kg": p["peso_kg"],
                "precio": p["precio"],
                "descontinuado": p.get("descontinuado", False),
                "linea_codigo": p.get("linea_codigo", ""),
                "keywords": generar_keywords(
                    p["nombre"],
                    # El nombre de la linea (no el codigo) es lo que la gente
                    # busca ("PELOTAS", "ARCHIVO"). El codigo va aparte, como
                    # extra, para que buscar "01" tambien encuentre el SKU.
                    p.get("linea_nombre", "") or p.get("linea", ""),
                    p["categoria"],
                    extra=p.get("linea", ""),
                ),
            }
        )

    productos_final.sort(
        key=lambda x: (x.get("orden", 0) == 0, x.get("orden", 0) or 0, x["sku"])
    )

    metadata = {
        "version": VERSION,
        "generated_at": datetime.now().isoformat(),
        "source_erp": "PRODUCTOS.xls",
        "source_un_bx": "SKU_BX.xlsx",
        "total_productos": len(productos_final),
        "estadisticas": estadisticas,
        # Taxonomia publicada: los consumidores la leen de aca en vez de
        # mantener su propia copia (que terminaba contradiciendose).
        "categorias_por_linea": dict(CATEGORIA_POR_LINEA),
        "lineas_nombre_a_codigo": dict(LINEA_NOMBRE_A_CODIGO),
        # Desambiguacion por GRUPO: "ACCESORIOS" designa a mas de una linea
        # en el ERP; el grupo desempata. Serializado como "LINEA|GRUPO".
        "lineas_grupo_a_codigo": {
            f"{lin}|{grp}": cod for (lin, grp), cod in LINEA_GRUPO_A_CODIGO.items()
        },
        # Trazabilidad: que filas del ERP quedaron fuera y por que, y si el
        # universo de stock entro en la generacion. Sin esto no se puede
        # explicar por que el catalogo tiene N SKUs.
        "exclusiones": dict(exclusiones or {}),
        "universo_stock": dict(universo_stock or {"incluido": False}),
    }

    output = {"metadata": metadata, "productos": productos_final}

    p = Path(ruta_salida)
    previo = None
    if p.exists():
        # Guarda el total anterior para avisar si el catalogo se achica: una
        # caida suele significar que faltó una fuente (p.ej. el universo de
        # stock) y no que el ERP tenga menos productos.
        try:
            previo = json.loads(p.read_text(encoding="utf-8")).get("metadata", {})
        except (OSError, json.JSONDecodeError):
            previo = None
        bak = p.with_suffix(f".{datetime.now():%Y%m%d_%H%M%S}.bak.json")
        if bak.exists():
            bak.unlink()
        p.rename(bak)
        print(f"  Backup: {bak.name}")

    with open(p, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Guardado: {ruta_salida} ({p.stat().st_size / 1024:.1f} KB)")

    if previo and previo.get("total_productos"):
        antes = int(previo["total_productos"])
        despues = len(productos_final)
        if despues < antes:
            print(
                f"  ALERTA: el catalogo se achico de {antes} a {despues} SKUs "
                f"(-{antes - despues}). Revisa el universo de stock y el ERP."
            )
        elif despues > antes:
            print(
                f"  OK: el catalogoCREcio de {antes} a {despues} SKUs (+{despues - antes})."
            )
    return output


def leer_universo_stock(api_url=None, api_key=None, timeout=90):
    """SKUs con stock fisico segun el API de stock (opcional).

    Sirve para que entren al catalogo los SKU que tienen despacho pendiente
    aunque no esten en la guia SKU_BX: sin catalogo no se conoce su peso,
    EAN ni caja, y hay carga que hacer.

    Config: G360_STOCK_URL / G360_STOCK_API_KEY (o --stock-url / --stock-key).
    La clave de lectura cae a API_KEY: el API acepta la clave administrativa
    para leer stock, asi que una sola variable alcanza para todo el flujo.
    Sin clave no se consulta: se sigue con el criterio de SKU_BX.
    """
    url = api_url or os.environ.get("G360_STOCK_URL", "") or URL_STOCK_DEFAULT
    key = (
        api_key
        or os.environ.get("G360_STOCK_API_KEY", "")
        or os.environ.get("API_KEY", "")
    )
    if not url:
        return set(), "sin URL configurada"
    if not key:
        return set(), "sin G360_STOCK_API_KEY ni API_KEY"
    try:
        import requests

        r = requests.get(
            f"{url.rstrip('/')}/api/v1/stock",
            params={"fuente": "todas"},
            headers={"x-api-key": key, "Accept": "application/json"},
            timeout=timeout,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        return (
            {
                str(i.get("sku", "")).strip()
                for i in items
                if str(i.get("sku", "")).strip()
            },
            "",
        )
    except Exception as e:  # noqa: BLE001
        return set(), str(e)


def main():
    ap = argparse.ArgumentParser(description=f"G360 Catalog Generator v{VERSION}")
    ap.add_argument("--erp", "-e", default="data/PRODUCTOS.xls", help="Archivo ERP")
    ap.add_argument("--unbx", "-u", default="data/SKU_BX.xlsx", help="Archivo SKU_BX")
    ap.add_argument(
        "--output", "-o", default="output/catalogo_productos.json", help="JSON salida"
    )
    ap.add_argument(
        "--validate-only", "-v", action="store_true", help="Solo validar, no generar"
    )
    ap.add_argument(
        "--stock-url",
        default=os.environ.get("G360_STOCK_URL", ""),
        help="API de stock para traer el universo con stock fisico",
    )
    ap.add_argument(
        "--stock-key",
        default=os.environ.get("G360_STOCK_API_KEY", ""),
        help="Clave de lectura del API de stock (G360_STOCK_API_KEY)",
    )
    ap.add_argument(
        "--sin-universo-stock",
        action="store_true",
        help="No consultar el API: solo se incluye lo que esta en SKU_BX",
    )
    a = ap.parse_args()

    print("=" * 50)
    print(f"G360 CATALOG GENERATOR v{VERSION}")
    print("=" * 50)
    print(f"ERP:      {a.erp}")
    print(f"SKU_BX:   {a.unbx}")
    print(f"Output:   {a.output}")
    print()

    # Leer fuentes (BX primero: es la guía primaria de inclusión)
    print("Leyendo fuentes...")
    orden_map, unbx_map, estado_map = leer_unbx(a.unbx)

    # Universo con stock fisico: los SKU con despacho pendiente tambien
    # necesitan catalogo (peso/EAN/caja para despachar).
    stock_skus = set()
    universo_stock = {"incluido": False, "skus": 0, "error": ""}
    if a.sin_universo_stock:
        print("  Universo de stock: omitido (--sin-universo-stock)")
        universo_stock["error"] = "omitido por --sin-universo-stock"
    else:
        stock_skus, err = leer_universo_stock(a.stock_url, a.stock_key)
        if err:
            print(f"  Universo de stock: no disponible ({err}) -> solo SKU_BX")
            print(
                "  WARN: el catalogo va a quedar INCOMPLETO: los SKUs con stock "
                "que no esten en SKU_BX no entran."
            )
            universo_stock["error"] = err
        else:
            print(f"  Universo de stock: {len(stock_skus)} SKUs con stock fisico")
            universo_stock = {
                "incluido": True,
                "skus": len(stock_skus),
                "error": "",
            }

    productos, errs, erp_skus, exclusiones = leer_erp(
        a.erp, bx_skus=set(orden_map), stock_skus=stock_skus
    )
    if errs:
        print(f"Errores: {errs}")

    huerfanos = sorted(set(orden_map) - erp_skus)
    if huerfanos:
        print(
            f"  WARN: {len(huerfanos)} SKUs en SKU_BX no existen en ERP (se omiten): "
            f"{', '.join(huerfanos[:10])}"
            f"{'...' if len(huerfanos) > 10 else ''}"
        )

    if not productos:
        print("ERROR: No hay productos válidos")
        sys.exit(1)

    print(f"\nTotal productos válidos: {len(productos)}")
    print(f"  Con orden definido:    {len(orden_map)}")
    print(f"  Con un_bx definido:    {len(unbx_map)}")
    print(f"  Sin un_bx (default 1): {len(productos) - len(unbx_map)}")
    if exclusiones:
        print("  Exclusiones del ERP:")
        for motivo, cnt in sorted(exclusiones.items(), key=lambda x: -x[1]):
            print(f"    {motivo}: {cnt}")

    if a.validate_only:
        print("\nValidación completada")
        return

    # Generar output
    print("\nGenerando catálogo...")
    output = generar_output(
        productos,
        unbx_map,
        estado_map,
        orden_map,
        a.output,
        exclusiones=exclusiones,
        universo_stock=universo_stock,
    )

    print(f"\n{'=' * 50}")
    print("CATÁLOGO GENERADO")
    print(f"{'=' * 50}")
    meta = output["metadata"]
    print(f"Productos:    {meta['total_productos']}")
    est = meta["estadisticas"]
    print(f"  Con ean14:  {est['con_ean14']}")
    print(f"  Sin ean13:  {est['sin_ean13']}")
    print(f"  Con un_bx:  {est['con_unbx']}")
    print(f"  Sin un_bx:  {est['sin_unbx']}")
    print(f"  Descontinuados:           {est['descontinuados']}")
    print(f"  Sin linea_codigo:          {est['sin_linea_codigo']}")
    uni = meta.get("universo_stock", {})
    print(
        f"  Universo de stock:         "
        f"{'incluido (' + str(uni.get('skus', 0)) + ' SKUs)' if uni.get('incluido') else 'NO INCLUIDO'}"
    )
    print(f"\nCategorías:")
    for cat, cnt in sorted(est["por_categoria"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")
    print(f"\nListo!")


if __name__ == "__main__":
    main()
