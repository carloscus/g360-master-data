#!/usr/bin/env python3
"""
Tests unitarios para G360 Catalog Generator v3
Ejecutar: python -m pytest scripts/tests/ -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generar_catalogo_base import (
    generar_nombre_corto,
    generar_keywords,
    _safe_float,
    _clean_ean,
    LINEA_A_CATEGORIA,
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


class TestLineaACategoria:
    def test_known_lines(self):
        assert LINEA_A_CATEGORIA["PELOTAS"] == "VINIBALL"
        assert LINEA_A_CATEGORIA["ARCHIVO"] == "VINIFAN"
        assert LINEA_A_CATEGORIA["REPRESENTADAS"] == "REPRESENTADAS"

    def test_all_vinifan_lines(self):
        for linea in ["ARCHIVO", "FORROS", "ESCRITURA", "PINTURA", "DIBUJO",
                       "DIDACTICOS", "MANUALIDADES", "PEGAMENTOS", "ACCESORIOS",
                       "METALICA", "SENSORIALES", "KITS"]:
            assert LINEA_A_CATEGORIA[linea] == "VINIFAN"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
