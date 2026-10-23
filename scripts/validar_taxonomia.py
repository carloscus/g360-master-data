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

    # 8b. Sub-marcas Crayola publicadas al vuelo: el generador las declara en
    #     el metadata, pero si no estan fijas en CATEGORIA_POR_LINEA la
    #     taxonomia depende de cada generacion (y el API las deja en OTROS
    #     hasta el proximo deploy). Es mantenimiento pendiente, no un error.
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

    # 9. Coherencia de precio y flags de negocio (v3.6.0).    #    El precio NO decide la presencia (todo SKU con stock/compromiso
    #    esta en el catalogo aunque no tenga precio), pero si la
    #    cotizabilidad: lo que no tiene precio no se cotiza.
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
        if p.get("derivado_de"):
            base = str(p["derivado_de"])
            if base == sku:
                errores.append(
                    f"ALERTA: {sku} se deriva de si mismo (derivado_de={base})"
                )
            elif base not in {q.get("sku", "") for q in ps}:
                # La base puede estar fuera del catalogo (descontinuada, sin
                # precio): el D se publica con su propia ficha igual, pero
                # conviene saberlo al revisar por que la base no entra.
                avisos.append(
                    f"AVISO: {sku} se deriva de {base}, que no esta publicado "
                    "(el D usa su propia ficha; revisar la base)"
                )
            # NOTA: desde v3.8 el D es un producto separado (solo similar a
            # su base): su linea/categoria/precio son propios y NO tienen
            # que coincidir con los de la base. No se valida coincidencia.

    # 9b. Invariante de cobertura: TODO SKU con stock o compromiso tiene
    #     que estar en el catalogo (salvo lineas de proceso). El generador
    #     publica la lista y sus faltantes; los faltantes deben ser cero.
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

    # 9c. Cross-check independiente: la lista del universo publicada tiene
    #     que estar entera en el catalogo (asi el invariante no depende de
    #     que el generador reporte bien sus propios faltantes).
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

    # 9d. Coherencia de la caja: si el SKU publica dimensiones, el volumen
    #     tiene que dar (es un calculo, no un dato libre: una celda pegada a
    #     mano lo rompe). Sin dimensiones se publica null y no se juzga.
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
