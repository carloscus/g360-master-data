#!/usr/bin/env python3
"""
G360 Catalog Generator — Versión simplificada
Genera catálogo enriquecido desde PRODUCTOS.xls + SKU_BX.xlsx
Autor: CCUSI | v3.2.0

Fuentes:
  - data/PRODUCTOS.xls       → SKU, nombre, ean13, ean14, peso, linea, grupo, tipo, familia, precio
  - data/SKU_BX.xlsx         → SKU, un_bx (cantidad por caja)

Regla de inclusión (SKU_BX es la guía primaria de lo que se vende):
  - Se muestra el SKU si está vigente en ERP, o si está descontinuado
    pero curado en SKU_BX (con precio > 0 y no inactivo).
  - Los descontinuados incluidos se marcan con descontinuado=true.

Filtros absolutos (siempre excluyen):
  - Inactivos (FLG_INACTIVO)
  - Sin precio (<= 0)
  - Líneas de proceso
"""
import argparse
import json
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

# Mapeo de línea → categoría de negocio
LINEA_A_CATEGORIA = {
    # VINIBALL
    "PELOTAS": "VINIBALL", "MASCOTAS": "VINIBALL",
    "ACCESORIOS DEPORTIVOS": "VINIBALL",
    # VINIFAN
    "ARCHIVO": "VINIFAN", "FORROS": "VINIFAN", "ESCRITURA": "VINIFAN",
    "PINTURA": "VINIFAN", "DIBUJO": "VINIFAN", "DIDACTICOS": "VINIFAN",
    "MANUALIDADES": "VINIFAN", "PEGAMENTOS": "VINIFAN", "ACCESORIOS": "VINIFAN",
    "METALICA": "VINIFAN", "SENSORIALES": "VINIFAN", "KITS": "VINIFAN",
    # REPRESENTADAS
    "REPRESENTADAS": "REPRESENTADAS", "PUBLICIDAD": "REPRESENTADAS",
    "PRODUCTOS INDUSTRIALES": "REPRESENTADAS", "MATERIALES AUXILIARES": "REPRESENTADAS",
    "OTROS": "REPRESENTADAS", "VARIOS": "REPRESENTADAS", "SET": "REPRESENTADAS",
}

# Mapeo nombre de línea → código corto (2 chars), derivado del reporte de
# stock del API ("0178 - ARCHIVO" → "78", "01MA - MASCOTAS" → "MA").
# Semilla estática: el reporte es la verdad; el funnel lo sobrescribe
# dinámicamente por nombre si la semilla no cubre una línea nueva.
LINEA_NOMBRE_A_CODIGO = {
    "PELOTAS": "01", "FORROS": "02", "SENSORIALES": "09", "METALICA": "11",
    "OTROS": "14", "PEGAMENTOS": "72", "DIDACTICOS": "73", "DIBUJO": "75",
    "ESCRITURA": "76", "PINTURA": "77", "ARCHIVO": "78", "ACCESORIOS": "79",
    "PUBLICIDAD": "80", "KITS": "81", "REPRESENTADAS": "85",
    "MASCOTAS": "MA", "MANUALIDADES": "CE", "SET": "CF", "ACCESORIOS DEPORTIVOS": "AD",
    "PRODUCTOS INDUSTRIALES": "20", "REPRESENTACIONES INDUSTRIALES": "21",
    "SEGURIDAD Y SEÑALIZACION VIAL": "23", "CIPTECH ETIQUETAS": "30",
    "CIPTECH CINTAS": "31", "CIPTECH CPEI": "32", "CIPTECH CIL": "33",
    "CIPTECH SUPPLY CHAIN": "35", "MATERIA PRIMA": "40",
    "MATERIALES AUXILIARES": "50", "INDUMENTARIA Y EPP": "57", "SCRAP": "60",
    "MERCADERIAS VARIAS": "65", "ECONOMATO": "66", "PRODUCTOS EN PROCESO": "70",
    "PRODUCTOS SIN EMBALAJE": "98",
}

# Lineas que NO son productos de venta
LINEAS_EXCLUIR = {"PRODUCTOS EN PROCESO", "PRODUCTOS EN PROCESO CIPTECH"}


def generar_nombre_corto(nombre):
    """Elimina prefijos y marcas del nombre para generar versión corta."""
    if not nombre:
        return ""
    texto = nombre.upper().strip()
    texto = re.sub(r'^PELOTA(\s+DE)?\s+', '', texto)
    texto = re.sub(r'\b(N|INFLABLE|PELOTA|BALON|JUEGO)\s+', '', texto)
    texto = re.sub(r'\b(GOMA|PVC|CUERO|PU)\b', '', texto)
    texto = re.sub(r'\bVINIFAN\w*\b', '', texto)
    texto = re.sub(r'\bVFAN\w*\b', '', texto)
    texto = re.sub(r'\bN\b', '', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto.title()


def generar_keywords(nombre, linea, categoria):
    """Genera keywords desde nombre y categorías."""
    keywords = set()
    if nombre:
        for p in nombre.upper().replace("#", "").replace(".", " ").split():
            if len(p) > 2:
                keywords.add(p)
    if linea:
        keywords.add(linea.upper())
    if categoria:
        keywords.add(categoria.upper())
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


def decidir_inclusion(flg_inactivo, flg_discont, precio, linea, en_bx):
    """Decide si un SKU del ERP entra al catálogo.

    SKU_BX es la guía primaria de lo que se vende: un descontinuado se
    incluye solo si está curado en SKU_BX (llegó stock que se puede vender).

    Retorna (incluir, descontinuado).
    """
    if flg_inactivo:
        return False, False
    if precio <= 0:
        return False, False
    if linea in LINEAS_EXCLUIR:
        return False, False
    if flg_discont and not en_bx:
        return False, False
    return True, flg_discont


def leer_erp(ruta, bx_skus=None):
    """Lee PRODUCTOS.xls y retorna (productos, errores, erp_skus).

    bx_skus: set de SKUs curados en SKU_BX (guía primaria). Los
    descontinuados solo se incluyen si están en este set.
    """
    productos = []
    errores = []
    skus_vistos = {}
    erp_skus = set()
    bx_skus = bx_skus or set()
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
            flg_inactivo = str(ws.cell_value(r, 9)).strip().lower() == 'checked'
            flg_discont = str(ws.cell_value(r, 10)).strip().lower() == 'checked'
            precio = _safe_float(ws.cell_value(r, 11))

            if sku in skus_vistos:
                continue
            skus_vistos[sku] = r
            erp_skus.add(sku)

            incluir, descontinuado = decidir_inclusion(
                flg_inactivo, flg_discont, precio, linea, sku in bx_skus)
            if not incluir:
                continue

            linea_upper = linea.upper()
            if linea_upper not in LINEA_A_CATEGORIA:
                print(f"  WARN: Linea desconocida '{linea}' (SKU {sku}), asignando REPRESENTADAS")

            categoria = LINEA_A_CATEGORIA.get(linea_upper, "REPRESENTADAS")

            productos.append({
                "sku": sku,
                "nombre": nombre,
                "ean13": ean13,
                "ean14": ean14,
                "peso_kg": peso_kg,
                "linea": linea,
                "grupo": grupo,
                "tipo": tipo,
                "familia": familia,
                "categoria": categoria,
                "precio": round(precio, 2),
                "descontinuado": descontinuado,
                "linea_codigo": LINEA_NOMBRE_A_CODIGO.get(linea_upper, ""),
            })
        wb.release_resources()
        print(f"  ERP: {len(productos)} productos válidos")
    except Exception as e:
        errores.append(str(e))
    return productos, errores, erp_skus


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


def generar_output(productos, unbx_map, estado_map, orden_map, ruta_salida):
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
        estadisticas["por_categoria"][cat] = estadisticas["por_categoria"].get(cat, 0) + 1
        estadisticas["por_linea"][lin] = estadisticas["por_linea"].get(lin, 0) + 1

        est = estado_map.get(p["sku"], "")
        if est:
            estadisticas["por_estado_linea"][est] = estadisticas["por_estado_linea"].get(est, 0) + 1

        productos_final.append({
            "sku": p["sku"],
            "nombre": p["nombre"],
            "nombre_corto": generar_nombre_corto(p["nombre"]),
            "ean13": p["ean13"],
            "ean14": p["ean14"],
            "categoria": p["categoria"],
            "linea": p["linea"],
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
            "keywords": generar_keywords(p["nombre"], p["linea"], p["categoria"]),
        })

    productos_final.sort(key=lambda x: (x.get("orden", 0) == 0, x.get("orden", 0) or 0, x["sku"]))

    metadata = {
        "version": "3.2.0",
        "generated_at": datetime.now().isoformat(),
        "source_erp": "PRODUCTOS.xls",
        "source_un_bx": "SKU_BX.xlsx",
        "total_productos": len(productos_final),
        "estadisticas": estadisticas,
    }

    output = {"metadata": metadata, "productos": productos_final}

    p = Path(ruta_salida)
    if p.exists():
        bak = p.with_suffix(f".{datetime.now():%Y%m%d_%H%M%S}.bak.json")
        if bak.exists():
            bak.unlink()
        p.rename(bak)
        print(f"  Backup: {bak.name}")

    with open(p, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Guardado: {ruta_salida} ({p.stat().st_size / 1024:.1f} KB)")
    return output


def main():
    ap = argparse.ArgumentParser(description="G360 Catalog Generator v3.2")
    ap.add_argument("--erp", "-e", default="data/PRODUCTOS.xls", help="Archivo ERP")
    ap.add_argument("--unbx", "-u", default="data/SKU_BX.xlsx", help="Archivo SKU_BX")
    ap.add_argument("--output", "-o", default="output/catalogo_productos.json", help="JSON salida")
    ap.add_argument("--validate-only", "-v", action="store_true", help="Solo validar, no generar")
    a = ap.parse_args()

    print("=" * 50)
    print("G360 CATALOG GENERATOR v3.2.0")
    print("=" * 50)
    print(f"ERP:      {a.erp}")
    print(f"SKU_BX:   {a.unbx}")
    print(f"Output:   {a.output}")
    print()

    # Leer fuentes (BX primero: es la guía primaria de inclusión)
    print("Leyendo fuentes...")
    orden_map, unbx_map, estado_map = leer_unbx(a.unbx)
    productos, errs, erp_skus = leer_erp(a.erp, bx_skus=set(orden_map))
    if errs:
        print(f"Errores: {errs}")

    huerfanos = sorted(set(orden_map) - erp_skus)
    if huerfanos:
        print(f"  WARN: {len(huerfanos)} SKUs en SKU_BX no existen en ERP (se omiten): "
              f"{', '.join(huerfanos[:10])}"
              f"{'...' if len(huerfanos) > 10 else ''}")

    if not productos:
        print("ERROR: No hay productos válidos")
        sys.exit(1)

    print(f"\nTotal productos válidos: {len(productos)}")
    print(f"  Con orden definido:    {len(orden_map)}")
    print(f"  Con un_bx definido:    {len(unbx_map)}")
    print(f"  Sin un_bx (default 1): {len(productos) - len(unbx_map)}")

    if a.validate_only:
        print("\nValidación completada")
        return

    # Generar output
    print("\nGenerando catálogo...")
    output = generar_output(productos, unbx_map, estado_map, orden_map, a.output)

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
    print(f"  Descontinuados (en BX): {est['descontinuados']}")
    print(f"  Sin linea_codigo:       {est['sin_linea_codigo']}")
    print(f"\nCategorías:")
    for cat, cnt in sorted(est["por_categoria"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")
    print(f"\nListo!")


if __name__ == "__main__":
    main()
