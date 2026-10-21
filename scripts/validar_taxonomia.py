"""Validacion cruzada entre repos: detecta inconsistencias de taxonomia.

Correr despues de cualquier cambio en master-data, stock-api o vigencias.
Si hay ERRORES, el catalogo no debe subirse al API.

Uso:
    python scripts/validar_taxonomia.py
    python scripts/validar_taxonomia.py --catalogo ruta.json
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO_POR_DEFECTO = RAIZ / "output" / "catalogo_productos.json"

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


def _dict_de_fuente(ruta_fuente: Path, nombre_constante: str) -> ast.Dict | None:
    """Localiza el dict literal de una constante en un fuente (AST)."""
    if not ruta_fuente.exists():
        return None
    arbol = ast.parse(ruta_fuente.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if _asignacion_nombre(nodo) != nombre_constante:
            continue
        if isinstance(nodo.value, ast.Dict):
            return nodo.value
    return None


def _claves_duplicadas(ruta_fuente: Path, nombre_constante: str) -> list[str]:
    """Claves repetidas en un dict literal del fuente (AST).

    En un dict de Python una clave repetida no avisa: gana la ultima. Por eso
    la taxonomia podia "cambiar" sin que nadie se diera cuenta.
    """
    d = _dict_de_fuente(ruta_fuente, nombre_constante)
    if d is None:
        return []
    repetidas: list[str] = []
    vistas: set[str] = set()
    for key in d.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if key.value in vistas:
                repetidas.append(key.value)
            vistas.add(key.value)
    return repetidas


def _taxonomia_de_fuente(ruta_fuente: Path, nombre_constante: str) -> dict[str, str]:
    """Dict literal simple {str: str} de una constante del fuente."""
    d = _dict_de_fuente(ruta_fuente, nombre_constante)
    if d is None:
        return {}
    mapa: dict[str, str] = {}
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
            mapa[str(k.value)] = str(v.value)
    return mapa


def _taxonomia_api_stock(ruta: Path) -> dict[str, str] | None:
    """Taxonomia linea->categoria declarada en el API de stock (constants.py)."""
    d = _dict_de_fuente(ruta, "CATEGORIAS")
    if d is None:
        return None
    mapa: dict[str, str] = {}
    for k, v in zip(d.keys, d.values):
        if not isinstance(k, ast.Constant) or not isinstance(v, ast.List):
            continue
        categoria = str(k.value)
        for cod in v.elts:
            if isinstance(cod, ast.Constant):
                mapa[str(cod.value)] = categoria
    return mapa


def validar(catalogo: dict, raiz: Path = RAIZ) -> tuple[list[str], list[str]]:
    """Valida el catálogo.

    Devuelve (errores, avisos):
      - errores: incoherencias reales. Bloquean la subida al API.
      - avisos:  mantenimiento pendiente (p.ej. una sub-marca Crayola nueva
                 que hay que dejar fija en el codigo). No bloquean.
    """
    errores: list[str] = []
    avisos: list[str] = []
    ps = catalogo.get("productos", [])
    meta = catalogo.get("metadata", {})

    # 1. Todos los C* en catalogo son REPRESENTADAS
    c_skus = [p for p in ps if str(p.get("sku", "")).upper().startswith("C")]
    for p in c_skus:
        if p.get("categoria") != "REPRESENTADAS":
            errores.append(
                f"ALERTA: {p['sku']} es C* pero categoria={p.get('categoria')} "
                "(debe ser REPRESENTADAS)"
            )

    # 2. Las lineas 72/76/77/79 no tienen REPRESENTADAS
    for p in ps:
        lin = str(p.get("linea", ""))
        if lin in LINEAS_VINIFAN_PURA and p.get("categoria") == "REPRESENTADAS":
            errores.append(
                f"ALERTA: {p['sku']} en linea {lin} (VINIFAN) pero "
                f"categoria={p.get('categoria')}"
            )

    # 3. Las lineas CA/CB/CC/CD/CE/CF son REPRESENTADAS
    for p in ps:
        lin = str(p.get("linea", ""))
        if lin in LINEAS_CRAYOLA and p.get("categoria") != "REPRESENTADAS":
            errores.append(
                f"ALERTA: {p['sku']} en linea {lin} (Crayola) pero "
                f"categoria={p.get('categoria')}"
            )

    # 4. Ninguna linea puede tener mas de una categoria (lineas mixtas)
    cats_por_linea: dict[str, set[str]] = defaultdict(set)
    for p in ps:
        cats_por_linea[str(p.get("linea", ""))].add(str(p.get("categoria", "")))
    for lin, cats in sorted(cats_por_linea.items()):
        if len(cats) > 1:
            errores.append(
                f"ALERTA: Linea {lin} tiene categorias mixtas: {sorted(cats)}"
            )

    # 5. Metadata coherente con los productos
    cat_por_linea = meta.get("categorias_por_linea", {})
    for lin in LINEAS_CRAYOLA:
        if cat_por_linea.get(lin) != "REPRESENTADAS":
            errores.append(
                f"ALERTA: metadata categorias_por_linea[{lin}] = "
                f"{cat_por_linea.get(lin)} (debe ser REPRESENTADAS)"
            )
    for p in ps:
        lin = str(p.get("linea", ""))
        cod = str(p.get("linea_codigo", ""))
        if cod and lin and cat_por_linea.get(cod) not in (None, p.get("categoria")):
            errores.append(
                f"ALERTA: {p['sku']} linea={lin} categoria={p.get('categoria')} "
                f"no coincide con metadata categorias_por_linea[{cod}]="
                f"{cat_por_linea.get(cod)}"
            )

    # 6. El codigo de linea de un C* debe existir en la taxonomia
    for p in ps:
        cod = str(p.get("linea_codigo", ""))
        if cod and cod not in cat_por_linea:
            errores.append(
                f"ALERTA: {p['sku']} tiene linea_codigo={cod} que no esta en la "
                "taxonomia publicada"
            )

    # 7. Sin claves duplicadas en el diccionario de taxonomia del maestro
    for cod in _claves_duplicadas(
        raiz / "scripts" / "generar_catalogo_base.py", "CATEGORIA_POR_LINEA"
    ):
        errores.append(
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
                errores.append(
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
            errores.append(
                f"ALERTA: {p['sku']} esta publicado con precio={precio} "
                "(sin precio no se publica)"
            )

    # 10. La taxonomia publicada debe coincidir con la del codigo fuente.
    #     Si difiere, la generacion detecto una sub-marca Crayola nueva y la
    #     declaro al vuelo: hay que dejarla fija en el codigo.
    tax_codigo = _taxonomia_de_fuente(
        raiz / "scripts" / "generar_catalogo_base.py", "CATEGORIA_POR_LINEA"
    )
    if tax_codigo:
        for cod, cat in sorted(cat_por_linea.items()):
            if cod not in tax_codigo:
                avisos.append(
                    f"AVISO: la linea {cod} ({cat}) se publico pero no esta fija "
                    "en CATEGORIA_POR_LINEA: agregala a "
                    "scripts/generar_catalogo_base.py y a CATEGORIAS en "
                    "g360-stock-api/app/core/constants.py"
                )
        for cod, cat in sorted(tax_codigo.items()):
            if cod not in cat_por_linea:
                avisos.append(
                    f"AVISO: CATEGORIA_POR_LINEA declara {cod} ({cat}) pero la "
                    "taxonomia publicada no: revisa que no se haya quedado obsoleta"
                )

    # 11. El universo de stock tiene que haber entrado en la generacion.
    #     Sin el, el catalogo pierde los SKUs con despacho que no estan en
    #     SKU_BX (212 SKUs en la ultima corrida). Salvo que se haya omitido
    #     a proposito.
    uni = meta.get("universo_stock", {})
    if uni and not uni.get("incluido"):
        error = str(uni.get("error", ""))
        if "omitido" in error:
            avisos.append(
                "AVISO: el catalogo se genero SIN universo de stock "
                f"({error}): faltan los SKUs con stock que no estan en SKU_BX"
            )
        else:
            errores.append(
                f"ALERTA: el catalogo se genero SIN universo de stock ({error}): "
                "el catalogo esta incompleto (212 SKUs en la ultima corrida). "
                "No lo subas: regenera cuando el API de stock responda."
            )

    return errores, avisos


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
    errores, avisos = validar(catalogo, RAIZ)
    c_skus = [p for p in ps if str(p.get("sku", "")).upper().startswith("C")]

    print("=" * 70)
    print("VALIDACION CRUZADA DE TAXONOMIA")
    print("=" * 70)
    print(f"Productos en catalogo: {len(ps)}")
    print(f"SKUs C*: {len(c_skus)}")
    print(f"Lineas Crayola: {LINEAS_CRAYOLA}")
    print()

    if avisos:
        print(f"--- {len(avisos)} AVISOS (no bloquean la subida) ---")
        for a in avisos:
            print(f"  {a}")
        print()

    if errores:
        print(f"!!! {len(errores)} ERRORES: NO SUBIR EL CATALOGO AL API !!!")
        print()
        for e in errores:
            print(f"  {e}")
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
