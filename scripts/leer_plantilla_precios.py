#!/usr/bin/env python3
"""G360 Plantilla Precios Reader v2.1

Lee plantilla_precios.xlsx y genera el JSON de precios del flujo G360.

v2.1: los descuentos y el precio fijo viven en UNA hoja (SKU_PRECIOS), un
SKU por fila. La hoja SKU_CLIENTES quedo descontinuada (relacion 1-a-muchos:
no cabe en una planilla plana). Las columnas se leen por NOMBRE
(scripts/contratos.py). Si el archivo todavia usa el layout legacy (hojas
DESCUENTOS + PRECIOS_FIJOS) se lee igual, con un aviso de migrar.

Uso:
    python scripts/leer_plantilla_precios.py -i data/plantilla_precios.xlsx
    python scripts/leer_plantilla_precios.py -i ... --sku-bx data/SKU_BX.xlsx
    python scripts/leer_plantilla_precios.py -i ... --catalogo output/catalogo_productos.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
from contratos import (
    CONTRATO_PLANTILLA_DESCUENTOS,
    CONTRATO_PLANTILLA_PRECIOS,
    CONTRATO_PLANTILLA_PRECIOS_FIJOS,
    ErrorContrato,
    huella_fuente,
    limpiar_texto,
    resolver_xlsx,
    sku_texto,
)

VERSION = "2.1.0"

# Descuentos = FRACCION (10% -> 0.10). El rango se valida: un 10 en la celda
# es un error de carga (seria 1000%), no un 10%.
DESC_MIN, DESC_MAX = 0.0, 1.0


def _numero(valor) -> float | None:
    texto = limpiar_texto(valor).replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _fecha(valor) -> str:
    """Fecha ISO (YYYY-MM-DD) desde Excel o texto. '' si no se puede."""
    if valor in (None, ""):
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = limpiar_texto(valor)
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return texto


def leer_plantilla_precios(ruta, skus_validos=None, ordenes=None):
    """Lee la plantilla y devuelve (precios, errores, avisos).

    skus_validos: si se pasa, solo esos SKUs salen en el resultado (el resto
                  se cuenta como ignorado). Pensado para `--catalogo`.
    ordenes:      {sku: orden} para publicar el orden maestro (SKU_BX).
    """
    precios: list[dict] = []
    errores: list[str] = []
    avisos: list[str] = []

    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        hojas = set(libro.sheetnames)

        if "SKU_PRECIOS" in hojas:
            # Layout actual: descuentos + precio fijo en una sola hoja.
            unificados, avisos_uni, errs_uni = _leer_precios_unificados(libro)
            avisos.extend(avisos_uni)
            errores.extend(errs_uni)
            descuentos = {
                sku: {k: v for k, v in item.items() if k.startswith("desc")}
                for sku, item in unificados.items()
                if not item["es_remate"]
            }
            fijos = {sku: item for sku, item in unificados.items() if item["es_remate"]}
        elif "DESCUENTOS" in hojas or "PRECIOS_FIJOS" in hojas:
            avisos.append(
                "layout viejo (hojas DESCUENTOS/PRECIOS_FIJOS): se lee igual, "
                "pero migra con: python scripts/crear_plantillas.py --migrar"
            )
            descuentos, avisos_desc, errs_desc = _leer_descuentos(libro)
            fijos, avisos_fijos, errs_fijos = _leer_precios_fijos(libro)
            avisos.extend(avisos_desc)
            avisos.extend(avisos_fijos)
            errores.extend(errs_desc)
            errores.extend(errs_fijos)
        else:
            errores.append(
                "no encuentro la hoja 'SKU_PRECIOS' (ni las legacy "
                "DESCUENTOS/PRECIOS_FIJOS); hojas encontradas: "
                f"{libro.sheetnames}"
            )
            return precios, errores, avisos

        if "SKU_CLIENTES" in hojas:
            avisos.append(
                "la hoja SKU_CLIENTES ya no se usa (descontinuada); se ignora"
            )
        if "PRODUCTOS" in hojas:
            avisos.append(
                "la hoja PRODUCTOS ya no se usa (el orden vive en SKU_BX); se ignora"
            )
    finally:
        libro.close()

    ignorados = 0
    for sku in sorted(set(descuentos) | set(fijos)):
        if skus_validos is not None and sku not in skus_validos:
            ignorados += 1
            continue
        fijo = fijos.get(sku, {})
        desc = descuentos.get(sku, {})
        item = {
            "sku": sku,
            "orden": (ordenes or {}).get(sku, 0),
            "tipo": "FIJO" if fijo else "DESCUENTO",
            "es_remate": bool(fijo),
            "precio_fijo": fijo.get("precio_fijo"),
            "desc1": desc.get("desc1", 0.0),
            "desc2": desc.get("desc2", 0.0),
            "desc3": desc.get("desc3", 0.0),
            "desc4": desc.get("desc4", 0.0),
            "desc5": desc.get("desc5", 0.0),
            "desc6": desc.get("desc6", 0.0),
            "vigencia_ini": fijo.get("vigencia_precio")
            or desc.get("vigencia_desc", ""),
            "vigencia_fin": fijo.get("vigencia_precio")
            or desc.get("vigencia_desc", ""),
            "observacion": fijo.get("observacion", ""),
        }
        precios.append(item)

    print(f"  SKUs con precios leidos: {len(precios)}")
    if skus_validos is not None:
        print(f"  SKUs ignorados (fuera del catalogo): {ignorados}")
    return precios, errores, avisos


def _leer_precios_unificados(libro):
    """Lee la hoja unica SKU_PRECIOS: descuentos y precio fijo por fila.

    Devuelve {sku: item} donde item ya trae tipo/es_remate/precios/vigencias.
    """
    unificados: dict[str, dict] = {}
    avisos: list[str] = []
    errores: list[str] = []

    columnas, hoja = resolver_xlsx(libro, CONTRATO_PLANTILLA_PRECIOS)
    avisos.extend(columnas.avisos)
    campos_desc = [f"desc{i}" for i in range(1, 7) if columnas.tiene(f"desc{i}")]
    primera = CONTRATO_PLANTILLA_PRECIOS.fila_header + 1
    for n, fila in enumerate(
        hoja.iter_rows(min_row=primera, values_only=True), start=primera
    ):
        sku = sku_texto(columnas.valor(fila, "sku"))
        if not sku:
            continue
        if isinstance(columnas.valor(fila, "sku"), (int, float)):
            avisos.append(
                f"fila {n}: SKU numerico ({columnas.valor(fila, 'sku')}); "
                "si tenia ceros a la izquierda ya se perdieron en el archivo"
            )

        desc: dict[str, float] = {}
        for campo in campos_desc:
            valor = _numero(columnas.valor(fila, campo))
            if valor is None:
                continue
            if not (DESC_MIN <= valor < DESC_MAX):
                errores.append(
                    f"SKU_PRECIOS fila {n} ({sku}) {campo.upper()}={valor}: "
                    "va como fraccion (10% = 0.10)"
                )
                continue
            desc[campo] = valor

        precio_fijo = _numero(columnas.valor(fila, "precio_fijo"))
        if precio_fijo is not None and precio_fijo <= 0:
            errores.append(
                f"SKU_PRECIOS fila {n} ({sku}): PRECIO_FIJO invalido "
                f"({columnas.valor(fila, 'precio_fijo')!r})"
            )
            precio_fijo = None

        if not desc and precio_fijo is None:
            continue  # fila sin datos de precio: se ignora

        if sku in unificados:
            avisos.append(f"SKU {sku} repetido; se usa la ultima fila")

        unificados[sku] = {
            "es_remate": precio_fijo is not None,
            "precio_fijo": precio_fijo,
            "desc1": desc.get("desc1", 0.0),
            "desc2": desc.get("desc2", 0.0),
            "desc3": desc.get("desc3", 0.0),
            "desc4": desc.get("desc4", 0.0),
            "desc5": desc.get("desc5", 0.0),
            "desc6": desc.get("desc6", 0.0),
            "vigencia_desc": _fecha(columnas.valor(fila, "vigencia_desc")),
            "vigencia_precio": _fecha(columnas.valor(fila, "vigencia_precio")),
            "observacion": limpiar_texto(columnas.valor(fila, "observacion")),
        }
    return unificados, avisos, errores


def _leer_descuentos(libro):
    """Layout legacy: hoja DESCUENTOS."""
    datos: dict[str, dict] = {}
    avisos: list[str] = []
    errores: list[str] = []
    columnas, hoja = resolver_xlsx(libro, CONTRATO_PLANTILLA_DESCUENTOS)
    avisos.extend(columnas.avisos)

    campos_desc = [f"desc{i}" for i in range(1, 7) if columnas.tiene(f"desc{i}")]
    primera = CONTRATO_PLANTILLA_DESCUENTOS.fila_header + 1
    for n, fila in enumerate(
        hoja.iter_rows(min_row=primera, values_only=True), start=primera
    ):
        sku = sku_texto(columnas.valor(fila, "sku"))
        if not sku:
            continue
        registro = {campo: 0.0 for campo in campos_desc}
        con_datos = False
        for campo in campos_desc:
            valor = _numero(columnas.valor(fila, campo))
            if valor is None:
                continue
            if not (DESC_MIN <= valor < DESC_MAX):
                errores.append(
                    f"DESCUENTOS fila {n} ({sku}) {campo.upper()}={valor}: "
                    "va como fraccion (10% = 0.10)"
                )
                continue
            registro[campo] = valor
            con_datos = True
        registro["vigencia_desc"] = _fecha(columnas.valor(fila, "vigencia_ini"))
        registro["vigencia_precio"] = ""
        registro["es_remate"] = False
        registro["precio_fijo"] = None
        registro["observacion"] = ""
        if not con_datos:
            continue
        if sku in datos:
            avisos.append(f"DESCUENTOS: SKU {sku} repetido; se usa la ultima fila")
        datos[sku] = registro
    return datos, avisos, errores


def _leer_precios_fijos(libro):
    """Layout legacy: hoja PRECIOS_FIJOS."""
    datos: dict[str, dict] = {}
    avisos: list[str] = []
    errores: list[str] = []
    columnas, hoja = resolver_xlsx(libro, CONTRATO_PLANTILLA_PRECIOS_FIJOS)
    avisos.extend(columnas.avisos)

    primera = CONTRATO_PLANTILLA_PRECIOS_FIJOS.fila_header + 1
    for n, fila in enumerate(
        hoja.iter_rows(min_row=primera, values_only=True), start=primera
    ):
        sku = sku_texto(columnas.valor(fila, "sku"))
        if not sku:
            continue
        precio = _numero(columnas.valor(fila, "precio_fijo"))
        if precio is None or precio <= 0:
            errores.append(
                f"PRECIOS_FIJOS fila {n} ({sku}): PRECIO_FIJO invalido "
                f"({columnas.valor(fila, 'precio_fijo')!r})"
            )
            continue
        if sku in datos:
            avisos.append(f"PRECIOS_FIJOS: SKU {sku} repetido; se usa la ultima fila")
        datos[sku] = {
            "precio_fijo": precio,
            "vigencia_precio": _fecha(columnas.valor(fila, "vigencia_fin")),
            "observacion": limpiar_texto(columnas.valor(fila, "observacion")),
        }
    return datos, avisos, errores


def _ordenes_desde_sku_bx(ruta) -> dict[str, int]:
    from contratos import CONTRATO_SKU_BX

    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        columnas, hoja = resolver_xlsx(libro, CONTRATO_SKU_BX)
        primera = CONTRATO_SKU_BX.fila_header + 1
        ordenes: dict[str, int] = {}
        for fila in hoja.iter_rows(min_row=primera, values_only=True):
            sku = sku_texto(columnas.valor(fila, "sku"))
            valor = _numero(columnas.valor(fila, "orden"))
            if sku and valor is not None:
                ordenes[sku] = int(valor)
        return ordenes
    finally:
        libro.close()


def _skus_del_catalogo(ruta) -> set[str]:
    with open(ruta, encoding="utf-8") as f:
        catalogo = json.load(f)
    return {str(p.get("sku", "")).strip() for p in catalogo.get("productos", [])}


def gen_meta(precios, ruta, avisos=None) -> dict:
    tipos = sorted({p.get("tipo", "DESCUENTO") for p in precios})
    return {
        "version": VERSION,
        "generated_at": datetime.now().isoformat(),
        "source_file": Path(ruta).name,
        "fuente": huella_fuente(ruta),
        "total_precios": len(precios),
        "tipos_precio": tipos,
        "moneda_default": "PEN",
        "formato": "plantilla_precios",
        "descuentos_en": "fraccion (10% = 0.10)",
        "total_remates": sum(1 for p in precios if p.get("es_remate")),
        "avisos": list(avisos or []),
        "nota": (
            "Productos con 'es_remate': true son remates/liquidaciones y deben "
            "resaltarse en reportes"
        ),
    }


def guardar(datos, ruta):
    try:
        p = Path(ruta)
        if p.exists():
            bk = p.with_suffix(f".{datetime.now():%Y%m%d_%H%M%S}.bak.json")
            p.rename(bk)
            print(f"Backup: {bk.name}")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        print(f"Guardado: {ruta}")
        return True
    except OSError as e:
        print(f"Error: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description=f"G360 Plantilla Precios Reader v{VERSION}"
    )
    ap.add_argument("--input", "-i", required=True, help="Excel plantilla_precios.xlsx")
    ap.add_argument("--output", "-o", default="precios_productos.json")
    ap.add_argument(
        "--sku-bx", default="", help="SKU_BX.xlsx para publicar el orden maestro"
    )
    ap.add_argument(
        "--catalogo",
        default="",
        help="catalogo_productos.json: solo salen los SKUs publicados",
    )
    ap.add_argument("--validate-only", "-v", action="store_true")
    args = ap.parse_args()

    print("=" * 50)
    print(f"G360 PLANTILLA PRECIOS READER v{VERSION}")
    print("=" * 50)
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print()

    ordenes = None
    if args.sku_bx:
        ordered = _ordenes_desde_sku_bx(args.sku_bx)
        ordenes = ordered
        print(f"  Orden desde {args.sku_bx}: {len(ordered)} SKUs")
    skus_validos = None
    if args.catalogo:
        skus_validos = _skus_del_catalogo(args.catalogo)
        print(f"  Filtro por catalogo: {len(skus_validos)} SKUs")

    try:
        precios, errores, avisos = leer_plantilla_precios(
            args.input, skus_validos=skus_validos, ordenes=ordenes
        )
    except ErrorContrato as e:
        print()
        print(str(e))
        return 1

    for aviso in avisos[:20]:
        print(f"  AVISO: {aviso}")
    if len(avisos) > 20:
        print(f"  AVISO: ... y {len(avisos) - 20} mas")
    if errores:
        print(f"\nErrores ({len(errores)}):")
        for error in errores[:20]:
            print(f"  ERROR: {error}")
        if len(errores) > 20:
            print(f"  ... y {len(errores) - 20} mas")

    if not precios:
        print("\nSin precios validos")
        return 1

    print(f"\nOK: {len(precios)} precios")
    print(f"Con descuentos: {sum(1 for p in precios if p['tipo'] == 'DESCUENTO')}")
    print(f"Precios fijos: {sum(1 for p in precios if p['tipo'] == 'FIJO')}")

    if args.validate_only:
        print("\nValidacion completada")
        return 1 if errores else 0

    meta = gen_meta(precios, args.input, avisos)
    if not guardar({"metadata": meta, "precios": precios}, args.output):
        return 1
    print(f"\n{'=' * 50}")
    print("PRECIOS GENERADOS")
    print(f"{'=' * 50}")
    print(f"Total: {meta['total_precios']}")
    print(f"Tipos: {', '.join(meta['tipos_precio'])}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
