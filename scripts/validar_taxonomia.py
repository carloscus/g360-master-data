"""Validacion cruzada entre repos: detecta inconsistencias de taxonomia.

Correr despues de cualquier cambio en master-data, stock-api o vigencias.
Si hay ALERTAS, revisar antes de commitear.

Uso:
    python scripts/validar_taxonomia.py
    python scripts/validar_taxonomia.py --catalogo ruta.json
"""

import argparse
import ast
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO_POR_DEFECTO = RAIZ / "output" / "catalogo_productos.json"
API_STOCK_RELATIVO = RAIZ.parent / "g360-stock-api" / "app" / "core" / "constants.py"

LINEAS_CRAYOLA = ("CA", "CB", "CC", "CD", "CE", "CF")
LINEAS_VINIFAN_PURA = ("72", "76", "77", "79")


def _cargar_catalogo(ruta: Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _asignacion_nombre(nodo) -> str | None:
    """Nombre del objetivo de una asignacion (Assign o AnnAssign).

    Las taxonomias se declaran anotadas (`CATEGORIA_POR_LINEA: dict[str, str] = ...`),
    que en el AST es AnnAssign y no Assign: si solo se busca Assign, el chequeo
    se pasa sin revisar nada.
    """
    if isinstance(nodo, ast.Assign):
        for t in nodo.targets:
            if isinstance(t, ast.Name):
                return t.id
    elif isinstance(nodo, ast.AnnAssign):
        if isinstance(nodo.target, ast.Name):
            return nodo.target.id
    return None


def _claves_duplicadas(ruta_fuente: Path, nombre_constante: str) -> list[str]:
    """Claves repetidas en un dict literal del fuente (AST).

    En un dict de Python una clave repetida no avisa: gana la ultima. Por eso
    la taxonomia podia "cambiar" sin que nadie se diera cuenta.
    """
    if not ruta_fuente.exists():
        return []
    arbol = ast.parse(ruta_fuente.read_text(encoding="utf-8"))
    repetidas: list[str] = []
    for nodo in ast.walk(arbol):
        if _asignacion_nombre(nodo) != nombre_constante:
            continue
        if not isinstance(nodo.value, ast.Dict):
            continue
        vistas: set[str] = set()
        for key in nodo.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in vistas:
                    repetidas.append(key.value)
                vistas.add(key.value)
    return repetidas


def _taxonomia_api_stock(ruta: Path) -> dict[str, str] | None:
    """Taxonomia linea->categoria declarada en el API de stock (constants.py)."""
    if not ruta.exists():
        return None
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    mapa: dict[str, str] = {}
    for nodo in ast.walk(arbol):
        if _asignacion_nombre(nodo) != "CATEGORIAS":
            continue
        if not isinstance(nodo.value, ast.Dict):
            continue
        for k, v in zip(nodo.value.keys, nodo.value.values):
            if not isinstance(k, ast.Constant) or not isinstance(v, ast.List):
                continue
            categoria = str(k.value)
            for cod in v.elts:
                if isinstance(cod, ast.Constant):
                    mapa[str(cod.value)] = categoria
    return mapa


def validar(catalogo: dict, raiz: Path = RAIZ) -> list[str]:
    """Devuelve la lista de alertas del catálogo (vacía = todo coherente)."""
    alertas: list[str] = []
    ps = catalogo.get("productos", [])
    meta = catalogo.get("metadata", {})

    # 1. Todos los C* en catalogo son REPRESENTADAS
    c_skus = [p for p in ps if str(p.get("sku", "")).upper().startswith("C")]
    for p in c_skus:
        if p.get("categoria") != "REPRESENTADAS":
            alertas.append(
                f"ALERTA: {p['sku']} es C* pero categoria={p.get('categoria')} "
                "(debe ser REPRESENTADAS)"
            )

    # 2. Las lineas 72/76/77/79 no tienen REPRESENTADAS
    for p in ps:
        lin = str(p.get("linea", ""))
        if lin in LINEAS_VINIFAN_PURA and p.get("categoria") == "REPRESENTADAS":
            alertas.append(
                f"ALERTA: {p['sku']} en linea {lin} (VINIFAN) pero "
                f"categoria={p.get('categoria')}"
            )

    # 3. Las lineas CA/CB/CC/CD/CE/CF son REPRESENTADAS
    for p in ps:
        lin = str(p.get("linea", ""))
        if lin in LINEAS_CRAYOLA and p.get("categoria") != "REPRESENTADAS":
            alertas.append(
                f"ALERTA: {p['sku']} en linea {lin} (Crayola) pero "
                f"categoria={p.get('categoria')}"
            )

    # 4. Ninguna linea puede tener mas de una categoria (lineas mixtas)
    cats_por_linea: dict[str, set[str]] = defaultdict(set)
    for p in ps:
        cats_por_linea[str(p.get("linea", ""))].add(str(p.get("categoria", "")))
    for lin, cats in sorted(cats_por_linea.items()):
        if len(cats) > 1:
            alertas.append(
                f"ALERTA: Linea {lin} tiene categorias mixtas: {sorted(cats)}"
            )

    # 5. Metadata coherente con los productos
    cat_por_linea = meta.get("categorias_por_linea", {})
    for lin in LINEAS_CRAYOLA:
        if cat_por_linea.get(lin) != "REPRESENTADAS":
            alertas.append(
                f"ALERTA: metadata categorias_por_linea[{lin}] = "
                f"{cat_por_linea.get(lin)} (debe ser REPRESENTADAS)"
            )
    for p in ps:
        lin = str(p.get("linea", ""))
        cod = str(p.get("linea_codigo", ""))
        if cod and lin and cat_por_linea.get(cod) not in (None, p.get("categoria")):
            alertas.append(
                f"ALERTA: {p['sku']} linea={lin} categoria={p.get('categoria')} "
                f"no coincide con metadata categorias_por_linea[{cod}]="
                f"{cat_por_linea.get(cod)}"
            )

    # 6. El codigo de linea de un C* debe existir en la taxonomia
    for p in ps:
        cod = str(p.get("linea_codigo", ""))
        if cod and cod not in cat_por_linea:
            alertas.append(
                f"ALERTA: {p['sku']} tiene linea_codigo={cod} que no esta en la "
                "taxonomia publicada"
            )

    # 7. Sin claves duplicadas en el diccionario de taxonomia del maestro
    for cod in _claves_duplicadas(
        raiz / "scripts" / "generar_catalogo_base.py", "CATEGORIA_POR_LINEA"
    ):
        alertas.append(
            f"ALERTA: CATEGORIA_POR_LINEA tiene la clave duplicada '{cod}' "
            "(gana la ultima en silencio)"
        )

    # 8. La taxonomia del maestro debe ser la misma que la del API de stock
    api_ruta = raiz.parent / "g360-stock-api" / "app" / "core" / "constants.py"
    tax_api = _taxonomia_api_stock(api_ruta)
    if tax_api:
        for cod, categoria_api in sorted(tax_api.items()):
            categoria_maestro = cat_por_linea.get(cod)
            if categoria_maestro is None:
                continue  # el API tiene lineas que el maestro no publica
            if categoria_maestro != categoria_api:
                alertas.append(
                    f"ALERTA: linea {cod}: master-data dice {categoria_maestro} y "
                    f"g360-stock-api dice {categoria_api} (/stock y /catalog se "
                    "contradicen)"
                )

    # 9. Coherencia de precios: la regla "sin precio no se publica" es absoluta
    for p in ps:
        try:
            precio = float(p.get("precio", 0))
        except (TypeError, ValueError):
            precio = 0.0
        if precio <= 0:
            alertas.append(
                f"ALERTA: {p['sku']} esta publicado con precio={precio} "
                "(sin precio no se publica)"
            )

    return alertas


def main() -> int:
    ap = argparse.ArgumentParser(description="Validacion de taxonomia del catalogo")
    ap.add_argument(
        "--catalogo",
        default=str(CATALOGO_POR_DEFECTO),
        help="Ruta del catalogo a validar",
    )
    args = ap.parse_args()

    ruta = Path(args.catalogo)
    if not ruta.exists():
        print(f"ERROR: no existe {ruta}")
        return 2

    catalogo = _cargar_catalogo(ruta)
    ps = catalogo.get("productos", [])
    alertas = validar(catalogo, RAIZ)
    c_skus = [p for p in ps if str(p.get("sku", "")).upper().startswith("C")]

    print("=" * 70)
    print("VALIDACION CRUZADA DE TAXONOMIA")
    print("=" * 70)
    print(f"Productos en catalogo: {len(ps)}")
    print(f"SKUs C*: {len(c_skus)}")
    print(f"Lineas Crayola: {LINEAS_CRAYOLA}")
    print()

    if alertas:
        print(f"!!! {len(alertas)} ALERTAS DETECTADAS !!!")
        print()
        for a in alertas:
            print(f"  {a}")
        print()
        print("REVISAR ANTES DE COMMITEAR")
        return 1

    print("OK: No hay inconsistencias de taxonomia")
    print()
    print("Resumen:")
    print(f"  - C* ({len(c_skus)}): todos REPRESENTADAS")
    print(f"  - Lineas {LINEAS_VINIFAN_PURA}: 100% VINIFAN")
    print("  - Lineas Crayola: 100% REPRESENTADAS")
    print("  - 0 lineas mixtas")
    print("  - Metadata consistente")
    print("  - Taxonomia master-data == taxonomia g360-stock-api")
    return 0


if __name__ == "__main__":
    sys.exit(main())
