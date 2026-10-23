#!/usr/bin/env python3
"""Repara los archivos fuente de data/ con los encabezados de la plantilla.

Que corrige
-----------
1. SKU como TEXTO: los SKUs guardados como numero perdieron los ceros a la
   izquierda (2169 vs 02169). Se reparan contra el ERP: si existe exactamente
   UN sku cuyo valor numerico coincide, se restaura. Sin match unico no se
   adivina (queda como estaba y queda el aviso).
2. SKU_BX.xlsx: agrega las columnas de caja de la plantilla (LARGO_CM,
   ANCHO_CM, ALTO_CM, PESO_CAJA_KG, M3_CAJA, M3_UNIDAD con formulas).
3. plantilla_precios.xlsx: agrega VIGENCIA_INI/VIGENCIA_FIN en DESCUENTOS y
   da formato fecha a las columnas de vigencia.

Aplica a: data/SKU_BX.xlsx, data/plantilla_precios.xlsx y data/SKU_PRECIOS.xlsx
(hoja SKU_PRECIOS + SKU_LOGISTICA). Siempre hace backup antes de escribir.

Uso:
    python scripts/reparar_datos.py            # repara todo lo que exista
    python scripts/reparar_datos.py --solo SKU_BX.xlsx
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from contratos import normalizar_encabezado, sku_texto

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"

AZUL = "1F4E79"
VERDE = "E2EFDA"

COLUMNA_CAJA_EXTRA = (
    ("LARGO_CM", 11),
    ("ANCHO_CM", 11),
    ("ALTO_CM", 11),
    ("PESO_CAJA_KG", 14),
    ("M3_CAJA", 12),
    ("M3_UNIDAD", 12),
)

COLUMNA_PRECIOS_EXTRA = (
    ("VIGENCIA_INI", 14),
    ("VIGENCIA_FIN", 14),
)


def _skus_del_erp(ruta: Path) -> dict[int, list[str]]:
    """Indice {valor_numerico: [skus]} del ERP para reparar SKUs numericos."""
    import xlrd

    from contratos import encabezados_xls

    indice: dict[int, list[str]] = {}
    try:
        libro = xlrd.open_workbook(str(ruta))
        hoja = libro.sheet_by_index(0)
        encabezados = [normalizar_encabezado(h) for h in encabezados_xls(hoja, 1)]
        if "CODIGO" in encabezados:
            col = encabezados.index("CODIGO")
        elif "SKU" in encabezados:
            col = encabezados.index("SKU")
        else:
            return indice
        for r in range(1, hoja.nrows):
            texto = str(hoja.cell_value(r, col)).strip().lstrip("'")
            # Solo SKUs 100% numericos: 'CA001' no puede responder a un int().
            if not texto.isdigit():
                continue
            indice.setdefault(int(texto), []).append(texto)
        libro.release_resources()
    except Exception as e:  # noqa: BLE001
        print(f"  WARN ERP: no se pudo leer para reparar SKUs: {e}")
    return indice


def _reparar_sku(valor, indice_erp: dict[int, list[str]]) -> str:
    """SKU como texto; si era numero, repara los ceros si el match es unico."""
    sku = sku_texto(valor)
    if not sku:
        return ""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        candidatos = indice_erp.get(int(valor), [])
        if len(candidatos) == 1:
            return candidatos[0]
        # 0 o 2+ candidatos: no se adivina.
    return sku


def _reparar_columna_sku(ws, col_sku: int, indice_erp, etiqueta: str) -> None:
    """Repara SKUs numericos en una hoja y deja la columna como TEXTO.

    Tres casos:
      - ceros recuperados: el ERP tiene un SKU distinto con ceros adelante;
      - solo formato: el numero coincide con el SKU del ERP tal cual (no
        hubo perdida, era formato de celda);
      - sin match: no hay match unico en el ERP -> revisar a mano.
    """
    reparados, formato, sin_match = 0, 0, 0
    sin_match_ejemplos: list[str] = []
    for fila in range(2, ws.max_row + 1):
        celda = ws.cell(row=fila, column=col_sku)
        crudo = celda.value
        if crudo in (None, ""):
            continue
        if not isinstance(crudo, (int, float)) or isinstance(crudo, bool):
            celda.number_format = "@"
            continue
        reparado = _reparar_sku(crudo, indice_erp)
        texto = sku_texto(crudo)
        if reparado != texto:
            reparados += 1
        elif texto in indice_erp.get(int(crudo), []):
            formato += 1
        else:
            sin_match += 1
            if len(sin_match_ejemplos) < 5:
                sin_match_ejemplos.append(texto)
        celda.value = reparado
        celda.number_format = "@"
    if reparados:
        print(f"  {etiqueta}: {reparados} SKU(s) reparados (ceros recuperados)")
    if formato:
        print(
            f"  {etiqueta}: {formato} SKU(s) numericos sin perdida "
            "(formato de celda corregido a TEXTO)"
        )
    if sin_match:
        detalle = (
            f" (ej: {', '.join(sin_match_ejemplos)})" if sin_match_ejemplos else ""
        )
        print(
            f"  {etiqueta}: {sin_match} SKU(s) numericos SIN match en el ERP"
            f"{detalle}; revisar a mano"
        )


def _agregar_columnas(ws, columnas_nuevas) -> int:
    """Agrega columnas al final de una hoja si no existen (con encabezado)."""
    existentes = {normalizar_encabezado(c.value) for c in ws[1] if c.value is not None}
    faltan = [
        (nombre, ancho)
        for nombre, ancho in columnas_nuevas
        if normalizar_encabezado(nombre) not in existentes
    ]
    if not faltan:
        return 0
    inicio = ws.max_column + 1
    for offset, (nombre, ancho) in enumerate(faltan):
        col = inicio + offset
        celda = ws.cell(row=1, column=col, value=nombre)
        celda.font = Font(color="FFFFFF", bold=True)
        celda.fill = PatternFill("solid", fgColor=AZUL)
        celda.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = ancho
    return len(faltan)


def reparar_sku_bx(indice_erp) -> None:
    ruta = DATA / "SKU_BX.xlsx"
    if not ruta.exists():
        print("  SKIP: data/SKU_BX.xlsx no existe")
        return
    wb = load_workbook(ruta)
    ws = wb["SKU_BX"] if "SKU_BX" in wb.sheetnames else wb.active
    encabezados = [normalizar_encabezado(c.value) for c in ws[1]]
    if "SKU" in encabezados:
        col_sku = encabezados.index("SKU") + 1
    elif "CODIGO" in encabezados:
        col_sku = encabezados.index("CODIGO") + 1
    else:
        print("  SKU_BX: no se encontro la columna SKU; no se repara")
        return

    respaldo = ruta.with_name(
        f"{ruta.stem}.{datetime.now():%Y%m%d_%H%M%S}.bak{ruta.suffix}"
    )
    shutil.copy2(ruta, respaldo)
    print(f"  Backup: {respaldo.name}")

    _reparar_columna_sku(ws, col_sku, indice_erp, "SKU_BX")

    nuevas = _agregar_columnas(ws, COLUMNA_CAJA_EXTRA)
    if nuevas:
        idx = {
            normalizar_encabezado(c.value): c.column
            for c in ws[1]
            if c.value is not None
        }
        if all(
            k in idx
            for k in ("LARGO_CM", "ANCHO_CM", "ALTO_CM", "M3_CAJA", "M3_UNIDAD")
        ):
            col_l = get_column_letter(idx["LARGO_CM"])
            col_a = get_column_letter(idx["ANCHO_CM"])
            col_al = get_column_letter(idx["ALTO_CM"])
            col_m3 = get_column_letter(idx["M3_CAJA"])
            col_u = get_column_letter(idx["UN_BX"])
            col_m3u = get_column_letter(idx["M3_UNIDAD"])
            for fila in range(2, ws.max_row + 1):
                ws[f"{col_m3}{fila}"] = (
                    f'=IF(COUNTIF({col_l}{fila}:{col_al}{fila},">0")=3,'
                    f'{col_l}{fila}*{col_a}{fila}*{col_al}{fila}/1000000,"")'
                )
                ws[f"{col_m3u}{fila}"] = (
                    f'=IF(AND({col_m3}{fila}<>"",{col_u}{fila}>0),'
                    f'{col_m3}{fila}/{col_u}{fila},"")'
                )
                for letra in (col_m3, col_m3u):
                    ws[f"{letra}{fila}"].fill = PatternFill("solid", fgColor=VERDE)
        print(f"  SKU_BX: agregadas {nuevas} columna(s) de caja con formulas")
    else:
        print("  SKU_BX: columnas de caja ya presentes")
    wb.save(ruta)


def reparar_plantilla_precios(indice_erp) -> None:
    """Repara la hoja unica SKU_PRECIOS (o las legacy) de plantilla_precios.xlsx."""
    ruta = DATA / "plantilla_precios.xlsx"
    if not ruta.exists():
        print("  SKIP: data/plantilla_precios.xlsx no existe")
        return
    wb = load_workbook(ruta)
    respaldo = ruta.with_name(
        f"{ruta.stem}.{datetime.now():%Y%m%d_%H%M%S}.bak{ruta.suffix}"
    )
    shutil.copy2(ruta, respaldo)
    print(f"  Backup: {respaldo.name}")

    if "SKU_PRECIOS" in wb.sheetnames:
        ws = wb["SKU_PRECIOS"]
        _reparar_columna_sku(ws, 1, indice_erp, "SKU_PRECIOS")
        for c in range(1, ws.max_column + 1):
            nombre = normalizar_encabezado(ws.cell(row=1, column=c).value)
            if nombre in ("VIGENCIA_DESC", "VIGENCIA_PRECIO"):
                letra = get_column_letter(c)
                for fila in range(2, ws.max_row + 1):
                    ws[f"{letra}{fila}"].number_format = "yyyy-mm-dd"
    else:
        for hoja in ("DESCUENTOS", "PRECIOS_FIJOS"):
            if hoja not in wb.sheetnames:
                continue
            ws = wb[hoja]
            encabezados = [normalizar_encabezado(c.value) for c in ws[1]]
            if "SKU" not in encabezados:
                print(f"  {hoja}: sin columna SKU; no se repara")
                continue
            col_sku = encabezados.index("SKU") + 1
            _reparar_columna_sku(ws, col_sku, indice_erp, hoja)
            if hoja == "DESCUENTOS":
                agregadas = _agregar_columnas(ws, COLUMNA_PRECIOS_EXTRA)
                if agregadas:
                    print(f"  DESCUENTOS: agregadas {agregadas} columna(s) de vigencia")
            for c in range(1, ws.max_column + 1):
                nombre = normalizar_encabezado(ws.cell(row=1, column=c).value)
                if nombre in ("VIGENCIA_INI", "VIGENCIA_FIN"):
                    letra = get_column_letter(c)
                    for fila in range(2, ws.max_row + 1):
                        ws[f"{letra}{fila}"].number_format = "yyyy-mm-dd"
    wb.save(ruta)


def reparar_sku_precios(indice_erp) -> None:
    ruta = DATA / "SKU_PRECIOS.xlsx"
    if not ruta.exists():
        print("  SKIP: data/SKU_PRECIOS.xlsx no existe")
        return
    wb = load_workbook(ruta)
    cambio = False
    if "SKU_PRECIOS" in wb.sheetnames:
        _reparar_columna_sku(wb["SKU_PRECIOS"], 1, indice_erp, "SKU_PRECIOS")
        cambio = True
    if "SKU_LOGISTICA" in wb.sheetnames:
        _reparar_columna_sku(wb["SKU_LOGISTICA"], 2, indice_erp, "SKU_LOGISTICA")
        cambio = True
    if cambio:
        wb.save(ruta)


def main() -> int:
    ap = argparse.ArgumentParser(description="Repara los archivos fuente de data/")
    ap.add_argument(
        "--solo",
        action="append",
        help="Repara solo ese archivo (SKU_BX.xlsx, plantilla_precios.xlsx, SKU_PRECIOS.xlsx)",
    )
    args = ap.parse_args()
    elegidos = set(args.solo or [])

    print("=" * 50)
    print("REPARACION DE ARCHIVOS FUENTE (SKU como TEXTO)")
    print("=" * 50)

    indice_erp = _skus_del_erp(DATA / "PRODUCTOS.xls")
    if not indice_erp:
        print("ERROR: no hay indice del ERP; no se puede reparar con seguridad")
        return 1
    print(f"  ERP: {len(indice_erp)} SKUs numericos indexados")
    print()

    if not elegidos or "SKU_BX.xlsx" in elegidos:
        reparar_sku_bx(indice_erp)
    if not elegidos or "plantilla_precios.xlsx" in elegidos:
        reparar_plantilla_precios(indice_erp)
    if not elegidos or "SKU_PRECIOS.xlsx" in elegidos:
        reparar_sku_precios(indice_erp)

    print()
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
