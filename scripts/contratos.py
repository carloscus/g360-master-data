#!/usr/bin/env python3
"""Contratos de encabezados: una sola convencion para todas las fuentes.

Por que existe
--------------
Cada lector usaba indices fijos (`cell_value(r, 11)`, `row[2]`). Si una fuente
agregaba o movia una columna, el catalogo se generaba IGUAL pero con el precio
en la familia y la linea en el peso: sin error, sin aviso. Ese es el peor bug
posible, porque el catalogo es el allowlist real del API.

Reglas
------
1. Se lee por NOMBRE, nunca por posicion.
2. Cada campo tiene nombre canonico + alias. Los alias existen para no obligar
   a renombrar archivos que ya se usan (CODIGO/SKU, DESC1/DESC_ADIC01).
3. Los encabezados se comparan normalizados: sin acentos, sin NBSP ni BOM,
   sin espacios de sobra, en mayusculas.
4. Si falta una columna requerida -> `ErrorContrato` (fatal): el proceso se
   detiene y no se escribe ningun catalogo.
5. Columnas de mas, duplicados y alias ambiguos -> AVISOS (no bloquean).
6. S1 no tiene encabezado real (celdas combinadas + preambulo): se ubica por
   ANCLAS, o sea la fila que contiene ARTICULO/ALMACEN/UM/STOCK/PREDESPACHO.

Este modulo no depende de pandas: sirve igual para xlrd (ERP/S1) y openpyxl
(SKU_BX/plantilla/KARDEX).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Normalizacion
# ─────────────────────────────────────────────────────────────────────────────


def normalizar_encabezado(valor) -> str:
    """Forma canonica de comparar un encabezado.

    'Artículo ', 'ARTICULO', 'art�culo' y 'ARTÍCULO' son el mismo encabezado.
    Tambien quita NBSP (\\xa0) y BOM (\\ufeff), que Excel mete y rompen el
    `strip()`.
    """
    if valor is None:
        return ""
    texto = str(valor).replace("\ufeff", "").replace("\xa0", " ")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.split()).strip().upper()


def limpiar_texto(valor) -> str:
    """Texto de una celda: sin espacios de borde ni NBSP/BOM. No cambia caja."""
    if valor is None:
        return ""
    return str(valor).replace("\ufeff", "").replace("\xa0", " ").strip()


def sku_texto(valor) -> str:
    """SKU como texto, sin perder la forma que trae la celda.

    Un SKU es TEXTO: '016763' y '16763' son articulos distintos (normalizar
    ceros fusiona articulos reales: medido sobre KARDEX vs ERP, 12.086 matches
    exactos bajan a 12.071 al normalizar). Si la celda viene numerica, se
    devuelve el entero sin decimales y quien llama debe avisar: los ceros a la
    izquierda ya se perdieron en el archivo, no aca.
    """
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return str(valor)
    return limpiar_texto(valor).lstrip("'")


def es_vacio(valor) -> bool:
    return limpiar_texto(valor) in ("", "-", "—", "N/A", "NA")


# ─────────────────────────────────────────────────────────────────────────────
# Error de contrato
# ─────────────────────────────────────────────────────────────────────────────


class ErrorContrato(Exception):
    """Una fuente no cumple el contrato de encabezados.

    Es fatal a proposito. El mensaje dice que fuente, que hoja, que columna
    falta (y que alias se aceptaban) y que encabezados se encontraron: no hay
    que abrir el archivo ni adivinar.
    """

    def __init__(
        self,
        contrato: Contrato,
        motivo: str,
        faltantes: list[tuple[str, tuple[str, ...]]] | None = None,
        encontrados: list[str] | None = None,
        detalle: str = "",
    ) -> None:
        self.contrato = contrato
        self.motivo = motivo
        self.faltantes = faltantes or []
        self.encontrados = encontrados or []
        self.detalle = detalle
        super().__init__(self.texto())

    def texto(self) -> str:
        lineas = [f"Contrato roto en {self.contrato.fuente}:"]
        ubicacion = []
        if self.contrato.hoja is not None:
            ubicacion.append(f"hoja {self.contrato.hoja!r}")
        if self.contrato.fila_header:
            ubicacion.append(f"fila de encabezado {self.contrato.fila_header}")
        if ubicacion:
            lineas.append("  " + "  |  ".join(ubicacion))
        lineas.append(f"  {self.motivo}")
        for campo, alias in self.faltantes:
            lineas.append(f"    - falta '{campo}' (se acepta: {', '.join(alias)})")
        if self.encontrados:
            visibles = [h for h in self.encontrados if h]
            lineas.append(f"  encabezados encontrados ({len(visibles)}): ")
            lineas.append("    " + " | ".join(visibles[:20]))
        if self.detalle:
            lineas.append(f"  {self.detalle}")
        lineas.append(
            "  No se genero nada. Revisa el export o actualiza el contrato en "
            "scripts/contratos.py."
        )
        return "\n".join(lineas)


# ─────────────────────────────────────────────────────────────────────────────
# Contrato y resolucion de columnas
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Contrato:
    """Que columnas necesita una fuente y con que nombres se aceptan.

    `requeridas` y `opcionales` son {campo_canonico: (alias en orden de
    prioridad)}. `fila_header` es 1-based (como lo ve el usuario en Excel).
    `hoja=None` significa "la hoja activa".
    """

    fuente: str
    requeridas: dict[str, tuple[str, ...]] = field(default_factory=dict)
    opcionales: dict[str, tuple[str, ...]] = field(default_factory=dict)
    hoja: str | int | None = None
    fila_header: int = 1

    def alias_de(self, campo: str) -> tuple[str, ...]:
        return self.requeridas.get(campo) or self.opcionales.get(campo) or ()

    @property
    def campos(self) -> dict[str, tuple[str, ...]]:
        return {**self.requeridas, **self.opcionales}


@dataclass
class Columnas:
    """Resultado de resolver un contrato contra una fila de encabezados."""

    contrato: Contrato
    encabezados: list[str]
    indices: dict[str, int]
    avisos: list[str]
    faltantes_opcionales: list[str]

    def idx(self, campo: str) -> int:
        try:
            return self.indices[campo]
        except KeyError as exc:
            raise KeyError(
                f"{self.contrato.fuente}: el campo '{campo}' no esta en el "
                f"contrato resuelto ({sorted(self.indices)})"
            ) from exc

    def tiene(self, campo: str) -> bool:
        return campo in self.indices

    def valor(self, fila, campo: str, default=None):
        """Valor crudo de `fila` para un campo (None si no aplica)."""
        if campo not in self.indices:
            return default
        i = self.indices[campo]
        if i >= len(fila):
            return default
        return fila[i]

    def texto(self, fila, campo: str, default: str = "") -> str:
        valor = self.valor(fila, campo)
        return limpiar_texto(valor) if valor is not None else default

    def resumen(self) -> str:
        return ", ".join(f"{c}->{i}" for c, i in sorted(self.indices.items()))


def resolver_columnas(encabezados, contrato: Contrato) -> Columnas:
    """Mapea campo canonico -> indice de columna. Falla si falta una requerida."""
    crudos = ["" if h is None else str(h) for h in encabezados]
    normalizados = [normalizar_encabezado(h) for h in crudos]

    posiciones: dict[str, list[int]] = {}
    for i, nombre in enumerate(normalizados):
        if nombre:
            posiciones.setdefault(nombre, []).append(i)

    avisos: list[str] = []
    for nombre, pos in sorted(posiciones.items()):
        if len(pos) > 1:
            avisos.append(
                f"encabezado duplicado '{nombre}' en columnas "
                f"{[p + 1 for p in pos]}; se usa la primera"
            )

    indices: dict[str, int] = {}
    faltantes: list[tuple[str, tuple[str, ...]]] = []

    for campo, alias in contrato.requeridas.items():
        encontrados = [
            (a, posiciones[normalizar_encabezado(a)][0])
            for a in alias
            if normalizar_encabezado(a) in posiciones
        ]
        if not encontrados:
            faltantes.append((campo, alias))
            continue
        indices[campo] = _elegir_alias(campo, encontrados, avisos)

    for campo, alias in contrato.opcionales.items():
        encontrados = [
            (a, posiciones[normalizar_encabezado(a)][0])
            for a in alias
            if normalizar_encabezado(a) in posiciones
        ]
        if encontrados:
            indices[campo] = _elegir_alias(campo, encontrados, avisos)

    if faltantes:
        raise ErrorContrato(
            contrato,
            f"faltan {len(faltantes)} columna(s) obligatoria(s)",
            faltantes=faltantes,
            encontrados=crudos,
        )

    # Dos campos no pueden apuntar a la misma columna: seria un contrato mal
    # escrito y volveria a leer lo mismo dos veces sin avisar.
    por_indice: dict[int, list[str]] = {}
    for campo, i in indices.items():
        por_indice.setdefault(i, []).append(campo)
    choques = {i: campos for i, campos in por_indice.items() if len(campos) > 1}
    if choques:
        detalle = "; ".join(
            f"columna {i + 1}: {sorted(campos)}"
            for i, campos in sorted(choques.items())
        )
        raise ErrorContrato(
            contrato,
            "dos campos apuntan a la misma columna",
            encontrados=crudos,
            detalle=detalle,
        )

    usadas = set(indices.values())
    for i, crudo in enumerate(crudos):
        if not normalizar_encabezado(crudo):
            continue
        if i not in usadas:
            avisos.append(
                f"columna {i + 1} ('{limpiar_texto(crudo)}') no se usa en este contrato"
            )

    faltantes_opcionales = [
        campo
        for campo, alias in contrato.opcionales.items()
        if not any(normalizar_encabezado(a) in posiciones for a in alias)
    ]

    return Columnas(
        contrato=contrato,
        encabezados=crudos,
        indices=indices,
        avisos=avisos,
        faltantes_opcionales=faltantes_opcionales,
    )


def _elegir_alias(campo, encontrados, avisos) -> int:
    indice = encontrados[0][1]
    distintos = {i for _, i in encontrados}
    if len(distintos) > 1:
        avisos.append(
            f"campo '{campo}' ambiguo: {', '.join(a for a, _ in encontrados)} en "
            f"columnas {sorted(i + 1 for i in distintos)}; se usa '{encontrados[0][0]}'"
        )
    return indice


# ─────────────────────────────────────────────────────────────────────────────
# Lectura de la fila de encabezados
# ─────────────────────────────────────────────────────────────────────────────


def encabezados_xls(hoja, fila_header: int = 1) -> list[str]:
    """Fila de encabezados de una hoja xlrd (fila_header 1-based)."""
    r = max(0, fila_header - 1)
    if r >= hoja.nrows:
        return []
    return [hoja.cell_value(r, c) for c in range(hoja.ncols)]


def encabezados_xlsx(hoja, fila_header: int = 1) -> list[str]:
    """Fila de encabezados de una hoja openpyxl (fila_header 1-based)."""
    fila = next(
        hoja.iter_rows(min_row=fila_header, max_row=fila_header, values_only=True), ()
    )
    return list(fila)


def hoja_de_xlsx(libro, contrato: Contrato):
    """Selecciona la hoja del contrato y falla con un mensaje util."""
    if contrato.hoja is None:
        return libro.active
    if isinstance(contrato.hoja, int):
        try:
            return libro.worksheets[contrato.hoja]
        except IndexError as exc:
            raise ErrorContrato(
                contrato,
                f"no existe la hoja en la posicion {contrato.hoja}",
                detalle=f"hojas disponibles: {libro.sheetnames}",
            ) from exc
    if contrato.hoja not in libro.sheetnames:
        if len(libro.sheetnames) == 1:
            return libro.worksheets[0]
        raise ErrorContrato(
            contrato,
            f"no existe la hoja {contrato.hoja!r}",
            detalle=f"hojas disponibles: {libro.sheetnames}",
        )
    return libro[contrato.hoja]


def hoja_de_xls(libro, contrato: Contrato):
    """Selecciona la hoja del contrato en un libro xlrd."""
    nombres = libro.sheet_names()
    if contrato.hoja is None:
        return libro.sheet_by_index(0)
    if isinstance(contrato.hoja, int):
        if contrato.hoja >= len(nombres):
            raise ErrorContrato(
                contrato,
                f"no existe la hoja en la posicion {contrato.hoja}",
                detalle=f"hojas disponibles: {nombres}",
            )
        return libro.sheet_by_index(contrato.hoja)
    if contrato.hoja not in nombres:
        # El export del ERP a veces cambia el nombre de la hoja. Si hay una
        # sola hoja, se acepta y se avisa por stderr: no vale la pena perder
        # una corrida por el nombre de una hoja que no cambia el contenido.
        if len(nombres) == 1:
            return libro.sheet_by_index(0)
        raise ErrorContrato(
            contrato,
            f"no existe la hoja {contrato.hoja!r}",
            detalle=f"hojas disponibles: {nombres}",
        )
    return libro.sheet_by_name(contrato.hoja)


def resolver_xlsx(libro, contrato: Contrato) -> tuple[Columnas, object]:
    hoja = hoja_de_xlsx(libro, contrato)
    columnas = resolver_columnas(encabezados_xlsx(hoja, contrato.fila_header), contrato)
    _avisar_hoja_unica(libro.sheetnames, contrato, columnas)
    return columnas, hoja


def resolver_xls(libro, contrato: Contrato) -> tuple[Columnas, object]:
    hoja = hoja_de_xls(libro, contrato)
    columnas = resolver_columnas(encabezados_xls(hoja, contrato.fila_header), contrato)
    _avisar_hoja_unica(libro.sheet_names(), contrato, columnas)
    return columnas, hoja


def _avisar_hoja_unica(nombres, contrato: Contrato, columnas: Columnas) -> None:
    """Si la hoja esperada no existe pero hay una sola, se acepto igual."""
    if (
        isinstance(contrato.hoja, str)
        and contrato.hoja not in nombres
        and len(nombres) == 1
    ):
        columnas.avisos.insert(
            0,
            f"la hoja se llama {nombres[0]!r} (se esperaba {contrato.hoja!r}); "
            "se acepta porque es la unica",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Contratos concretos
# ─────────────────────────────────────────────────────────────────────────────

# ERP: export fijo de 12 columnas. `CAN_KG_UM` es el PESO (no la unidad): el
# nombre del ERP miente, por eso el campo canonico es `peso_kg`.
CONTRATO_ERP = Contrato(
    fuente="ERP (PRODUCTOS.xls)",
    hoja="codigos productos",
    fila_header=1,
    requeridas={
        "sku": ("CODIGO", "SKU"),
        "nombre": ("NOMBRE", "DESCRIPCION"),
        "linea": ("LINEA",),
        "grupo": ("GRUPO",),
        "precio": ("PRECIO", "PRECIO_LISTA"),
        "inactivo": ("FLG_INACTIVO", "INACTIVO"),
        "descontinuado": ("FLG_DESCONTINUADO", "DESCONTINUADO"),
    },
    opcionales={
        "ean13": ("COD_EAN", "EAN13"),
        "ean14": ("COD_EAN_14", "EAN14"),
        "peso_kg": ("CAN_KG_UM", "PESO", "PESO_KG"),
        "tipo": ("TIPO",),
        "familia": ("FAMILIA",),
    },
)

# Guia comercial (manual). SKU/UN_BX/ORDEN ya existen; las dimensiones de caja
# son el bloque nuevo y son OPCIONALES: la plantilla vieja sigue funcionando.
CONTRATO_SKU_BX = Contrato(
    fuente="SKU_BX.xlsx",
    hoja="SKU_BX",
    requeridas={
        "orden": ("ORDEN", "N", "N°", "NRO"),
        "sku": ("SKU", "CODIGO"),
        "un_bx": ("UN_BX", "U_BX", "U/BOX", "UNIDADES_POR_CAJA"),
    },
    opcionales={
        "estado_linea": ("ESTADO_LINEA", "ESTADO"),
        "largo_cm": ("LARGO_CM", "LARGO"),
        "ancho_cm": ("ANCHO_CM", "ANCHO"),
        "alto_cm": ("ALTO_CM", "ALTO"),
        "peso_caja_kg": ("PESO_CAJA_KG", "PESO_CAJA"),
        "m3_caja": ("M3_CAJA",),
        "m3_unidad": ("M3_UNIDAD",),
    },
)

# Nueva estructura consolidada (v3.8): dos hojas en un solo archivo
# `data/SKU_PRECIOS.xlsx` — cada SKV vive una sola vez y se une por SKU.
#
# HOJA SKU_LOGISTICA: dimensiones, orden, unidades por caja. Nada de precios.
# HOJA SKU_PRECIOS: descuentos (hasta 6), precio fijo, vigencias y observacion.
CONTRATO_SKU_LOGISTICA = Contrato(
    fuente="SKU_PRECIOS.xlsx (hoja SKU_LOGISTICA)",
    hoja="SKU_LOGISTICA",
    requeridas={
        "orden": ("ORDEN", "N", "N°", "NRO"),
        "sku": ("SKU", "CODIGO"),
        "un_bx": ("UN_BX", "U_BX", "U/BOX", "UNIDADES_POR_CAJA"),
    },
    opcionales={
        "estado_linea": ("ESTADO_LINEA", "ESTADO"),
        "largo_cm": ("LARGO_CM", "LARGO"),
        "ancho_cm": ("ANCHO_CM", "ANCHO"),
        "alto_cm": ("ALTO_CM", "ALTO"),
        "peso_caja_kg": ("PESO_CAJA_KG", "PESO_CAJA"),
        "m3_caja": ("M3_CAJA",),
        "m3_unidad": ("M3_UNIDAD",),
    },
)

CONTRATO_SKU_PRECIOS = Contrato(
    fuente="SKU_PRECIOS.xlsx (hoja SKU_PRECIOS)",
    hoja="SKU_PRECIOS",
    requeridas={
        "sku": ("SKU", "CODIGO"),
        "desc1": ("DESC1", "DESC_ADIC01", "DESC_ADIC1"),
    },
    opcionales={
        "desc2": ("DESC2", "DESC_ADIC02", "DESC_ADIC2"),
        "desc3": ("DESC3", "DESC_ADIC03", "DESC_ADIC3"),
        "desc4": ("DESC4", "DESC_ADIC04", "DESC_ADIC4"),
        "desc5": ("DESC5", "DESC_ADIC05", "DESC_ADIC5"),
        "desc6": ("DESC6", "DESC_ADIC06", "DESC_ADIC6"),
        "vigencia_desc": ("VIGENCIA_DESC", "VIGENCIA_INI", "VIGENCIA_DESDE"),
        "vigencia_precio": ("VIGENCIA_PRECIO", "VIGENCIA_FIN", "VIGENCIA_HASTA"),
        "precio_fijo": ("PRECIO_FIJO", "PRECIO_FINAL", "PRECIO"),
        "observacion": ("OBSERVACION", "OBSERVACIONES", "MOTIVO"),
    },
)

# Plantilla de precios legacy (2 hojas separadas). Se mantiene para leer
# archivos viejos; el layout actual es UNA hoja SKU_PRECIOS (ver abajo).
CONTRATO_PLANTILLA_DESCUENTOS = Contrato(
    fuente="plantilla_precios.xlsx",
    hoja="DESCUENTOS",
    requeridas={
        "sku": ("SKU", "CODIGO"),
        "desc1": ("DESC1", "DESC_ADIC01", "DESC_ADIC1"),
    },
    opcionales={
        "desc2": ("DESC2", "DESC_ADIC02", "DESC_ADIC2"),
        "desc3": ("DESC3", "DESC_ADIC03", "DESC_ADIC3"),
        "desc4": ("DESC4", "DESC_ADIC04", "DESC_ADIC4"),
        "desc5": ("DESC5", "DESC_ADIC05", "DESC_ADIC5"),
        "desc6": ("DESC6", "DESC_ADIC06", "DESC_ADIC6"),
        "vigencia_ini": ("VIGENCIA_INI", "VIGENCIA_DESDE", "DESDE"),
        "vigencia_fin": ("VIGENCIA_FIN", "VIGENCIA_HASTA", "HASTA"),
    },
)

CONTRATO_PLANTILLA_PRECIOS_FIJOS = Contrato(
    fuente="plantilla_precios.xlsx",
    hoja="PRECIOS_FIJOS",
    requeridas={
        "sku": ("SKU", "CODIGO"),
        "precio_fijo": ("PRECIO_FIJO", "PRECIO_FINAL", "PRECIO"),
    },
    opcionales={
        "vigencia_ini": ("VIGENCIA_INI", "VIGENCIA_DESDE", "DESDE"),
        "vigencia_fin": ("VIGENCIA_FIN", "VIGENCIA_HASTA", "HASTA"),
        "observacion": ("OBSERVACION", "OBSERVACIONES", "MOTIVO"),
    },
)

CONTRATO_KARDEX = Contrato(
    fuente="KARDEX_BASE.xlsx",
    hoja=None,
    requeridas={
        "id_almacen": ("colIdAlmacen",),
        "nom_almacen": ("colNomAlmacen",),
        "id_articulo": ("colIdArticulo",),
        "nom_articulo": ("colNomArticulo",),
        "id_linea": ("colIdLinea",),
        "nom_linea": ("colNomLinea",),
        "id_um": ("colIdUM",),
    },
    opcionales={
        "id_grupo": ("colIdGrupo",),
        "nom_grupo": ("colNomGrupo",),
        "id_tipo": ("colIdTipo",),
        "nom_tipo": ("colNomTipo",),
        "id_familia": ("colIdFamilia",),
        "nom_familia": ("colNomFamilia",),
    },
)

# Plantilla de precios (v3.9): UNA hoja SKU_PRECIOS con descuentos + precio
# fijo en la misma fila (un SKU = una fila). Si hay PRECIO_FIJO reemplaza a
# los descuentos. La hoja SKU_CLIENTES quedo descontinuada: es una relacion
# 1-a-muchos (un SKU, muchos clientes) que no cabe en una planilla plana.
CONTRATO_PLANTILLA_SKU_CLIENTES = Contrato(
    fuente="plantilla_precios.xlsx",
    hoja="SKU_CLIENTES",
    requeridas={
        "sku": ("SKU", "CODIGO"),
        "sku_cliente": ("SKU_CLIENTE", "CODIGO_CLIENTE"),
    },
    opcionales={"cliente": ("CLIENTE", "RAZON_SOCIAL")},
)

CONTRATO_PLANTILLA_PRECIOS = Contrato(
    fuente="plantilla_precios.xlsx",
    hoja="SKU_PRECIOS",
    requeridas={
        "sku": ("SKU", "CODIGO"),
        "desc1": ("DESC1", "DESC_ADIC01", "DESC_ADIC1"),
    },
    opcionales={
        "desc2": ("DESC2", "DESC_ADIC02", "DESC_ADIC2"),
        "desc3": ("DESC3", "DESC_ADIC03", "DESC_ADIC3"),
        "desc4": ("DESC4", "DESC_ADIC04", "DESC_ADIC4"),
        "desc5": ("DESC5", "DESC_ADIC05", "DESC_ADIC5"),
        "desc6": ("DESC6", "DESC_ADIC06", "DESC_ADIC6"),
        "vigencia_desc": ("VIGENCIA_DESC", "VIGENCIA_INI", "VIGENCIA_DESDE"),
        "vigencia_precio": ("VIGENCIA_PRECIO", "VIGENCIA_FIN", "VIGENCIA_HASTA"),
        "precio_fijo": ("PRECIO_FIJO", "PRECIO_FINAL", "PRECIO"),
        "observacion": ("OBSERVACION", "OBSERVACIONES", "MOTIVO"),
    },
)

# Layout legacy (2 hojas separadas): se mantiene para leer archivos viejos.
# Migrar con: python scripts/crear_plantillas.py --migrar
CONTRATOS_PLANTILLA_LEGACY = {
    "DESCUENTOS": CONTRATO_PLANTILLA_DESCUENTOS,
    "PRECIOS_FIJOS": CONTRATO_PLANTILLA_PRECIOS_FIJOS,
}

# ─────────────────────────────────────────────────────────────────────────────
# S1: reporte sin encabezado real
# ─────────────────────────────────────────────────────────────────────────────

# El reporte S1 trae 9-12 filas de preambulo (titulo, filtros) y una fila de
# encabezados visual con celdas COMBINADAS: 'ARTICULO' queda en la columna de
# la descripcion y el SKU vive en la columna ANTERIOR. Por eso no se puede
# buscar por nombre y ya esta: hay que ubicar la fila y corregir el desfase.
ANCLAS_S1: dict[str, tuple[str, ...]] = {
    "descripcion": ("ARTICULO", "DESCRIPCION", "NOMBRE"),
    "almacen": ("ALMACEN",),
    "um": ("UM", "UNIDAD DE MEDIDA", "U.M."),
    "stock": ("STOCK",),
    "predespacho": ("PREDESPACHO", "COMPROMISO", "PEDIDO"),
    "disponible": ("DISPONIBLE",),
}

ANCLAS_S1_OBLIGATORIAS: tuple[str, ...] = (
    "descripcion",
    "almacen",
    "um",
    "stock",
    "predespacho",
)

FILAS_PREAMBULO_S1_MAX = 60

# Los 8 almacenes publicados. Cualquier otro en el reporte es un almacen
# interno (o un cambio de configuracion del reporte): se avisa.
#
# La lista VIVE en config/almacenes.json (versionado): es VARIABLE de
# configuracion, no codigo. Este tuple es solo el default de emergencia si
# la config no existe; la fuente de verdad es `cargar_almacenes()`.
ALMACENES_S1: tuple[str, ...] = ("121", "129", "VES", "118", "122", "40", "106", "92")

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG_ALMACENES = RAIZ / "config" / "almacenes.json"
RUTA_GUIA_IGNORADOS = RAIZ / "config" / "guia_ignorados.json"

_almacenes_cache: dict | None = None


def cargar_almacenes(ruta=None) -> dict:
    """Carga config/almacenes.json (la lista de almacenes como VARIABLE).

    Devuelve {"almacen_principal": str, "almacenes": {codigo: tipo},
    "fuente": "config"|"default"}. Si el archivo no existe o es invalido,
    cae al default historico (los 8 de hoy) con tipo "venta", y el validador
    avisa: la config es la via correcta para agregar o retirar almacenes.
    """
    global _almacenes_cache
    if _almacenes_cache is not None and ruta is None:
        return _almacenes_cache

    p = Path(ruta) if ruta else RUTA_CONFIG_ALMACENES
    resultado = {
        "almacen_principal": "VES",
        "almacenes": {a: "venta" for a in ALMACENES_S1},
        "fuente": "default",
        "avisos": [],
    }
    if not p.exists():
        resultado["avisos"].append(
            f"no existe {p.name}: se usan los {len(ALMACENES_S1)} almacenes "
            "historicos; crealo con la lista actualizada"
        )
    else:
        try:
            import json

            with open(p, encoding="utf-8-sig") as f:  # utf-8-sig: tolera BOM
                config = json.load(f)
            almacenes = config.get("almacenes") or {}
            if not almacenes:
                resultado["avisos"].append(
                    f"{p.name}: sin clave 'almacenes'; se usan los historicos"
                )
            else:
                resultado["almacenes"] = {
                    str(cod).strip().upper(): str(tipo).strip().lower()
                    for cod, tipo in almacenes.items()
                }
                principal = config.get("almacen_principal")
                resultado["almacen_principal"] = (
                    str(principal).strip().upper()
                    if principal
                    else next(
                        (c for c, t in resultado["almacenes"].items() if t == "venta"),
                        "",
                    )
                )
                resultado["fuente"] = "config"
        except (OSError, ValueError) as e:
            resultado["avisos"].append(
                f"{p.name} invalido ({e}): se usan los almacenes historicos"
            )

    if ruta is None:
        _almacenes_cache = resultado
    return resultado


def almacenes_publicados(ruta=None) -> tuple[str, ...]:
    """Codigos de almacenes publicados, ordenados (VENTA primero)."""
    config = cargar_almacenes(ruta)
    venta = sorted(c for c, t in config["almacenes"].items() if t == "venta")
    mktd = sorted(c for c, t in config["almacenes"].items() if t == "mktd")
    return tuple(venta + mktd)


def cargar_guia_ignorados(ruta=None) -> dict[str, str]:
    """SKUs de la guia ya revisados a mano: {SKU: motivo}.

    El paso 0 y el generador no vuelven a avisar por ellos: la proxima
    corrida ya no los muestra. Si el SKU se corrige o se elimina de la
    guia, la entrada sobra (se puede borrar).
    """
    p = Path(ruta) if ruta else RUTA_GUIA_IGNORADOS
    try:
        with open(p, encoding="utf-8-sig") as f:
            datos = json.load(f)
        ignorados = datos.get("ignorados") or {}
        return {str(k).strip().upper(): str(v) for k, v in ignorados.items()}
    except (OSError, ValueError):
        return {}


# Palabras que ocupan la columna del SKU y NO son SKU.
_PALABRAS_NO_SKU = ("TOTAL", "SUBTOTAL", "TOTAL GENERAL", "ARTICULO", "ARTÍCULO")

CONTRATO_S1 = Contrato(
    fuente="Reporte S1 (REPT_STOCK_*.xls)",
    hoja=None,
    fila_header=0,  # se detecta: no es fija
)


def parece_sku(valor) -> bool:
    """Forma de SKU (5-8 alfanumericos). Solo es una ayuda para ubicar la
    columna, no una validacion del dato."""
    texto = sku_texto(valor).upper()
    if not texto or texto in _PALABRAS_NO_SKU:
        return False
    return bool(re.fullmatch(r"[0-9A-Z]{5,8}", texto))


@dataclass
class ColumnasS1:
    fila_header: int  # 0-based
    fila_datos: int  # 0-based
    indices: dict[str, int]
    avisos: list[str]

    @property
    def idx_sku(self) -> int:
        return self.indices["sku"]

    def valor(self, fila, campo: str, default=None):
        i = self.indices.get(campo)
        if i is None or i >= len(fila):
            return default
        return fila[i]

    def resumen(self) -> str:
        return ", ".join(f"{c}->{i + 1}" for c, i in sorted(self.indices.items()))


def detectar_columnas_s1(
    filas: list[list], max_filas: int = FILAS_PREAMBULO_S1_MAX
) -> ColumnasS1:
    """Ubica la fila de encabezados del reporte S1 y las columnas por ancla.

    Devuelve indices 0-based y la fila de datos (header + 1). `sku` sale de
    `descripcion - 1` (celda combinada) y se verifica contra los datos; si no
    parece SKU, se busca la columna que si lo parezca.
    """
    avisos: list[str] = []
    fila_header = -1
    indices: dict[str, int] = {}

    limite = min(len(filas), max_filas)
    for r in range(limite):
        normalizados = [normalizar_encabezado(c) for c in filas[r]]
        candidatos: dict[str, int] = {}
        for campo, alias in ANCLAS_S1.items():
            for a in alias:
                buscado = normalizar_encabezado(a)
                if buscado in normalizados:
                    candidatos[campo] = normalizados.index(buscado)
                    break
        if all(c in candidatos for c in ANCLAS_S1_OBLIGATORIAS):
            fila_header = r
            indices = candidatos
            break

    if fila_header < 0:
        encontrados = [limpiar_texto(c) for c in (filas[0] if filas else [])]
        raise ErrorContrato(
            CONTRATO_S1,
            f"no encontre la fila de encabezado en las primeras {limite} filas",
            faltantes=[
                (c, ANCLAS_S1[c]) for c in ANCLAS_S1_OBLIGATORIAS if c not in indices
            ],
            encontrados=encontrados,
            detalle=(
                "El reporte S1 cambio de formato (preambulo mas largo o "
                "columnas renombradas). Revisa el .xls y actualiza ANCLAS_S1."
            ),
        )

    fila_datos = fila_header + 1
    idx_desc = indices["descripcion"]

    # SKU = columna anterior a la descripcion (por la celda combinada).
    idx_sku = idx_desc - 1 if idx_desc > 0 else -1
    muestra = filas[fila_datos : fila_datos + 10]
    if idx_sku < 0 or not any(
        parece_sku(fila[idx_sku]) for fila in muestra if len(fila) > idx_sku
    ):
        alternativo = _buscar_columna_sku(muestra, idx_desc)
        if alternativo is None:
            raise ErrorContrato(
                CONTRATO_S1,
                "no pude ubicar la columna SKU",
                detalle=(
                    f"El encabezado dice 'ARTICULO' en la columna {idx_desc + 1} "
                    "y ni esa columna ni la anterior contienen SKUs en las "
                    "primeras filas de datos."
                ),
            )
        idx_sku = alternativo
        avisos.append(
            f"la columna SKU no es 'descripcion - 1'; se detecto en la columna "
            f"{idx_sku + 1} por el contenido"
        )

    indices["sku"] = idx_sku

    # El reporte se lee con 19 columnas: si aparece un corte raro conviene
    # saberlo antes de interpretar los datos.
    ancho = len(filas[fila_header]) if fila_header < len(filas) else 0
    if ancho and idx_sku >= ancho:
        avisos.append(
            f"la columna SKU ({idx_sku + 1}) queda fuera del ancho del "
            f"encabezado ({ancho})"
        )

    return ColumnasS1(
        fila_header=fila_header,
        fila_datos=fila_datos,
        indices=indices,
        avisos=avisos,
    )


def _buscar_columna_sku(filas_datos: list[list], idx_desc: int) -> int | None:
    """Busca la columna con mas celdas con forma de SKU, cerca de la descripcion."""
    ancho = max((len(f) for f in filas_datos), default=0)
    mejor: tuple[int, int] | None = None  # (aciertos, -distancia)
    elegido: int | None = None
    for col in range(ancho):
        if col == idx_desc:
            continue
        aciertos = sum(
            1 for fila in filas_datos if col < len(fila) and parece_sku(fila[col])
        )
        if not aciertos:
            continue
        distancia = abs(col - (idx_desc - 1))
        candidato = (aciertos, -distancia)
        if mejor is None or candidato > mejor:
            mejor = candidato
            elegido = col
    return elegido


def almacenes_fuera_de_lista(almacenes, permitidos=None) -> list[str]:
    """Almacenes del reporte que no estan en la lista publicada.

    `permitidos` es opcional: si no se pasa, se usan los de la config
    (config/almacenes.json) o el default historico.
    """
    if permitidos is None:
        permitidos = set(cargar_almacenes()["almacenes"])
    return sorted(
        {
            limpiar_texto(a).upper()
            for a in almacenes
            if limpiar_texto(a)
            and normalizar_encabezado(a)
            not in {normalizar_encabezado(p) for p in permitidos}
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Huella de las fuentes (trazabilidad del catalogo)
# ─────────────────────────────────────────────────────────────────────────────


def huella_fuente(ruta) -> dict:
    """Nombre, tamano, sha256 corto y fecha de la fuente que se leyo."""
    p = Path(ruta)
    if not p.exists():
        return {"archivo": p.name, "error": "no existe"}
    datos = p.read_bytes()
    return {
        "archivo": p.name,
        "bytes": len(datos),
        "sha256": hashlib.sha256(datos).hexdigest()[:16],
        "modificado": datetime.fromtimestamp(p.stat().st_mtime).isoformat(
            timespec="seconds"
        ),
    }


def calcular_m3(largo_cm, ancho_cm, alto_cm) -> float | None:
    """Volumen de la caja en m3 (largo*ancho*alto/1e6). None si falta un lado."""
    lados = []
    for valor in (largo_cm, ancho_cm, alto_cm):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return None
        if numero <= 0:
            return None
        lados.append(numero)
    return round(lados[0] * lados[1] * lados[2] / 1_000_000, 6)


# ─────────────────────────────────────────────────────────────────────────────
# KARDEX completo: una sola lectura compartida
# ─────────────────────────────────────────────────────────────────────────────
#
# El KARDEX es padrón artículo × almacén (179k filas): leerlo entero tarda.
# Se lee UNA vez por archivo y se cachea en data/.cache_kardex.json; todos
# los consumidores (UM del catálogo, revisión de guía, auditoría vs ERP)
# derivan de esa única lectura. Así ningún campo "se deja de leer".

CACHE_KARDEX_NOMBRE = ".cache_kardex.json"
CACHE_KARDEX_VERSION = 5


def derecha2(valor) -> str:
    """IDs de jerarquia a 2 caracteres por la derecha: ('00' + v)[-2:].

    '1' -> '01', '101' -> '01', 'ad' -> 'AD', 40 -> '40', '01' -> '01'.
    Solo para columnas con contrato de 2 (linea/grupo/tipo/familia):
    nunca para SKUs, EAN ni nombres. Vacio -> vacio (no inventa '00').
    """
    if valor is None or isinstance(valor, bool):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    t = limpiar_texto(valor)
    if not t:
        return ""
    return ("00" + t)[-2:].upper()


def prefijo_uno_sistematico(valores) -> bool:
    """True si TODOS los valores no vacios empiezan con '1'.

    Solo para colIdArticulo: un archivo donde todos los SKUs traen el '1'
    inicial trae un prefijo sistematico (se quita uno solo). Si hay mezcla
    (1, 3, 2, ...) son codigos reales: se lee sin modificar.
    """
    vistos = [v for v in valores if v]
    return bool(vistos) and all(v.startswith("1") for v in vistos)


def canon_sku(codigo) -> str:
    """Clave canonica para calzar SKUs entre fuentes: mayusculas sin prefijo
    numerico ('01CA001' -> 'CA001').

    El prefijo solo se quita si lo que queda tiene alguna letra: un SKU
    puramente numerico ('016763') NUNCA se reduce ('16763' seria otro
    articulo: los ceros a la izquierda son parte del codigo).
    """
    texto = str(codigo or "").strip().upper()
    base = re.sub(r"^[0-9]+", "", texto)
    if base and re.search(r"[A-Z]", base):
        return base
    return texto if re.search(r"[A-Z]", texto) else ""


def reducir_uno_numerico(codigo) -> str:
    """Quita UN '1' inicial solo a SKU puramente numerico de 6-7 digitos.

    '1014458' -> '014458', '111019' -> '11019'. Len 5 ('11028', el codigo
    real de 5) y alfanumericos: intactos ('' = no aplica). La existencia
    en el maestro la verifica quien llama (emparejar_skus): sin calce
    exacto del reducido no se toca nada.
    """
    t = str(codigo or "").strip()
    if t.isdigit() and len(t) in (6, 7) and t.startswith("1"):
        return t[1:]
    return ""


def emparejar_skus(buscados, candidatos) -> tuple[dict[str, str], dict]:
    """Calza SKUs entre dos fuentes por codigo EXACTO primero, sin prefijo
    despues (letras o '1' numerico). Devuelve ({buscado: candidato}, stats).

    El prefijo se acepta en CUALQUIER lado: KARDEX '01CA001' vs JSON 'CA001'
    y KARDEX '1014458' vs ERP '014458' calzan igual que al reves. La forma
    reducida solo vale si existe TAL CUAL en la otra fuente; si ambas
    formas existen el exacto ya gano antes (nunca se fusiona). Len 5
    ('11028') y alfanumericos sin letras de sobra: intactos.

    stats: exactos / prefijo / ambiguos (2+ candidatos distintos) /
    sin_match. Lo ambiguo y lo no encontrado NO se adivinan: se reportan.
    """
    candidatos = list(dict.fromkeys(candidatos))
    exactos = set(candidatos)
    por_base: dict[str, list[str]] = {}
    por_num: dict[str, list[str]] = {}
    for c in candidatos:
        b = canon_sku(c)
        if b and b != c.upper():
            por_base.setdefault(b, []).append(c)
        nb = reducir_uno_numerico(c)
        if nb:
            por_num.setdefault(nb, []).append(c)

    match: dict[str, str] = {}
    stats = {"exactos": 0, "prefijo": 0, "ambiguos": 0, "sin_match": 0}
    for s in dict.fromkeys(buscados):
        if s in exactos:
            match[s] = s
            stats["exactos"] += 1
            continue
        b = canon_sku(s)
        if b and b in exactos:
            # El buscado trae el prefijo ('01CA001' vs 'CA001').
            match[s] = b
            stats["prefijo"] += 1
            continue
        nb = reducir_uno_numerico(s)
        if nb and nb in exactos:
            # Prefijo '1' sistematico verificado: el reducido existe tal cual.
            match[s] = nb
            stats["prefijo"] += 1
            continue
        cands = (
            [c for c in por_base.get(b, []) if c.upper() != str(s).upper()] if b else []
        )
        cands += [c for c in por_num.get(str(s), []) if c != s]
        if len(cands) == 1:
            match[s] = cands[0]
            stats["prefijo"] += 1
        elif len(cands) > 1:
            stats["ambiguos"] += 1
        else:
            stats["sin_match"] += 1
    return match, stats


def indice_jerarquia_por_nombre(fichas) -> dict[tuple, list[dict]]:
    """Índice (grupo, tipo, familia) normalizados -> registros de jerarquía.

    Permite resolver los IDs de un producto que solo trae NOMBRES (SKU nuevo
    de S1 o D-sin-ficha) contra el maestro KARDEX. Cada registro guarda la
    linea completa (id y nombre) para que quien consulta verifique la
    pertenencia: la combinacion de nombres sola no basta.

    - Normaliza con normalizar_encabezado (sin acentos, mayusculas): la misma
      taxonomia escrita 'S/IMPRESION' o 'S/IMPRESIÓN' cae en la misma clave.
    - Solo entra si los 3 IDs estan completos.
    - Dos combinaciones con IDs distintos NO se fusionan: el llamador decide
      (si tras filtrar por linea queda mas de un candidato, no se adivina).
    """
    indice: dict[tuple, list[dict]] = {}
    for f in fichas.values():
        ids = {
            "linea_id": f.get("linea_id", ""),
            "grupo_id": f.get("grupo_id", ""),
            "tipo_id": f.get("tipo_id", ""),
            "familia_id": f.get("familia_id", ""),
        }
        if not (ids["grupo_id"] and ids["tipo_id"] and ids["familia_id"]):
            continue
        clave = tuple(
            normalizar_encabezado(f.get(k, "")) for k in ("grupo", "tipo", "familia")
        )
        reg = {
            **ids,
            "linea": normalizar_encabezado(f.get("linea", "")),
        }
        registros = indice.setdefault(clave, [])
        if not any(r == reg for r in registros):
            registros.append(reg)
    return indice


def resolver_jerarquia_por_nombre(p, indice) -> dict:
    """IDs jerarquicos para un producto que solo trae nombres.

    `p` es el producto del catalogo (linea_codigo, linea_nombre, grupo, tipo,
    familia). Filtra los candidatos del indice por LINEA (nombre o codigo:
    cualquiera de los dos prueba la pertenencia) y devuelve los IDs solo si
    queda EXACTAMENTE un candidato. Cero o mas de uno -> {} (nunca se
    adivina; el llamador lo reporta como sin IDs).
    """
    clave = tuple(
        normalizar_encabezado(p.get(k, "")) for k in ("grupo", "tipo", "familia")
    )
    cands = indice.get(clave, [])
    lin_cod = normalizar_encabezado(p.get("linea_codigo", ""))
    lin_nom = normalizar_encabezado(p.get("linea_nombre", ""))
    validos = [
        c
        for c in cands
        if (lin_cod and c["linea_id"] == lin_cod) or (lin_nom and c["linea"] == lin_nom)
    ]
    if len(validos) == 1:
        return {k: validos[0][k] for k in ("grupo_id", "tipo_id", "familia_id")}
    return {}


def _cache_kardex(cache, huella) -> tuple | None:
    """Cache del indice KARDEX: devuelve (articulos, ajustes, almacenes)
    si el archivo no cambio; None si hay que reconstruirlo (archivo nuevo,
    version de cache distinta o cache ilegible)."""
    try:
        with open(cache, encoding="utf-8") as f:
            guardado = json.load(f)
    except (OSError, ValueError):
        return None
    if guardado.get("v") != CACHE_KARDEX_VERSION:
        return None
    if not all(guardado.get("huella", {}).get(k) == v for k, v in huella.items()):
        return None
    return (
        guardado.get("articulos", {}),
        guardado.get("ajustes", {}),
        guardado.get("almacenes", {}),
    )


def _construir_indice_kardex(hoja, columnas) -> dict:
    """Recorre las filas del KARDEX y arma el indice de articulos.

    Reglas por columna (nada se corrige en silencio, todo queda en ajustes):
      - jerarquia: IDs a 2 chars por la derecha (derecha2) con conteo.
      - almacenes: id como texto ('40', 'VES') -> nombre; conflicto = primero.
      - SKU: texto, sin tocar. Si TODOS empiezan con '1' queda senalado
        (prefijo sistematico, se quita uno solo en _ajustes_finales).
    Devuelve un dict con articulos, stats, almacenes y banderas del loop.
    """
    idx = {c: columnas.idx(c) for c in columnas.indices}
    i_sku, i_um = idx["id_articulo"], idx["id_um"]
    # La 2da ocurrencia de colNomArticulo es la descripcion larga
    # (la 1ra es el nombre corto y es la que mapea el contrato).
    # Se acepta solo si el encabezado vecino es el mismo nombre:
    # nunca por posicion a ciegas.
    nombres_norm = [normalizar_encabezado(h) for h in columnas.encabezados]
    i_nom = idx["nom_articulo"]
    i_largo = None
    if i_nom + 1 < len(nombres_norm) and nombres_norm[i_nom + 1] == nombres_norm[i_nom]:
        i_largo = i_nom + 1

    def _txt(fila, campo, default=""):
        v = columnas.valor(fila, campo) if campo in idx else default
        return limpiar_texto(v)

    def _id(fila, campo, stats):
        # IDs de jerarquia: siempre ('00'+v)[-2:] en mayusculas.
        # '1'->'01', '101'->'01', 'ad'->'AD'. Lo que ya viene bien ('01')
        # pasa igual; lo distinto queda contado en stats (visible en meta).
        v = columnas.valor(fila, campo) if campo in idx else ""
        crudo = limpiar_texto(v)
        norm = derecha2(v)
        if crudo and crudo != norm:
            stats["n"] += 1
            if len(stats["ej"]) < 5 and crudo not in stats["vistos"]:
                stats["vistos"].add(crudo)
                stats["ej"].append(f"{crudo}->{norm}")
        return norm

    articulos: dict[str, dict] = {}
    stats_jer = {"n": 0, "ej": [], "vistos": set()}
    # Almacenes del archivo: id como texto ('40', 'VES') -> nombre visible.
    almacenes: dict[str, str] = {}
    almacenes_conflictos: set[str] = set()
    todos_uno = True
    hay_skus = False
    for fila in hoja.iter_rows(min_row=2, values_only=True):
        if len(fila) <= max(i_sku, i_um):
            continue
        aid = (
            sku_texto(columnas.valor(fila, "id_almacen")) if "id_almacen" in idx else ""
        )
        if aid:
            nom_alm = _txt(fila, "nom_almacen")
            if not almacenes.get(aid):
                almacenes[aid] = nom_alm
            elif nom_alm and nom_alm != almacenes[aid]:
                almacenes_conflictos.add(aid)
        sku = sku_texto(fila[i_sku])
        um = limpiar_texto(fila[i_um]).upper() if len(fila) > i_um else ""
        if not sku:
            continue
        # Regla SKU: todos empiezan con '1' => prefijo sistematico
        # (se quita uno solo al final). Mezcla => codigos reales, intactos.
        hay_skus = True
        if not sku.startswith("1"):
            todos_uno = False
        ficha = articulos.get(sku)
        largo = (
            limpiar_texto(fila[i_largo])
            if i_largo is not None and len(fila) > i_largo
            else ""
        )
        if ficha is None:
            articulos[sku] = {
                "um": um,
                "linea_id": _id(fila, "id_linea", stats_jer),
                "linea": _txt(fila, "nom_linea"),
                "grupo_id": _id(fila, "id_grupo", stats_jer),
                "grupo": _txt(fila, "nom_grupo"),
                "tipo_id": _id(fila, "id_tipo", stats_jer),
                "tipo": _txt(fila, "nom_tipo"),
                "familia_id": _id(fila, "id_familia", stats_jer),
                "familia": _txt(fila, "nom_familia"),
                "nombre_corto": _txt(fila, "nom_articulo"),
                "nombre_largo": largo,
                "n_almacenes": 1,
                "conflictos": {},
            }
            continue
        ficha["n_almacenes"] += 1
        for campo, valor in (
            ("um", um),
            ("linea", _txt(fila, "nom_linea")),
            ("grupo", _txt(fila, "nom_grupo")),
            ("tipo", _txt(fila, "nom_tipo")),
            ("familia", _txt(fila, "nom_familia")),
        ):
            if valor and valor != ficha[campo]:
                ficha["conflictos"].setdefault(campo, sorted({ficha[campo], valor}))
    return {
        "articulos": articulos,
        "stats_jer": stats_jer,
        "almacenes": almacenes,
        "almacenes_conflictos": almacenes_conflictos,
        "todos_uno": todos_uno,
        "hay_skus": hay_skus,
    }


def _ajustes_finales(indice) -> tuple[dict, dict]:
    """Ajustes aplicados en la construccion (todo visible en meta): jerarquia
    normalizada, conflictos de almacen y el prefijo '1' sistematico. Devuelve
    (articulos_finales, ajustes); con mezcla de prefijos no se toca nada."""
    ajustes: dict = {}
    stats_jer = indice["stats_jer"]
    if stats_jer["n"]:
        ajustes["jerarquia_normalizada"] = stats_jer["n"]
        ajustes["jerarquia_ejemplos"] = stats_jer["ej"]
    if indice["almacenes_conflictos"]:
        # Mismo id de almacen con nombres distintos: el primero gana y se
        # reporta (nada se cambia en silencio).
        ajustes["almacenes_conflictos"] = sorted(indice["almacenes_conflictos"])
    articulos = indice["articulos"]
    if indice["hay_skus"] and indice["todos_uno"]:
        articulos = {s[1:]: f for s, f in articulos.items()}
        ajustes["sku_prefijo_uno"] = True
    return articulos, ajustes


def _guardar_cache_kardex(cache, huella, articulos, ajustes, almacenes) -> None:
    """Escribe el cache en disco (si falla el disco, se reconstruye la
    proxima vez: el cache es un acelerador, nunca la fuente de verdad)."""
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "v": CACHE_KARDEX_VERSION,
                    "huella": huella,
                    "articulos": articulos,
                    "ajustes": ajustes,
                    "almacenes": almacenes,
                },
                f,
            )
    except OSError:
        pass


def leer_kardex(ruta) -> tuple[dict, dict]:
    """Lee KARDEX_BASE.xlsx completo, una sola vez por archivo (cache en
    disco). Devuelve (articulos, meta) donde articulos es
    {colIdArticulo: ficha} con ficha = {um, linea_id, linea, grupo_id,
    grupo, tipo_id, tipo, familia_id, familia, nombre_corto, nombre_largo,
    n_almacenes, conflictos}.

    `conflictos` junta los valores distintos vistos para el mismo SKU en
    distintas filas/almacenes (UM, linea, grupo...): el KARDEX tambien
    trae defectos y aca quedan a la vista en vez de perderse en silencio.
    """
    import openpyxl

    p = Path(ruta)
    meta = {"archivo": p.name, "articulos": 0, "nota": "sin KARDEX"}
    try:
        st = p.stat()
    except OSError:
        return {}, meta
    huella = {"archivo": p.name, "bytes": st.st_size, "modificado": st.st_mtime}
    cache = p.with_name(CACHE_KARDEX_NOMBRE)
    cacheado = _cache_kardex(cache, huella)
    if cacheado is not None:
        articulos, ajustes, almacenes = cacheado
        meta = {
            "archivo": p.name,
            "articulos": len(articulos),
            "nota": "indice cacheado",
        }
        meta.update(ajustes)
        meta["almacenes"] = almacenes
        return articulos, meta

    print("  (leyendo KARDEX completo: una sola vez por archivo...)")
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        columnas, hoja = resolver_xlsx(libro, CONTRATO_KARDEX)
        construido = _construir_indice_kardex(hoja, columnas)
    except ErrorContrato:
        return {}, {"archivo": p.name, "articulos": 0, "nota": "contrato roto"}
    finally:
        libro.close()
    articulos, ajustes = _ajustes_finales(construido)
    almacenes = construido["almacenes"]
    _guardar_cache_kardex(cache, huella, articulos, ajustes, almacenes)
    meta = {
        "archivo": p.name,
        "articulos": len(articulos),
        "nota": "indice reconstruido",
    }
    meta.update(ajustes)
    meta["almacenes"] = almacenes
    return articulos, meta
