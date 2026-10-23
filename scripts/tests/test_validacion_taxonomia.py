"""Tests de la validacion de taxonomia del catalogo.

La validacion vive en scripts/validar_taxonomia.py (una sola implementacion):
este test la EJERCE y falla si encuentra errores. Antes este archivo era una
copia que hacia `return 1` en vez de `assert`: pytest nunca lo daba por
fallido y el "test de validacion autonoma" no vigilaba nada.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validar_taxonomia import (  # noqa: E402
    CATALOGO_POR_DEFECTO,
    LINEAS_CRAYOLA,
    LINEAS_VINIFAN_PURA,
    _taxonomia_api_stock,
    validar,
)
from generar_catalogo_base import CATEGORIA_POR_LINEA  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent


@pytest.mark.skipif(not CATALOGO_POR_DEFECTO.exists(), reason="catalogo no generado")
def test_catalogo_real_no_tiene_errores():
    """El catalogo publicado no puede tener incoherencias de taxonomia."""
    with open(CATALOGO_POR_DEFECTO, encoding="utf-8") as f:
        catalogo = json.load(f)
    errores, avisos = validar(catalogo, RAIZ)
    assert errores == [], "\n".join(errores)
    # Avisos de mantenimiento: la taxonomia publicada tiene que coincidir con
    # el codigo. Sin excepciones: no hay enlaces por parecido que justifiquen
    # avisos especiales.
    assert avisos == [], "\n".join(avisos)


def test_detecta_crayola_fuera_de_representadas():
    """Un C* con otra categoria debe dispararse como error."""
    catalogo = {
        "metadata": {"categorias_por_linea": {}},
        "productos": [
            {
                "sku": "CA001",
                "linea": "CA",
                "linea_codigo": "CA",
                "categoria": "VINIFAN",
                "precio": 10.0,
            }
        ],
    }
    errores, _ = validar(catalogo, RAIZ)
    assert any("CA001" in e for e in errores)


def test_detecta_linea_mixta():
    """Una linea con dos categorias es un error."""
    catalogo = {
        "metadata": {"categorias_por_linea": {}},
        "productos": [
            {
                "sku": "A001",
                "linea": "78",
                "linea_codigo": "",
                "categoria": "VINIFAN",
                "precio": 1.0,
            },
            {
                "sku": "A002",
                "linea": "78",
                "linea_codigo": "",
                "categoria": "REPRESENTADAS",
                "precio": 1.0,
            },
        ],
    }
    errores, _ = validar(catalogo, RAIZ)
    assert any("categorias mixtas" in e for e in errores)


def test_detecta_precio_cero():
    """Publicar un producto sin precio viola la regla absoluta."""
    catalogo = {
        "metadata": {"categorias_por_linea": {}},
        "productos": [
            {
                "sku": "A001",
                "linea": "78",
                "linea_codigo": "",
                "categoria": "VINIFAN",
                "precio": 0.0,
            }
        ],
    }
    errores, _ = validar(catalogo, RAIZ)
    assert any("precio" in e for e in errores)


def test_detecta_universo_sin_taxonomia():
    """Un universo sin lineas S1 (parseo viejo/cache) frena la subida."""
    catalogo = {
        "metadata": {
            "categorias_por_linea": {},
            "universo_stock": {
                "incluido": True,
                "skus": 2257,
                "sin_taxonomia_s1": 513,
                "alerta_sin_taxonomia": "513/2257 SKUs sin taxonomia",
            },
            "universo_skus": [],
            "cobertura_faltante": [],
        },
        "productos": [],
    }
    errores, _ = validar(catalogo, RAIZ)
    assert any("sin_taxonomia" in e or "sin taxonomia" in e for e in errores)


def test_detecta_linea_sin_declarar():
    """Una linea publicada que no esta en la taxonomia es un error."""
    catalogo = {
        "metadata": {"categorias_por_linea": {}},
        "productos": [
            {
                "sku": "X990",
                "linea": "ZZ",
                "linea_codigo": "ZZ",
                "categoria": "OTROS",
                "precio": 5.0,
            }
        ],
    }
    errores, _ = validar(catalogo, RAIZ)
    assert any("linea_codigo=ZZ" in e for e in errores)


def test_sub_marca_nueva_es_aviso_no_error():
    """Una sub-marca Crayola nueva: aviso de mantenimiento, no bloquea.

    El generador la declara al vuelo en la taxonomia publicada (para que
    /stock la resuelva), pero hay que dejarla fija en el codigo.
    """
    catalogo = {
        "metadata": {
            "categorias_por_linea": {**CATEGORIA_POR_LINEA, "CH": "REPRESENTADAS"}
        },
        "productos": [
            {
                "sku": "CH990",
                "linea": "CH",
                "linea_codigo": "CH",
                "categoria": "REPRESENTADAS",
                "precio": 5.0,
            }
        ],
    }
    errores, avisos = validar(catalogo, RAIZ)
    assert not any("CH990" in e for e in errores)
    assert any("CH" in a and "CATEGORIA_POR_LINEA" in a for a in avisos)


def test_taxonomia_del_maestro_es_la_misma_que_la_del_api():
    """master-data y g360-stock-api deben clasificar igual cada linea.

    /stock y /catalog leen la misma taxonomia: si divergen, el mismo SKU
    aparece con dos categorias distintas segun el endpoint.
    """
    api = RAIZ.parent / "g360-stock-api" / "app" / "core" / "constants.py"
    if not api.exists():
        pytest.skip("g360-stock-api no esta presente")
    tax_api = _taxonomia_api_stock(api)
    tax_maestro = CATEGORIA_POR_LINEA
    divergentes = {
        cod: (tax_maestro.get(cod), cat)
        for cod, cat in tax_api.items()
        if cod in tax_maestro and tax_maestro[cod] != cat
    }
    assert divergentes == {}, f"taxonomias divergentes: {divergentes}"


def test_lineas_crayola_publicadas_como_representadas():
    """Las lineas Crayola del catalogo real son 100% REPRESENTADAS."""
    if not CATALOGO_POR_DEFECTO.exists():
        pytest.skip("catalogo no generado")
    with open(CATALOGO_POR_DEFECTO, encoding="utf-8") as f:
        catalogo = json.load(f)
    for p in catalogo["productos"]:
        if str(p.get("linea")) in LINEAS_CRAYOLA:
            assert p.get("categoria") == "REPRESENTADAS", (p["sku"], p.get("categoria"))
        if str(p.get("linea")) in LINEAS_VINIFAN_PURA:
            assert p.get("categoria") != "REPRESENTADAS", p["sku"]
