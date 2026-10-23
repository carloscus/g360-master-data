#!/usr/bin/env python3
"""Lector unificado SKU_PRECIOS.xlsx (v3.8).

Lee el archivo consolidado con 2 hojas:

  SKU_LOGISTICA  → ORDEN, SKU, UN_BX, ESTADO_LINEA, LARGO, ANCHO, ALTO,
                   PESO_CAJA_KG, M3_CAJA (calculo automatico en Excel),
                   M3_UNIDAD (calculo automatico).
  SKU_PRECIOS    → SKU, DESC1..6, VIGENCIA_DESC, PRECIO_FIJO,
                   VIGENCIA_PRECIO, OBSERVACION.

Devuelve:
  DatosKardex = namedtuple(orden, un_bx, estado, caja, precios)

El generador usa esto en lugar de leer SKU_BX.xlsx + plantilla_precios.xlsx
por separado. La union se hace por SKU.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("ERROR: pip install openpyxl")
    sys.exit(1)

from contratos import (
    CONTRATO_SKU_LOGISTICA,
    CONTRATO_SKU_PRECIOS,
    ErrorContrato,
    calcular_m3,
    limpiar_texto,
    resolver_xlsx,
    sku_texto,
)

VERSION = "1.0.0"


@dataclass
class DatosKardex:
    """Resultado de leer SKU_PRECIOS.xlsx."""

    orden: dict[str, int] = field(default_factory=dict)
    un_bx: dict[str, int] = field(default_factory=dict)
    estado: dict[str, str] = field(default_factory=dict)
    caja: dict[str, dict] = field(default_factory=dict)
    precios: dict[str, dict] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    @property
    def skus(self) -> set[str]:
        return set(self.orden)


def _entero(valor) -> int:
    texto = limpiar_texto(valor)
    if not texto:
        return 0
    try:
        return int(float(texto))
    except (ValueError, TypeError):
        return 0


def _fraccion(valor) -> float | None:
    texto = limpiar_texto(valor).replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _fecha(valor) -> str:
    if valor in (None, ""):
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    try:
        return str(datetime.strptime(limpiar_texto(valor), "%Y-%m-%d").date())
    except ValueError:
        return limpiar_texto(valor)


def leer_sku_precios(ruta: str, skus_validos: set[str] | None = None):
    """Lee SKU_PRECIOS.xlsx y devuelve DatosKardex.

    skus_validos: si se pasa, solo se incluyen los precios de esos SKUs
                  (el resto se cuenta como ignorado). Usado cuando se valida
                  contra un catalogo ya generado.
    """
    datos = DatosKardex()
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        # ── SKU_LOGISTICA ──
        try:
            columnas, hoja = resolver_xlsx(libro, CONTRATO_SKU_LOGISTICA)
            for aviso in columnas.avisos:
                datos.avisos.append(f"[SKU_LOGISTICA] {aviso}")
            primera = CONTRATO_SKU_LOGISTICA.fila_header + 1
            for n, fila in enumerate(
                hoja.iter_rows(min_row=primera, values_only=True), start=primera
            ):
                sku = sku_texto(columnas.valor(fila, "sku"))
                if not sku:
                    continue
                if isinstance(columnas.valor(fila, "sku"), (int, float)):
                    datos.avisos.append(
                        f"[SKU_LOGISTICA] fila {n}: SKU numerico ({columnas.valor(fila, 'sku')}); "
                        "los ceros a la izquierda ya se perdieron"
                    )
                orden = _entero(columnas.valor(fila, "orden"))
                datos.orden[sku] = orden
                un_bx = _entero(columnas.valor(fila, "un_bx"))
                if un_bx:
                    datos.un_bx[sku] = un_bx
                estado = limpiar_texto(columnas.valor(fila, "estado_linea"))
                if estado:
                    datos.estado[sku] = estado

                largo = float(columnas.valor(fila, "largo_cm") or 0) or 0
                ancho = float(columnas.valor(fila, "ancho_cm") or 0) or 0
                alto = float(columnas.valor(fila, "alto_cm") or 0) or 0
                m3 = calcular_m3(largo, ancho, alto)
                if m3 is not None:
                    datos.caja[sku] = {
                        "largo_cm": round(largo, 2),
                        "ancho_cm": round(ancho, 2),
                        "alto_cm": round(alto, 2),
                        "m3_caja": m3,
                        "m3_unidad": round(m3 / un_bx, 6) if un_bx else None,
                        "peso_caja_kg": round(
                            float(columnas.valor(fila, "peso_caja_kg") or 0), 3
                        )
                        or None,
                    }
                elif largo or ancho or alto:
                    datos.avisos.append(
                        f"[SKU_LOGISTICA] fila {n} ({sku}): caja incompleta "
                        f"(largo={largo}, ancho={ancho}, alto={alto}); no se publica volumen"
                    )
        except ErrorContrato as e:
            datos.avisos.append(str(e))
            datos.avisos.append(
                "[SKU_LOGISTICA] no se pudo leer la hoja (contrato roto)"
            )

        # ── SKU_PRECIOS ──
        try:
            columnas, hoja = resolver_xlsx(libro, CONTRATO_SKU_PRECIOS)
            for aviso in columnas.avisos:
                datos.avisos.append(f"[SKU_PRECIOS] {aviso}")
            primera = CONTRATO_SKU_PRECIOS.fila_header + 1
            for n, fila in enumerate(
                hoja.iter_rows(min_row=primera, values_only=True), start=primera
            ):
                sku = sku_texto(columnas.valor(fila, "sku"))
                if not sku:
                    continue
                if isinstance(columnas.valor(fila, "sku"), (int, float)):
                    datos.avisos.append(
                        f"[SKU_PRECIOS] fila {n}: SKU numerico ({columnas.valor(fila, 'sku')}); "
                        "los ceros a la izquierda ya se perdieron"
                    )

                campos_desc = [
                    col
                    for col in ("desc1", "desc2", "desc3", "desc4", "desc5", "desc6")
                    if columnas.tiene(col)
                ]
                desc = {}
                for campo in campos_desc:
                    valor = _fraccion(columnas.valor(fila, campo))
                    if valor is not None:
                        if not (0 <= valor < 1):
                            datos.avisos.append(
                                f"[SKU_PRECIOS] fila {n} ({sku}) {campo.upper()}={valor}: "
                                "va como fraccion (10% = 0.10)"
                            )
                        else:
                            desc[campo] = valor

                precio_fijo = _fraccion(columnas.valor(fila, "precio_fijo"))
                if precio_fijo is not None and precio_fijo <= 0:
                    datos.avisos.append(
                        f"[SKU_PRECIOS] fila {n} ({sku}): PRECIO_FIJO invalido "
                        f"({columnas.valor(fila, 'precio_fijo')!r})"
                    )
                    precio_fijo = None

                if not desc and precio_fijo is None:
                    continue  # SKU sin ningun tipo de precio: se ignora

                item = {
                    "tipo": "FIJO" if precio_fijo is not None else "DESCUENTO",
                    "es_remate": precio_fijo is not None,
                    "precio_fijo": precio_fijo,
                    "desc1": desc.get("desc1", 0.0),
                    "desc2": desc.get("desc2", 0.0),
                    "desc3": desc.get("desc3", 0.0),
                    "desc4": desc.get("desc4", 0.0),
                    "desc5": desc.get("desc5", 0.0),
                    "desc6": desc.get("desc6", 0.0),
                    "vigencia_ini": _fecha(columnas.valor(fila, "vigencia_desc")),
                    "vigencia_fin": _fecha(columnas.valor(fila, "vigencia_precio")),
                    "observacion": limpiar_texto(columnas.valor(fila, "observacion")),
                }
                datos.precios[sku] = item
        except ErrorContrato as e:
            datos.avisos.append(str(e))
            datos.avisos.append("[SKU_PRECIOS] no se pudo leer la hoja (contrato roto)")
    finally:
        libro.close()

    if skus_validos is not None:
        ignorados = sum(
            1
            for sku in set(datos.orden) | set(datos.precios)
            if sku not in skus_validos
        )
        if ignorados:
            datos.avisos.append(
                f"[SKU_PRECIOS] {ignorados} SKU(s) fuera del catalogo (ignorados)"
            )

    for aviso in datos.avisos[:30]:
        print(f"  AVISO: {aviso}")
    if len(datos.avisos) > 30:
        print(f"  AVISO: ... y {len(datos.avisos) - 30} mas")

    print(f"  SKU_LOGISTICA: {len(datos.orden)} filas")
    print(f"  SKU_LOGISTICA: {len(datos.un_bx)} con un_bx definido")
    print(f"  SKU_LOGISTICA: {len(datos.estado)} con estado_linea")
    print(f"  SKU_LOGISTICA: {len(datos.caja)} con caja (largo/ancho/alto/m3)")
    print(f"  SKU_PRECIOS: {len(datos.precios)} con descuento o precio_fijo")
    return datos


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Lector unificado SKU_PRECIOS v{VERSION}")
    ap.add_argument("--input", "-i", required=True, help="SKU_PRECIOS.xlsx")
    ap.add_argument("--output", "-o", default="sku_precios.json")
    ap.add_argument(
        "--catalogo",
        default="",
        help="catalogo_productos.json: solo muestra precios de SKUs publicados",
    )
    args = ap.parse_args()

    print("=" * 50)
    print(f"G360 SKU_PRECIOS READER v{VERSION}")
    print("=" * 50)
    print(f"Input:  {args.input}")
    print()

    skus_validos = None
    if args.catalogo:
        with open(args.catalogo, encoding="utf-8") as f:
            catalogo = json.load(f)
        skus_validos = {
            str(p.get("sku", "")).strip() for p in catalogo.get("productos", [])
        }
        print(f"  Filtro por catalogo: {len(skus_validos)} SKUs")

    try:
        datos = leer_sku_precios(args.input, skus_validos=skus_validos)
    except ErrorContrato as e:
        print()
        print(str(e))
        return 1

    salida = {
        "metadata": {
            "version": VERSION,
            "generated_at": datetime.now().isoformat(),
            "source_file": Path(args.input).name,
            "total_skus_logistica": len(datos.orden),
            "total_skus_precios": len(datos.precios),
            "total_con_caja": len(datos.caja),
            "total_con_descuento": sum(
                1 for p in datos.precios.values() if p["tipo"] == "DESCUENTO"
            ),
            "total_con_precio_fijo": sum(
                1 for p in datos.precios.values() if p["tipo"] == "FIJO"
            ),
            "avisos": datos.avisos,
        },
        "logistica": {
            "orden": datos.orden,
            "un_bx": datos.un_bx,
            "estado": datos.estado,
            "caja": datos.caja,
        },
        "precios": datos.precios,
    }

    try:
        p = Path(args.output)
        bk = p.with_suffix(f".{datetime.now():%Y%m%d_%H%M%S}.bak.json")
        if p.exists():
            p.rename(bk)
            print(f"Backup: {bk.name}")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(salida, f, ensure_ascii=False, indent=2)
        print(f"\nOK: guardado en {args.output}")
        return 0
    except OSError as e:
        print(f"\nERROR al guardar: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
