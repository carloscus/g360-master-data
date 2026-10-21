#!/usr/bin/env python3
"""
Tests de ROBUSTEZ y REGRESION de la taxonomia de linea/marca.

Objetivo: que un PROCESO NUEVO (una linea nueva, una marca nueva, un grupo
nuevo dentro de una linea ambigua) no rompa la generacion ni mal-clasifique
en silencio. Los casos borde deben ser predecibles y fail-safe.

Ejecutar: python -m pytest scripts/tests/test_taxonomia_robustez.py -v
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from generar_catalogo_base import (  # noqa: E402
    CATEGORIA_DEFAULT,
    LINEA_GRUPO_A_CODIGO,
    LINEA_NOMBRE_A_CODIGO,
    PREFIJO_MARCA_A_CATEGORIA,
    asignar_categoria,
    categoria_de_producto,
    decidir_inclusion,
    resolver_codigo_linea_grupo,
)

RUTA_CATALOGO = (
    Path(__file__).parent.parent.parent / "output" / "catalogo_productos.json"
)


class TestProcesosNuevos:
    """Un proceso nuevo no debe romper ni mal-clasificar (fail-safe).

    'Proceso nuevo' = linea que aun no existe en el mapa, marca con prefijo
    nuevo, grupo nuevo dentro de una linea ambigua.
    """

    def test_linea_nueva_cae_en_otros_sin_romper(self):
        """Una linea desconocida no revienta: codigo vacio -> categoria vacia."""
        assert resolver_codigo_linea_grupo("LINEA NUEVA", "GRUPO X") == ""
        assert categoria_de_producto("99999", "") == ""

    def test_linea_nueva_con_codigo_embebido(self):
        """'01ZZ - LINEA NUEVA' conserva su codigo aunque el nombre sea nuevo."""
        assert resolver_codigo_linea_grupo("01ZZ - LINEA NUEVA", "") == "ZZ"

    def test_marca_crayola_con_prefijo_nuevo(self):
        """CG (aun inexistente) ya se reconoce como Crayola por el prefijo C."""
        assert categoria_de_producto("CG999", "77") == "REPRESENTADAS"

    def test_marca_desconocida_usa_la_linea(self):
        """Un prefijo de marca no registrado no inventa categoria: usa la linea."""
        assert categoria_de_producto("X001", "78") == "VINIFAN"

    def test_grupo_nuevo_en_linea_ambigua_va_al_default(self):
        """ACCESORIOS + grupo no mapeado -> 79 (fail-safe, nunca CD)."""
        assert resolver_codigo_linea_grupo("ACCESORIOS", "BROCHES") == "79"
        assert resolver_codigo_linea_grupo("ACCESORIOS", "") == "79"

    def test_grupo_pinceles_es_estable_en_ambas_cajas(self):
        """La regla de negocio no depende de mayusculas/minusculas."""
        assert resolver_codigo_linea_grupo("ACCESORIOS", "PINCELES") == "CD"
        assert resolver_codigo_linea_grupo("accesorios", "pinceles") == "CD"

    def test_inclusion_sin_precio_siempre_fuera(self):
        """Sin precio no se publica, aunque tenga BX y stock (regla absoluta)."""
        assert decidir_inclusion(False, False, 0.0, "PINTURA", True, True) == (
            False,
            False,
        )
        assert decidir_inclusion(False, False, 0.0, "CA001", True, True) == (
            False,
            False,
        )

    def test_inclusion_descontinuado_entra_si_aporta(self):
        """Un descontinuado sin BX ni stock queda fuera; con stock o BX entra."""
        assert decidir_inclusion(False, True, 10.0, "PINTURA", False, False) == (
            False,
            False,
        )
        assert decidir_inclusion(False, True, 10.0, "PINTURA", False, True) == (
            True,
            True,
        )
        assert decidir_inclusion(False, True, 10.0, "PINTURA", True, False) == (
            True,
            True,
        )

    def test_inactivo_siempre_fuera(self):
        assert decidir_inclusion(True, False, 10.0, "PINTURA", True, True) == (
            False,
            False,
        )


class TestConsistenciaTaxonomia:
    """Los mapas deben ser coherentes entre si (sin reglas contradictorias)."""

    def test_sin_reglas_de_grupo_contradictorias(self):
        vistos = {}
        for clave, cod in LINEA_GRUPO_A_CODIGO.items():
            assert clave not in vistos or vistos[clave] == cod, clave
            vistos[clave] = cod

    def test_codigos_de_grupo_son_2_chars(self):
        for cod in LINEA_GRUPO_A_CODIGO.values():
            assert len(str(cod)) == 2, cod

    def test_prefijos_de_marca_no_vacios(self):
        assert PREFIJO_MARCA_A_CATEGORIA
        for pref in PREFIJO_MARCA_A_CATEGORIA:
            assert pref and pref == pref.upper(), pref

    def test_nombre_no_ambiguo_nunca_resuelve_por_grupo(self):
        """Un grupo solo desempata cuando el NOMBRE designa a mas de una linea."""
        assert resolver_codigo_linea_grupo("PINTURA", "PINCELES") == "77"
        assert resolver_codigo_linea_grupo("ARCHIVO", "TIJERAS") == "78"

    def test_resolver_y_categoria_son_idempotentes(self):
        assert resolver_codigo_linea_grupo(
            "ACCESORIOS", "PINCELES"
        ) == resolver_codigo_linea_grupo("ACCESORIOS", "PINCELES")
        assert categoria_de_producto("CA001", "77") == categoria_de_producto(
            "CA001", "77"
        )


@pytest.mark.skipif(not RUTA_CATALOGO.exists(), reason="catalogo no generado")
class TestCatalogoRealSinRegresion:
    """Regresiones sobre el catalogo GENERADO (integridad de los datos)."""

    @staticmethod
    def _catalogo():
        return json.loads(RUTA_CATALOGO.read_text(encoding="utf-8"))

    def test_ninguna_tijera_cae_en_linea_cd(self):
        """La linea CD es SOLO Crayola: ninguna tijera debe caer ahi."""
        d = self._catalogo()
        cds = [p for p in d["productos"] if str(p.get("linea")) == "CD"]
        assert cds, "deberia haber SKUs en CD"
        for p in cds:
            assert "TIJERA" not in str(p.get("nombre", "")).upper(), p["sku"]

    def test_ningun_crayola_cae_en_linea_79(self):
        """La linea 79 es VINIFAN: ningun producto Crayola debe quedar ahi."""
        d = self._catalogo()
        p79 = [p for p in d["productos"] if str(p.get("linea")) == "79"]
        for p in p79:
            assert "CRAYOLA" not in str(p.get("nombre", "")).upper(), p["sku"]

    def test_todo_sku_prefijo_c_es_representadas(self):
        """Invariante de marca: ningun C* (Crayola) puede ser VINIFAN."""
        d = self._catalogo()
        for p in d["productos"]:
            if str(p.get("sku", "")).upper().startswith("C"):
                assert p.get("categoria") == "REPRESENTADAS", (
                    p["sku"],
                    p.get("categoria"),
                )

    def test_linea_y_categoria_no_estan_vacias(self):
        """Ningun producto publicado puede quedar sin linea ni categoria."""
        d = self._catalogo()
        for p in d["productos"]:
            assert str(p.get("linea", "")).strip(), p["sku"]
            assert str(p.get("categoria", "")).strip(), p["sku"]

    def test_metadata_expone_la_desambiguacion(self):
        """Los consumidores deben poder leer la regla desde el metadata."""
        d = self._catalogo()
        meta = d["metadata"]
        assert meta.get("lineas_grupo_a_codigo", {}).get("ACCESORIOS|PINCELES") == "CD"
        assert "lineas_nombre_a_codigo" in meta
        assert "categorias_por_linea" in meta

    def test_metadata_afirma_que_la_marca_manda(self):
        """No podemos publicar una categoria por linea que contradiga la marca.

        La linea 77 se mapea a VINIFAN por linea, pero sus SKUs C* deben ser
        REPRESENTADAS: el catalogo debe tener ambos (marca > linea).
        """
        d = self._catalogo()
        por_linea = defaultdict(Counter)
        for p in d["productos"]:
            por_linea[str(p["linea"])][str(p["categoria"])] += 1
        # 77 = PINTURA: VINIFAN (propio) + REPRESENTADAS (Crayola)
        assert por_linea["77"]["VINIFAN"] > 0
        assert por_linea["77"]["REPRESENTADAS"] > 0
