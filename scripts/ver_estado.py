"""Muestra el estado del catalogo generado (opcion 2 del BAT)."""

import json
import sys
from pathlib import Path

ruta = Path("output/catalogo_productos.json")
if not ruta.exists():
    print("No hay catalogo generado")
    sys.exit(1)

d = json.load(open(ruta, encoding="utf-8"))
m = d["metadata"]
e = m["estadisticas"]
uni = m.get("universo_stock", {})

print(f"Productos:    {m['total_productos']}")
print(f"Version:      {m.get('version', '?')}")
print(f"Generado:     {m['generated_at']}")
print(f"Tamano:       {ruta.stat().st_size / 1024:.1f} KB")
print()
print("Cobertura de datos:")
print(f"  Con ean13:        {m['total_productos'] - e['sin_ean13']}")
print(f"  Sin ean13:        {e['sin_ean13']}")
print(f"  Con ean14:        {e['con_ean14']}")
print(f"  Con un_bx:        {e['con_unbx']}")
print(f"  Sin un_bx (1):    {e['sin_unbx']}")
print(f"  Descontinuados:   {e['descontinuados']}")
print(f"  Sin linea_codigo: {e['sin_linea_codigo']}")
print()
print("Universo de stock (SKUs con despacho pendiente):")
if uni.get("incluido"):
    print(f"  Incluido: {uni.get('skus', 0)} SKUs")
else:
    print(f"  NO INCLUIDO: {uni.get('error') or 'sin consultar'}")
    print("  -> el catalogo esta incompleto: faltan los SKUs con stock")
    print("     que no estan en SKU_BX. Define API_KEY y vuelve a generar.")
print()
print("Categorias:")
for cat, cnt in sorted(e["por_categoria"].items(), key=lambda x: -x[1]):
    print(f"  {cat}: {cnt}")
print()
print("Lineas (codigo canonico):")
for lin, cnt in sorted(e["por_linea"].items(), key=lambda x: -x[1]):
    print(f"  {lin}: {cnt}")
print()
print("Estados de linea:")
for est, cnt in sorted(e["por_estado_linea"].items(), key=lambda x: -x[1]):
    print(f"  {est}: {cnt}")
if m.get("exclusiones"):
    print()
    print("Exclusiones del ERP (por que no entraron):")
    for motivo, cnt in sorted(m["exclusiones"].items(), key=lambda x: -x[1]):
        print(f"  {motivo}: {cnt}")
