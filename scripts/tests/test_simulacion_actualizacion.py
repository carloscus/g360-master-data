"""Tests del ciclo de actualizacion de codigo (SKU nuevo).

Reproduce con un ERP minimo las reglas de inclusion del catalogo para las
situaciones reales de una actualizacion de codigo:

  - SKU nuevo vigente curado en SKU_BX  -> entra con un_bx/orden/estado
  - SKU nuevo descontinuado sin BX/stock -> queda fuera
  - SKU nuevo descontinuado con stock    -> entra marcado como descontinuado
  - SKU nuevo Crayola (C*)              -> entra con linea propia

Ejecutar: python -m pytest scripts/tests/test_simulacion_actualizacion.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from simular_actualizacion import (  # noqa: E402
    FILAS_NUEVAS,
    SKU_ESCENARIO_1,
    SKU_ESCENARIO_2,
    SKU_ESCENARIO_3,
    SKU_ESCENARIO_4,
    _generar,
    escribir_bx_minimo,
    escribir_erp_minimo,
)


@pytest.fixture(scope="module")
def catalogo_minimo(tmp_path_factory):
    """Catalogo generado desde un ERP minimo con los 4 escenarios."""
    tmp = tmp_path_factory.mktemp("sim_minimo")
    erp = escribir_erp_minimo(tmp / "PRODUCTOS.xls", FILAS_NUEVAS)
    bx = escribir_bx_minimo(tmp / "SKU_BX.xlsx", [SKU_ESCENARIO_1])
    salida = tmp / "catalogo.json"
    out = _generar(erp, bx, salida, stock_skus={SKU_ESCENARIO_3})
    return {p["sku"]: p for p in out["productos"]}, out["metadata"]


def test_sku_nuevo_curado_en_bx_entra_con_datos_de_caja(catalogo_minimo):
    """Escenario 1: el SKU_BX aporta un_bx, orden y estado_linea."""
    productos, _ = catalogo_minimo
    assert SKU_ESCENARIO_1 in productos
    p = productos[SKU_ESCENARIO_1]
    assert p["un_bx"] == 24
    assert p["orden"] > 0
    assert p["estado_linea"] == "NUEVO"
    assert p["categoria"] == "VINIFAN"
    assert p["linea"] == "76"


def test_sku_descontinuado_sin_bx_ni_stock_queda_fuera(tmp_path):
    """Escenario 2: un descontinuado que no esta en SKU_BX no se publica."""
    erp = escribir_erp_minimo(tmp_path / "PRODUCTOS.xls", FILAS_NUEVAS)
    bx = escribir_bx_minimo(tmp_path / "SKU_BX.xlsx", [SKU_ESCENARIO_1])
    out = _generar(erp, bx, tmp_path / "cat.json", stock_skus=set())
    skus = {p["sku"] for p in out["productos"]}
    assert SKU_ESCENARIO_2 not in skus


def test_sku_descontinuado_con_stock_entra_marcado(catalogo_minimo):
    """Escenario 3: hay despacho que hacer, entra aunque no este en SKU_BX."""
    productos, _ = catalogo_minimo
    assert SKU_ESCENARIO_3 in productos
    assert productos[SKU_ESCENARIO_3]["descontinuado"] is True


def test_sku_crayola_entra_con_linea_propia(catalogo_minimo):
    """Escenario 4: un C* nuevo define su propia linea y es REPRESENTADAS."""
    productos, _ = catalogo_minimo
    assert SKU_ESCENARIO_4 in productos
    p = productos[SKU_ESCENARIO_4]
    assert p["linea"] == "CG"
    assert p["categoria"] == "REPRESENTADAS"


def test_metadata_registra_el_universo_de_stock(catalogo_minimo):
    """El catalogo deja constancia de si el universo de stock entro."""
    _, meta = catalogo_minimo
    assert meta["universo_stock"]["incluido"] is True
    assert meta["universo_stock"]["skus"] == 1


def test_metadata_registra_las_exclusiones(catalogo_minimo):
    """Las filas del ERP que quedaron fuera quedan auditadas con su motivo."""
    _, meta = catalogo_minimo
    exclusiones = meta["exclusiones"]
    assert exclusiones.get("descontinuado_sin_guia_ni_stock", 0) >= 1
    # v3.6.0: el motivo "sin_precio" se reemplazo por "sin_precio_ni_movimiento"
    # (el precio ya no excluye si hay stock/guia/compromiso).
    assert "sin_precio" not in exclusiones
