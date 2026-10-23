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
    LINEA_GRUPO_A_CODIGO,
    PREFIJO_MARCA_A_CATEGORIA,
    categoria_de_producto,
    codigo_linea_crayola,
    decidir_inclusion,
    resolver_codigo_linea_grupo,
    taxonomias_crayola_nuevas,
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

    def test_prefijo_crayola_con_digito_no_es_linea_valida(self):
        """'C0150' no define la linea 'C0': cae a la linea real del ERP."""
        assert codigo_linea_crayola("C0150") == ""
        assert codigo_linea_crayola("CA001") == "CA"
        assert codigo_linea_crayola("CG990") == "CG"

    def test_sub_marca_crayola_nueva_se_declara_sola(self):
        """Una sub-marca nueva (CH) se publica como REPRESENTADAS.

        Si no se declarara, el consumidor que resuelva linea -> categoria la
        dejaria en el default (OTROS) y el SKU quedaria con linea y
        categoria incoherentes.
        """
        productos = [
            {"sku": "CH990", "linea": "CH"},
            {"sku": "CG990", "linea": "CG"},
            {"sku": "CA001", "linea": "CA"},
            {"sku": "X001", "linea": "78"},
        ]
        nuevos = taxonomias_crayola_nuevas(productos)
        assert nuevos == {"CH": "REPRESENTADAS"}
        # Las sub-marcas ya conocidas (CA..CG) no se redeclaran.
        assert "CG" not in nuevos
        assert "CA" not in nuevos

    def test_categoria_de_crayola_no_depende_de_la_linea(self):
        """La marca manda: un C* en linea generica sigue siendo REPRESENTADAS."""
        assert categoria_de_producto("CG990", "77") == "REPRESENTADAS"
        assert categoria_de_producto("CB999", "76") == "REPRESENTADAS"
        assert categoria_de_producto("CA001", "") == "REPRESENTADAS"

    def test_grupo_pinceles_es_estable_en_ambas_cajas(self):
        """La regla de negocio no depende de mayusculas/minusculas."""
        assert resolver_codigo_linea_grupo("ACCESORIOS", "PINCELES") == "CD"
        assert resolver_codigo_linea_grupo("accesorios", "pinceles") == "CD"

    def test_inclusion_sin_precio_entra_si_hay_producto(self):
        """v3.6.0: sin precio pero con stock/guia se publica (no cotizable)."""
        assert decidir_inclusion(False, False, 0.0, "PINTURA", True, True) == (
            True,
            False,
        )
        assert decidir_inclusion(False, False, 0.0, "CA001", True, True) == (
            True,
            False,
        )
        # Sin ningun movimiento ni guia, sigue fuera.
        assert decidir_inclusion(False, False, 0.0, "CA001", False, False) == (
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
        """La linea CD es SOLO Crayola (ACCESORIOS+PINCELES): ningun no-Crayola
        ni tijera debe caer ahi. Los CD* son Crayola y van a REPRESENTADAS."""
        d = self._catalogo()
        cds = [p for p in d["productos"] if str(p.get("linea")) == "CD"]
        assert cds, "debe haber SKUs en CD (los pinceles Crayola)"
        for p in cds:
            assert p["sku"].upper().startswith("C"), f"{p['sku']} no es Crayola"
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
        """Cada prefijo Crayola (CA, CB, CC, CD, CE, CF) es una linea propia
        dentro de REPRESENTADAS. Las lineas ERP originales (72, 76, 77, 79)
        quedan 100% VINIFAN sin contaminacion."""
        d = self._catalogo()
        por_linea = defaultdict(Counter)
        for p in d["productos"]:
            por_linea[str(p["linea"])][str(p["categoria"])] += 1
        # Lineas Crayola: cada una 100% REPRESENTADAS
        for cod in ("CA", "CB", "CC", "CD", "CE", "CF"):
            assert por_linea[cod]["REPRESENTADAS"] > 0, cod
            assert "VINIFAN" not in por_linea[cod], f"{cod} no debe tener VINIFAN"
        # Lineas ERP originales: 100% VINIFAN (los C* se fueron a sus lineas propias)
        for cod in ("72", "76", "77", "79"):
            assert por_linea[cod]["VINIFAN"] > 0, cod
            assert "REPRESENTADAS" not in por_linea[cod], (
                f"{cod} no debe tener REPRESENTADAS"
            )
        # Linea 85: REPRESENTADAS puras (no-Crayola)
        assert por_linea["85"]["REPRESENTADAS"] > 0
        # Todos los C* en REPRESENTADAS
        c_skus = [p for p in d["productos"] if p["sku"].upper().startswith("C")]
        assert all(p["categoria"] == "REPRESENTADAS" for p in c_skus)
        # Ningun C* esta en VINIFAN
        assert all(p["categoria"] != "VINIFAN" for p in c_skus)
