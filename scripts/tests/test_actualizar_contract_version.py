#!/usr/bin/env python3
"""
Tests para scripts/actualizar_contract_version.py.

El script es determinista, idempotente y sin red: solo inserta/corrige
``metadata.contract_version`` en el catalogo sin tocar nada mas.
"""

import ast
import json
from pathlib import Path

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from actualizar_contract_version import actualizar, CONTRACT_VERSION


def _escribir_catalogo(ruta: Path, extra_meta=None, con_contract=False) -> None:
    meta = {
        "version": "3.8.0",
        "generated_at": "2026-10-26T09:47:24.067439",
        "total_productos": 3550,
        "estadisticas": {"sin_ean13": 2295, "derivados": 0},
    }
    if con_contract:
        meta["contract_version"] = "3.8.0"
    if extra_meta:
        meta.update(extra_meta)
    datos = {"metadata": meta, "productos": [{"sku": "A", "nombre": "X"}]}
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_inserta_contract_version_cuando_falta(tmp_path):
    """Al correr el script sobre una copia sin el campo, lo agrega con el
    valor correcto y no modifica el resto de los valores."""
    destino = tmp_path / "cat.json"
    _escribir_catalogo(destino)

    assert actualizar(destino) is True

    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["metadata"]["contract_version"] == CONTRACT_VERSION == "3.8.0"
    # Nada mas cambio: generated_at, total_productos, estadisticas, productos intactos.
    assert datos["metadata"]["generated_at"] == "2026-10-26T09:47:24.067439"
    assert datos["metadata"]["total_productos"] == 3550
    assert datos["metadata"]["estadisticas"] == {"sin_ean13": 2295, "derivados": 0}
    assert datos["productos"] == [{"sku": "A", "nombre": "X"}]


def test_no_modifica_si_ya_esta_correcto(tmp_path):
    """Idempotencia: segunda corrida no toca el archivo (devuelve False)."""
    destino = tmp_path / "cat.json"
    _escribir_catalogo(destino, con_contract=True)
    contenido_antes = destino.read_text(encoding="utf-8")

    assert actualizar(destino) is False
    assert destino.read_text(encoding="utf-8") == contenido_antes


def test_corrige_valor_erroneo(tmp_path):
    """Si contract_version existe con valor distinto, lo corrige sin tocar lo demas."""
    destino = tmp_path / "cat.json"
    _escribir_catalogo(destino, con_contract=True)
    datos = json.loads(destino.read_text(encoding="utf-8"))
    datos["metadata"]["contract_version"] = "9.9.9"
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert actualizar(destino) is True
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["metadata"]["contract_version"] == "3.8.0"
    assert datos["metadata"]["generated_at"] == "2026-10-26T09:47:24.067439"


def test_preserva_el_terminador_original(tmp_path):
    """El script respeta el terminador de línea original del archivo: si el
    JSON termina sin newline, se guarda sin newline; si termina con newline,
    se guarda con newline. El diff del artefacto publicado debe ser solo la
    clave insertada, nunca un salto de linea extra."""
    from actualizar_contract_version import _terminador_original

    # Caso sin newline al final: el ultimo byte es '}' (125).
    sin_nl = tmp_path / "sin_nl.json"
    sin_nl.write_text('{"a": 1}', encoding="utf-8")
    assert _terminador_original(sin_nl) == ""
    assert sin_nl.read_bytes()[-1] == 125  # '}'

    # Caso con newline al final: el ultimo byte es '\n' (10).
    con_nl = tmp_path / "con_nl.json"
    con_nl.write_text('{"a": 1}\n', encoding="utf-8")
    assert _terminador_original(con_nl) == "\n"
    assert con_nl.read_bytes()[-1] == 10  # '\n'


def test_import_de_version_usa_except_importerror_no_exception(tmp_path):
    """El import de VERSION captura solo ImportError, no Exception, para no
    enmascarar errores reales (SyntaxError, etc.) con el fallback 3.8.0.
    Verificado por AST sobre el source del script: ninguna cláusula
    'except Exception' (ni 'except BaseException') rodea el import."""
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "actualizar_contract_version.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    excepciones_anchas = []
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ExceptHandler) and nodo.type is not None:
            # nodo.type es un Name (ej. Exception) o un Tuple de nombres.
            nombres = nodo.type.elts if isinstance(nodo.type, ast.Tuple) else [nodo.type]
            for n in nombres:
                if isinstance(n, ast.Name) and n.id in ("Exception", "BaseException"):
                    excepciones_anchas.append(n.id)

    assert excepciones_anchas == [], (
        f"se encontró cláusula 'except {excepciones_anchas}' que enmascara errores: "
        "debe ser solo ImportError"
    )
