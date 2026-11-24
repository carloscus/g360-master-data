#!/usr/bin/env python3
"""
actualizar_contract_version.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Inserta (o corrige) SOLO ``metadata.contract_version`` en
``output/catalogo_productos.json`` sin tocar ningun otro dato.

Es un paso determinista, idempotente y sin red: se ejecuta despues de que el
generador escribio el catalogo completo y publica el campo que los consumidores
(``g360-stock-api``: ``app/config.py:37`` y ``app/services/catalog_service.py:41-55``)
leen para decidir compatibilidad en runtime.

No modifica ``generated_at``, ``total_productos``, productos, estadisticas ni
ningun otro campo. Si ``contract_version`` ya tiene el valor esperado, el
archivo queda intacto (no se reescribe).

Uso (desde la raiz del repo):

    python scripts/actualizar_contract_version.py [ruta_al_catalogo]

Si no se pasa ruta, usa ``output/catalogo_productos.json`` relativo al repo.

Devuelve 0 si todo ok (campo publicado o ya estaba), 1 si el archivo no existe
o no es JSON valido.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# VERSION vive en generar_catalogo_base.py (mismo directorio). Se importa para
# no declarar dos fuentes de verdad: si falla el import (script usado fuera del
# repo), se usa el literal 3.8.0 sincronizado con VERSION.
try:  # pragma: no cover - solo falla fuera del contexto del repo
    from generar_catalogo_base import VERSION as _VERSION
except ImportError:  # pragma: no cover
    # Fallback solo cuando el modulo no esta disponible (script usado fuera
    # del repo). Cualquier otro error (SyntaxError, etc.) debe propagarse, no
    # silenciarse con un 3.8.0 inventado.
    _VERSION = "3.8.0"

CONTRACT_VERSION = _VERSION
DEFAULT_SALIDA = Path("output/catalogo_productos.json")
CLAVE = "contract_version"


def _cargar_json(ruta: Path):
    with ruta.open(encoding="utf-8") as f:
        return json.load(f)


def _guardar_json(ruta: Path, datos: dict, terminador_original: str) -> None:
    """Reescribe con formato canónico (indent=2, sin acentos escapados).

    El orden de claves se conserva tal cual lo trae el JSON leido
    (Python 3.7+ mantiene el orden de inserción al parsear), por lo que
    solo cambia la clave que se inserta/actualiza; el resto de los valores
    queda intacto. `terminador_original` preserva si el archivo terminaba
    o no en salto de línea, para que el diff sea estrictamente la clave
    insertada y nada más.
    """
    with ruta.open("w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
        f.write(terminador_original)


def _terminador_original(ruta: Path) -> str:
    """Devuelve '\n' si el archivo termina en salto de linea, '' si no."""
    with ruta.open("rb") as f:
        f.seek(0, 2)
        tam = f.tell()
        if tam == 0:
            return ""
        f.seek(tam - 1)
        ultimo = f.read(1)
    return "\n" if ultimo == b"\n" else ""


def actualizar(ruta: Path) -> bool:
    """Inserta/corrige ``metadata.contract_version``.

    Retorna True si el archivo se modifico, False si ya estaba correcto.
    """
    datos = _cargar_json(ruta)
    metadata = datos.get("metadata")
    if not isinstance(metadata, dict):
        print(f"ERROR: {ruta} no tiene metadata", file=sys.stderr)
        return False

    actual = metadata.get(CLAVE)
    if actual == CONTRACT_VERSION:
        return False  # ya esta: no tocar nada

    # Reconstruir metadata copiando todas las claves excepto contract_version,
    # e insertando contract_version inmediatamente despues de "version" para
    # alinear el artefacto con el generador y el ejemplo del README. json.load
    # conserva el orden de claves, asi que el resto queda intacto.
    nueva_metadata = {}
    insertado = False
    for clave, valor in metadata.items():
        if clave == CLAVE:
            # Se reinserta en la posicion correcta (despues de version); se
            # salta aca para no duplicar ni sobrescribir con el valor viejo.
            continue
        nueva_metadata[clave] = valor
        if clave == "version" and not insertado:
            nueva_metadata[CLAVE] = CONTRACT_VERSION
            insertado = True
    if not insertado:
        # "version" no existe: dejar contract_version al final como fallback.
        nueva_metadata[CLAVE] = CONTRACT_VERSION
    datos["metadata"] = nueva_metadata

    _guardar_json(ruta, datos, _terminador_original(ruta))
    return True


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ruta = Path(argv[0]) if argv else DEFAULT_SALIDA

    if not ruta.is_absolute():
        ruta = Path.cwd() / ruta

    if not ruta.exists():
        print(f"ERROR: no existe {ruta}", file=sys.stderr)
        return 1

    try:
        cambio = actualizar(ruta)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: no se pudo procesar {ruta}: {exc}", file=sys.stderr)
        return 1

    if cambio:
        print(f"OK: metadata.{CLAVE} = {CONTRACT_VERSION} publicado en {ruta}")
    else:
        print(f"OK: metadata.{CLAVE} ya era {CONTRACT_VERSION} (sin cambios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
