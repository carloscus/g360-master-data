#!/usr/bin/env python3
"""Valida los encabezados de todas las fuentes antes de generar el catalogo.

Es el paso 0 del workflow (actualizar_catalogo.bat): si una fuente cambio de
formato, se corta aca con un mensaje util en vez de generar un catalogo
corrupto que nadie nota.

Valida, por fuente:
  - que existan las columnas obligatorias (por NOMBRE, con alias);
  - que el contenido de las columnas clave sea del tipo esperado
    (un SKU parece SKU, un precio es numero): esto detecta el corrimiento de
    columnas que la sola presencia del encabezado no ve;
  - avisos: orden de columnas distinto al historico, duplicados, columnas de
    mas, cajas incompletas, SKUs numericos (perdida de ceros), etc.
  - revision de guia: cada SKU de SKU_BX/precios que no va a entrar al
    catalogo se reporta con el motivo (inactivo / proceso / tipeo /
    en KARDEX pero no en ERP / inexistente) para revisarlo o eliminarlo.
    Los ya revisados se silencian en config/guia_ignorados.json.

Uso:
    python scripts/validar_encabezados.py
    python scripts/validar_encabezados.py --data-dir data --s1-xls ruta.xls
    python scripts/validar_encabezados.py --json

Salida: 0 si no hay errores (puede haber avisos), 1 si hay errores.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from contratos import (
    ALMACENES_S1,
    CONTRATO_ERP,
    CONTRATO_KARDEX,
    CONTRATO_SKU_BX,
    CONTRATO_SKU_LOGISTICA,
    CONTRATO_SKU_PRECIOS,
    CONTRATO_PLANTILLA_PRECIOS,
    ErrorContrato,
    almacenes_fuera_de_lista,
    calcular_m3,
    cargar_guia_ignorados,
    detectar_columnas_s1,
    limpiar_texto,
    normalizar_encabezado,
    resolver_xls,
    resolver_xlsx,
    sku_texto,
)

RAIZ = Path(__file__).resolve().parent.parent

# Orden historico del export del ERP. Si cambia, se avisa: el generador lee
# por nombre y sigue funcionando, pero conviene saberlo (un export reordenado
# suele venir de una version nueva del sistema).
ORDEN_ERP_HISTORICO = (
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
)

MUESTRA = 200
UMBRAL_CONTENIDO = 0.90


@dataclass
class Bloque:
    """Resultado de validar una fuente.

    `bloqueante` distingue las fuentes que alimentan el catalogo (ERP,
    SKU_BX, S1) de las que todavia no lo alimentan (plantilla de precios,
    KARDEX): un defecto en estas ultimas se reporta, pero no frena la
    publicacion.
    """

    fuente: str
    ruta: str
    bloqueante: bool = True
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    omitido: str = ""

    @property
    def estado(self) -> str:
        if self.omitido:
            return "skip"
        if self.errores:
            return "error"
        if self.avisos:
            return "aviso"
        return "ok"

    def como_dict(self) -> dict:
        return {
            "fuente": self.fuente,
            "ruta": self.ruta,
            "bloqueante": self.bloqueante,
            "estado": self.estado,
            "omitido": self.omitido,
            "errores": self.errores,
            "avisos": self.avisos,
            "info": self.info,
        }


def _proporcion(valores, predicado) -> float:
    valores = [v for v in valores if not _sin_valor(v)]
    if not valores:
        return 0.0
    return sum(1 for v in valores if predicado(v)) / len(valores)


def _sin_valor(valor) -> bool:
    return valor is None or limpiar_texto(valor) in ("", "None")


def _parece_sku(valor) -> bool:
    texto = sku_texto(valor).upper()
    return bool(re.fullmatch(r"[0-9A-Z]{4,9}", texto))


def _aviso_columnas(bloque: Bloque, columnas) -> None:
    bloque.avisos.extend(columnas.avisos)
    ausentes = columnas.faltantes_opcionales
    if ausentes:
        bloque.avisos.append(
            f"{len(ausentes)} columna(s) opcional(es) ausente(s): "
            f"{', '.join(ausentes)} (la fuente sigue siendo valida)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ERP
# ─────────────────────────────────────────────────────────────────────────────


def validar_erp(ruta: Path) -> Bloque:
    bloque = Bloque("ERP (PRODUCTOS.xls)", str(ruta))
    if not ruta.exists():
        bloque.omitido = f"no existe {ruta}"
        return bloque

    import xlrd

    libro = xlrd.open_workbook(str(ruta))
    try:
        try:
            columnas, hoja = resolver_xls(libro, CONTRATO_ERP)
        except ErrorContrato as e:
            bloque.errores.append(str(e))
            return bloque
        _aviso_columnas(bloque, columnas)

        encabezado = [normalizar_encabezado(h) for h in columnas.encabezados]
        no_vacias = [h for h in encabezado if h]
        if tuple(no_vacias) != ORDEN_ERP_HISTORICO:
            bloque.avisos.append(
                "el orden de columnas cambio respecto al historico "
                f"({len(no_vacias)} columnas); se leyo por NOMBRE, asi que "
                "los datos son correctos"
            )
        if hoja.name and hoja.name != CONTRATO_ERP.hoja:
            bloque.avisos.append(
                f"la hoja se llama {hoja.name!r} (historico: "
                f"{CONTRATO_ERP.hoja!r}); se acepto porque es la unica"
            )

        filas = [
            hoja.row_values(r)
            for r in range(CONTRATO_ERP.fila_header, min(hoja.nrows, MUESTRA + 2))
        ]
        total = hoja.nrows - CONTRATO_ERP.fila_header
        bloque.info.append(f"{total} filas de datos")
        if not filas:
            bloque.errores.append("el archivo no tiene filas de datos")
            return bloque

        i_sku = columnas.idx("sku")
        i_precio = columnas.idx("precio")
        i_linea = columnas.idx("linea")
        i_inactivo = columnas.idx("inactivo")

        proporcion_sku = _proporcion([f[i_sku] for f in filas], _parece_sku)
        if proporcion_sku < UMBRAL_CONTENIDO:
            bloque.errores.append(
                f"la columna SKU ('{columnas.contrato.requeridas['sku'][0]}', "
                f"posicion {i_sku + 1}) no contiene SKUs: "
                f"{proporcion_sku:.0%} de la muestra. Ejemplo: {filas[0][i_sku]!r}. "
                "El export cambio de formato."
            )

        def _numero(valor) -> bool:
            try:
                float(limpiar_texto(valor).replace(",", ""))
                return True
            except (TypeError, ValueError):
                return False

        proporcion_precio = _proporcion([f[i_precio] for f in filas], _numero)
        if proporcion_precio < UMBRAL_CONTENIDO:
            bloque.errores.append(
                f"la columna PRECIO (posicion {i_precio + 1}) no contiene "
                f"numeros: {proporcion_precio:.0%} de la muestra. "
                f"Ejemplo: {filas[0][i_precio]!r}. El export cambio de formato."
            )

        proporcion_linea = sum(1 for f in filas if limpiar_texto(f[i_linea])) / len(
            filas
        )
        if proporcion_linea < 0.5:
            bloque.avisos.append(
                f"la columna LINEA viene vacia en {1 - proporcion_linea:.0%} "
                "de la muestra"
            )

        flags = {normalizar_encabezado(f[i_inactivo]) for f in filas}
        raros = flags - {"CHECKED", "UNCHECKED", ""}
        if raros:
            bloque.avisos.append(
                f"FLG_INACTIVO trae valores no esperados: {sorted(raros)[:5]}"
            )

        tipos = {hoja.cell_type(r, i_sku) for r in range(1, min(hoja.nrows, MUESTRA))}
        if 2 in tipos:
            bloque.avisos.append(
                "hay SKUs guardados como NUMERO en el ERP: si tenian ceros a la "
                "izquierda ya estan perdidos en el archivo"
            )

        vistos: set[str] = set()
        duplicados: list[str] = []
        for f in filas:
            sku = sku_texto(f[i_sku])
            if not sku:
                continue
            if sku in vistos:
                duplicados.append(sku)
            vistos.add(sku)
        if duplicados:
            bloque.avisos.append(
                f"{len(duplicados)} SKU(s) duplicado(s) en la muestra "
                f"(ej: {', '.join(duplicados[:5])}); el generador se queda con "
                "el primero"
            )
    finally:
        libro.release_resources()
    return bloque


# ─────────────────────────────────────────────────────────────────────────────
# SKU_BX
# ─────────────────────────────────────────────────────────────────────────────


def validar_sku_bx(ruta: Path) -> Bloque:
    import openpyxl

    bloque = Bloque("SKU_BX.xlsx", str(ruta))
    if not ruta.exists():
        bloque.omitido = f"no existe {ruta}"
        return bloque

    libro = openpyxl.load_workbook(ruta, data_only=True)
    try:
        try:
            columnas, hoja = resolver_xlsx(libro, CONTRATO_SKU_BX)
        except ErrorContrato as e:
            bloque.errores.append(str(e))
            return bloque
        _aviso_columnas(bloque, columnas)

        primera = CONTRATO_SKU_BX.fila_header + 1
        filas = list(
            hoja.iter_rows(
                min_row=primera,
                max_row=min(hoja.max_row, primera + MUESTRA * 5),
                values_only=True,
            )
        )
        bloque.info.append(f"{hoja.max_row - CONTRATO_SKU_BX.fila_header} filas")

        i_sku = columnas.idx("sku")
        i_un_bx = columnas.idx("un_bx")

        numericos = 0
        vistos: set[str] = set()
        duplicados: list[str] = []
        for n, fila in enumerate(filas, start=primera):
            crudo = columnas.valor(fila, "sku")
            sku = sku_texto(crudo)
            if not sku:
                continue
            if isinstance(crudo, (int, float)):
                numericos += 1
            if sku in vistos:
                duplicados.append(sku)
            vistos.add(sku)
        if numericos:
            bloque.errores.append(
                f"{numericos} SKU(s) guardados como numero: los ceros a la "
                "izquierda se pierden y el SKU deja de coincidir con el ERP. "
                "Formatea la columna SKU como TEXTO."
            )
        proporcion_sku = _proporcion([fila[i_sku] for fila in filas], _parece_sku)
        if proporcion_sku < UMBRAL_CONTENIDO:
            bloque.errores.append(
                f"la columna SKU no parece contener SKUs "
                f"({proporcion_sku:.0%} de la muestra)"
            )
        if duplicados:
            bloque.avisos.append(
                f"{len(duplicados)} SKU(s) duplicado(s) "
                f"(ej: {', '.join(duplicados[:5])}); se usa la ultima fila"
            )

        def _entero(valor) -> bool:
            texto = limpiar_texto(valor)
            if not texto:
                return False
            try:
                numero = float(texto)
            except (TypeError, ValueError):
                return False
            return numero >= 1 and numero == int(numero)

        proporcion_un_bx = _proporcion([fila[i_un_bx] for fila in filas], _entero)
        if proporcion_un_bx < 0.80:
            bloque.errores.append(
                f"la columna UN_BX no contiene enteros >= 1 en "
                f"{1 - proporcion_un_bx:.0%} de las filas"
            )

        if not columnas.tiene("largo_cm"):
            bloque.info.append(
                "sin caja: la plantilla vieja es valida (el volumen es opcional)"
            )
        else:
            completo = incompleto = 0
            for fila in filas:
                lados = [
                    columnas.valor(fila, "largo_cm"),
                    columnas.valor(fila, "ancho_cm"),
                    columnas.valor(fila, "alto_cm"),
                ]
                if not any(limpiar_texto(v) for v in lados):
                    continue
                if calcular_m3(*lados) is None:
                    incompleto += 1
                else:
                    completo += 1
            bloque.info.append(
                f"caja: {completo} completa(s), {incompleto} incompleta(s)"
            )
            if incompleto:
                bloque.avisos.append(
                    f"{incompleto} fila(s) con caja incompleta: hace falta "
                    "largo, ancho y alto (> 0) para publicar el m3"
                )
    finally:
        libro.close()
    return bloque


# ─────────────────────────────────────────────────────────────────────────────
# SKU_PRECIOS.xlsx (formato unificado: 2 hojas)
# ─────────────────────────────────────────────────────────────────────────────


def validar_sku_precios(ruta: Path) -> Bloque:
    """Valida el archivo consolidado (SKU_LOGISTICA + SKU_PRECIOS)."""
    import openpyxl

    bloque = Bloque("SKU_PRECIOS.xlsx (unificado)", str(ruta))
    if not ruta.exists():
        bloque.omitido = f"no existe {ruta} (se usara SKU_BX.xlsx)"
        return bloque

    libro = openpyxl.load_workbook(ruta, data_only=True)
    try:
        for contrato in (CONTRATO_SKU_LOGISTICA, CONTRATO_SKU_PRECIOS):
            nombre_hoja = contrato.hoja
            try:
                columnas, hoja = resolver_xlsx(libro, contrato)
            except ErrorContrato as e:
                bloque.errores.append(str(e))
                continue
            _aviso_columnas(bloque, columnas)

            filas = list(
                hoja.iter_rows(
                    min_row=contrato.fila_header + 1,
                    max_row=min(hoja.max_row, contrato.fila_header + MUESTRA * 5),
                    values_only=True,
                )
            )
            con_sku = [f for f in filas if sku_texto(columnas.valor(f, "sku"))]
            bloque.info.append(f"{nombre_hoja}: {len(con_sku)} fila(s)")

            numericos = sum(
                1 for f in con_sku if isinstance(columnas.valor(f, "sku"), (int, float))
            )
            if numericos:
                bloque.errores.append(
                    f"{nombre_hoja}: {numericos} SKU(s) guardados como numero "
                    "(se pierden los ceros); formatea la columna como TEXTO"
                )

            if nombre_hoja == "SKU_LOGISTICA":
                if not columnas.tiene("largo_cm"):
                    bloque.info.append("sin caja (el volumen es opcional)")
                else:
                    completo = incompleto = 0
                    for fila in filas:
                        lados = [
                            columnas.valor(fila, "largo_cm"),
                            columnas.valor(fila, "ancho_cm"),
                            columnas.valor(fila, "alto_cm"),
                        ]
                        if not any(limpiar_texto(v) for v in lados):
                            continue
                        if calcular_m3(*lados) is None:
                            incompleto += 1
                        else:
                            completo += 1
                    bloque.info.append(
                        f"caja: {completo} completa(s), {incompleto} incompleta(s)"
                    )
            else:
                con_precio = 0
                for fila in con_sku:
                    descs = [
                        columnas.valor(fila, f"desc{i}")
                        for i in range(1, 7)
                        if columnas.tiene(f"desc{i}")
                    ]
                    precio = columnas.valor(fila, "precio_fijo")
                    if any(limpiar_texto(v) for v in descs) or limpiar_texto(precio):
                        con_precio += 1
                bloque.info.append(f"con descuento o precio fijo: {con_precio}")

        # Cross-check: los SKU de precios deberian existir en la hoja logistica
        if "SKU_LOGISTICA" in libro.sheetnames and "SKU_PRECIOS" in libro.sheetnames:
            ws_log = libro["SKU_LOGISTICA"]
            ws_prc = libro["SKU_PRECIOS"]
            log_skus = {
                sku_texto(c[1])
                for c in ws_log.iter_rows(min_row=2, values_only=True)
                if len(c) > 1 and sku_texto(c[1])
            }
            prc_skus = {
                sku_texto(c[0])
                for c in ws_prc.iter_rows(min_row=2, values_only=True)
                if c and sku_texto(c[0])
            }
            fuera = prc_skus - log_skus
            if fuera:
                bloque.avisos.append(
                    f"{len(fuera)} SKU(s) en SKU_PRECIOS no estan en SKU_LOGISTICA "
                    f"(ej: {', '.join(sorted(fuera)[:5])}); sus precios quedan sin "
                    "guia (no aparecen en el catalogo si no tienen stock)"
                )
    finally:
        libro.close()
    return bloque


# ─────────────────────────────────────────────────────────────────────────────
# Plantilla de precios
# ─────────────────────────────────────────────────────────────────────────────


def validar_plantilla(ruta: Path) -> Bloque:
    import openpyxl

    bloque = Bloque("plantilla_precios.xlsx", str(ruta), bloqueante=False)
    if not ruta.exists():
        bloque.omitido = f"no existe {ruta}"
        return bloque

    libro = openpyxl.load_workbook(ruta, data_only=True)
    try:
        hojas = set(libro.sheetnames)

        # Hojas muertas: se avisa para que se borren.
        if "SKU_CLIENTES" in hojas:
            bloque.avisos.append(
                "la hoja SKU_CLIENTES ya no se usa (descontinuada): se puede borrar"
            )
        if "PRODUCTOS" in hojas:
            bloque.avisos.append(
                "la hoja PRODUCTOS ya no se usa (el orden vive en SKU_BX): "
                "se puede borrar"
            )

        # Layout actual: UNA hoja SKU_PRECIOS (descuentos + precio fijo).
        if "SKU_PRECIOS" in hojas:
            contrato = CONTRATO_PLANTILLA_PRECIOS
            try:
                columnas, hoja = resolver_xlsx(libro, contrato)
            except ErrorContrato as e:
                bloque.errores.append(str(e))
                return bloque
            _aviso_columnas(bloque, columnas)
            filas = list(
                hoja.iter_rows(
                    min_row=contrato.fila_header + 1,
                    max_row=min(hoja.max_row, contrato.fila_header + MUESTRA * 5),
                    values_only=True,
                )
            )
            con_sku = [f for f in filas if sku_texto(columnas.valor(f, "sku"))]
            con_precio = 0
            for f in con_sku:
                descs = [
                    columnas.valor(f, f"desc{i}")
                    for i in range(1, 7)
                    if columnas.tiene(f"desc{i}")
                ]
                precio = columnas.valor(f, "precio_fijo")
                if any(limpiar_texto(v) for v in descs) or limpiar_texto(precio):
                    con_precio += 1
            bloque.info.append(
                f"SKU_PRECIOS: {len(con_sku)} fila(s) ({con_precio} con precio)"
            )

            numericos = sum(
                1 for f in con_sku if isinstance(columnas.valor(f, "sku"), (int, float))
            )
            if numericos:
                bloque.errores.append(
                    f"SKU_PRECIOS: {numericos} SKU(s) guardados como numero (se "
                    "pierden los ceros a la izquierda); formatea la columna como TEXTO"
                )

            if "desc1" in columnas.indices:
                campos = [c for c in columnas.indices if c.startswith("desc")]
                valores = []
                for f in con_sku:
                    for campo in campos:
                        valor = limpiar_texto(columnas.valor(f, campo))
                        if valor:
                            valores.append(valor)
                fuera = [v for v in valores if not _fraccion_valida(v)]
                if fuera:
                    bloque.errores.append(
                        f"SKU_PRECIOS: {len(fuera)} descuento(s) fuera de rango "
                        f"(ej: {fuera[:3]}). Se guardan como FRACCION: 10% = 0.10"
                    )
            return bloque

        # Layout legacy (2 hojas): se lee con aviso, no bloquea.
        if "DESCUENTOS" in hojas or "PRECIOS_FIJOS" in hojas:
            bloque.avisos.append(
                "layout viejo (hojas DESCUENTOS/PRECIOS_FIJOS): funciona, pero "
                "migra con: python scripts/crear_plantillas.py --migrar"
            )
            bloque.info.append("hojas legacy detectadas; validacion informativa")
            return bloque

        bloque.errores.append(
            "no encuentro la hoja 'SKU_PRECIOS' (ni las legacy "
            f"DESCUENTOS/PRECIOS_FIJOS); hojas: {libro.sheetnames}"
        )
    finally:
        libro.close()
    return bloque


def _fraccion_valida(valor: str) -> bool:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return False
    return 0 <= numero < 1


# ─────────────────────────────────────────────────────────────────────────────
# S1 (reporte sin encabezado real: se ubica por anclas)
# ─────────────────────────────────────────────────────────────────────────────


def validar_s1(ruta: Path) -> Bloque:
    import xlrd

    bloque = Bloque("Reporte S1 (.xls)", str(ruta))
    if not ruta.exists():
        bloque.omitido = f"no existe {ruta}"
        return bloque

    libro = xlrd.open_workbook(str(ruta))
    try:
        hoja = libro.sheet_by_index(0)
        filas = [hoja.row_values(r) for r in range(hoja.nrows)]
        try:
            columnas = detectar_columnas_s1(filas)
        except ErrorContrato as e:
            bloque.errores.append(str(e))
            return bloque
        bloque.avisos.extend(columnas.avisos)
        bloque.info.append(
            f"header en fila {columnas.fila_header + 1}, datos desde la fila "
            f"{columnas.fila_datos + 1} ({hoja.nrows - columnas.fila_datos} filas)"
        )

        muestra = filas[columnas.fila_datos : columnas.fila_datos + 50]

        def _entero(valor) -> bool:
            try:
                float(limpiar_texto(valor).replace(",", ""))
                return True
            except (TypeError, ValueError):
                return False

        for campo in ("stock", "predespacho"):
            proporcion = _proporcion(
                [columnas.valor(f, campo) for f in muestra], _entero
            )
            if proporcion < UMBRAL_CONTENIDO:
                bloque.errores.append(
                    f"la columna {campo.upper()} (posicion "
                    f"{columnas.indices.get(campo, 0) + 1}) no es numerica en "
                    f"{(1 - proporcion):.0%} de la muestra: el reporte cambio "
                    "de formato o de ancho de columnas"
                )

        proporcion_sku = _proporcion(
            [columnas.valor(f, "sku") for f in muestra], _parece_sku
        )
        if proporcion_sku < UMBRAL_CONTENIDO:
            bloque.errores.append(
                f"la columna SKU detectada (posicion {columnas.idx_sku + 1}) no "
                f"contiene SKUs en {(1 - proporcion_sku):.0%} de la muestra"
            )

        almacenes = {
            limpiar_texto(columnas.valor(f, "almacen")).upper()
            for f in muestra
            if limpiar_texto(columnas.valor(f, "almacen"))
        }
        fuera = almacenes_fuera_de_lista(almacenes)
        if fuera:
            bloque.avisos.append(
                f"almacen(es) fuera de la lista publicada {list(ALMACENES_S1)}: "
                f"{fuera} (si son internos, el generador de catalogo los ignora; "
                "si son nuevos, hay que sumarlos a la lista)"
            )
        bloque.info.append(f"almacenes en la muestra: {sorted(almacenes)}")
    finally:
        libro.release_resources()
    return bloque


# ─────────────────────────────────────────────────────────────────────────────
# KARDEX (informativo: todavia no alimenta el catalogo)
# ─────────────────────────────────────────────────────────────────────────────


def validar_kardex(ruta: Path) -> Bloque:
    import openpyxl

    bloque = Bloque("KARDEX_BASE.xlsx", str(ruta), bloqueante=False)
    if not ruta.exists():
        bloque.omitido = f"no existe {ruta}"
        return bloque

    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        try:
            columnas, hoja = resolver_xlsx(libro, CONTRATO_KARDEX)
        except ErrorContrato as e:
            bloque.errores.append(str(e))
            return bloque
        _aviso_columnas(bloque, columnas)
        bloque.info.append(f"{hoja.max_row} filas")

        # colNomArticulo viene DOS veces (posiciones 12 y 13) con valores
        # distintos: por nombre solo se lee la primera, asi que hay que decirlo.
        repetidos = [
            a for a in columnas.avisos if "duplicado" in a and "COLNOM" in a.upper()
        ]
        if repetidos:
            bloque.avisos.append(
                "KARDEX trae colNomArticulo duplicado: se lee la primera "
                "ocurrencia; si el nombre bueno es el de la segunda, hay que "
                "renombrar la columna en el origen"
            )

        i_alm = columnas.idx("nom_almacen")
        almacenes = set()
        for fila in hoja.iter_rows(
            min_row=CONTRATO_KARDEX.fila_header + 1,
            max_row=min(hoja.max_row, 5000),
            values_only=True,
        ):
            nombre = limpiar_texto(fila[i_alm]) if i_alm < len(fila) else ""
            if nombre:
                almacenes.add(nombre.upper())
        bloque.info.append(
            f"almacenes en la muestra: {len(almacenes)} "
            "(el KARDEX usa mas que los 8 del reporte S1)"
        )
    finally:
        libro.close()
    return bloque


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def _imprimir(bloques: list[Bloque]) -> None:
    iconos = {"ok": "OK", "aviso": "AVISO", "error": "ERROR", "skip": "SKIP"}
    print("=" * 70)
    print("VALIDACION DE ENCABEZADOS")
    print("=" * 70)
    for b in bloques:
        print()
        etiqueta = f"[{iconos[b.estado]}] {b.fuente}"
        if not b.bloqueante:
            etiqueta += "  (informativo: no bloquea el catalogo)"
        print(etiqueta)
        if b.omitido:
            print(f"  {b.omitido}")
            continue
        for linea in b.info:
            print(f"  - {linea}")
        for aviso in b.avisos:
            print(f"  AVISO: {aviso}")
        for error in b.errores:
            for i, linea in enumerate(str(error).splitlines()):
                print(f"  ERROR: {linea}" if i == 0 else f"         {linea}")

    bloqueantes = [b for b in bloques if b.bloqueante and b.errores]
    informativos = [b for b in bloques if not b.bloqueante and b.errores]
    avisos = sum(len(b.avisos) for b in bloques)
    print()
    print("-" * 70)
    if bloqueantes:
        total = sum(len(b.errores) for b in bloqueantes)
        print(f"{total} ERROR(ES) de contrato: NO se puede generar el catalogo.")
        return
    if informativos:
        total = sum(len(b.errores) for b in informativos)
        print(
            f"OK: las fuentes del catalogo cumplen el contrato. "
            f"{total} problema(s) en fuentes informativas (no bloquean) "
            f"y {avisos} aviso(s)."
        )
        return
    print(f"OK: todas las fuentes cumplen el contrato ({avisos} aviso(s)).")


# ─────────────────────────────────────────────────────────────────────────────
# Revision de guia: SKUs manuales que no entran al catalogo
# ─────────────────────────────────────────────────────────────────────────────


def clasificar_guia(sku, ficha_erp, kardex, codigos_erp) -> tuple[str, str]:
    """Por que un SKU de la guia (SKU_BX/precios) no entra al catalogo.

    `ficha_erp` es None si el SKU no esta en el ERP, o
    {inactivo: bool, linea: str}. `kardex` es el set de colIdArticulo.
    Devuelve (motivo, detalle); motivo 'ok' = entra por guia.
    """
    from generar_catalogo_base import LINEAS_EXCLUIR

    if ficha_erp is not None:
        if ficha_erp.get("inactivo"):
            return (
                "inactivo",
                "inactivo en ERP: no entra al catalogo aunque este en guia; "
                "dar de baja en guia o reactivar en ERP",
            )
        if ficha_erp.get("linea", "") in LINEAS_EXCLUIR:
            return (
                "proceso",
                f"linea de proceso en ERP ({ficha_erp['linea']}): excluido "
                "aunque este en guia",
            )
        return ("ok", "")

    sugerencia = ""
    candidatos = difflib.get_close_matches(sku, codigos_erp, n=1, cutoff=0.8)
    if candidatos and candidatos[0] != sku:
        sugerencia = candidatos[0]
    if sku in kardex:
        detalle = (
            "existe en KARDEX pero no en ERP: revisar maestro "
            "(baja, codigo nuevo o reemplazo)"
        )
        if sugerencia:
            detalle += f"; similar a '{sugerencia}'"
        return ("kardex", detalle)
    if sugerencia:
        return (
            "tipeo",
            "no existe en ERP ni KARDEX; posible tipeo: "
            f"quisiste decir '{sugerencia}'?",
        )
    return (
        "inexistente",
        "no existe en ERP ni KARDEX: mal escrito o codigo inexistente "
        "(solo entraria si reporta stock: ficha S1)",
    )


def _fichas_erp(ruta: Path) -> dict[str, dict] | None:
    """{sku: {inactivo, linea}} con TODAS las filas del ERP. None si el
    contrato esta roto (el bloque ERP ya lo reporta: no duplicar el error)."""
    import xlrd

    try:
        libro = xlrd.open_workbook(str(ruta))
    except (OSError, ValueError):
        return None
    try:
        columnas, hoja = resolver_xls(libro, CONTRATO_ERP)
    except ErrorContrato:
        return None
    finally:
        libro.release_resources()
    fichas: dict[str, dict] = {}
    for r in range(1, hoja.nrows):
        fila = hoja.row_values(r)
        sku = sku_texto(columnas.valor(fila, "sku"))
        if not sku or sku in fichas:
            continue
        fichas[sku] = {
            "inactivo": limpiar_texto(columnas.valor(fila, "inactivo")).lower()
            == "checked",
            "linea": limpiar_texto(columnas.valor(fila, "linea")),
        }
    return fichas


def _skus_kardex(ruta: Path) -> tuple[set[str], str]:
    """Set de colIdArticulo del KARDEX + nota de origen.

    El archivo pesa 11 MB / 179k filas: se cachea el set en
    data/.cache_kardex_skus.json y solo se reconstruye si el archivo cambio
    (mismo nombre, tamano y fecha). Sin KARDEX devuelve set vacio.
    """
    import openpyxl

    try:
        st = ruta.stat()
    except OSError:
        return set(), "sin KARDEX"
    huella = {"archivo": ruta.name, "bytes": st.st_size, "modificado": st.st_mtime}
    cache = ruta.with_name(".cache_kardex_skus.json")
    try:
        with open(cache, encoding="utf-8") as f:
            guardado = json.load(f)
        if all(guardado.get(k) == v for k, v in huella.items()):
            return set(guardado.get("skus", [])), "indice cacheado"
    except (OSError, ValueError):
        pass

    print("  (construyendo indice KARDEX: una sola vez por archivo...)")
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        columnas, hoja = resolver_xlsx(libro, CONTRATO_KARDEX)
        i_art = columnas.idx("id_articulo")
        skus = {
            sku_texto(f[i_art])
            for f in hoja.iter_rows(min_row=2, values_only=True)
            if len(f) > i_art and sku_texto(f[i_art])
        }
    except ErrorContrato:
        return set(), "contrato roto (ver bloque KARDEX)"
    finally:
        libro.close()
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({**huella, "skus": sorted(skus)}, f)
    except OSError:
        pass
    return skus, f"indice reconstruido ({len(skus)} articulos)"


def _skus_guia(data: Path) -> dict[str, str]:
    """{sku: origen} de las guias manuales. Origen: 'SKU_BX', 'precios' o
    'SKU_BX+precios'. Las hojas con contrato roto se omiten (su bloque ya
    lo reporta)."""
    from contratos import (
        CONTRATO_PLANTILLA_DESCUENTOS,
        CONTRATO_PLANTILLA_PRECIOS_FIJOS,
    )

    import openpyxl

    guia: dict[str, str] = {}

    def _agregar(ruta, contrato, etiqueta):
        try:
            libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        except (OSError, ValueError):
            return
        try:
            columnas, hoja = resolver_xlsx(libro, contrato)
            for fila in hoja.iter_rows(
                min_row=contrato.fila_header + 1, values_only=True
            ):
                sku = sku_texto(columnas.valor(fila, "sku"))
                if not sku:
                    continue
                guia[sku] = f"{guia[sku]}+{etiqueta}" if sku in guia else etiqueta
        except ErrorContrato:
            return
        finally:
            libro.close()

    _agregar(data / "SKU_BX.xlsx", CONTRATO_SKU_BX, "SKU_BX")

    # Precios: hoja unica actual o layout legacy (2 hojas).
    ruta_pr = data / "plantilla_precios.xlsx"
    try:
        hojas = openpyxl.load_workbook(ruta_pr, read_only=True).sheetnames
    except (OSError, ValueError):
        hojas = []
    if "SKU_PRECIOS" in hojas:
        _agregar(ruta_pr, CONTRATO_PLANTILLA_PRECIOS, "precios")
    else:
        _agregar(ruta_pr, CONTRATO_PLANTILLA_DESCUENTOS, "precios")
        _agregar(ruta_pr, CONTRATO_PLANTILLA_PRECIOS_FIJOS, "precios")
    return guia


def validar_guia_vs_maestros(data: Path) -> Bloque:
    """Cruza la guia manual (SKU_BX + precios) contra ERP y KARDEX.

    Avisa por cada SKU que NO va a entrar al catalogo, con el motivo
    (inactivo / proceso / tipeo / en KARDEX pero no en ERP / inexistente)
    para revisarlo o eliminarlo. Informativo: no bloquea la publicacion
    (el generador ya omite estos SKUs por regla).
    """
    bloque = Bloque("Guia vs maestros (SKU_BX + precios)", str(data), bloqueante=False)
    ruta_erp = data / "PRODUCTOS.xls"
    if not ruta_erp.exists():
        bloque.omitido = "sin ERP: no se puede cruzar la guia"
        return bloque

    fichas = _fichas_erp(ruta_erp)
    if fichas is None:
        bloque.avisos.append(
            "ERP ilegible o con contrato roto: la revision de guia se omite "
            "(ver bloque ERP)"
        )
        return bloque
    bloque.info.append(f"ERP: {len(fichas)} SKUs en maestro")

    guia = _skus_guia(data)
    if not guia:
        bloque.info.append("guia vacia o ilegible: nada que revisar")
        return bloque

    kardex, nota_kardex = _skus_kardex(data / "KARDEX_BASE.xlsx")
    bloque.info.append(f"KARDEX: {len(kardex)} articulos ({nota_kardex})")

    ignorados = cargar_guia_ignorados()
    omitidos_ack = 0
    codigos = sorted(fichas)
    for sku in sorted(guia):
        if sku in ignorados:
            omitidos_ack += 1
            continue
        motivo, detalle = clasificar_guia(sku, fichas.get(sku), kardex, codigos)
        if motivo == "ok":
            continue
        bloque.avisos.append(f"{sku} ({guia[sku]}): {detalle}")
    if omitidos_ack:
        bloque.info.append(
            f"{omitidos_ack} SKU(s) ya revisados (config/guia_ignorados.json): "
            "no se avisan"
        )
    if not bloque.avisos:
        bloque.info.append(f"{len(guia)} SKUs de guia existen en ERP: nada que revisar")
    return bloque


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Valida los encabezados de las fuentes del catalogo"
    )
    ap.add_argument("--data-dir", default=str(RAIZ / "data"))
    ap.add_argument(
        "--s1-xls",
        default="",
        help="Reporte S1 .xls a validar (si no se pasa, se busca en data/)",
    )
    ap.add_argument(
        "--sin-kardex", action="store_true", help="No validar KARDEX_BASE.xlsx"
    )
    ap.add_argument("--json", action="store_true", help="Salida JSON")
    args = ap.parse_args()

    data = Path(args.data_dir)
    s1 = Path(args.s1_xls) if args.s1_xls else _buscar_s1(data)

    bloques = [
        validar_erp(data / "PRODUCTOS.xls"),
        validar_sku_precios(data / "SKU_PRECIOS.xlsx"),
        validar_sku_bx(data / "SKU_BX.xlsx"),
        validar_plantilla(data / "plantilla_precios.xlsx"),
    ]
    if s1 is None:
        bloque_s1 = Bloque("Reporte S1 (.xls)", "")
        bloque_s1.omitido = (
            "no hay reporte S1 en data/ (el universo de stock se lee del API); "
            "pasa --s1-xls para validar el .xls"
        )
        bloques.append(bloque_s1)
    else:
        bloques.append(validar_s1(s1))
    if not args.sin_kardex:
        bloques.append(validar_kardex(data / "KARDEX_BASE.xlsx"))
    bloques.append(validar_guia_vs_maestros(data))

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not any(b.errores for b in bloques if b.bloqueante),
                    "bloques": [b.como_dict() for b in bloques],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _imprimir(bloques)

    return 1 if any(b.errores for b in bloques if b.bloqueante) else 0


def _buscar_s1(data: Path) -> Path | None:
    patrones = ("REPT_STOCK*.xls", "REPORTE_STOCK*.xls", "*STOCK*.xls")
    for patron in patrones:
        encontrados = sorted(glob.glob(str(data / patron)))
        if encontrados:
            return Path(encontrados[-1])
    return None


if __name__ == "__main__":
    sys.exit(main())
