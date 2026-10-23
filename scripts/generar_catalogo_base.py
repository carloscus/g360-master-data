#!/usr/bin/env python3
"""
G360 Catalog Generator
Genera el catálogo maestro (el ALLOWLIST real del API) desde las fuentes
disponibles. El API de stock no tiene allowlist propia: lo que no está en
este catálogo se ve como `sin_catalogo` (precio 0, caja 1, sin peso/EAN).
Autor: CCUSI | v3.7.0

Fuentes (se leen por NOMBRE de columna, ver scripts/contratos.py):
  - data/PRODUCTOS.xls       → SKU, nombre, ean13, ean14, peso, linea, grupo, tipo, familia, precio
  - data/SKU_BX.xlsx         → SKU, un_bx (cantidad por caja) + orden de la guía
                               + dimensiones de caja (largo/ancho/alto → m³)
  - API de stock / cache S1  → stock y predespacho por SKU + ficha mínima
                               (descripción, línea, grupo, tipo, familia, UM)

Regla de inclusión (una sola, en `motivo_exclusion`):

    en catálogo  <=>  en guía  ∨  stock > 0  ∨  compromiso > 0
                      ∨  (vigente ∧ precio > 0)

O sea: el catálogo cubre TODO lo que se puede vender, despachar o cotizar.
Las filas que entran por movimiento (stock/compromiso/guía) pero sin precio
se publican igual, marcadas `por_activar=true` y `cotizable=false`: hay
producto y hay que activarlo, pero todavía no se cotiza.

Filtros absolutos (siempre excluyen):
  - Inactivos (FLG_INACTIVO): al pasar a inactivo el producto desaparece
    del ERP, así que no existe "inactivo con stock".
  - Líneas de proceso (materia prima en proceso, productos en proceso).

Semáforo de venta (`categoria_venta`): VINIBALL / VINIFAN / REPRESENTADAS
son las tres categorías de negocio; todo el resto queda en REVISION_VENTA.
"""

# Versión única del catálogo. El banner, la ayuda del CLI y el metadata del
# JSON salen de acá: antes cada uno declaraba una versión distinta y el
# README terminaba describiendo un producto que no existía.
VERSION = "3.8.0"

# Caida del universo vs la corrida anterior que dispara la alerta: el API
# pudo devolver un reporte parcial con HTTP 200 (corte a medias). La
# cobertura no lo ve (se calcula contra este mismo universo), asi que se
# compara aca. No bloquea por si solo: el validador lo convierte en error.
UMBRAL_CAIDA_UNIVERSO = 0.15

# API de stock por defecto. El universo de stock (SKUs con despacho pendiente)
# es parte del catalogo: sin el, el catalogo sale incompleto y nadie lo nota.
URL_STOCK_DEFAULT = "https://g360-stock-api.onrender.com"

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from contratos import (
    CONTRATO_ERP,
    CONTRATO_SKU_BX,
    ErrorContrato,
    calcular_m3,
    cargar_almacenes,
    cargar_guia_ignorados,
    huella_fuente,
    limpiar_texto,
    resolver_xls,
    resolver_xlsx,
    sku_texto,
)

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
    # CG = JUGUETES (Silly Putty y demás juguetes Crayola). Se validó sobre
    # los 68.003 artículos del KARDEX: la regla "todo C* es Crayola" tiene 0
    # falsos positivos y CG es una sub-marca más, no una línea ajena.
    "CG": "REPRESENTADAS",
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
    # OTROS es el estado terminal de la ficha S1 sin taxonomia (ver fallback
    # en productos_desde_universo): tiene que estar declarado, o el validador
    # rechaza esos productos por "linea no publicada" aunque sean legitimos.
    "OTROS": "OTROS",
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

    Regla validada sobre los 68.003 artículos del KARDEX: TODO SKU que
    empieza con C es Crayola (CA/CB/CC/CD/CE/CF/CG y las sub-marcas que
    aparezcan), sin falsos positivos. Si algún día apareciera un SKU interno
    con prefijo C, `validar_taxonomia.py` lo delata (linea mixta / categoria
    incoherente) antes de subir el catálogo.
    """
    if str(sku or "").upper().startswith("C"):
        return "REPRESENTADAS"
    return asignar_categoria(codigo_linea)


# Categorias de negocio que se VENDEN. Todo lo demás (MATERIALES, CIPTECH,
# INDUSTRIAL, DESCARTE Y VARIOS, OTROS...) queda en REVISION_VENTA: puede
# estar en el catálogo (allowlist) pero necesita una revisión comercial
# antes de cotizarse.
CATEGORIAS_VENTA = ("VINIBALL", "VINIFAN", "REPRESENTADAS")
CATEGORIA_VENTA_REVISION = "REVISION_VENTA"


def categoria_venta(categoria: str) -> str:
    """Semaforo de venta: VINIBALL/VINIFAN/REPRESENTADAS o REVISION_VENTA."""
    cat = str(categoria or "").strip().upper()
    return cat if cat in CATEGORIAS_VENTA else CATEGORIA_VENTA_REVISION


def normalizar_texto(valor) -> str:
    """Mayúsculas, sin acentos ni signos, espacios colapsados.

    Sirve para comparar nombres entre fuentes que escriben distinto el mismo
    producto ("FANTASÍA A-4" vs "FANTASIA A4").
    """
    txt = unicodedata.normalize("NFKD", str(valor or "").upper())
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"[^0-9A-Z ]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def nombre_sin_codigo(valor) -> str:
    """'03 - BORRADOR' -> 'BORRADOR'.

    El reporte S1 entrega grupo/tipo/familia con el código adelante; el
    catálogo publica el nombre limpio (y antes /stock y /catalog mostraban
    el mismo campo en dos formatos distintos).
    """
    txt = str(valor or "").strip()
    if not txt:
        return ""
    sin_codigo = re.sub(r"^[0-9A-Z]{2,4}\s*-\s*", "", txt).strip()
    return sin_codigo or txt


# NOTA DE DISEÑO (SKU exactos, sin parecidos):
# Antes existia un "metodo D" que enlazaba 03077D con 03077 por similitud
# de nombre. Se elimino: cada SKU es exacto y standalone, y la linea 98
# (sin embalaje) esta fuera del semaforo vendible. Un SKU que termina en
# D es un producto mas, sin vinculo con nada que "se le parezca".


def codigo_linea_crayola(sku: str) -> str:
    """Codigo de linea propio de un SKU Crayola: CA, CB, CC, CD, CE, CF...

    El prefijo de 2 caracteres SOLO es valido si son DOS LETRAS: un SKU como
    "C0150" no define la linea "C0" (codigo de linea inexistente que quedaba
    colgado en la taxonomia). En ese caso se devuelve "" y el SKU cae a la
    linea real del ERP.
    """
    prefijo = str(sku or "").strip().upper()[:2]
    if len(prefijo) != 2:
        return ""
    if not prefijo.isalpha():
        return ""
    return prefijo


def taxonomias_crayola_nuevas(productos) -> dict[str, str]:
    """Sub-marcas Crayola detectadas que NO estan en CATEGORIA_POR_LINEA.

    Si aparece una sub-marca nueva (CG, CH...) su linea tiene que estar
    declarada en la taxonomia: si no, el consumidor que resuelva linea ->
    categoria la deja en el default (OTROS) y el SKU queda con linea y
    categoria incoherentes. Se declaran como REPRESENTADAS (son Crayola)
    y se avisa para que queden fijas en CATEGORIA_POR_LINEA.
    """
    nuevos: dict[str, str] = {}
    for p in productos:
        sku = str(p.get("sku", "")).upper()
        if not sku.startswith("C"):
            continue
        codigo = codigo_linea_crayola(sku)
        if not codigo or codigo in CATEGORIA_POR_LINEA:
            continue
        nuevos.setdefault(codigo, "REPRESENTADAS")
    return nuevos


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
    "JUGUETES": "CG",
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

# Los mismos procesos por CODIGO: el reporte S1 trae "0171 - PRODUCTOS EN
# PROCESO CIPTECH", no el nombre. Un SKU de proceso nunca se publica aunque
# tenga stock (es materia prima, no producto vendible).
LINEAS_PROCESO_CODIGOS = {"70", "71"}


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
    tiene_compromiso=False,
):
    """Motivo por el que un SKU del ERP queda FUERA del catálogo (None si entra).

    Única fuente de las reglas de inclusión: `decidir_inclusion` la usa y el
    generador la usa para auditar cuántas filas se quedaron afuera y por qué.

    La regla completa (v3.6.0):

        entra  <=>  en guía ∨ stock > 0 ∨ compromiso > 0
                    ∨ (vigente ∧ precio > 0)

    El precio ya NO decide la presencia: decide la COTIZABILIDAD. Un SKU con
    stock o compromiso sin precio entra marcado `por_activar` (hay producto
    físico y hay que activarlo); el flag `cotizable` lo deja fuera de toda
    cotización hasta que tenga precio.
    """
    if flg_inactivo:
        return "inactivo"
    if linea in LINEAS_EXCLUIR:
        return "linea_proceso"
    if force_incluir:
        return None
    if en_bx:
        return None
    if tiene_stock:
        return None
    if tiene_compromiso:
        return None
    if not flg_discont and precio > 0:
        return None
    if flg_discont:
        return "descontinuado_sin_guia_ni_stock"
    return "sin_precio_ni_movimiento"


def decidir_inclusion(
    flg_inactivo,
    flg_discont,
    precio,
    linea,
    en_bx,
    tiene_stock=False,
    force_incluir=False,
    tiene_compromiso=False,
):
    """Decide si un SKU del ERP entra al catálogo.

    Entra si está en la guía (SKU_BX), si tiene stock o compromiso (hay
    despacho/venta que atender) o si está vigente y tiene precio (se puede
    cotizar hoy). Un descontinuado entra si está en la guía o tiene
    movimiento, y queda marcado con descontinuado=true para que se negocie.

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
        tiene_compromiso,
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


def _es_checked(valor) -> bool:
    """Flag del ERP: la celda dice 'Checked' / 'Unchecked'."""
    return limpiar_texto(valor).lower() == "checked"


def _avisar_columnas(columnas, etiqueta):
    """Deja en el log que columnas se mapearon y que se ignoro.

    Es la evidencia de que se leyo lo que se cree: sin esta linea, un contrato
    resuelto a otra columna se ve igual que uno correcto.
    """
    for aviso in columnas.avisos:
        print(f"  AVISO {etiqueta}: {aviso}")
    for campo in columnas.faltantes_opcionales:
        print(f"  AVISO {etiqueta}: columna ausente, no se leyo '{campo}'")
    print(f"  {etiqueta}: columnas OK ({columnas.resumen()})")


def leer_erp(ruta, bx_skus=None, stock_skus=None, compromiso_skus=None):
    """Lee PRODUCTOS.xls y retorna (productos, errores, erp_skus, exclusiones, erp_todos).

    bx_skus:          SKUs curados en SKU_BX (guía de lo que se vende).
    stock_skus:       SKUs con stock físico (reporte S1).
    compromiso_skus:  SKUs con predespacho/compromiso (reporte S1).
    exclusiones:      dict {motivo: n} con cuántas filas del ERP quedaron
                      fuera y por qué. Sin esto no se puede auditar por qué
                      el catálogo tiene N SKUs y no otros.
    erp_todos:        TODAS las filas válidas del ERP (aunque queden fuera),
                      para decidir `por_activar` sin releer el archivo.
    """
    productos = []
    errores = []
    skus_vistos = {}
    erp_skus = set()
    erp_todos: dict[str, dict] = {}
    bx_skus = bx_skus or set()
    stock_skus = stock_skus or set()
    compromiso_skus = compromiso_skus or set()
    lineas_desconocidas = set()
    exclusiones: dict[str, int] = {}
    try:
        wb = xlrd.open_workbook(ruta)
        # Por NOMBRE de columna, no por posicion: un export con una columna
        # nueva ya no puede producir un catalogo corrupto en silencio.
        columnas, ws = resolver_xls(wb, CONTRATO_ERP)
        _avisar_columnas(columnas, "ERP")
        for r in range(CONTRATO_ERP.fila_header, ws.nrows):
            fila = ws.row_values(r)
            sku = sku_texto(columnas.valor(fila, "sku"))
            if not sku:
                continue
            nombre = limpiar_texto(columnas.valor(fila, "nombre"))
            if not nombre:
                continue
            ean13 = _clean_ean(columnas.valor(fila, "ean13"))
            ean14 = _clean_ean(columnas.valor(fila, "ean14"))
            peso_kg = _safe_float(columnas.valor(fila, "peso_kg"))
            linea = limpiar_texto(columnas.valor(fila, "linea"))
            grupo = limpiar_texto(columnas.valor(fila, "grupo"))
            tipo = limpiar_texto(columnas.valor(fila, "tipo"))
            familia = limpiar_texto(columnas.valor(fila, "familia"))
            flg_inactivo = _es_checked(columnas.valor(fila, "inactivo"))
            flg_discont = _es_checked(columnas.valor(fila, "descontinuado"))
            precio = _safe_float(columnas.valor(fila, "precio"))

            if sku in skus_vistos:
                exclusiones["duplicado_erp"] = exclusiones.get("duplicado_erp", 0) + 1
                continue
            skus_vistos[sku] = r
            erp_skus.add(sku)
            erp_todos[sku] = {
                "sku": sku,
                "nombre": nombre,
                "linea": linea.upper(),
                "grupo": grupo,
                "precio": precio,
                "inactivo": flg_inactivo,
                "descontinuado": flg_discont,
            }

            # C* (Crayola) entra sin importar guía/stock: es representada y
            # hay que llevarla. El precio ya no excluye (v3.6.0): sin precio
            # queda `por_activar` / no cotizable, pero presente.
            force_crayola = sku.upper().startswith("C")
            motivo = motivo_exclusion(
                flg_inactivo,
                flg_discont,
                precio,
                linea.upper(),
                sku in bx_skus,
                sku in stock_skus,
                force_incluir=force_crayola,
                tiene_compromiso=sku in compromiso_skus,
            )
            if motivo:
                exclusiones[motivo] = exclusiones.get(motivo, 0) + 1
                continue
            descontinuado = bool(flg_discont)

            linea_upper = linea.upper()
            # C* usan su prefijo como linea propia (CA, CB, CC, CD, CE, CF, CG)
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
                    "um": "",
                    "origen": "erp",
                }
            )
        wb.release_resources()
        if lineas_desconocidas:
            print(
                f"  WARN: {len(lineas_desconocidas)} linea(s) sin codigo conocido: "
                f"{sorted(lineas_desconocidas)[:8]}"
            )
        print(f"  ERP: {len(productos)} productos válidos")
    except ErrorContrato as e:
        # Fatal y explicito: una fuente que no cumple el contrato no puede
        # producir un catalogo "parecido".
        errores.append(str(e))
    except Exception as e:
        errores.append(f"{type(e).__name__}: {e}")
    return productos, errores, erp_skus, exclusiones, erp_todos


def productos_desde_universo(universo, productos_incluidos, erp_todos):
    """Ficha mínima desde el reporte S1 para SKUs con movimiento que no estaban.

    Un SKU que llega con stock (o compromiso) y no existe en el ERP no se
    puede cotizar, pero hay que poder verlo, buscarlo y despacharlo: se arma
    su ficha con lo que el reporte S1 ya trae (nombre, línea con código,
    grupo, tipo, familia, UM) y queda marcado `por_activar`. Es el caso
    "SKU no registrado que llega con stock": hoy sale como `sin_catalogo`
    (precio 0, caja 1); con esto queda con línea y familia.
    """
    ya_incluidos = {p["sku"] for p in productos_incluidos}
    nuevos = []
    for sku, datos in sorted(universo.items()):
        if sku in ya_incluidos:
            continue
        if sku in erp_todos:
            # Existe en el ERP pero quedó fuera por regla (línea de proceso
            # o inactivo). Las líneas de proceso nunca se publican.
            linea_erp = erp_todos[sku].get("linea", "")
            if linea_erp in LINEAS_EXCLUIR:
                continue
        linea_raw = str(datos.get("linea") or "").strip().upper()
        if _extraer_codigo_linea(linea_raw) in LINEAS_PROCESO_CODIGOS:
            continue
        nombre = str(datos.get("descripcion") or "").strip()
        if not nombre:
            continue
        linea_raw = str(datos.get("linea") or "").strip().upper()
        # Misma regla que el ERP: un C* toma su sub-marca Crayola como línea
        # (CA/CB/CC/CD/CE/CF/CG), no la línea genérica donde lo reporta S1.
        codigo = codigo_linea_crayola(sku) if sku.upper().startswith("C") else ""
        if not codigo:
            codigo = _extraer_codigo_linea(linea_raw)
        if not codigo:
            codigo = _extraer_codigo_linea(
                str(erp_todos.get(sku, {}).get("linea", "")) or linea_raw
            )
        linea_nombre = normalizar_texto(nombre_sin_codigo(linea_raw)) or linea_raw
        if not codigo and not linea_nombre:
            # S1 no trajo taxonomia y no hay de donde sacarla (p.ej. un D
            # huerfano como 03273D cuya base no existe en ninguna fuente):
            # OTROS/REVISION_VENTA en vez de linea vacia, que rompe los
            # filtros y el contrato del API. Queda visible para revision
            # comercial (test_linea_y_categoria_no_estan_vacias lo vigila).
            codigo = linea_nombre = CATEGORIA_DEFAULT
            categoria = CATEGORIA_DEFAULT
        else:
            categoria = (
                categoria_de_producto(sku, codigo) if codigo else CATEGORIA_DEFAULT
            )
        nuevos.append(
            {
                "sku": sku,
                "nombre": nombre,
                "ean13": "",
                "ean14": "",
                "peso_kg": 0.0,
                "linea": codigo or linea_nombre,
                "linea_nombre": linea_nombre,
                "grupo": nombre_sin_codigo(datos.get("grupo", "")),
                "tipo": nombre_sin_codigo(datos.get("tipo", "")),
                "familia": nombre_sin_codigo(datos.get("familia", "")),
                "categoria": categoria,
                # Sin precio en ninguna fuente: se publica sin cotizar.
                "precio": 0.0,
                "descontinuado": bool(
                    erp_todos.get(sku, {}).get("descontinuado", False)
                ),
                "linea_codigo": codigo,
                "um": str(datos.get("um") or "").strip().upper(),
                "origen": "s1",
            }
        )
    return nuevos


@dataclass
class DatosSKUBX:
    """Lo que aporta la guia comercial (SKU_BX.xlsx).

    `orden` es el indice maestro (y la prueba de `en_guia`), `un_bx` las
    unidades por caja y `caja` las dimensiones/volumen ya calculados.
    """

    orden: dict[str, int] = field(default_factory=dict)
    un_bx: dict[str, int] = field(default_factory=dict)
    estado: dict[str, str] = field(default_factory=dict)
    caja: dict[str, dict] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    @property
    def skus(self) -> set[str]:
        return set(self.orden)


def leer_unbx(ruta):
    """Lee SKU_BX.xlsx por nombre de columna y arma DatosSKUBX.

    Acepta la plantilla vieja (ORDEN, SKU, UN_BX, ESTADO_LINEA) y la nueva,
    que agrega LARGO_CM/ANCHO_CM/ALTO_CM/PESO_CAJA_KG. Si las dimensiones
    estan, el volumen se calcula aca (no se confia en la formula de Excel:
    una celda pegada como valor no se recalcula nunca).
    """
    datos = DatosSKUBX()
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        columnas, hoja = resolver_xlsx(libro, CONTRATO_SKU_BX)
        _avisar_columnas(columnas, "SKU_BX")
        primera = CONTRATO_SKU_BX.fila_header + 1
        for n, fila in enumerate(
            hoja.iter_rows(min_row=primera, values_only=True), start=primera
        ):
            crudo_sku = columnas.valor(fila, "sku")
            sku = sku_texto(crudo_sku)
            if not sku:
                continue
            if isinstance(crudo_sku, (int, float)):
                datos.avisos.append(
                    f"fila {n}: SKU numerico ({crudo_sku}); si tenia ceros a la "
                    "izquierda ya se perdieron en el archivo"
                )
            orden = columnas.valor(fila, "orden")
            try:
                datos.orden[sku] = int(orden) if orden not in (None, "") else 0
            except (ValueError, TypeError):
                datos.orden[sku] = 0
                datos.avisos.append(f"fila {n}: ORDEN no numerico ({orden!r})")
            un_bx = _entero(columnas.valor(fila, "un_bx"))
            if un_bx:
                datos.un_bx[sku] = un_bx
            estado = limpiar_texto(columnas.valor(fila, "estado_linea"))
            if estado:
                datos.estado[sku] = estado
            largo = _safe_float(columnas.valor(fila, "largo_cm"))
            ancho = _safe_float(columnas.valor(fila, "ancho_cm"))
            alto = _safe_float(columnas.valor(fila, "alto_cm"))
            m3 = calcular_m3(largo, ancho, alto)
            if m3 is None:
                if largo or ancho or alto:
                    datos.avisos.append(
                        f"fila {n} ({sku}): caja incompleta "
                        f"(largo={largo}, ancho={ancho}, alto={alto}); no se "
                        "publica volumen"
                    )
                continue
            peso_caja = _safe_float(columnas.valor(fila, "peso_caja_kg"))
            datos.caja[sku] = {
                "largo_cm": round(largo, 2),
                "ancho_cm": round(ancho, 2),
                "alto_cm": round(alto, 2),
                "m3_caja": m3,
                "m3_unidad": round(m3 / un_bx, 6) if un_bx else None,
                "peso_caja_kg": round(peso_caja, 3) if peso_caja > 0 else None,
            }
    finally:
        libro.close()

    for aviso in datos.avisos[:10]:
        print(f"  AVISO SKU_BX: {aviso}")
    if len(datos.avisos) > 10:
        print(f"  AVISO SKU_BX: ... y {len(datos.avisos) - 10} mas")
    print(f"  SKU_BX: {len(datos.orden)} SKUs con orden (indice maestro)")
    print(f"  SKU_BX: {len(datos.un_bx)} SKUs con un_bx definido")
    print(f"  SKU_BX: {len(datos.estado)} SKUs con estado_linea definido")
    if datos.caja:
        print(f"  SKU_BX: {len(datos.caja)} SKUs con caja (largo/ancho/alto/m3)")
    return datos


def _entero(valor) -> int:
    """Entero tolerante ('18', 18.0, '18.0'); 0 si no se puede."""
    texto = limpiar_texto(valor)
    if not texto:
        return 0
    try:
        return int(float(texto))
    except (ValueError, TypeError):
        return 0


def generar_output(
    productos,
    unbx_map,
    estado_map,
    orden_map,
    ruta_salida,
    exclusiones=None,
    universo_stock=None,
    taxonomia_extra=None,
    universo=None,
    caja_map=None,
    fuentes=None,
    erp_todos=None,
):
    """Genera el JSON de catálogo completo.

    `universo` es el detalle del reporte S1 {sku: {stock, predespacho, ...}}:
    con él se publican los flags de negocio (compromiso, cotizable,
    por_activar) y el snapshot de stock que justificó cada inclusión.
    `caja_map` son las dimensiones/volumen por SKU (SKU_BX) y `fuentes` la
    huella (sha256, filas, fecha) de cada archivo que se leyó.
    """
    universo = universo or {}
    caja_map = caja_map or {}
    estadisticas = {
        "sin_ean13": 0,
        "con_ean14": 0,
        "sin_unbx": 0,
        "con_unbx": 0,
        "con_caja": 0,
        "descontinuados": 0,
        "sin_linea_codigo": 0,
        "con_linea_otros": 0,
        "en_guia": 0,
        "con_compromiso": 0,
        "por_activar": 0,
        "cotizables": 0,
        # Sin enlaces por parecido: siempre 0. Se mantiene la clave para no
        # romper consumidores del metadata.
        "derivados": 0,
        "solo_s1": 0,
        "por_categoria": {},
        "por_categoria_venta": {},
        "por_linea": {},
        "por_estado_linea": {},
    }

    productos_final = []
    for p in productos:
        tiene_unbx = p["sku"] in unbx_map
        un_bx = unbx_map.get(p["sku"], 1)
        caja = caja_map.get(p["sku"])
        if caja:
            estadisticas["con_caja"] += 1
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
        if p.get("linea_codigo") == "OTROS":
            # S1 no trajo taxonomia para este SKU (ficha minima con fallback).
            # Si este numero es alto, el reporte S1 o su parseo tienen un
            # problema: revisar el universo antes de publicar.
            estadisticas["con_linea_otros"] += 1

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

        # ── Flags de negocio (v3.6.0) ─────────────────────────────────
        mov = universo.get(p["sku"], {})
        stock_snap = int(mov.get("stock") or 0)
        predespacho_snap = int(mov.get("predespacho") or 0)
        precio = float(p.get("precio") or 0.0)
        origen = p.get("origen", "erp")
        en_guia = p["sku"] in orden_map
        compromiso = predespacho_snap > 0
        vigente = not bool(p.get("descontinuado"))
        # `por_activar` = está en el catálogo pero todavía NO se puede
        # cotizar: no tiene precio. El origen ('erp'/'s1') ya queda en
        # su propio campo.
        cotizable = precio > 0
        por_activar = not cotizable
        # Sin enlaces: derivado_de siempre vacio (cada SKU es exacto y
        # standalone; se mantiene la clave por compatibilidad con el API).
        derivado_de = ""
        cat_venta = categoria_venta(cat)

        if en_guia:
            estadisticas["en_guia"] += 1
        if compromiso:
            estadisticas["con_compromiso"] += 1
        if por_activar:
            estadisticas["por_activar"] += 1
        if cotizable:
            estadisticas["cotizables"] += 1
        if origen == "s1":
            estadisticas["solo_s1"] += 1
        estadisticas["por_categoria_venta"][cat_venta] = (
            estadisticas["por_categoria_venta"].get(cat_venta, 0) + 1
        )

        productos_final.append(
            {
                "sku": p["sku"],
                "nombre": p["nombre"],
                "nombre_corto": generar_nombre_corto(p["nombre"]),
                "ean13": p["ean13"],
                "ean14": p["ean14"],
                "categoria": p["categoria"],
                "categoria_venta": cat_venta,
                # linea = CODIGO canonico | linea_nombre = nombre legible
                "linea": p["linea"],
                "linea_nombre": p.get("linea_nombre", ""),
                "grupo": p["grupo"],
                "tipo": p["tipo"],
                "familia": p["familia"],
                "um": p.get("um", ""),
                "un_bx": un_bx,
                "orden": orden_map.get(p["sku"], 0),
                "estado_linea": est,
                "peso_kg": p["peso_kg"],
                # Caja y volumen (SKU_BX). `un_bx` es unidades por caja; esto
                # es el tamano fisico. Va como objeto para no confundirlo con
                # el `caja` (unidades) que usa el API.
                "dimensiones_caja": caja,
                "precio": precio,
                "descontinuado": bool(p.get("descontinuado", False)),
                "linea_codigo": p.get("linea_codigo", ""),
                # Flags de negocio: explican POR QUE el SKU está publicado.
                "en_guia": en_guia,
                "compromiso": compromiso,
                "cotizable": cotizable,
                "vigente": vigente,
                "por_activar": por_activar,
                "derivado_de": derivado_de,
                "origen": origen,
                # Snapshot del reporte S1 que justificó la inclusión (el
                # stock vivo lo sirve /api/v1/stock, esto es solo trazabilidad).
                "stock_snapshot": stock_snap,
                "predespacho_snapshot": predespacho_snap,
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

    # ── Invariante de cobertura ──────────────────────────────────────────
    # TODO SKU con stock o compromiso tiene que estar en el catálogo (salvo
    # líneas de proceso, que no son vendibles). Se publica la lista y los
    # faltantes para que el validador y el consumidor puedan auditarlo sin
    # volver a leer el reporte S1.
    incluidos = {p["sku"] for p in productos_final}
    universo_skus = []
    faltantes = []
    for sku in sorted(universo):
        datos = universo.get(sku, {})
        if (datos.get("stock") or 0) <= 0 and (datos.get("predespacho") or 0) <= 0:
            continue
        # Misma regla que productos_desde_universo: si el ERP lo marca como
        # línea de proceso, no cuenta para la cobertura.
        erp = erp_todos or {}
        if sku in erp:
            if erp[sku].get("linea", "") in LINEAS_EXCLUIR:
                continue
        linea = _extraer_codigo_linea(datos.get("linea", ""))
        if linea in LINEAS_PROCESO_CODIGOS:
            continue
        universo_skus.append(sku)
        if sku not in incluidos:
            faltantes.append(sku)
    if faltantes:
        print(
            f"  ALERTA: {len(faltantes)} SKUs con stock/compromiso quedaron "
            f"FUERA del catalogo: {', '.join(faltantes[:10])}"
            f"{'...' if len(faltantes) > 10 else ''}"
        )

    # Taxonomia publicada: los consumidores la leen de aca en vez de
    # mantener su propia copia (que terminaba contradiciendose).
    # `taxonomia_extra` son las sub-marcas Crayola nuevas detectadas: se
    # publican ya clasificadas para que ningun consumidor las deje en el
    # default (y el generador avisa para que queden fijas en el codigo).
    taxonomia_publicada = dict(CATEGORIA_POR_LINEA)
    taxonomia_publicada.update(taxonomia_extra or {})

    # Almacenes como VARIABLE: la lista vive en config/almacenes.json y se
    # publica en el metadata para que stock-api y las apps la lean del
    # catalogo en vez de llevarla hardcodeada en su codigo.
    config_almacenes = cargar_almacenes()
    for aviso in config_almacenes.get("avisos", []):
        print(f"  AVISO almacenes: {aviso}")

    metadata = {
        "version": VERSION,
        "generated_at": datetime.now().isoformat(),
        "source_erp": "PRODUCTOS.xls",
        "source_un_bx": "SKU_BX.xlsx",
        "source_stock": "reporte S1 (stock + predespacho)",
        # Que archivo exacto se leyo (sha256 + fecha): el catalogo queda
        # trazable aunque el archivo se reemplace despues.
        "fuentes": list(fuentes or []),
        "total_productos": len(productos_final),
        "estadisticas": estadisticas,
        "categorias_por_linea": taxonomia_publicada,
        # Semaforo de venta: las 3 categorias de negocio + revision.
        "categorias_venta": list(CATEGORIAS_VENTA),
        "categoria_venta_revision": CATEGORIA_VENTA_REVISION,
        # Almacenes publicados (VARIABLE de config/almacenes.json): quien
        # consuma stock/almacenes toma la lista de aca.
        "almacenes": {
            "principal": config_almacenes["almacen_principal"],
            "almacenes": config_almacenes["almacenes"],
            "fuente": config_almacenes["fuente"],
        },
        # Regla de inclusion publicada: el consumidor puede explicar por que
        # un SKU esta en el catalogo sin leer el codigo del generador.
        "regla_inclusion": (
            "en guia ∨ stock > 0 ∨ compromiso > 0 ∨ (vigente ∧ precio > 0)"
        ),
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
        # Invariante publicado: la lista del universo que justificó el
        # catálogo y lo que quedó afuera (debe ser []). Con esto el
        # validador detecta una cobertura rota sin releer el reporte S1.
        "universo_skus": universo_skus,
        "cobertura_faltante": faltantes,
    }

    # Caida del universo vs la corrida anterior (mismo archivo de salida).
    # Un universo parcial con HTTP 200 es indistinguible de uno real si no
    # se compara: la cobertura se calcula contra ESTE universo y daria OK.
    try:
        previo_meta = {}
        if Path(ruta_salida).exists():
            previo_meta = json.loads(Path(ruta_salida).read_text(encoding="utf-8")).get(
                "metadata", {}
            )
    except (OSError, ValueError):
        previo_meta = {}
    uni_meta = metadata.get("universo_stock")
    if isinstance(uni_meta, dict) and uni_meta.get("incluido"):
        n_ahora = int(uni_meta.get("skus", 0) or 0)
        uni_antes = previo_meta.get("universo_stock", {})
        n_antes = (
            int(uni_antes.get("skus", 0) or 0) if isinstance(uni_antes, dict) else 0
        )
        if n_antes > 0:
            variacion = (n_ahora - n_antes) / n_antes
            uni_meta["previo_skus"] = n_antes
            uni_meta["variacion"] = round(variacion, 4)
            if variacion <= -UMBRAL_CAIDA_UNIVERSO:
                uni_meta["alerta_caida"] = (
                    f"el universo cayo {variacion:.0%} vs la corrida anterior "
                    f"({n_antes} -> {n_ahora} SKUs): posible reporte parcial "
                    "del API; revisar antes de publicar"
                )
                print(f"  ALERTA: {uni_meta['alerta_caida']}")
            elif variacion:
                print(
                    f"  Universo vs anterior: {n_antes} -> {n_ahora} ({variacion:+.0%})"
                )

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
                f"  OK: el catalogo crecio de {antes} a {despues} SKUs (+{despues - antes})."
            )
    return output


def leer_universo_stock(
    api_url=None, api_key=None, timeout=120, intentos=3, cache_local=None
):
    """Universo de stock: {sku: detalle} segun el API o el cache local del S1.

    Devuelve (universo, error). `universo` es un dict:

        {sku: {"stock": int, "predespacho": int, "descripcion": str,
               "um": str, "linea": str, "grupo": str, "tipo": str,
               "familia": str}}

    Sirve para que entren al catalogo los SKU con stock o compromiso aunque
    no esten en la guia SKU_BX ni en el ERP: sin catalogo no se conoce su
    peso, EAN ni caja, y ademas hay despacho/venta que atender.

    Orden de lectura:
      1. `cache_local` (--s1-cache / G360_S1_CACHE): el JSON del reporte S1
         que el API de stock guarda en data/stock_cache.json. Es la via
         offline (el ERP y el KARDEX tambien son exports manuales).
      2. API: endpoint compacto /api/v1/stock/skus (v3.6.0) y, si el API
         desplegado todavia no lo tiene, /api/v1/stock como respaldo.
      3. Si el API falla, se intenta el cache local del repo hermano.

    Reintenta: /stock es pesado y en Render free-tier da 504 por cold start.
    Un fallo puntual NO debe dejar el catalogo incompleto en silencio.
    """
    import time

    def _desde_cache(ruta):
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
        return _agregar_universo(data.get("datos", {}), origen=f"cache {ruta}")

    if cache_local:
        ruta = Path(cache_local)
        if not ruta.exists():
            return {}, f"cache S1 no existe: {ruta}"
        try:
            return _desde_cache(ruta), ""
        except (OSError, json.JSONDecodeError) as e:
            return {}, f"cache S1 ilegible: {e}"

    url = api_url or os.environ.get("G360_STOCK_URL", "") or URL_STOCK_DEFAULT
    key = (
        api_key
        or os.environ.get("G360_STOCK_API_KEY", "")
        or os.environ.get("API_KEY", "")
    )
    if not url:
        return {}, "sin URL configurada"
    if not key:
        return {}, "sin G360_STOCK_API_KEY ni API_KEY"
    try:
        import requests
    except ImportError:
        return {}, "falta requests (pip install requests)"

    ultimo_error = ""
    for intento in range(1, intentos + 1):
        try:
            r = requests.get(
                f"{url.rstrip('/')}/api/v1/stock/skus",
                params={"fuente": "todas"},
                headers={"x-api-key": key, "Accept": "application/json"},
                timeout=timeout,
            )
            if r.status_code == 404:
                # API desplegado sin el endpoint compacto: usar el pesado.
                r = requests.get(
                    f"{url.rstrip('/')}/api/v1/stock",
                    params={"fuente": "todas"},
                    headers={"x-api-key": key, "Accept": "application/json"},
                    timeout=timeout,
                )
            r.raise_for_status()
            payload = r.json()
            items = payload.get("items", [])
            # Diagnostico de frescura: si el API sirve cache viejo o un
            # parseo sin taxonomia, se ve ACA (no despues, en el catalogo).
            meta_api = payload.get("metadata", {}) or {}
            if meta_api:
                print(
                    f"  Universo del API: descarga {meta_api.get('fecha_descarga', '?')} "
                    f"| cache_expirado={meta_api.get('cache_expirado', '?')} "
                    f"| enriquecido={meta_api.get('enriquecido', '?')}"
                )
            universo: dict[str, dict] = {}
            for i in items:
                sku = str(i.get("sku", "")).strip()
                if not sku:
                    continue
                d = universo.setdefault(
                    sku,
                    {
                        "stock": 0,
                        "predespacho": 0,
                        "descripcion": "",
                        "um": "",
                        "linea": "",
                        "grupo": "",
                        "tipo": "",
                        "familia": "",
                    },
                )
                # El endpoint compacto trae los totales; /stock trae el
                # desglose por almacen.
                if "almacenes" in i:
                    d["stock"] += sum(int(a.get("stock") or 0) for a in i["almacenes"])
                    d["predespacho"] += sum(
                        int(a.get("predespacho") or 0) for a in i["almacenes"]
                    )
                else:
                    d["stock"] += int(i.get("stock") or 0)
                    d["predespacho"] += int(i.get("predespacho") or 0)
                for campo in ("descripcion", "um", "linea", "grupo", "tipo", "familia"):
                    if not d[campo] and i.get(campo):
                        d[campo] = str(i[campo]).strip()
            return universo, ""
        except Exception as e:  # noqa: BLE001
            ultimo_error = str(e)
            if intento < intentos:
                print(
                    f"    intento {intento}/{intentos} fallido ({ultimo_error}); "
                    f"reintentando en {intento * 5}s"
                )
                time.sleep(intento * 5)

    # Ultimo recurso: el cache local del repo hermano (si existe).
    hermano = (
        Path(__file__).resolve().parent.parent.parent
        / "g360-stock-api"
        / "data"
        / "stock_cache.json"
    )
    if hermano.exists():
        try:
            universo = _desde_cache(hermano)
            print(
                f"  WARN: API de stock no respondio ({ultimo_error}). "
                f"Se uso el cache local {hermano}."
            )
            return universo, f"API no disponible ({ultimo_error}); cache local usado"
        except (OSError, json.JSONDecodeError):
            pass
    return {}, ultimo_error


def _agregar_universo(datos, origen=""):
    """Consolida el reporte S1 (dict almacen -> sku -> item) por SKU.

    `datos` es el formato del cache del API de stock:
    {"121": {"79103": {"stock": ..., "predespacho": ..., "descripcion": ...}}}.
    El stock y el predespacho se suman entre almacenes; la ficha se toma del
    primer almacen que la traiga (es la misma en todos).
    """
    universo: dict[str, dict] = {}
    for _almacen, prods in (datos or {}).items():
        for sku, item in (prods or {}).items():
            sku = str(sku or "").strip()
            if not sku:
                continue
            d = universo.setdefault(
                sku,
                {
                    "stock": 0,
                    "predespacho": 0,
                    "descripcion": "",
                    "um": "",
                    "linea": "",
                    "grupo": "",
                    "tipo": "",
                    "familia": "",
                },
            )
            d["stock"] += int(item.get("stock") or 0)
            d["predespacho"] += int(item.get("predespacho") or 0)
            for campo in ("descripcion", "um", "linea", "grupo", "tipo", "familia"):
                if not d[campo] and item.get(campo):
                    d[campo] = str(item[campo]).strip()
    if origen:
        print(f"  Universo de stock: {len(universo)} SKUs ({origen})")
    return universo


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
        "--s1-cache",
        default=os.environ.get("G360_S1_CACHE", ""),
        help=(
            "JSON del reporte S1 (data/stock_cache.json del API de stock). "
            "Via offline: no consulta el API. Tambien G360_S1_CACHE."
        ),
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
    if a.s1_cache:
        print(f"S1 cache: {a.s1_cache}")
    print()

    # Leer fuentes (BX primero: es la guía de lo que se vende).
    # v3.8: si existe `data/SKU_PRECIOS.xlsx` (archivo consolidado con 2 hojas:
    # SKU_LOGISTICA + SKU_PRECIOS) se usa el lector unificado. Si no, se cae
    # al lector viejo (SKU_BX.xlsx) para mantener compatibilidad con data/.
    print("Leyendo fuentes...")
    ruta_unificada = Path(a.unbx).with_name("SKU_PRECIOS.xlsx")
    guia_caja: dict[str, dict] = {}
    if ruta_unificada.exists():
        try:
            from leer_sku_precios import leer_sku_precios as leer_unificado

            datos_unificados = leer_unificado(str(ruta_unificada))
            orden_map = datos_unificados.orden
            unbx_map = datos_unificados.un_bx
            estado_map = datos_unificados.estado
            guia_caja = datos_unificados.caja
            print(f"  Fuente unificada: {ruta_unificada.name}")
        except ErrorContrato as e:
            print()
            print(str(e))
            sys.exit(1)
    else:
        if not Path(a.unbx).exists():
            print()
            print(f"ERROR: no existe la guia comercial: {a.unbx}")
            print("  Sin guia no hay orden comercial ni un_bx para el catálogo.")
            print("  Creala: python scripts\\crear_plantillas.py --instalar")
            print(
                "  O migra los archivos viejos: "
                "python scripts\\crear_plantillas.py --migrar"
            )
            sys.exit(1)
        try:
            guia = leer_unbx(a.unbx)
        except ErrorContrato as e:
            print()
            print(str(e))
            sys.exit(1)
        orden_map = guia.orden
        unbx_map = guia.un_bx
        estado_map = guia.estado
        guia_caja = guia.caja
    if not orden_map:
        print(
            "  WARN: la guia comercial esta VACIA (0 SKUs): el catalogo saldra "
            "sin en_guia y con un_bx=1 en todo"
        )

    # Universo de stock + compromiso: los SKU con despacho o venta pendiente
    # tambien necesitan catalogo (peso/EAN/caja para despachar).
    universo: dict[str, dict] = {}
    universo_stock = {"incluido": False, "skus": 0, "error": ""}
    if a.sin_universo_stock:
        print("  Universo de stock: omitido (--sin-universo-stock)")
        universo_stock["error"] = "omitido por --sin-universo-stock"
    else:
        universo, err = leer_universo_stock(
            a.stock_url, a.stock_key, cache_local=a.s1_cache
        )
        if err and not universo:
            print(f"  Universo de stock: no disponible ({err}) -> solo SKU_BX")
            print(
                "  WARN: el catalogo va a quedar INCOMPLETO: los SKUs con stock "
                "que no esten en SKU_BX no entran."
            )
            universo_stock["error"] = err
        else:
            con_stock = sum(1 for d in universo.values() if d["stock"] > 0)
            con_compromiso = sum(1 for d in universo.values() if d["predespacho"] > 0)
            print(
                f"  Universo de stock: {len(universo)} SKUs "
                f"({con_stock} con stock, {con_compromiso} con compromiso)"
            )
            universo_stock = {
                "incluido": True,
                "skus": len(universo),
                "con_stock": con_stock,
                "con_compromiso": con_compromiso,
                "error": err,
            }
            # Taxonomia del universo: si el API sirve un parseo sin lineas
            # (codigo viejo o cache anterior al parser por anclas), los S1
            # caen a OTROS y los D no se enlazan. Se avisa fuerte aca.
            sin_tax = sum(
                1 for d in universo.values() if not str(d.get("linea") or "").strip()
            )
            universo_stock["sin_taxonomia_s1"] = sin_tax
            if universo and sin_tax / len(universo) >= 0.15:
                universo_stock["alerta_sin_taxonomia"] = (
                    f"{sin_tax}/{len(universo)} SKUs del universo sin taxonomia S1: "
                    "el API puede estar sirviendo parseo viejo o cache anterior; "
                    "revisar deploy/refresh del API antes de publicar"
                )
                print(f"  ALERTA: {universo_stock['alerta_sin_taxonomia']}")

    stock_skus = {s for s, d in universo.items() if d["stock"] > 0}
    compromiso_skus = {s for s, d in universo.items() if d["predespacho"] > 0}

    productos, errs, erp_skus, exclusiones, erp_todos = leer_erp(
        a.erp,
        bx_skus=set(orden_map),
        stock_skus=stock_skus,
        compromiso_skus=compromiso_skus,
    )
    if errs:
        print("\nERRORES al leer el ERP:")
        for e in errs:
            print(str(e) if "\n" in str(e) else f"  {e}")

    # Ficha mínima desde el reporte S1 para los SKU con movimiento que no
    # entraron por el ERP (no existen o están en línea de proceso).
    desde_s1 = productos_desde_universo(universo, productos, erp_todos)
    if desde_s1:
        print(f"  Ficha mínima desde S1: {len(desde_s1)} SKUs con movimiento")
        productos.extend(desde_s1)

    # Sin enlaces por parecido: cada SKU es exacto y standalone (linea 98
    # incluida). Nada se deriva de nada por similitud de nombre o codigo.
    huerfanos = sorted(set(orden_map) - erp_skus)
    if huerfanos:
        # Los ya revisados a mano (config/guia_ignorados.json) no se vuelven
        # a avisar: el paso 0 ya dio el detalle con el motivo.
        ignorados = cargar_guia_ignorados()
        silenciados = [s for s in huerfanos if s in ignorados]
        huerfanos = [s for s in huerfanos if s not in ignorados]
        if silenciados:
            print(
                f"  ... {len(silenciados)} revisado(s) (guia_ignorados.json): "
                "no se avisan"
            )
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

    # Sub-marcas Crayola nuevas: se publican ya clasificadas y se avisa para
    # que queden fijas en CATEGORIA_POR_LINEA (y en el API de stock).
    crayolas_nuevas = taxonomias_crayola_nuevas(productos)
    if crayolas_nuevas:
        print("\n  ALERTA: sub-marca(s) Crayola nueva(s) detectada(s):")
        for cod, cat in sorted(crayolas_nuevas.items()):
            print(f"    {cod} -> {cat}")
        print(
            "    Agregalas a CATEGORIA_POR_LINEA (scripts/generar_catalogo_base.py)\n"
            "    y a CATEGORIAS (g360-stock-api/app/core/constants.py) para que\n"
            "    la taxonomia quede fija y no dependa de esta generacion."
        )

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
        taxonomia_extra=crayolas_nuevas,
        universo=universo,
        caja_map=guia_caja,
        fuentes=[huella_fuente(a.erp), huella_fuente(a.unbx)],
        erp_todos=erp_todos,
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
    print(f"  Con caja (largo/ancho/alto/m3): {est['con_caja']}")
    print(f"  Descontinuados:           {est['descontinuados']}")
    print(f"  Sin linea_codigo:          {est['sin_linea_codigo']}")
    print(f"  Con linea OTROS (S1 sin taxonomia): {est['con_linea_otros']}")
    print(f"  En guia (SKU_BX):          {est['en_guia']}")
    print(f"  Con compromiso:            {est['con_compromiso']}")
    print(f"  Cotizables:                {est['cotizables']}")
    print(f"  Por activar:               {est['por_activar']}")
    print(
        f"  Derivados (enlaces por parecido): {est['derivados']} (siempre 0: SKU exactos)"
    )
    print(f"  Solo S1 (sin ERP):         {est['solo_s1']}")
    uni = meta.get("universo_stock", {})
    print(
        f"  Universo de stock:         "
        f"{'incluido (' + str(uni.get('skus', 0)) + ' SKUs)' if uni.get('incluido') else 'NO INCLUIDO'}"
    )
    print("\nCategorías:")
    for cat, cnt in sorted(est["por_categoria"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")
    print("\nSemáforo de venta:")
    for cat, cnt in sorted(est["por_categoria_venta"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")
    print("\nListo!")


if __name__ == "__main__":
    main()
