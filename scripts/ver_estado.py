"""Muestra estado del catalogo generado."""
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

print(f"Productos:    {m['total_productos']}")
print(f"Generado:     {m['generated_at']}")
print(f"Con ean14:    {e['con_ean14']}")
print(f"Con un_bx:    {e['con_unbx']}")
print(f"Sin un_bx:    {e['sin_unbx']}")
print(f"Tamano:       {ruta.stat().st_size / 1024:.1f} KB")
