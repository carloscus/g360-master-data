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

Uso:
    python scripts/validar_encabezados.py
    python scripts/validar_encabezados.py --data-dir data --s1-xls ruta.xls
    python scripts/validar_encabezados.py --json

Salida: 0 si no hay errores (puede haber avisos), 1 si hay errores.
"""

from __future__ import annotations

import argparse
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
