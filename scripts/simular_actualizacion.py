#!/usr/bin/env python3
"""Simula el ciclo de actualizacion de codigo (SKU nuevo) de punta a punta.

Arma un reporte ERP simulado (.xls) y una guia SKU_BX simulada (.xlsx) a
partir de los reales, agrega SKUs nuevos en situaciones distintas y corre el
generador real sobre ellos. Al final sube el catalogo resultante a un API de
stock y verifica que el SKU nuevo quedo disponible.

Situaciones simuladas:
  1. SKU nuevo vigente + curado en SKU_BX      -> entra (guia primaria)
  2. SKU nuevo DESCONTINUADO, sin SKU_BX ni stock -> queda fuera
  3. SKU nuevo DESCONTINUADO, sin SKU_BX pero CON stock fisico -> entra
     marcado como descontinuado (universo de stock)
  4. SKU nuevo Crayola (C*)                     -> entra con linea propia
  5. Impacto del universo de stock: con y sin el, cuantos SKUs se pierden

Uso:
    python scripts/simular_actualizacion.py
    python scripts/simular_actualizacion.py --api-url http://127.0.0.1:8099 \
        --api-key MI_CLAVE
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

# Las consolas de Windows por defecto usan cp1252 y revientan con los
# caracteres de dibujo de linea. Se fuerza UTF-8 con reemplazo.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:  # pragma: no cover - Python < 3.7
    pass

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from generar_catalogo_base import (  # noqa: E402
    generar_output,
    leer_erp,
    leer_unbx,
    productos_desde_universo,
)

ERP_POR_DEFECTO = RAIZ / "data" / "PRODUCTOS.xls"
BX_POR_DEFECTO = RAIZ / "data" / "SKU_BX.xlsx"
URL_STOCK_DEFAULT = "https://g360-stock-api.onrender.com"

# SKU ficticios (prefijo 99) que no colisionan con el catalogo real.
SKU_ESCENARIO_1 = "990001"  # nuevo vigente + curado en SKU_BX
SKU_ESCENARIO_2 = "990002"  # nuevo descontinuado, sin BX, sin stock
SKU_ESCENARIO_3 = "990003"  # nuevo descontinuado, sin BX, con stock fisico
SKU_ESCENARIO_4 = "CG990"  # nuevo Crayola (sub-marca CG)
SKU_ESCENARIO_5 = "S199001"  # con stock y compromiso, NUNCA registrado en el ERP
SKU_ESCENARIO_6 = "03077D"  # SKU exacto con D: otro producto, sin vinculos

FILAS_NUEVAS = [
    # sku, nombre, ean13, ean14, peso, linea, grupo, tipo, familia,
    # inactivo, descontinuado, precio
    (
        SKU_ESCENARIO_1,
        "G360 SIMULACION LAPICERO RETRACTIL AZUL",
        "7754809990017",
        "17754809990017",
        "0.012",
        "ESCRITURA",
        "LAPICEROS",
        "RETRACTIL",
        "CLASICOS",
        "Unchecked",
        "Unchecked",
        "3.50000",
    ),
    (
        SKU_ESCENARIO_2,
        "G360 SIMULACION GOMA BORRADOR XL",
        "7754809990024",
        "17754809990024",
        "0.030",
        "ACCESORIOS",
        "GOMAS",
        "BORRADOR",
        "OFICIO",
        "Unchecked",
        "Checked",
        "2.75000",
    ),
    (
        SKU_ESCENARIO_3,
        "G360 SIMULACION MARCADOR CERA 12 COLORES",
        "7754809990031",
        "17754809990031",
        "0.080",
        "DIBUJO",
        "MARCADORES",
        "CERA",
        "12 COLORES",
        "Unchecked",
        "Checked",
        "8.90000",
    ),
    (
        SKU_ESCENARIO_4,
        "CRAYOLA SIMULACION ROTULADOR RESALTADOR NEON",
        "7754809990048",
        "17754809990048",
        "0.025",
        "PINTURA",
        "ROTULADORES",
        "RESALTADOR",
        "NEON",
        "Unchecked",
        "Unchecked",
        "6.25000",
    ),
]


def escribir_erp_simulado(ruta_destino: Path, filas_extra=()) -> Path:
    """Copia el ERP real (.xls) y le agrega filas nuevas.

    PRODUCTOS.xls es BIFF8 de solo lectura para xlrd: se reconstruye con
    xlwt conservando el contenido celda por celda.
    """
    import xlrd
    import xlwt

    libro = xlwt.Workbook(encoding="utf-8")
    hoja = libro.add_sheet("codigos productos")

    wb = xlrd.open_workbook(str(ERP_POR_DEFECTO))
    ws = wb.sheet_by_index(0)
    for r in range(ws.nrows):
        for c in range(ws.ncols):
            valor = ws.cell_value(r, c)
            if valor == "":
                continue
            hoja.write(r, c, valor)
    for i, fila in enumerate(filas_extra):
        for c, valor in enumerate(fila):
            if valor == "":
                continue
            hoja.write(ws.nrows + i, c, valor)
    libro.save(str(ruta_destino))
    wb.release_resources()
    return ruta_destino


def escribir_bx_simulado(ruta_destino: Path, skus_nuevos=()) -> Path:
    """Copia SKU_BX.xlsx y agrega SKUs nuevos al final."""
    import openpyxl

    wb = openpyxl.load_workbook(BX_POR_DEFECTO)
    ws = wb.active
    orden = ws.max_row
    for sku in skus_nuevos:
        orden += 1
        ws.cell(row=orden, column=1, value=orden)
        ws.cell(row=orden, column=2, value=sku)
        ws.cell(row=orden, column=3, value=24)
        ws.cell(row=orden, column=4, value="NUEVO")
    wb.save(str(ruta_destino))
    return ruta_destino


ENCABEZADO_ERP = [
    "CODIGO",
    "NOMBRE",
    "COD_EAN",
    "COD_EAN_14",
    "CAN_KG_UM",
    "LINEA",
    "GRUPO",
    "TIPO",
    "FAMILIA",
    "FLG_INACTIVO",
    "FLG_DESCONTINUADO",
    "PRECIO",
]


def escribir_erp_minimo(ruta_destino: Path, filas=()) -> Path:
    """Escribe un ERP .xls minimo (encabezado + filas) para tests rapidos."""
    import xlwt

    libro = xlwt.Workbook(encoding="utf-8")
    hoja = libro.add_sheet("codigos productos")
    for c, titulo in enumerate(ENCABEZADO_ERP):
        hoja.write(0, c, titulo)
    for i, fila in enumerate(filas):
        for c, valor in enumerate(fila):
            if valor == "":
                continue
            hoja.write(i + 1, c, valor)
    libro.save(str(ruta_destino))
    return ruta_destino


def escribir_bx_minimo(ruta_destino: Path, skus=()) -> Path:
    """Escribe un SKU_BX.xlsx minimo (encabezado + filas) para tests rapidos."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ORDEN", "SKU", "UN_BX", "ESTADO_LINEA"])
    for i, sku in enumerate(skus, start=1):
        ws.append([i, sku, 24, "NUEVO"])
    wb.save(str(ruta_destino))
    return ruta_destino


def _universo_stock_real() -> dict[str, dict]:
    """Universo real (stock + compromiso) segun el API configurado."""
    from generar_catalogo_base import leer_universo_stock

    universo, err = leer_universo_stock()
    if err:
        return {}
    return universo


def _generar(erp: Path, bx: Path, salida: Path, stock_skus, universo=None) -> dict:
    """Genera un catalogo completo (misma secuencia que main)."""
    universo = universo or {
        s: {"stock": 1, "predespacho": 0} for s in (stock_skus or set())
    }
    guia = leer_unbx(str(bx))
    orden_map, unbx_map, estado_map = guia.orden, guia.un_bx, guia.estado
    productos, errs, erp_skus, exclusiones, erp_todos = leer_erp(
        str(erp),
        bx_skus=set(orden_map),
        stock_skus={s for s, d in universo.items() if d.get("stock", 0) > 0},
        compromiso_skus={s for s, d in universo.items() if d.get("predespacho", 0) > 0},
    )
    if errs:
        raise RuntimeError(f"Error leyendo ERP simulado: {errs}")
    productos.extend(productos_desde_universo(universo, productos, erp_todos))
    return generar_output(
        productos,
        unbx_map,
        estado_map,
        orden_map,
        str(salida),
        exclusiones=exclusiones,
        universo_stock={"incluido": True, "skus": len(universo), "error": ""},
        universo=universo,
        caja_map=guia.caja,
        erp_todos=erp_todos,
    )


def _subir(api_url: str, api_key: str, catalogo: Path) -> dict:
    import requests

    with open(catalogo, "rb") as f:
        r = requests.post(
            f"{api_url.rstrip('/')}/api/v1/catalog/upload",
            headers={"X-API-Key": api_key},
            files={"archivo": (catalogo.name, f, "application/json")},
            timeout=120,
        )
    r.raise_for_status()
    return r.json()


def _consultar(api_url: str, api_key: str, sku: str) -> dict | None:
    import requests

    r = requests.get(
        f"{api_url.rstrip('/')}/api/v1/stock/{sku}",
        headers={"X-API-Key": api_key},
        timeout=60,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def ejecutar(api_url: str = "", api_key: str = "") -> int:
    tmp = Path(tempfile.mkdtemp(prefix="g360_sim_"))
    print("=" * 70)
    print("SIMULACION DE ACTUALIZACION DE CODIGO (SKU nuevo)")
    print("=" * 70)
    print(f"Directorio de trabajo: {tmp}\n")

    # -- Fuentes simuladas ------------------------------------------------
    erp_sim = escribir_erp_simulado(tmp / "PRODUCTOS_sim.xls", FILAS_NUEVAS)
    bx_sim = escribir_bx_simulado(tmp / "SKU_BX_sim.xlsx", [SKU_ESCENARIO_1])
    print(f"ERP simulado:   {erp_sim.name} (+{len(FILAS_NUEVAS)} filas)")
    print(f"SKU_BX simulado: {bx_sim.name} (+1 SKU: {SKU_ESCENARIO_1})\n")

    # -- Escenario 1 y 2: sin universo de stock ---------------------------
    cat_sin_stock = tmp / "catalogo_sin_stock.json"
    out1 = _generar(erp_sim, bx_sim, cat_sin_stock, stock_skus=set())
    skus1 = {p["sku"] for p in out1["productos"]}
    print("-- Escenario 1: SKU nuevo vigente + curado en SKU_BX")
    print(f"   {SKU_ESCENARIO_1} en catalogo: {SKU_ESCENARIO_1 in skus1}")
    p1 = next((p for p in out1["productos"] if p["sku"] == SKU_ESCENARIO_1), None)
    if p1:
        print(
            f"   linea={p1['linea']} categoria={p1['categoria']} un_bx={p1['un_bx']} "
            f"orden={p1['orden']} estado_linea={p1['estado_linea']}"
        )

    print("\n-- Escenario 2: SKU nuevo DESCONTINUADO sin SKU_BX y sin stock")
    print(f"   {SKU_ESCENARIO_2} en catalogo: {SKU_ESCENARIO_2 in skus1}")

    # -- Escenario 3: el mismo ERP pero con el SKU en el universo de stock --
    cat_con_stock = tmp / "catalogo_con_stock.json"
    out2 = _generar(erp_sim, bx_sim, cat_con_stock, stock_skus={SKU_ESCENARIO_3})
    skus2 = {p["sku"] for p in out2["productos"]}
    print("\n-- Escenario 3: SKU nuevo DESCONTINUADO sin SKU_BX pero CON stock")
    print(f"   {SKU_ESCENARIO_3} en catalogo: {SKU_ESCENARIO_3 in skus2}")
    p3 = next((p for p in out2["productos"] if p["sku"] == SKU_ESCENARIO_3), None)
    if p3:
        print(
            f"   linea={p3['linea']} categoria={p3['categoria']} "
            f"descontinuado={p3['descontinuado']}"
        )

    # -- Escenario 4: SKU Crayola nuevo -----------------------------------
    print("\n-- Escenario 4: SKU Crayola nuevo (prefijo C*)")
    print(f"   {SKU_ESCENARIO_4} en catalogo: {SKU_ESCENARIO_4 in skus2}")
    p4 = next((p for p in out2["productos"] if p["sku"] == SKU_ESCENARIO_4), None)
    if p4:
        print(
            f"   linea={p4['linea']} linea_nombre={p4['linea_nombre']} "
            f"categoria={p4['categoria']}"
        )

    # -- Escenario 5: SKU no registrado que llega con stock y compromiso ---
    universo_s5 = {
        SKU_ESCENARIO_3: {"stock": 5, "predespacho": 0},
        SKU_ESCENARIO_5: {
            "stock": 40,
            "predespacho": 12,
            "descripcion": "G360 SIMULACION CUADERNO ANILLADO A4",
            "um": "UND",
            "linea": "0178 - ARCHIVO",
            "grupo": "01 - CUADERNOS",
            "tipo": "02 - ANILLADO",
            "familia": "03 - A4",
        },
        # SKU con D: nombre parecido a otro codigo, pero es otro producto
        # exacto: no se enlaza ni hereda nada.
        SKU_ESCENARIO_6: {
            "stock": 7,
            "predespacho": 0,
            "descripcion": "FOLDER N VINIFAN TAPA FANTASIA OFICIO MIX SURTIDO",
            "um": "UND",
            "linea": "0198 - PRODUCTOS SIN EMBALAJE",
            "grupo": "01 - FOLDER",
            "tipo": "02 - FANTASIA",
            "familia": "03 - OFICIO",
        },
    }
    cat_s5 = tmp / "catalogo_no_registrado.json"
    out5 = _generar(erp_sim, bx_sim, cat_s5, set(), universo=universo_s5)
    skus5 = {p["sku"]: p for p in out5["productos"]}
    print("\n-- Escenario 5: SKU con stock/compromiso que NO existe en el ERP")
    p5 = skus5.get(SKU_ESCENARIO_5)
    if p5:
        print(
            f"   {SKU_ESCENARIO_5}: linea={p5['linea']} grupo={p5['grupo']} "
            f"categoria={p5['categoria']} categoria_venta={p5['categoria_venta']} "
            f"por_activar={p5['por_activar']} cotizable={p5['cotizable']} "
            f"compromiso={p5['compromiso']}"
        )
    else:
        print(f"   {SKU_ESCENARIO_5}: FUERA del catalogo")
    print("\n-- Escenario 6: SKU con D (producto exacto, sin vinculos)")
    p6 = skus5.get(SKU_ESCENARIO_6)
    if p6:
        print(
            f"   {SKU_ESCENARIO_6}: derivado_de={p6['derivado_de']!r} "
            f"linea={p6['linea']} categoria={p6['categoria']} "
            f"precio={p6['precio']} stock_snapshot={p6['stock_snapshot']}"
        )
    else:
        print(f"   {SKU_ESCENARIO_6}: FUERA del catalogo")

    # -- Escenario 7: impacto real del universo de stock -------------------
    print("\n-- Escenario 7: impacto del universo de stock sobre el catalogo")
    universo_real = _universo_stock_real()
    if universo_real:
        cat_completo = tmp / "catalogo_completo.json"
        out3 = _generar(erp_sim, bx_sim, cat_completo, set(), universo=universo_real)
        skus3 = {p["sku"] for p in out3["productos"]}
        perdidos = skus3 - skus1
        print(
            f"   sin universo: {len(skus1)} SKUs | con universo: {len(skus3)} SKUs "
            f"({len(perdidos)} SKUs con stock/compromiso se perdian sin el universo)"
        )
    else:
        print("   (sin API de stock disponible: se omite el contraste real)")

    # -- Verificacion -----------------------------------------------------
    esperados = {
        SKU_ESCENARIO_1: (True, "SKU_BX: entra con un_bx/orden/estado"),
        SKU_ESCENARIO_2: (False, "descontinuado sin BX ni stock: queda fuera"),
        SKU_ESCENARIO_3: (True, "universo de stock: entra aunque no este en BX"),
        SKU_ESCENARIO_4: (True, "Crayola: entra con linea propia"),
        SKU_ESCENARIO_5: (True, "no registrado con movimiento: ficha minima S1"),
        SKU_ESCENARIO_6: (True, "D exacto: entra sin enlaces ni herencia"),
    }
    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    fallos = 0
    for sku, (esperado, motivo) in esperados.items():
        ok = (sku in skus5) == esperado
        fallos += 0 if ok else 1
        print(
            f"  [{'OK ' if ok else 'FALLA'}] {sku}: "
            f"{'incluido' if sku in skus5 else 'fuera'} - {motivo}"
        )

    # -- Subida al API de stock -------------------------------------------
    if api_url and api_key:
        print(f"\n-- Subiendo el catalogo simulado a {api_url}")
        try:
            res = _subir(api_url, api_key, cat_con_stock)
            print(f"   Respuesta: {json.dumps(res, ensure_ascii=False)}")
            for sku in (SKU_ESCENARIO_1, SKU_ESCENARIO_3, SKU_ESCENARIO_4):
                item = _consultar(api_url, api_key, sku)
                if item:
                    print(
                        f"   /stock/{sku}: linea={item.get('linea')} "
                        f"categoria={item.get('categoria')} "
                        f"un_bx={item.get('un_bx')} precio={item.get('precio')}"
                    )
                else:
                    print(f"   /stock/{sku}: no encontrado")
        except Exception as e:  # noqa: BLE001
            print(f"   ERROR subiendo al API: {e}")
            fallos += 1
    else:
        print(
            "\n( Sin --api-url/--api-key: no se sube a ningun API. "
            "Para probar la subida: --api-url http://127.0.0.1:8099 --api-key CLAVE )"
        )

    shutil.rmtree(tmp, ignore_errors=True)
    print(
        "\n" + ("SIMULACION OK" if fallos == 0 else f"SIMULACION CON {fallos} FALLOS")
    )
    return 0 if fallos == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Simula actualizaciones de codigo")
    ap.add_argument("--api-url", default="", help="API de stock para subir el catalogo")
    ap.add_argument("--api-key", default="", help="Clave del API")
    args = ap.parse_args()
    return ejecutar(args.api_url, args.api_key)


if __name__ == "__main__":
    sys.exit(main())
