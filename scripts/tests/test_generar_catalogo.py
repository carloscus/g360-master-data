#!/usr/bin/env python3
"""
Tests unitarios para G360 Catalog Generator v3.1
Ejecutar: python -m pytest scripts/tests/ -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generar_catalogo_base import (
    decidir_inclusion,
    generar_nombre_corto,
    generar_keywords,
    generar_output,
    _safe_float,
    _clean_ean,
    _extraer_codigo_linea,
    asignar_categoria,
    LINEA_A_CATEGORIA,
    LINEA_NOMBRE_A_CODIGO,
    CATEGORIA_POR_LINEA,
)


class TestGenerarNombreCorto:
    def test_elimina_pelota_al_inicio(self):
        assert generar_nombre_corto("PELOTA FUTBOL PERU") == "Futbol Peru"
        assert generar_nombre_corto("PELOTA DE PVC VOLEY") == "Voley"

    def test_elimina_materiales(self):
        assert generar_nombre_corto("FUTBOL GOMA FREE") == "Futbol Free"
        assert generar_nombre_corto("VOLEY CUERO COSIDO") == "Voley Cosido"
        assert generar_nombre_corto("BASQUET PVC AZUL") == "Basquet Azul"
        assert generar_nombre_corto("FUTBOL PU FUTURE") == "Futbol Future"

    def test_elimina_marcas(self):
        assert generar_nombre_corto("CRAYONES VINIFAN DELGADO") == "Crayones Delgado"
        assert generar_nombre_corto("FORRO VINIFANCITO CRISTAL") == "Forro Cristal"
        assert generar_nombre_corto("LAPIZ VFAN TRIANGULAR") == "Lapiz Triangular"

    def test_elimina_n_sola(self):
        assert generar_nombre_corto("N DEPORTIVA FUTBOL") == "Deportiva Futbol"

    def test_combina_reglas(self):
        assert generar_nombre_corto("PELOTA DE PVC SEMIDEPORTIVA VOLEY STITCH") == "Semideportiva Voley Stitch"

    def test_vacio_retorna_vacio(self):
        assert generar_nombre_corto("") == ""
        assert generar_nombre_corto(None) == ""

    def test_capitaliza_correctamente(self):
        assert generar_nombre_corto("futbol peru") == "Futbol Peru"


class TestSafeFloat:
    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0
        assert _safe_float(None, 5.0) == 5.0

    def test_empty_string_returns_default(self):
        assert _safe_float("") == 0.0

    def test_valid_number(self):
        assert _safe_float(42) == 42.0
        assert _safe_float("3.14") == 3.14
        assert _safe_float(0) == 0.0

    def test_text_returns_default(self):
        assert _safe_float("N/A") == 0.0
        assert _safe_float("PENDIENTE") == 0.0


class TestCleanEan:
    def test_empty_values(self):
        assert _clean_ean("") == ""
        assert _clean_ean("0") == ""
        assert _clean_ean(None) == ""

    def test_valid_ean(self):
        assert _clean_ean("7754807167277") == "7754807167277"

    def test_float_serialized(self):
        assert _clean_ean("7754807167277.0") == "7754807167277"

    def test_strips_spaces(self):
        assert _clean_ean("  7754807167277  ") == "7754807167277"


class TestGenerarKeywords:
    def test_basic_keywords(self):
        kw = generar_keywords("FUTBOL PU FUTURE #5", "PELOTAS", "VINIBALL")
        assert "FUTBOL" in kw
        assert "FUTURE" in kw
        assert "PELOTAS" in kw
        assert "VINIBALL" in kw
        assert "#" not in kw

    def test_short_words_excluded(self):
        kw = generar_keywords("A BB CCC", "", "")
        assert "A" not in kw
        assert "BB" not in kw
        assert "CCC" in kw

    def test_empty_inputs(self):
        assert generar_keywords("", "", "") == []

    def test_sorted_output(self):
        kw = generar_keywords("ZULU ALFA BRAVO", "", "")
        assert kw == sorted(kw)


class TestDecidirInclusion:
    """Regla: vigente ERP entra; descontinuado solo si está en SKU_BX."""

    def test_vigente_entra(self):
        assert decidir_inclusion(False, False, 10.0, "PELOTAS", False) == (True, False)

    def test_descontinuado_en_bx_entra_marcado(self):
        assert decidir_inclusion(False, True, 3.36, "ACCESORIOS", True) == (True, True)

    def test_descontinuado_fuera_bx_se_excluye(self):
        assert decidir_inclusion(False, True, 3.36, "ACCESORIOS", False) == (False, False)

    def test_inactivo_siempre_fuera(self):
        assert decidir_inclusion(True, False, 10.0, "PELOTAS", True) == (False, False)
        assert decidir_inclusion(True, True, 10.0, "PELOTAS", True) == (False, False)

    def test_sin_precio_siempre_fuera(self):
        assert decidir_inclusion(False, False, 0.0, "PELOTAS", True) == (False, False)
        assert decidir_inclusion(False, True, 0.0, "PELOTAS", True) == (False, False)

    def test_linea_proceso_siempre_fuera(self):
        assert decidir_inclusion(False, False, 10.0, "PRODUCTOS EN PROCESO", True) == (False, False)
        assert decidir_inclusion(False, True, 10.0, "PRODUCTOS EN PROCESO", True) == (False, False)


def _prod(sku, descontinuado=False, linea="PELOTAS"):
    return {
        "sku": sku, "nombre": f"Producto {sku}", "ean13": "", "ean14": "",
        "peso_kg": 0.1, "linea": linea, "grupo": "G", "tipo": "T",
        "familia": "F", "categoria": "VINIBALL", "precio": 10.0,
        "descontinuado": descontinuado,
        "linea_codigo": LINEA_NOMBRE_A_CODIGO.get(linea.upper(), ""),
    }


class TestGenerarOutputDescontinuado:
    def test_marca_y_cuenta_descontinuados(self, tmp_path):
        out = tmp_path / "cat.json"
        res = generar_output(
            [_prod("A"), _prod("B", True)], {}, {}, {}, str(out))
        prods = {p["sku"]: p for p in res["productos"]}
        assert prods["A"]["descontinuado"] is False
        assert prods["B"]["descontinuado"] is True
        assert res["metadata"]["estadisticas"]["descontinuados"] == 1
        assert res["metadata"]["total_productos"] == 2

    def test_linea_codigo_emitido(self, tmp_path):
        out = tmp_path / "cat.json"
        res = generar_output(
            [_prod("A", linea="ARCHIVO"), _prod("B", linea="MASCOTAS"),
             _prod("C", linea="LINEA INVENTADA")], {}, {}, {}, str(out))
        prods = {p["sku"]: p for p in res["productos"]}
        assert prods["A"]["linea_codigo"] == "78"
        assert prods["B"]["linea_codigo"] == "MA"
        assert prods["C"]["linea_codigo"] == ""
        assert res["metadata"]["estadisticas"]["sin_linea_codigo"] == 1


class TestLineaNombreACodigo:
    def test_codigos_conocidos(self):
        assert LINEA_NOMBRE_A_CODIGO["PELOTAS"] == "01"
        assert LINEA_NOMBRE_A_CODIGO["ARCHIVO"] == "78"
        assert LINEA_NOMBRE_A_CODIGO["MASCOTAS"] == "MA"
        assert LINEA_NOMBRE_A_CODIGO["ACCESORIOS"] == "79"


class TestLineaACategoria:
    def test_known_lines(self):
        assert LINEA_A_CATEGORIA["PELOTAS"] == "VINIBALL"
        assert LINEA_A_CATEGORIA["ARCHIVO"] == "VINIFAN"
        assert LINEA_A_CATEGORIA["REPRESENTADAS"] == "REPRESENTADAS"

    def test_all_vinifan_lines(self):
        # MANUALIDADES (CE) y SET (CF) son lineas 100% Crayola -> REPRESENTADAS
        vinifan = [
            "ARCHIVO", "FORROS", "ESCRITURA", "PINTURA", "DIBUJO",
            "DIDACTICOS", "PEGAMENTOS", "ACCESORIOS",
            "METALICA", "SENSORIALES",
        ]
        representadas = ["MANUALIDADES", "SET"]
        for linea in vinifan:
            assert LINEA_A_CATEGORIA[linea] == "VINIFAN"
        for linea in representadas:
            assert LINEA_A_CATEGORIA[linea] == "REPRESENTADAS"

    def test_categorias_operativas_no_caen_en_representadas(self):
        """v3.3: las lineas operativas ya no se disfrazan de REPRESENTADAS."""
        assert LINEA_A_CATEGORIA["PRODUCTOS INDUSTRIALES"] == "INDUSTRIAL"
        assert LINEA_A_CATEGORIA["CIPTECH ETIQUETAS"] == "CIPTECH"
        assert LINEA_A_CATEGORIA["MATERIA PRIMA"] == "MATERIALES"
        assert LINEA_A_CATEGORIA["OTROS"] == "VINIBALL"

    def test_mapa_por_codigo_es_la_fuente(self):
        """El mapa por nombre se deriva del canónico por código."""
        for nombre, codigo in LINEA_NOMBRE_A_CODIGO.items():
            assert LINEA_A_CATEGORIA[nombre] == asignar_categoria(codigo)


class TestTaxonomiaCanonica:
    def test_asignar_categoria_por_codigo(self):
        assert asignar_categoria("78") == "VINIFAN"
        assert asignar_categoria("01") == "VINIBALL"
        assert asignar_categoria("20") == "INDUSTRIAL"
        assert asignar_categoria("30") == "CIPTECH"
        assert asignar_categoria("XX") == "OTROS"
        assert asignar_categoria("") == ""

    def test_asignar_categoria_tolera_formato_compuesto(self):
        assert asignar_categoria("78 - ARCHIVO") == "VINIFAN"

    def test_toda_linea_del_maestro_tiene_categoria(self):
        """Ninguna linea del maestro se queda sin clasificar."""
        sin_cat = [
            nombre
            for nombre, codigo in LINEA_NOMBRE_A_CODIGO.items()
            if not asignar_categoria(codigo)
        ]
        assert sin_cat == []

    def test_extraer_codigo_linea_formatos(self):
        assert _extraer_codigo_linea("0178 - ARCHIVO") == "78"
        assert _extraer_codigo_linea("01MA - MASCOTAS") == "MA"
        assert _extraer_codigo_linea("78") == "78"
        assert _extraer_codigo_linea("PELOTAS") == ""
        assert _extraer_codigo_linea("") == ""


class TestInclusionConStock:
    def test_sku_descontinuado_con_stock_entra_marcado(self):
        """Hay carga que hacer: un descontinuado con stock entra marcado."""
        assert decidir_inclusion(False, True, 3.0, "ARCHIVO", False, True) == (True, True)

    def test_sku_vigente_con_stock_entra(self):
        assert decidir_inclusion(False, False, 3.0, "ARCHIVO", False, True) == (True, False)

    def test_sku_descontinuado_sin_stock_sigue_fuera(self):
        assert decidir_inclusion(False, True, 3.0, "ARCHIVO", False, False) == (False, False)

    def test_sku_sin_precio_sigue_fuera_aunque_haya_stock(self):
        """Regla absoluta: sin precio no se publica (se mantiene de v3.2)."""
        assert decidir_inclusion(False, False, 0.0, "ARCHIVO", False, True) == (False, False)
        assert decidir_inclusion(False, True, 0.0, "ARCHIVO", True, True) == (False, False)

    def test_inactivo_siempre_fuera_incluso_con_stock(self):
        assert decidir_inclusion(True, False, 10.0, "ARCHIVO", True, True) == (False, False)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
