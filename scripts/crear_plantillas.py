#!/usr/bin/env python3
"""Crea las plantillas versionadas de los archivos manuales.

`plantillas/` guarda el MOLDE (versionado en git). El archivo que se llena y
se lee vive en `data/` (no se versiona). Copiar el molde a data/ es manual a
proposito, para no pisar un archivo que ya tiene datos:

    python scripts/crear_plantillas.py            # escribe plantillas/
    python scripts/crear_plantillas.py --instalar # copia a data/ solo si no existe
    python scripts/crear_plantillas.py --migrar   # rehace data/plantilla_precios.xlsx
                                                  # al layout unico (con backup)

Estructura de los archivos manuales (v3.9):
------------------------------------------
- plantillas/SKU_BX.xlsx        → hoja SKU_BX: ORDEN, SKU, UN_BX, ESTADO_LINEA
- plantillas/plantilla_precios.xlsx → hoja SKU_PRECIOS (UNICA):
      SKU, DESC1..6, VIGENCIA_DESC, PRECIO_FIJO, VIGENCIA_PRECIO, OBSERVACION

Los descuentos y el precio fijo viven en la MISMA fila (un SKU = una fila):
si hay PRECIO_FIJO, reemplaza a los descuentos. No hay hoja SKU_CLIENTES
(descontinuada: es una relacion 1-a-muchos que no cabe en una planilla).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

RAIZ = Path(__file__).resolve().parent.parent
DESTINO_PLANTILLAS = RAIZ / "plantillas"
DESTINO_DATA = RAIZ / "data"

AZUL = "1F4E79"
VERDE = "E2EFDA"

CAMPOS_SKU_BX = (
    ("ORDEN", 8),
    ("SKU", 12),
    ("UN_BX", 9),
    ("ESTADO_LINEA", 16),
)

CAMPOS_SKU_PRECIOS = (
    ("SKU", 12),
    ("DESC1", 10),
    ("DESC2", 10),
    ("DESC3", 10),
    ("DESC4", 10),
    ("DESC5", 10),
    ("DESC6", 10),
    ("VIGENCIA_DESC", 14),
    ("PRECIO_FIJO", 13),
    ("VIGENCIA_PRECIO", 14),
    ("OBSERVACION", 30),
)

ESTADOS_LINEA = ("NACIONAL", "IMPORTADO", "NUEVO", "TRADICIONAL")

LEEME_SKU_BX = [
    ("PLANTILLA SKU_BX", ""),
    ("Version", "2.0"),
    ("Que es", "Guia comercial: que SKU se vende y cuantas unidades por caja."),
    (
        "Donde va",
        "Se llena y se guarda como data/SKU_BX.xlsx (el generador lee de ahi).",
    ),
    ("", ""),
    ("Columna", "Regla"),
    ("ORDEN", "Entero. Indice maestro; tambien es la prueba de 'en guia' (en_guia)."),
    ("SKU", "TEXTO (no numero). 5 a 7 caracteres, con ceros a la izquierda: 016763."),
    ("UN_BX", "Entero >= 1. Unidades por caja."),
    ("ESTADO_LINEA", "NACIONAL / IMPORTADO / NUEVO / TRADICIONAL (lista desplegable)."),
    ("", ""),
    ("Nota", "Las columnas se leen por NOMBRE: se pueden reordenar, no renombrar."),
]

LEEME_PRECIOS = [
    ("PLANTILLA DE PRECIOS (hoja unica SKU_PRECIOS)", ""),
    ("Version", "2.0"),
    ("Que es", "Descuentos y precio fijo por SKU. Un SKU = una fila."),
    ("Donde va", "Se llena y se guarda como data/plantilla_precios.xlsx."),
    ("", ""),
    ("Columna", "Regla"),
    ("SKU", "TEXTO, con ceros a la izquierda. Debe existir en el ERP."),
    ("DESC1..DESC6", "FRACCION: 10% se escribe 0.10 (no 10). Vacio = sin descuento."),
    ("VIGENCIA_DESC", "Fecha (AAAA-MM-DD) de los descuentos. Vacio = sin limite."),
    (
        "PRECIO_FIJO",
        "Precio final en soles (> 0). Si existe, reemplaza a los descuentos.",
    ),
    ("VIGENCIA_PRECIO", "Fecha (AAAA-MM-DD) del precio fijo. Vacio = sin limite."),
    ("OBSERVACION", "Motivo (remate, liquidacion, campana, etc.)."),
    ("", ""),
    ("Nota", "Filas sin descuento y sin precio fijo se ignoran al leer."),
    ("Nota", "Las columnas se leen por NOMBRE: se pueden reordenar, no renombrar."),
]


def _cabecera(hoja, campos, comentarios=None) -> None:
    relleno = PatternFill("solid", fgColor=AZUL)
    for i, (nombre, ancho) in enumerate(campos, start=1):
        celda = hoja.cell(row=1, column=i, value=nombre)
        celda.font = Font(color="FFFFFF", bold=True)
        celda.fill = relleno
        celda.alignment = Alignment(horizontal="center", vertical="center")
        hoja.column_dimensions[get_column_letter(i)].width = ancho
        if comentarios and nombre in comentarios:
            celda.comment = Comment(comentarios[nombre], "G360")
    hoja.freeze_panes = "A2"
    hoja.row_dimensions[1].height = 22


def _texto_columna(hoja, letra: str, hasta: int = 5000) -> None:
    """Formatea la columna como TEXTO para que Excel no coma los ceros."""
    for fila in range(2, hasta + 1):
        hoja[f"{letra}{fila}"].number_format = "@"


def _validacion_lista(hoja, valores, celda: str) -> None:
    dv = DataValidation(
        type="list",
        formula1='"' + ",".join(valores) + '"',
        allow_blank=True,
        showDropDown=False,
    )
    dv.error = "Elegi un valor de la lista"
    dv.errorTitle = "Valor invalido"
    hoja.add_data_validation(dv)
    dv.add(celda)


def _validacion_decimal(hoja, rango: str, minimo: float, maximo: float) -> None:
    dv = DataValidation(
        type="decimal",
        operator="between",
        formula1=str(minimo),
        formula2=str(maximo),
        allow_blank=True,
    )
    dv.error = (
        f"Valor fuera de rango [{minimo}, {maximo}]. "
        "Los descuentos van como FRACCION: 10% = 0.10"
    )
    dv.errorTitle = "Descuento invalido"
    hoja.add_data_validation(dv)
    dv.add(rango)


def _leeme(libro, lineas) -> None:
    hoja = libro.create_sheet("LEEME", 0)
    hoja.column_dimensions["A"].width = 20
    hoja.column_dimensions["B"].width = 95
    hoja["A1"] = lineas[0][0]
    hoja["A1"].font = Font(bold=True, size=14, color=AZUL)
    for fila, (a, b) in enumerate(lineas[1:], start=2):
        hoja.cell(row=fila, column=1, value=a).font = Font(bold=True)
        hoja.cell(row=fila, column=2, value=b).alignment = Alignment(wrap_text=True)
    hoja.sheet_view.showGridLines = False


def crear_sku_bx(destino: Path) -> Path:
    """Molde de la guia comercial: 4 columnas basicas."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "SKU_BX"
    _cabecera(
        hoja,
        CAMPOS_SKU_BX,
        {"SKU": "TEXTO: 016763 (los ceros a la izquierda son parte del SKU)."},
    )
    _texto_columna(hoja, "B")
    _validacion_lista(hoja, ESTADOS_LINEA, "D2:D5000")
    _leeme(libro, LEEME_SKU_BX)
    libro.active = 0
    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)
    return destino


def crear_plantilla_precios(destino: Path) -> Path:
    """Molde de precios: UNA hoja (SKU_PRECIOS) con descuentos + precio fijo."""
    libro = Workbook()
    libro.remove(libro.active)
    hoja = libro.create_sheet("SKU_PRECIOS")
    _cabecera(
        hoja,
        CAMPOS_SKU_PRECIOS,
        {
            "SKU": "TEXTO, con ceros a la izquierda.",
            "DESC1": "Fraccion: 10% = 0.10",
            "PRECIO_FIJO": "Precio final en soles (> 0). Reemplaza a los descuentos.",
        },
    )
    _texto_columna(hoja, "A")
    _validacion_decimal(hoja, "B2:G5000", 0, 0.9999)
    _validacion_decimal(hoja, "I2:I5000", 0.01, 999999)
    for col in "HJ":
        for fila in range(2, 5001):
            hoja[f"{col}{fila}"].number_format = "yyyy-mm-dd"
    _leeme(libro, LEEME_PRECIOS)
    libro.active = 0
    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)
    return destino


# ─────────────────────────────────────────────────────────────────────────────
# Migracion: plantilla vieja (DESCUENTOS + PRECIOS_FIJOS) -> hoja unica
# ─────────────────────────────────────────────────────────────────────────────


def _filas_con_contrato(ruta: Path, contrato, etiqueta: str):
    """Lee una hoja POR NOMBRE de columna y devuelve dicts {campo: valor}."""
    from contratos import ErrorContrato, resolver_xlsx

    try:
        libro = load_workbook(ruta, read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        print(f"  WARN {etiqueta}: no se pudo abrir {ruta.name}: {e}")
        return []
    try:
        columnas, hoja = resolver_xlsx(libro, contrato)
        for aviso in columnas.avisos[:5]:
            print(f"  AVISO {etiqueta}: {aviso}")
        filas = []
        for cruda in hoja.iter_rows(min_row=contrato.fila_header + 1, values_only=True):
            registro = {}
            for campo in columnas.indices:
                registro[campo] = columnas.valor(cruda, campo)
            filas.append(registro)
        return filas
    except ErrorContrato as e:
        print(f"  WARN {etiqueta}: contrato roto, hoja no migrada:")
        print("  " + str(e).replace("\n", "\n  "))
        return []
    finally:
        libro.close()


FILA_VACIA_PRECIOS = {
    "desc1": None,
    "desc2": None,
    "desc3": None,
    "desc4": None,
    "desc5": None,
    "desc6": None,
    "vigencia_desc": None,
    "precio_fijo": None,
    "vigencia_precio": None,
    "observacion": None,
}


def fusionar_plantilla_precios(ruta: Path) -> bool:
    """Rehace data/plantilla_precios.xlsx al layout unico.

    Lee las hojas legacy (DESCUENTOS + PRECIOS_FIJOS) POR NOMBRE, fusiona por
    SKU y reescribe el archivo con UNA hoja SKU_PRECIOS. Los SKU sin ningun
    descuento ni precio fijo se descartan (eran placeholders). Siempre hace
    backup antes de escribir.
    """
    from contratos import (
        CONTRATO_PLANTILLA_DESCUENTOS,
        CONTRATO_PLANTILLA_PRECIOS_FIJOS,
    )

    if not ruta.exists():
        print(f"  SKIP: no existe {ruta}")
        return False

    registros: dict[str, dict] = {}
    for fila in _filas_con_contrato(ruta, CONTRATO_PLANTILLA_DESCUENTOS, "DESCUENTOS"):
        sku = str(fila.get("sku") or "").strip()
        if not sku:
            continue
        registro = registros.setdefault(sku, dict(FILA_VACIA_PRECIOS))
        for campo in ("desc1", "desc2", "desc3", "desc4", "desc5", "desc6"):
            if fila.get(campo) not in (None, ""):
                registro[campo] = fila.get(campo)
        if fila.get("vigencia_ini") not in (None, ""):
            registro["vigencia_desc"] = fila.get("vigencia_ini")

    for fila in _filas_con_contrato(
        ruta, CONTRATO_PLANTILLA_PRECIOS_FIJOS, "PRECIOS_FIJOS"
    ):
        sku = str(fila.get("sku") or "").strip()
        if not sku:
            continue
        registro = registros.setdefault(sku, dict(FILA_VACIA_PRECIOS))
        if fila.get("precio_fijo") not in (None, ""):
            registro["precio_fijo"] = fila.get("precio_fijo")
        if fila.get("vigencia_fin") not in (None, ""):
            registro["vigencia_precio"] = fila.get("vigencia_fin")
        if fila.get("observacion") not in (None, ""):
            registro["observacion"] = fila.get("observacion")

    con_datos = {
        sku: r
        for sku, r in registros.items()
        if any(
            r[c] is not None
            for c in (
                "desc1",
                "desc2",
                "desc3",
                "desc4",
                "desc5",
                "desc6",
                "precio_fijo",
            )
        )
    }
    descartados = len(registros) - len(con_datos)

    respaldo = ruta.with_name(
        f"{ruta.stem}.{datetime.now():%Y%m%d_%H%M%S}.bak{ruta.suffix}"
    )
    shutil.copy2(ruta, respaldo)
    print(f"  Backup: {respaldo.name}")

    libro = Workbook()
    libro.remove(libro.active)
    hoja = libro.create_sheet("SKU_PRECIOS")
    for n, (sku, r) in enumerate(sorted(con_datos.items()), start=2):
        valores = [
            sku,
            r["desc1"],
            r["desc2"],
            r["desc3"],
            r["desc4"],
            r["desc5"],
            r["desc6"],
            r["vigencia_desc"],
            r["precio_fijo"],
            r["vigencia_precio"],
            r["observacion"],
        ]
        for c, valor in enumerate(valores, start=1):
            hoja.cell(row=n, column=c, value=valor)
    # Formato por nombre (nunca posicional para los datos existentes).
    _cabecera(hoja, CAMPOS_SKU_PRECIOS)
    hasta = max(5000, len(con_datos) + 10)
    _texto_columna(hoja, "A", hasta=hasta)
    _validacion_decimal(hoja, f"B2:G{hasta}", 0, 0.9999)
    _validacion_decimal(hoja, f"I2:I{hasta}", 0.01, 999999)
    for col in "HJ":
        for fila in range(2, hasta + 1):
            hoja[f"{col}{fila}"].number_format = "yyyy-mm-dd"
    _leeme(libro, LEEME_PRECIOS)
    libro.active = 0
    libro.save(ruta)

    print(f"  OK: {ruta.name} reescrita al layout unico")
    print(
        f"      SKU con precios: {len(con_datos)} (descartados sin datos: {descartados})"
    )
    print(f"      hojas: {', '.join(libro.sheetnames)}")
    return True


def main() -> int:
    """CLI de moldes: genera/refresca plantillas/ (versionados);
    --instalar los copia a data/ SOLO si no existen (nunca pisa datos);
    --migrar agrega las columnas de caja a un data/ ya existente."""
    ap = argparse.ArgumentParser(description="Crea/actualiza las plantillas de datos")
    ap.add_argument(
        "--instalar",
        action="store_true",
        help="Copia las plantillas a data/ (solo si el archivo no existe)",
    )
    ap.add_argument(
        "--forzar",
        action="store_true",
        help="Con --instalar: pisa data/ aunque exista (destructivo)",
    )
    ap.add_argument(
        "--migrar",
        action="store_true",
        help=(
            "Rehace data/plantilla_precios.xlsx al layout unico (fusiona "
            "DESCUENTOS + PRECIOS_FIJOS, elimina SKU_CLIENTES) con backup"
        ),
    )
    ap.add_argument(
        "--solo",
        choices=["sku_bx", "precios"],
        default="",
        help="Crear solo un molde",
    )
    args = ap.parse_args()

    print("=" * 50)
    print("G360 PLANTILLAS (v3.9)")
    print("=" * 50)

    generadas = []
    if args.solo in ("", "sku_bx"):
        generadas.append(crear_sku_bx(DESTINO_PLANTILLAS / "SKU_BX.xlsx"))
    if args.solo in ("", "precios"):
        generadas.append(
            crear_plantilla_precios(DESTINO_PLANTILLAS / "plantilla_precios.xlsx")
        )
    for ruta in generadas:
        print(f"  OK: {ruta.relative_to(RAIZ)}")

    if args.instalar:
        for origen in generadas:
            destino = DESTINO_DATA / origen.name
            if destino.exists() and not args.forzar:
                print(f"  SKIP: {destino.relative_to(RAIZ)} ya existe (no se pisa)")
                continue
            shutil.copy2(origen, destino)
            print(f"  OK: copiado a {destino.relative_to(RAIZ)}")

    if args.migrar:
        fusionar_plantilla_precios(DESTINO_DATA / "plantilla_precios.xlsx")

    return 0


if __name__ == "__main__":
    sys.exit(main())
