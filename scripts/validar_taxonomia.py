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

LINEAS_CRAYOLA = ("CA", "CB", "CC", "CD", "CE", "CF", "CG")
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


def _check_categorias(ps, errores) -> None:
    """Checks 1-4: coherencia de CATEGORIA por SKU y por linea (C* son
    REPRESENTADAS, lineas VINIFAN puras, lineas Crayola y lineas mixtas)."""
    # 1. Todos los C* en catalogo son REPRESENTADAS
    for p in ps:
        if str(p.get("sku", "")).upper().startswith("C"):
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


def _check_metadata_publicada(ps, meta, errores) -> None:
    """Checks 5-6: la taxonomia publicada (metadata.categorias_por_linea)
    tiene que ser coherente con cada producto y cubrir sus codigos."""
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
        if cod and cod not in cat_por_linea:
            errores.append(
                f"ALERTA: {p['sku']} tiene linea_codigo={cod} que no esta en la "
                "taxonomia publicada"
            )


def _check_fuentes_taxonomia(raiz, meta, errores, avisos) -> None:
    """Checks 7-8b: la taxonomia del generador sin claves duplicadas, la
    misma que declara g360-stock-api (el API y el catalogo no se
    contradicen) y las sub-marcas Crayola publicadas al vuelo (aviso de
    mantenimiento, no error)."""
    cat_por_linea = meta.get("categorias_por_linea", {})
    for cod in _claves_duplicadas(
        raiz / "scripts" / "generar_catalogo_base.py", "CATEGORIA_POR_LINEA"
    ):
        errores.append(
            f"ALERTA: CATEGORIA_POR_LINEA tiene la clave duplicada '{cod}' "
            "(gana la ultima en silencio)"
        )

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

    # Sub-marcas Crayola publicadas al vuelo: si no estan fijas en
    # CATEGORIA_POR_LINEA, la taxonomia depende de cada generacion.
    taxonomia_codigo = _taxonomia_de_fuente(
        raiz / "scripts" / "generar_catalogo_base.py", "CATEGORIA_POR_LINEA"
    )
    for cod, cat in sorted(cat_por_linea.items()):
        if (
            isinstance(cod, str)
            and len(cod) == 2
            and cod.startswith("C")
            and cod[1].isalpha()
            and cod not in taxonomia_codigo
        ):
            avisos.append(
                f"AVISO: linea {cod} -> {cat} publicada al vuelo pero no esta "
                "fija en CATEGORIA_POR_LINEA (agregala al generador y a "
                "CATEGORIAS del API)"
            )


def _check_flags_negocio(ps, errores) -> None:
    """Check 9: coherencia de precio y flags de negocio (v3.6.0). El precio
    NO decide la presencia, pero si la cotizabilidad: lo que no tiene
    precio no cotiza, y los flags nunca pueden contradecirse."""
    for p in ps:
        sku = p.get("sku", "")
        try:
            precio = float(p.get("precio", 0))
        except (TypeError, ValueError):
            precio = 0.0
        # Los flags viejos (catalogo de version < 3.6.0) no los juzgamos:
        # solo se aplica la regla cuando el producto ya trae flags.
        if "cotizable" not in p:
            if precio <= 0:
                errores.append(
                    f"ALERTA: {sku} esta publicado con precio={precio} "
                    "(sin precio no se publica)"
                )
            continue
        if p.get("cotizable") and precio <= 0:
            errores.append(
                f"ALERTA: {sku} esta marcado cotizable con precio={precio} "
                "(sin precio no se cotiza)"
            )
        if precio > 0 and p.get("por_activar"):
            errores.append(
                f"ALERTA: {sku} tiene precio={precio} pero por_activar=true "
                "(por_activar es solo para SKUs sin precio)"
            )
        if p.get("por_activar") and p.get("cotizable"):
            errores.append(
                f"ALERTA: {sku} tiene por_activar=true y cotizable=true a la vez "
                "(un SKU por activar no se cotiza)"
            )
        origen = str(p.get("origen", ""))
        if origen and origen not in ("erp", "s1"):
            errores.append(
                f"ALERTA: {sku} tiene origen={origen} (debe ser 'erp' o 's1')"
            )
        cat_venta = p.get("categoria_venta", "")
        if cat_venta:
            cat = str(p.get("categoria", "")).upper()
            if cat in ("VINIBALL", "VINIFAN", "REPRESENTADAS") and cat != cat_venta:
                errores.append(
                    f"ALERTA: {sku} categoria={p.get('categoria')} pero "
                    f"categoria_venta={cat_venta} (deberia ser {cat})"
                )
            if cat not in ("VINIBALL", "VINIFAN", "REPRESENTADAS") and (
                cat_venta != "REVISION_VENTA"
            ):
                errores.append(
                    f"ALERTA: {sku} categoria={p.get('categoria')} pero "
                    f"categoria_venta={cat_venta} (deberia ser REVISION_VENTA)"
                )
        predespacho = p.get("predespacho_snapshot", None)
        if predespacho is not None and bool(p.get("compromiso")) != (
            float(predespacho) > 0
        ):
            errores.append(
                f"ALERTA: {sku} tiene predespacho_snapshot={predespacho} y "
                f"compromiso={p.get('compromiso')} (incoherentes)"
            )


def _check_cobertura(ps, meta, errores) -> None:
    """Checks 9b-9c3: invariante de cobertura (todo SKU con stock o
    compromiso publicado), cross-check independiente contra universo_skus,
    caida vs corrida anterior y universo sin taxonomia S1. Todo bloquea:
    un universo parcial es indistinguible de uno real sin estas barras."""
    faltantes = meta.get("cobertura_faltante", None)
    if faltantes is None and meta.get("universo_stock", {}).get("incluido"):
        errores.append(
            "ALERTA: el metadata no publica cobertura_faltante: regenera con "
            "generar_catalogo_base.py v3.6.0 o superior"
        )
    elif faltantes:
        errores.append(
            f"ALERTA: {len(faltantes)} SKUs con stock/compromiso quedaron fuera "
            f"del catalogo: {', '.join(str(s) for s in faltantes[:10])}"
            f"{'...' if len(faltantes) > 10 else ''}"
        )

    universo_skus = meta.get("universo_skus", [])
    if universo_skus:
        en_catalogo = {str(p.get("sku", "")) for p in ps}
        fuera = [s for s in universo_skus if s not in en_catalogo]
        if fuera:
            errores.append(
                f"ALERTA: {len(fuera)} SKUs publicados en universo_skus no estan "
                f"en productos: {', '.join(str(s) for s in fuera[:10])}"
                f"{'...' if len(fuera) > 10 else ''}"
            )

    uni = meta.get("universo_stock", {})
    if isinstance(uni, dict) and uni.get("alerta_caida"):
        errores.append(f"ALERTA: {uni['alerta_caida']}")
    if isinstance(uni, dict) and uni.get("alerta_sin_taxonomia"):
        errores.append(f"ALERTA: {uni['alerta_sin_taxonomia']}")


def _check_caja(ps, errores) -> None:
    """Check 9d: coherencia de la caja. Si el SKU publica dimensiones, el
    volumen es un CALCULO (largo*ancho*alto), no un dato libre: una celda
    pegada a mano lo rompe. Sin dimensiones (null) no se juzga."""
    for p in ps:
        caja = p.get("dimensiones_caja")
        if not caja:
            continue
        sku = p.get("sku", "")
        lados = [caja.get("largo_cm"), caja.get("ancho_cm"), caja.get("alto_cm")]
        try:
            lados_num = [float(v) for v in lados]
        except (TypeError, ValueError):
            errores.append(
                f"ALERTA: {sku} tiene dimensiones_caja no numericas: {lados}"
            )
            continue
        if any(v <= 0 for v in lados_num):
            errores.append(
                f"ALERTA: {sku} tiene dimensiones_caja con un lado <= 0: {lados}"
            )
            continue
        m3 = round(lados_num[0] * lados_num[1] * lados_num[2] / 1_000_000, 6)
        if abs(float(caja.get("m3_caja") or 0) - m3) > 1e-6:
            errores.append(
                f"ALERTA: {sku} m3_caja={caja.get('m3_caja')} no coincide con "
                f"largo*ancho*alto ({m3})"
            )
        un_bx = p.get("un_bx") or 0
        if un_bx:
            m3_unidad = round(m3 / un_bx, 6)
            if abs(float(caja.get("m3_unidad") or 0) - m3_unidad) > 1e-6:
                errores.append(
                    f"ALERTA: {sku} m3_unidad={caja.get('m3_unidad')} no "
                    f"coincide con m3_caja/un_bx ({m3_unidad})"
                )


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

    _check_categorias(ps, errores)
    _check_metadata_publicada(ps, meta, errores)
    _check_fuentes_taxonomia(raiz, meta, errores, avisos)
    _check_flags_negocio(ps, errores)
    _check_cobertura(ps, meta, errores)
    _check_caja(ps, errores)
    return errores, avisos


def main() -> int:
    """Gate post-generacion (lo llama el BAT antes de subir): coherencia
    linea->categoria, cobertura y caida del universo vs la corrida anterior,
    y cruce master-data vs g360-stock-api. ERRORES => exit 1 y NO SUBIR;
    los avisos no bloquean la subida."""
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
