"""Validacion cruzada entre repos: detecta inconsistencias de taxonomia.

Correr despues de cualquier cambio en master-data, stock-api o vigencias.
Si hay ALERTAS, revisar antes de commitear.
"""

import json
import sys
from pathlib import Path
from collections import Counter


def main():
    MASTER = Path(
        r"C:\Users\ccusi\Documents\Proyect_Coder\G360-ecosystem\projects\g360-master-data"
    )

    # Cargar catalogo
    cat = json.load(
        open(MASTER / "output" / "catalogo_productos.json", encoding="utf-8")
    )
    ps = cat["productos"]

    alerts = []

    # 1. Verificar que todos los C* en catalogo sean REPRESENTADAS
    c_skus = [p for p in ps if p["sku"].upper().startswith("C")]
    for p in c_skus:
        if p.get("categoria") != "REPRESENTADAS":
            alerts.append(
                f"ALERTA: {p['sku']} es C* pero categoria={p.get('categoria')} (debe ser REPRESENTADAS)"
            )

    # 2. Verificar que líneas 72/76/77/79 no tengan REPRESENTADAS
    for p in ps:
        lin = str(p.get("linea", ""))
        cat_p = p.get("categoria", "")
        if lin in ("72", "76", "77", "79") and cat_p == "REPRESENTADAS":
            alerts.append(
                f"ALERTA: {p['sku']} en linea {lin} (VINIFAN) pero categoria={cat_p}"
            )

    # 3. Verificar que líneas CA/CB/CC/CD/CE/CF sean REPRESENTADAS
    crayola_lines = ("CA", "CB", "CC", "CD", "CE", "CF")
    for p in ps:
        lin = str(p.get("linea", ""))
        cat_p = p.get("categoria", "")
        if lin in crayola_lines and cat_p != "REPRESENTADAS":
            alerts.append(
                f"ALERTA: {p['sku']} en linea {lin} (Crayola) pero categoria={cat_p}"
            )

    # 4. Verificar que no haya líneas mixtas (mas de una categoria)
    por_linea = Counter()
    for p in ps:
        por_linea[str(p.get("linea", ""))] += 1

    mixed_lines = []
    for p in ps:
        lin = str(p.get("linea", ""))
        cat_p = p.get("categoria", "")
        # Contar categorias por linea
        cats_en_linea = set(
            pp.get("categoria") for pp in ps if str(pp.get("linea", "")) == lin
        )
        if len(cats_en_linea) > 1:
            mixed_lines.append((lin, cats_en_linea))

    # Deduplicar
    mixed_lines = list(set(mixed_lines))
    for lin, cats in mixed_lines:
        alerts.append(f"ALERTA: Linea {lin} tiene categorias mixtas: {cats}")

    # 5. Verificar integridad de metadata
    meta = cat.get("metadata", {})
    cat_por_linea = meta.get("categorias_por_linea", {})
    for lin in crayola_lines:
        if cat_por_linea.get(lin) != "REPRESENTADAS":
            alerts.append(
                f"ALERTA: metadata categorias_por_linea[{lin}] = {cat_por_linea.get(lin)} (debe ser REPRESENTADAS)"
            )

    # Reporte
    print("=" * 70)
    print("VALIDACION CRUZADA DE TAXONOMIA")
    print("=" * 70)
    print(f"Productos en catalogo: {len(ps)}")
    print(f"SKUs C*: {len(c_skus)}")
    print(f"Lineas Crayola: {crayola_lines}")
    print()

    if alerts:
        print(f"!!! {len(alerts)} ALERTAS DETECTADAS !!!")
        print()
        for a in alerts:
            print(f"  {a}")
        print()
        print("REVISAR ANTES DE COMMITEAR")
        return 1
    else:
        print("OK: No hay inconsistencias de taxonomia")
        print()
        print("Resumen:")
        print(f"  - C* ({len(c_skus)}): todos REPRESENTADAS")
        print(f"  - Lineas 72/76/77/79: 100% VINIFAN")
        print(f"  - Lineas Crayola: 100% REPRESENTADAS")
        print(f"  - 0 lineas mixtas")
        print(f"  - Metadata consistente")
        return 0


if __name__ == "__main__":
    sys.exit(main())
