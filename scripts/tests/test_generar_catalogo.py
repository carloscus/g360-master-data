#!/usr/bin/env python3
"""
Tests unitarios para G360 Catalog Generator v3.1
Ejecutar: python -m pytest scripts/tests/ -v
"""

import json
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
    categoria_venta,
    nombre_sin_codigo,
    productos_desde_universo,
    leer_universo_stock,
    _agregar_universo,
    LINEA_A_CATEGORIA,
    LINEA_NOMBRE_A_CODIGO,
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
        assert (
            generar_nombre_corto("PELOTA DE PVC SEMIDEPORTIVA VOLEY STITCH")
            == "Semideportiva Voley Stitch"
        )

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
    """Regla v3.6.0: guía ∨ stock ∨ compromiso ∨ (vigente ∧ precio > 0)."""

    def test_vigente_entra(self):
        assert decidir_inclusion(False, False, 10.0, "PELOTAS", False) == (True, False)

    def test_descontinuado_en_bx_entra_marcado(self):
        assert decidir_inclusion(False, True, 3.36, "ACCESORIOS", True) == (True, True)

    def test_descontinuado_fuera_bx_se_excluye(self):
        assert decidir_inclusion(False, True, 3.36, "ACCESORIOS", False) == (
            False,
            False,
        )

    def test_inactivo_siempre_fuera(self):
        assert decidir_inclusion(True, False, 10.0, "PELOTAS", True) == (False, False)
        assert decidir_inclusion(True, True, 10.0, "PELOTAS", True) == (False, False)

    def test_sin_precio_en_guia_entra_no_cotizable(self):
        """El precio decide la COTIZABILIDAD, no la presencia (v3.6.0)."""
        assert decidir_inclusion(False, False, 0.0, "PELOTAS", True) == (True, False)
        assert decidir_inclusion(False, True, 0.0, "PELOTAS", True) == (True, True)

    def test_sin_precio_ni_movimiento_queda_fuera(self):
        assert decidir_inclusion(False, False, 0.0, "PELOTAS", False) == (False, False)
        assert decidir_inclusion(False, True, 0.0, "PELOTAS", False) == (False, False)

    def test_linea_proceso_siempre_fuera(self):
        assert decidir_inclusion(False, False, 10.0, "PRODUCTOS EN PROCESO", True) == (
            False,
            False,
        )
        assert decidir_inclusion(False, True, 10.0, "PRODUCTOS EN PROCESO", True) == (
            False,
            False,
        )


def _prod(sku, descontinuado=False, linea="PELOTAS"):
    return {
        "sku": sku,
        "nombre": f"Producto {sku}",
        "ean13": "",
        "ean14": "",
        "peso_kg": 0.1,
        "linea": linea,
        "grupo": "G",
        "tipo": "T",
        "familia": "F",
        "categoria": "VINIBALL",
        "precio": 10.0,
        "descontinuado": descontinuado,
        "linea_codigo": LINEA_NOMBRE_A_CODIGO.get(linea.upper(), ""),
    }


class TestGenerarOutputDescontinuado:
    def test_marca_y_cuenta_descontinuados(self, tmp_path):
        out = tmp_path / "cat.json"
        res = generar_output([_prod("A"), _prod("B", True)], {}, {}, {}, str(out))
        prods = {p["sku"]: p for p in res["productos"]}
        assert prods["A"]["descontinuado"] is False
        assert prods["B"]["descontinuado"] is True
        assert res["metadata"]["estadisticas"]["descontinuados"] == 1
        assert res["metadata"]["total_productos"] == 2

    def test_linea_codigo_emitido(self, tmp_path):
        out = tmp_path / "cat.json"
        res = generar_output(
            [
                _prod("A", linea="ARCHIVO"),
                _prod("B", linea="MASCOTAS"),
                _prod("C", linea="LINEA INVENTADA"),
            ],
            {},
            {},
            {},
            str(out),
        )
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
            "ARCHIVO",
            "FORROS",
            "ESCRITURA",
            "PINTURA",
            "DIBUJO",
            "DIDACTICOS",
            "PEGAMENTOS",
            "ACCESORIOS",
            "METALICA",
            "SENSORIALES",
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
        assert decidir_inclusion(False, True, 3.0, "ARCHIVO", False, True) == (
            True,
            True,
        )

    def test_sku_vigente_con_stock_entra(self):
        assert decidir_inclusion(False, False, 3.0, "ARCHIVO", False, True) == (
            True,
            False,
        )

    def test_sku_descontinuado_sin_stock_sigue_fuera(self):
        assert decidir_inclusion(False, True, 3.0, "ARCHIVO", False, False) == (
            False,
            False,
        )

    def test_sku_sin_precio_entra_con_stock_pero_no_cotiza(self, tmp_path):
        """v3.6.0: hay producto fisico -> se publica; sin precio -> por_activar."""
        assert decidir_inclusion(False, False, 0.0, "ARCHIVO", False, True) == (
            True,
            False,
        )
        assert decidir_inclusion(False, True, 0.0, "ARCHIVO", True, True) == (
            True,
            True,
        )

        out = tmp_path / "cat.json"
        prod = _prod("SINPRECIO")
        prod["precio"] = 0.0
        prod["origen"] = "s1"
        res = generar_output(
            [prod],
            {},
            {},
            {},
            str(out),
            universo={"SINPRECIO": {"stock": 4, "predespacho": 0, "linea": ""}},
        )
        p = res["productos"][0]
        assert p["cotizable"] is False
        assert p["por_activar"] is True
        assert p["stock_snapshot"] == 4

    def test_sku_con_compromiso_sin_stock_entra(self):
        """Un SKU con compromiso de venta y sin stock tambien debe estar."""
        assert decidir_inclusion(
            False,
            False,
            0.0,
            "ARCHIVO",
            False,
            tiene_stock=False,
            tiene_compromiso=True,
        ) == (True, False)

    def test_inactivo_siempre_fuera_incluso_con_stock(self):
        assert decidir_inclusion(True, False, 10.0, "ARCHIVO", True, True) == (
            False,
            False,
        )


class TestNombreSinCodigo:
    def test_quita_el_codigo_del_reporte_s1(self):
        assert nombre_sin_codigo("03 - BORRADOR") == "BORRADOR"
        assert nombre_sin_codigo("01 - RESALTADOR") == "RESALTADOR"
        assert nombre_sin_codigo("02 - BLANCO BLISTER") == "BLANCO BLISTER"

    def test_respeta_nombres_sin_codigo(self):
        assert nombre_sin_codigo("FOLDER") == "FOLDER"
        assert nombre_sin_codigo("") == ""


class TestCategoriaVenta:
    def test_las_tres_categorias_de_negocio_se_mantienen(self):
        for cat in ("VINIBALL", "VINIFAN", "REPRESENTADAS"):
            assert categoria_venta(cat) == cat

    def test_el_resto_es_revision_de_venta(self):
        for cat in ("MATERIALES", "INDUSTRIAL", "CIPTECH", "PRODUCCION", "OTROS", ""):
            assert categoria_venta(cat) == "REVISION_VENTA"


class TestSinEnlacesPorParecido:
    """Los SKU son exactos: nada se enlaza por similitud de codigo o nombre.

    03077D NO es 03077 aunque se parezca: es otro producto, con su propia
    ficha. La linea 98 esta fuera del semaforo vendible, pero sus SKUs
    existen igual en el catalogo (visibles, por_activar, no cotizables).
    """

    def test_d_con_nombre_identico_no_genera_enlace(self, tmp_path):
        base = _prod("03077", linea="ARCHIVO")
        base["nombre"] = "FOLDER N VINIFAN FANTASIA OFICIO MIX SURTIDO"
        base["precio"] = 4.17
        base["linea"] = "78"
        base["linea_codigo"] = "78"
        derivado = _prod("03077D", linea="ARCHIVO")
        derivado["nombre"] = "FOLDER N VINIFAN TAPA FANTASIA OFICIO MIX SURTIDO"
        derivado["precio"] = 0.0
        derivado["linea"] = "98"
        derivado["linea_codigo"] = "98"
        derivado["categoria"] = "DESCARTE Y VARIOS"
        derivado["origen"] = "s1"

        universo = {
            "03077": {"stock": 100, "predespacho": 0, "linea": "0178 - ARCHIVO"},
            "03077D": {"stock": 7, "predespacho": 0, "linea": "0198 - SIN EMBALAJE"},
        }
        out = tmp_path / "cat.json"
        res = generar_output([base, derivado], {}, {}, {}, str(out), universo=universo)
        prod = {p["sku"]: p for p in res["productos"]}
        # Sin enlace: cada uno conserva su ficha intacta.
        assert prod["03077D"].get("derivado_de", "") == ""
        assert prod["03077D"]["linea"] == "98"
        assert prod["03077D"]["linea_codigo"] == "98"
        assert prod["03077D"]["categoria"] == "DESCARTE Y VARIOS"
        assert prod["03077D"]["precio"] == 0.0
        # Stock propio, sin fusionar.
        assert prod["03077"]["stock_snapshot"] == 100
        assert prod["03077D"]["stock_snapshot"] == 7
        # Sin precio propio: no cotiza (por_activar) aunque tenga stock.
        assert prod["03077D"]["cotizable"] is False
        assert prod["03077D"]["por_activar"] is True
        # Ningun enlace contado.
        assert res["metadata"]["estadisticas"]["derivados"] == 0

    def test_d_en_guia_no_hereda_nada(self, tmp_path):
        """Aunque el supuesto 'parecido' este en guia, no se copia nada."""
        base = _prod("03077", linea="ARCHIVO")
        base["nombre"] = "FOLDER N VINIFAN FANTASIA OFICIO MIX SURTIDO"
        base["peso_kg"] = 0.1
        otro = _prod("03077D", linea="ARCHIVO")
        otro["nombre"] = "FOLDER PLASTICO OFICIO TAPA TRANSPARENTE"
        otro["linea"] = "98"
        otro["linea_codigo"] = "98"
        otro["peso_kg"] = 0.5
        out = tmp_path / "cat.json"
        res = generar_output([base, otro], {}, {}, {}, str(out))
        prod = {p["sku"]: p for p in res["productos"]}
        assert prod["03077D"].get("derivado_de", "") == ""
        assert prod["03077D"]["ean13"] == ""
        assert prod["03077D"]["peso_kg"] == 0.5  # el suyo, no el de la base


class TestKardexIds:
    """El JSON publica los IDs KARDEX (grupo/tipo/familia) para que las apps
    filtren por jerarquia sin leer el KARDEX. Sin cruce no hay IDs (vacios,
    nunca inventados)."""

    def test_ids_del_cruce_quedan_en_producto(self, tmp_path):
        out = tmp_path / "cat.json"
        res = generar_output(
            [_prod("011019")],
            {},
            {},
            {},
            str(out),
            kardex_ids={
                "011019": {"grupo_id": "01", "tipo_id": "02", "familia_id": "01"}
            },
        )
        p = res["productos"][0]
        assert p["grupo_id"] == "01"
        assert p["tipo_id"] == "02"
        assert p["familia_id"] == "01"
        assert res["metadata"]["estadisticas"]["con_ids_jerarquia"] == 1

    def test_sin_cruce_ids_vacios(self, tmp_path):
        out = tmp_path / "cat.json"
        res = generar_output([_prod("ZZZ99")], {}, {}, {}, str(out))
        p = res["productos"][0]
        assert p["grupo_id"] == ""
        assert p["tipo_id"] == ""
        assert p["familia_id"] == ""
        assert res["metadata"]["estadisticas"]["con_ids_jerarquia"] == 0


class TestFichaDesdeUniverso:
    def test_arma_la_ficha_minima_con_lo_que_trae_s1(self):
        universo = {
            "S199001": {
                "stock": 40,
                "predespacho": 12,
                "descripcion": "CUADERNO ANILLADO A4",
                "um": "UND",
                "linea": "0178 - ARCHIVO",
                "grupo": "01 - CUADERNOS",
                "tipo": "02 - ANILLADO",
                "familia": "03 - A4",
            }
        }
        nuevos = productos_desde_universo(universo, [], {})
        assert len(nuevos) == 1
        p = nuevos[0]
        assert p["sku"] == "S199001"
        assert p["origen"] == "s1"
        assert p["precio"] == 0.0
        assert p["linea"] == "78"
        assert p["linea_codigo"] == "78"
        assert p["grupo"] == "CUADERNOS"
        assert p["tipo"] == "ANILLADO"
        assert p["familia"] == "A4"
        assert p["um"] == "UND"
        assert p["categoria"] == "VINIFAN"

    def test_no_duplica_ni_publica_lineas_de_proceso(self):
        universo = {
            "YA_ESTA": {"stock": 1, "descripcion": "X", "linea": "0178 - ARCHIVO"},
            "PROC001": {
                "stock": 1,
                "descripcion": "MATERIA EN PROCESO",
                "linea": "0171 - PRODUCTOS EN PROCESO CIPTECH",
            },
        }
        incluidos = [{"sku": "YA_ESTA"}]
        nuevos = productos_desde_universo(universo, incluidos, {})
        assert nuevos == []

    def test_sin_taxonomia_en_s1_cae_a_otros_no_a_vacio(self):
        """Si S1 no trae linea/grupo (p.ej. un D huerfano como 03273D en el
        universo en vivo), la ficha sale en OTROS, nunca con linea vacia
        (rompe filtros y el contrato del API)."""
        universo = {
            "03273D": {
                "stock": 5,
                "predespacho": 0,
                "descripcion": "FOLDER N VINIFAN FANTASIA",
                "um": "UND",
                "linea": "",
                "grupo": "",
                "tipo": "",
                "familia": "",
            }
        }
        nuevos = productos_desde_universo(universo, [], {})
        assert len(nuevos) == 1
        p = nuevos[0]
        assert p["linea"] == "OTROS"
        assert p["linea_codigo"] == "OTROS"
        assert p["categoria"] == "OTROS"


class TestCobertura:
    def test_universo_completo_no_deja_faltantes(self, tmp_path):
        universo = {
            "A": {"stock": 3, "predespacho": 0, "linea": "0178 - ARCHIVO"},
            "B": {"stock": 0, "predespacho": 2, "linea": "0178 - ARCHIVO"},
        }
        out = tmp_path / "cat.json"
        res = generar_output(
            [_prod("A"), _prod("B")], {}, {}, {}, str(out), universo=universo
        )
        meta = res["metadata"]
        assert meta["cobertura_faltante"] == []
        assert meta["universo_skus"] == ["A", "B"]

    def test_detecta_un_sku_con_stock_fuera_del_catalogo(self, tmp_path, capsys):
        universo = {
            "A": {"stock": 3, "predespacho": 0, "linea": "0178 - ARCHIVO"},
            "HUERFANO": {"stock": 9, "predespacho": 0, "linea": "0178 - ARCHIVO"},
        }
        out = tmp_path / "cat.json"
        res = generar_output([_prod("A")], {}, {}, {}, str(out), universo=universo)
        assert res["metadata"]["cobertura_faltante"] == ["HUERFANO"]
        assert "HUERFANO" in capsys.readouterr().out

    def test_las_lineas_de_proceso_no_cuentan_para_la_cobertura(self, tmp_path):
        universo = {
            "A": {"stock": 3, "predespacho": 0, "linea": "0178 - ARCHIVO"},
            "PROC": {
                "stock": 50,
                "predespacho": 0,
                "linea": "0171 - PRODUCTOS EN PROCESO CIPTECH",
            },
        }
        out = tmp_path / "cat.json"
        res = generar_output([_prod("A")], {}, {}, {}, str(out), universo=universo)
        assert res["metadata"]["cobertura_faltante"] == []
        assert "PROC" not in res["metadata"]["universo_skus"]


class _Respuesta:
    """Respuesta minima de requests para monkeypatch."""

    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")


class TestUniversoStock:
    """La cobertura del catalogo depende de leer bien el universo de stock.

    Un fallo silencioso aca no rompe el catalogo: lo deja incompleto (y el
    inventario con despacho queda sin precio, peso ni caja).
    """

    def test_usa_el_endpoint_compacto(self, monkeypatch):
        import requests

        llamadas = []

        def fake_get(url, **kw):
            llamadas.append(url)
            return _Respuesta(
                200,
                {
                    "items": [
                        {
                            "sku": "A",
                            "stock": 10,
                            "predespacho": 2,
                            "descripcion": "PRODUCTO A",
                            "um": "UND",
                            "linea": "0178 - ARCHIVO",
                            "grupo": "FOLDER",
                            "tipo": "OFICIO",
                            "familia": "A4",
                        },
                        {"sku": "B", "stock": 0, "predespacho": 5},
                    ]
                },
            )

        monkeypatch.setattr(requests, "get", fake_get)
        universo, error = leer_universo_stock(
            api_url="http://api.local", api_key="k", intentos=1
        )
        assert error == ""
        assert llamadas == ["http://api.local/api/v1/stock/skus"]
        assert universo["A"]["stock"] == 10
        assert universo["A"]["predespacho"] == 2
        assert universo["A"]["familia"] == "A4"
        assert universo["B"]["predespacho"] == 5

    def test_cae_al_endpoint_pesado_si_no_hay_compacto(self, monkeypatch):
        import requests

        llamadas = []

        def fake_get(url, **kw):
            llamadas.append(url)
            if url.endswith("/api/v1/stock/skus"):
                return _Respuesta(404, {"detail": "Not Found"})
            return _Respuesta(
                200,
                {
                    "items": [
                        {
                            "sku": "A",
                            "almacenes": [
                                {"almacen": "VES", "stock": 4, "predespacho": 1},
                                {"almacen": "40", "stock": 6, "predespacho": 2},
                            ],
                        }
                    ]
                },
            )

        monkeypatch.setattr(requests, "get", fake_get)
        universo, error = leer_universo_stock(
            api_url="http://api.local", api_key="k", intentos=1
        )
        assert error == ""
        assert len(llamadas) == 2
        assert llamadas[0].endswith("/api/v1/stock/skus")
        assert llamadas[1].endswith("/api/v1/stock")
        assert universo["A"]["stock"] == 10
        assert universo["A"]["predespacho"] == 3

    def test_lee_el_cache_local_del_s1(self, tmp_path):
        cache = tmp_path / "stock_cache.json"
        cache.write_text(
            json.dumps(
                {
                    "fecha_descarga": "2026-10-22T10:00:00",
                    "datos": {
                        "VES": {
                            "A": {
                                "stock": 7,
                                "predespacho": 1,
                                "descripcion": "PRODUCTO A",
                                "linea": "0178 - ARCHIVO",
                            }
                        },
                        "40": {"A": {"stock": 3, "predespacho": 0}},
                    },
                }
            ),
            encoding="utf-8",
        )
        universo, error = leer_universo_stock(cache_local=str(cache))
        assert error == ""
        assert universo["A"]["stock"] == 10
        assert universo["A"]["predespacho"] == 1
        assert universo["A"]["linea"] == "0178 - ARCHIVO"

    def test_cache_inexistente_devuelve_error(self, tmp_path):
        universo, error = leer_universo_stock(cache_local=str(tmp_path / "no.json"))
        assert universo == {}
        assert "no existe" in error

    def test_sin_clave_lo_dice(self, monkeypatch):
        monkeypatch.delenv("G360_STOCK_API_KEY", raising=False)
        monkeypatch.delenv("API_KEY", raising=False)
        universo, error = leer_universo_stock(
            api_url="http://api.local", api_key="", intentos=1
        )
        assert universo == {}
        assert "API_KEY" in error

    def test_agregar_universo_suma_almacenes(self):
        datos = {
            "VES": {
                "A": {"stock": 5, "predespacho": 2, "descripcion": "PRODUCTO A"},
            },
            "40": {
                "A": {"stock": 1, "predespacho": 0},
                "B": {"stock": 9, "predespacho": 0, "linea": "0178 - ARCHIVO"},
            },
        }
        universo = _agregar_universo(datos)
        assert universo["A"]["stock"] == 6
        assert universo["A"]["predespacho"] == 2
        assert universo["B"]["stock"] == 9
        assert universo["B"]["linea"] == "0178 - ARCHIVO"


class TestUmFallbackUniverso:
    """UM: ficha (S1-only) -> KARDEX (primaria) -> universo S1 (fallback
    para un SKU ERP que tenga stock y aun no exista en el KARDEX). Si
    ninguna fuente lo sabe, la UM queda vacia: no se inventa."""

    def test_kardex_gana_sobre_universo(self, tmp_path):
        res = generar_output(
            [_prod("A")],
            {},
            {},
            {},
            str(tmp_path / "cat.json"),
            um_kardex={"A": "KGR"},
            universo={"A": {"stock": 3, "predespacho": 0, "um": "UND"}},
        )
        p = res["productos"][0]
        assert p["um"] == "KGR"
        assert res["metadata"]["estadisticas"]["con_um"] == 1

    def test_universo_cubre_sku_erp_sin_kardex(self, tmp_path):
        res = generar_output(
            [_prod("B")],
            {},
            {},
            {},
            str(tmp_path / "cat.json"),
            um_kardex={},
            universo={"B": {"stock": 3, "predespacho": 0, "um": " pza "}},
        )
        p = res["productos"][0]
        assert p["um"] == "PZA"  # limpio y en mayusculas, como el resto
        assert res["metadata"]["estadisticas"]["con_um"] == 1

    def test_sin_fuente_um_vacia(self, tmp_path):
        res = generar_output([_prod("C")], {}, {}, {}, str(tmp_path / "cat.json"))
        p = res["productos"][0]
        assert p["um"] == ""
        assert res["metadata"]["estadisticas"]["con_um"] == 0


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
