"""Consulta autonoma por jerarquia: KARDEX manda, el JSON responde.

El KARDEX es la estructura primaria en jerarquia (linea/grupo/tipo/familia
por ID); el ERP aporta precio y peso; SKU_BX aporta unidades por caja.
Este script cruza las tres capas sin ayuda externa:

    1. Filtra SKUs en KARDEX por IDs de jerarquia (exactos, sin parecidos).
    2. Los busca en el catalogo JSON publicado (calce exacto primero,
       sin prefijo numerico despues: la misma regla del generador).
    3. Reporta que esta publicado, a que precio/peso/caja/stock, y que
       quedo fuera (regla de inclusion: guia, stock, compromiso o
       vigente con precio).

Uso:
    python scripts/consultar_por_taxonomia.py --linea 01 --grupo 01 --tipo 02 --familia 01,02
    python scripts/consultar_por_taxonomia.py --linea 01 --json
"""

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from contratos import emparejar_skus, leer_kardex  # noqa: E402

CAMPOS_JERARQUIA = (
    ("linea", "linea_id"),
    ("grupo", "grupo_id"),
    ("tipo", "tipo_id"),
    ("familia", "familia_id"),
)


def _parse_ids(texto: str | list[str] | None) -> set[str] | None:
    # action="append": llega lista si se repite el flag (--familia 01 --familia 02).
    # OJO PowerShell: --familia 01,02 sin comillas llega como numeros 1 2
    # (la coma es operador de arreglo). Siempre entrecomillar: '01,02'.
    if not texto:
        return None
    partes = texto if isinstance(texto, list) else [texto]
    return {p.strip() for t in partes for p in t.split(",") if p.strip()}


def filtrar_jerarquia(
    fichas: dict,
    linea: set[str] | None = None,
    grupo: set[str] | None = None,
    tipo: set[str] | None = None,
    familia: set[str] | None = None,
) -> dict:
    """SKUs del KARDEX cuya ficha calza con TODOS los IDs pedidos.

    Los IDs son los `*_id` del KARDEX ('01', no 'PELOTAS'). Un filtro
    vacio/None no restringe ese nivel. Comparacion exacta de strings.
    """
    pedido = {
        "linea_id": linea,
        "grupo_id": grupo,
        "tipo_id": tipo,
        "familia_id": familia,
    }
    seleccion = {}
    for sku, ficha in fichas.items():
        ok = True
        for campo, elegidos in pedido.items():
            if elegidos and ficha.get(campo) not in elegidos:
                ok = False
                break
        if ok:
            seleccion[sku] = ficha
    return seleccion


def _cargar_catalogo(ruta: Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def consultar(fichas: dict, catalogo: dict, filtros: dict) -> dict:
    """Cruza seleccion KARDEX con productos del JSON. Devuelve el reporte."""
    seleccion = filtrar_jerarquia(
        fichas,
        linea=filtros.get("linea"),
        grupo=filtros.get("grupo"),
        tipo=filtros.get("tipo"),
        familia=filtros.get("familia"),
    )
    prods = {p["sku"]: p for p in catalogo.get("productos", [])}
    # Una sola regla de calce en todo el sistema (contratos.emparejar_skus):
    # exacto primero, prefijo despues en cualquier lado ('01CA001'<->'CA001',
    # '1014458'<->'014458'), siempre verificado contra la otra fuente.
    match, stats = emparejar_skus(set(seleccion), set(prods))

    filas = []
    for sku in sorted(seleccion):
        ficha = seleccion[sku]
        if sku in match:
            p = prods[match[sku]]
            filas.append(
                {
                    "sku": sku,
                    "sku_catalogo": match[sku] if match[sku] != sku else sku,
                    "via_prefijo": match[sku] != sku,
                    "en_catalogo": True,
                    "nombre": ficha.get("nombre_corto", ""),
                    "um": ficha.get("um", ""),
                    "ean13": p.get("ean13", ""),
                    "ean14": p.get("ean14", ""),
                    "precio": p.get("precio", 0),
                    "peso_kg": p.get("peso_kg", 0),
                    "un_bx": p.get("un_bx", 0),
                    "stock": p.get("stock_snapshot", 0),
                    "categoria": p.get("categoria", ""),
                    "cotizable": bool(p.get("precio", 0)),
                }
            )
        else:
            filas.append(
                {
                    "sku": sku,
                    "en_catalogo": False,
                    "nombre": ficha.get("nombre_corto", ""),
                    "um": ficha.get("um", ""),
                    "motivo": (
                        "no publicado (fuera de la regla de inclusion: "
                        "guia, stock, compromiso o vigente con precio)"
                    ),
                }
            )
    return {
        "filtros": {k: sorted(v) for k, v in filtros.items() if v},
        "kardex_seleccion": len(seleccion),
        "calce": stats,
        "en_catalogo": sum(1 for f in filas if f["en_catalogo"]),
        "cotizables": sum(1 for f in filas if f.get("cotizable")),
        "filas": filas,
    }


def _imprimir(reporte: dict, limite: int) -> None:
    f = reporte["filtros"]
    print(
        "Jerarquia pedida: "
        + (
            ", ".join(f"{k}={','.join(v)}" for k, v in f.items())
            or "(sin filtro: todo el KARDEX)"
        )
    )
    print(
        f"KARDEX: {reporte['kardex_seleccion']} SKUs | en catalogo: {reporte['en_catalogo']} | cotizables: {reporte['cotizables']}"
    )
    calce = reporte["calce"]
    if calce.get("prefijo"):
        print(f"(calce con prefijo numerico: {calce['prefijo']})")
    print(
        f"{'SKU_KARDEX -> SKU_JSON':<28}{'EAN13':<14}{'EAN14':<15}{'NOMBRE':<24}{'UM':<5}{'PRECIO':>9}{'UN_BX':>7}{'STOCK':>8}  CATEGORIA"
    )
    for fila in reporte["filas"][:limite]:
        if fila["en_catalogo"]:
            marca = " *" if fila["via_prefijo"] else ""
            sku = fila["sku"]
            if fila["via_prefijo"]:
                sku = f"{fila['sku']} -> {fila['sku_catalogo']}"
            print(
                f"{sku:<28}{fila.get('ean13', ''):<14}{fila.get('ean14', ''):<15}{fila['nombre'][:23]:<24}{fila['um']:<5}"
                f"{fila['precio']:>9.2f}{fila['un_bx'] or '-':>7}{fila['stock'] or 0:>8}  {fila['categoria']}{marca}"
            )
        else:
            print(
                f"{fila['sku']:<28}{'':<14}{'':<15}{fila['nombre'][:23]:<24}{fila['um']:<5}{'--':>9}  FUERA"
            )
    resto = len(reporte["filas"]) - min(limite, len(reporte["filas"]))
    if resto:
        print(f"... y {resto} filas mas (usar --limite 0 para ver todo)")
    print("(* = calce con prefijo KARDEX; FUERA = no publicado por regla de inclusion)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Consulta autonoma por jerarquia KARDEX vs catalogo JSON"
    )
    ap.add_argument(
        "--linea",
        default=[],
        action="append",
        help="IDs de linea (ej: '01'). Repetible o con coma '01,02' (entrecomillar en PowerShell)",
    )
    ap.add_argument(
        "--grupo", default=[], action="append", help="IDs de grupo (ej: '01')"
    )
    ap.add_argument(
        "--tipo", default=[], action="append", help="IDs de tipo (ej: '02')"
    )
    ap.add_argument(
        "--familia", default=[], action="append", help="IDs de familia (ej: '01,02')"
    )
    ap.add_argument("--kardex", default=str(RAIZ / "data" / "KARDEX_BASE.xlsx"))
    ap.add_argument(
        "--catalogo", default=str(RAIZ / "output" / "catalogo_productos.json")
    )
    ap.add_argument(
        "--limite", type=int, default=40, help="Filas a mostrar (0 = todas)"
    )
    ap.add_argument("--json", action="store_true", help="Salida JSON en vez de tabla")
    args = ap.parse_args()

    fichas, meta = leer_kardex(args.kardex)
    if not fichas:
        print(f"Sin KARDEX ({meta.get('nota', '')}): no hay jerarquia que consultar.")
        return 1
    catalogo = _cargar_catalogo(Path(args.catalogo))
    reporte = consultar(
        fichas,
        catalogo,
        {
            "linea": _parse_ids(args.linea),
            "grupo": _parse_ids(args.grupo),
            "tipo": _parse_ids(args.tipo),
            "familia": _parse_ids(args.familia),
        },
    )
    if args.json:
        print(json.dumps(reporte, ensure_ascii=False, indent=1))
    else:
        if not reporte["kardex_seleccion"] and reporte["filtros"]:
            print(
                "AVISO: ningun SKU calza con esos IDs. Verificar que sean "
                "los *_id del KARDEX ('01', no 'PELOTAS') y entrecomillar "
                "las comas en PowerShell: --familia '01,02'."
            )
        _imprimir(reporte, args.limite if args.limite > 0 else len(reporte["filas"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
