#!/usr/bin/env python3
"""Tests del contrato de encabezados y de los lectores que lo usan.

Ejecutar: python -m pytest scripts/tests/test_contratos.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from contratos import (  # noqa: E402
    ALMACENES_S1,
    CONTRATO_ERP,
    CONTRATO_SKU_BX,
    Contrato,
    ErrorContrato,
    almacenes_fuera_de_lista,
    almacenes_publicados,
    calcular_m3,
    cargar_almacenes,
    cargar_guia_ignorados,
    detectar_columnas_s1,
    huella_fuente,
    limpiar_texto,
    normalizar_encabezado,
    resolver_columnas,
    sku_texto,
)
from validar_encabezados import (  # noqa: E402
    clasificar_guia,
    validar_guia_vs_maestros,
)


class TestNormalizarEncabezado:
    def test_acentos_y_caja(self):
        assert normalizar_encabezado("Artículo") == "ARTICULO"
        assert normalizar_encabezado("ARTÍCULO") == "ARTICULO"

    def test_espacios_nbsp_y_bom(self):
        assert normalizar_encabezado("\ufeff  COD \xa0 EAN  ") == "COD EAN"
        assert normalizar_encabezado("  SKU ") == "SKU"

    def test_vacio(self):
        assert normalizar_encabezado(None) == ""
        assert normalizar_encabezado("   ") == ""


class TestLimpiarTexto:
    def test_quita_bordes(self):
        assert limpiar_texto(" PELOTA \xa0") == "PELOTA"
        assert limpiar_texto(None) == ""

    def test_no_cambia_caja(self):
        assert limpiar_texto(" Viniball ") == "Viniball"


class TestSkuTexto:
    def test_conserva_ceros(self):
        assert sku_texto("016763") == "016763"

    def test_float_entero(self):
        assert sku_texto(16763.0) == "16763"

    def test_apostrofo_de_excel(self):
        assert sku_texto("'016763") == "016763"

    def test_bool_y_none(self):
        assert sku_texto(True) == ""
        assert sku_texto(None) == ""


class TestResolverColumnas:
    def test_mapea_por_nombre(self):
        columnas = resolver_columnas(
            [
                "CODIGO",
                "NOMBRE",
                "LINEA",
                "GRUPO",
                "PRECIO",
                "FLG_INACTIVO",
                "FLG_DESCONTINUADO",
            ],
            CONTRATO_ERP,
        )
        assert columnas.idx("sku") == 0
        assert columnas.idx("precio") == 4
        assert columnas.idx("inactivo") == 5

    def test_columnas_reordenadas(self):
        # El bug clasico: el export reordena y leer por posicion toma el peso
        # como precio. Por nombre, el mapeo sigue siendo correcto.
        columnas = resolver_columnas(
            [
                "PRECIO",
                "CODIGO",
                "FLG_DESCONTINUADO",
                "NOMBRE",
                "LINEA",
                "GRUPO",
                "FLG_INACTIVO",
            ],
            CONTRATO_ERP,
        )
        assert columnas.idx("precio") == 0
        assert columnas.idx("sku") == 1
        assert columnas.idx("nombre") == 3

    def test_alias(self):
        columnas = resolver_columnas(
            [
                "SKU",
                "DESCRIPCION",
                "LINEA",
                "GRUPO",
                "PRECIO_LISTA",
                "INACTIVO",
                "DESCONTINUADO",
            ],
            CONTRATO_ERP,
        )
        assert columnas.idx("sku") == 0
        assert columnas.idx("precio") == 4

    def test_falta_columna_requerida(self):
        with pytest.raises(ErrorContrato) as exc:
            resolver_columnas(
                ["CODIGO", "NOMBRE", "LINEA", "GRUPO", "FLG_INACTIVO"],
                CONTRATO_ERP,
            )
        texto = str(exc.value)
        assert "precio" in texto
        assert "se acepta" in texto
        assert "CODIGO" in texto
        assert "No se genero nada" in texto

    def test_duplicado_usa_primera_y_avisa(self):
        columnas = resolver_columnas(
            [
                "CODIGO",
                "NOMBRE",
                "LINEA",
                "GRUPO",
                "PRECIO",
                "FLG_INACTIVO",
                "FLG_DESCONTINUADO",
                "PRECIO",
            ],
            CONTRATO_ERP,
        )
        assert columnas.idx("precio") == 4
        assert any("duplicado" in a for a in columnas.avisos)

    def test_columna_de_mas_avisa(self):
        columnas = resolver_columnas(
            [
                "CODIGO",
                "NOMBRE",
                "LINEA",
                "GRUPO",
                "PRECIO",
                "FLG_INACTIVO",
                "FLG_DESCONTINUADO",
                "OBSERVACION",
            ],
            CONTRATO_ERP,
        )
        assert any("OBSERVACION" in a for a in columnas.avisos)

    def test_dos_campos_a_la_misma_columna(self):
        contrato = Contrato(
            fuente="test",
            requeridas={"a": ("X",), "b": ("X",)},
        )
        with pytest.raises(ErrorContrato) as exc:
            resolver_columnas(["X"], contrato)
        assert "misma columna" in str(exc.value)

    def test_alias_ambiguo_avisa(self):
        contrato = Contrato(
            fuente="test",
            requeridas={"a": ("X", "Y")},
        )
        columnas = resolver_columnas(["X", "Y"], contrato)
        assert columnas.idx("a") == 0
        assert any("ambiguo" in a for a in columnas.avisos)

    def test_opcional_ausente_se_informa(self):
        columnas = resolver_columnas(
            [
                "CODIGO",
                "NOMBRE",
                "LINEA",
                "GRUPO",
                "PRECIO",
                "FLG_INACTIVO",
                "FLG_DESCONTINUADO",
            ],
            CONTRATO_ERP,
        )
        assert "peso_kg" in columnas.faltantes_opcionales
        assert not columnas.tiene("peso_kg")


class TestSkuBxContrato:
    def test_plantilla_vieja_es_valida(self):
        columnas = resolver_columnas(
            ["ORDEN", "SKU", "UN_BX", "ESTADO_LINEA"], CONTRATO_SKU_BX
        )
        assert columnas.idx("un_bx") == 2
        assert not columnas.tiene("largo_cm")

    def test_plantilla_nueva_con_caja(self):
        columnas = resolver_columnas(
            [
                "ORDEN",
                "SKU",
                "UN_BX",
                "ESTADO_LINEA",
                "LARGO_CM",
                "ANCHO_CM",
                "ALTO_CM",
                "PESO_CAJA_KG",
                "M3_CAJA",
                "M3_UNIDAD",
            ],
            CONTRATO_SKU_BX,
        )
        assert columnas.idx("largo_cm") == 4
        assert columnas.idx("m3_unidad") == 9


class TestCalcularM3:
    def test_caja_40x30x25(self):
        assert calcular_m3(40, 30, 25) == 0.03

    def test_falta_un_lado(self):
        assert calcular_m3(40, 30, None) is None
        assert calcular_m3(40, 30, 0) is None
        assert calcular_m3("", 30, 25) is None

    def test_texto_numerico(self):
        assert calcular_m3("40", "30", "25") == 0.03


def _fila_s1(ancho=19):
    return [""] * ancho


def _reporte_s1(filas_preamble=9, desplazamiento=0):
    filas = [_fila_s1(20) for _ in range(filas_preamble)]
    cabecera = _fila_s1(20)
    cabecera[2 + desplazamiento] = "ARTÍCULO"
    cabecera[9 + desplazamiento] = "ALMACEN"
    cabecera[12 + desplazamiento] = "UM"
    cabecera[13 + desplazamiento] = "STOCK"
    cabecera[16 + desplazamiento] = "PREDESPACHO"
    cabecera[18 + desplazamiento] = "DISPONIBLE"
    filas.append(cabecera)
    for i in range(3):
        datos = _fila_s1()
        datos[1 + desplazamiento] = f"01101{i}"
        datos[2 + desplazamiento] = f"PELOTA {i}"
        datos[9 + desplazamiento] = "118"
        datos[12 + desplazamiento] = "UND"
        datos[13 + desplazamiento] = 10
        datos[16 + desplazamiento] = 2
        filas.append(datos)
    return filas


class TestDetectarColumnasS1:
    def test_reporte_real(self):
        columnas = detectar_columnas_s1(_reporte_s1())
        assert columnas.fila_header == 9
        assert columnas.fila_datos == 10
        assert columnas.idx_sku == 1
        assert columnas.indices["descripcion"] == 2
        assert columnas.indices["stock"] == 13
        assert columnas.indices["predespacho"] == 16

    def test_preambulo_mas_largo(self):
        columnas = detectar_columnas_s1(_reporte_s1(filas_preamble=25))
        assert columnas.fila_header == 25
        assert columnas.fila_datos == 26

    def test_columnas_desplazadas(self):
        # Todo el reporte corrido una columna: se detecta por ancla.
        columnas = detectar_columnas_s1(_reporte_s1(desplazamiento=1))
        assert columnas.idx_sku == 2
        assert columnas.indices["stock"] == 14

    def test_sin_header_falla_claro(self):
        filas = [_fila_s1() for _ in range(15)]
        with pytest.raises(ErrorContrato) as exc:
            detectar_columnas_s1(filas)
        assert "no encontre la fila de encabezado" in str(exc.value)

    def test_falta_predespacho_falla(self):
        filas = _reporte_s1()
        filas[9][16] = ""
        with pytest.raises(ErrorContrato) as exc:
            detectar_columnas_s1(filas)
        assert "predespacho" in str(exc.value)

    def test_sku_no_es_descripcion_menos_uno(self):
        # Header en col 3 pero el SKU vive en la col 0 (no en la 2).
        filas = _reporte_s1()
        for r in (10, 11, 12):
            filas[r][1] = ""
            filas[r][0] = filas[r][1] or ""
        filas[10][0] = "011010"
        filas[11][0] = "011011"
        filas[12][0] = "011012"
        columnas = detectar_columnas_s1(filas)
        assert columnas.idx_sku == 0
        assert any("se detecto en la columna" in a for a in columnas.avisos)


class TestAlmacenesS1:
    def test_fuera_de_lista(self):
        assert almacenes_fuera_de_lista(
            ["118", "VES", "999", "S1"], permitidos=set(ALMACENES_S1)
        ) == [
            "999",
            "S1",
        ]

    def test_todos_conocidos(self):
        assert (
            almacenes_fuera_de_lista(
                ["121", "129", "VES", "118", "122"], permitidos=set(ALMACENES_S1)
            )
            == []
        )

    def test_case_insensitive(self):
        assert (
            almacenes_fuera_de_lista(["ves", " 118 "], permitidos=set(ALMACENES_S1))
            == []
        )


class TestCargarAlmacenes:
    """Los almacenes son VARIABLE (config/almacenes.json), no codigo."""

    def test_config_valida(self, tmp_path):
        import json

        ruta = tmp_path / "almacenes.json"
        ruta.write_text(
            json.dumps(
                {
                    "almacen_principal": "VES",
                    "almacenes": {"VES": "venta", "118": "mktd", "777": "venta"},
                }
            ),
            encoding="utf-8",
        )
        config = cargar_almacenes(ruta)
        assert config["fuente"] == "config"
        assert config["almacen_principal"] == "VES"
        assert config["almacenes"]["777"] == "venta"
        assert almacenes_publicados(ruta) == ("777", "VES", "118")
        assert almacenes_fuera_de_lista(["999"], permitidos=config["almacenes"]) == [
            "999"
        ]
        assert almacenes_fuera_de_lista(["118"], permitidos=config["almacenes"]) == []

    def test_sin_config_cae_al_default(self, tmp_path):
        config = cargar_almacenes(tmp_path / "no_existe.json")
        assert config["fuente"] == "default"
        assert "VES" in config["almacenes"]
        assert any("historicos" in a for a in config["avisos"])

    def test_config_rota_cae_al_default(self, tmp_path):
        ruta = tmp_path / "almacenes.json"
        ruta.write_text("{no es json", encoding="utf-8")
        config = cargar_almacenes(ruta)
        assert config["fuente"] == "default"
        assert "VES" in config["almacenes"]


class TestHuellaFuente:
    def test_incluye_sha_y_tamano(self, tmp_path):
        archivo = tmp_path / "x.txt"
        archivo.write_text("hola", encoding="utf-8")
        huella = huella_fuente(archivo)
        assert huella["archivo"] == "x.txt"
        assert huella["bytes"] == 4
        assert len(huella["sha256"]) == 16
        assert "modificado" in huella

    def test_archivo_inexistente(self, tmp_path):
        assert huella_fuente(tmp_path / "no.txt")["error"] == "no existe"


# ─────────────────────────────────────────────────────────────────────────────
# Integracion: los lectores reales sobre archivos temporales
# ─────────────────────────────────────────────────────────────────────────────


def _escribir_erp(ruta: Path, columnas: list[str], filas: list[list]) -> Path:
    import xlwt

    libro = xlwt.Workbook(encoding="utf-8")
    hoja = libro.add_sheet("codigos productos")
    for i, nombre in enumerate(columnas):
        hoja.write(0, i, nombre)
    for r, fila in enumerate(filas, start=1):
        for c, valor in enumerate(fila):
            hoja.write(r, c, valor)
    libro.save(str(ruta))
    return ruta


class TestLeerErpPorNombre:
    def test_columnas_reordenadas(self, tmp_path):
        from generar_catalogo_base import leer_erp

        ruta = _escribir_erp(
            tmp_path / "PRODUCTOS.xls",
            [
                "PRECIO",
                "CODIGO",
                "NOMBRE",
                "LINEA",
                "GRUPO",
                "FLG_INACTIVO",
                "FLG_DESCONTINUADO",
            ],
            [
                [
                    "12.50",
                    "016763",
                    "PELOTA VINIBALL",
                    "PELOTAS",
                    "PELOTAS",
                    "Unchecked",
                    "Unchecked",
                ]
            ],
        )
        productos, errores, *_ = leer_erp(ruta)
        assert errores == []
        assert len(productos) == 1
        assert productos[0]["sku"] == "016763"
        assert productos[0]["precio"] == 12.5

    def test_columna_faltante_no_genera_catalogo(self, tmp_path):
        from generar_catalogo_base import leer_erp

        ruta = _escribir_erp(
            tmp_path / "PRODUCTOS.xls",
            ["CODIGO", "NOMBRE", "LINEA", "GRUPO", "PRECIO"],
            [["016763", "PELOTA", "PELOTAS", "PELOTAS", "12.50"]],
        )
        productos, errores, *_ = leer_erp(ruta)
        assert productos == []
        assert any("Contrato roto" in e for e in errores)

    def test_hoja_renombrada_con_una_sola_hoja(self, tmp_path):
        import xlwt

        from generar_catalogo_base import leer_erp

        libro = xlwt.Workbook(encoding="utf-8")
        hoja = libro.add_sheet("Hoja1")
        columnas = [
            "CODIGO",
            "NOMBRE",
            "LINEA",
            "GRUPO",
            "PRECIO",
            "FLG_INACTIVO",
            "FLG_DESCONTINUADO",
        ]
        for i, nombre in enumerate(columnas):
            hoja.write(0, i, nombre)
        hoja.write(1, 0, "016763")
        hoja.write(1, 1, "PELOTA")
        hoja.write(1, 2, "PELOTAS")
        hoja.write(1, 3, "PELOTAS")
        hoja.write(1, 4, "12.50")
        hoja.write(1, 5, "Unchecked")
        hoja.write(1, 6, "Unchecked")
        ruta = tmp_path / "PRODUCTOS.xls"
        libro.save(str(ruta))

        productos, errores, *_ = leer_erp(ruta)
        assert errores == []
        assert len(productos) == 1


class TestLeerUnbxCaja:
    def _crear(self, ruta: Path, cabecera: list[str], filas: list[list]) -> Path:
        import openpyxl

        libro = openpyxl.Workbook()
        hoja = libro.active
        hoja.title = "SKU_BX"
        hoja.append(cabecera)
        for fila in filas:
            hoja.append(fila)
        libro.save(ruta)
        return ruta

    def test_caja_calculada(self, tmp_path):
        from generar_catalogo_base import leer_unbx

        ruta = self._crear(
            tmp_path / "SKU_BX.xlsx",
            [
                "ORDEN",
                "SKU",
                "UN_BX",
                "ESTADO_LINEA",
                "LARGO_CM",
                "ANCHO_CM",
                "ALTO_CM",
                "PESO_CAJA_KG",
            ],
            [[1, "016763", 18, "IMPORTADO", 40, 30, 25, 2.5]],
        )
        guia = leer_unbx(ruta)
        assert guia.orden["016763"] == 1
        assert guia.un_bx["016763"] == 18
        caja = guia.caja["016763"]
        assert caja["m3_caja"] == 0.03
        assert caja["m3_unidad"] == round(0.03 / 18, 6)
        assert caja["peso_caja_kg"] == 2.5

    def test_sin_dimensiones_no_publica_caja(self, tmp_path):
        from generar_catalogo_base import leer_unbx

        ruta = self._crear(
            tmp_path / "SKU_BX.xlsx",
            ["ORDEN", "SKU", "UN_BX"],
            [[1, "016763", 18]],
        )
        guia = leer_unbx(ruta)
        assert guia.caja == {}
        assert guia.un_bx["016763"] == 18

    def test_caja_incompleta_avisa(self, tmp_path):
        from generar_catalogo_base import leer_unbx

        ruta = self._crear(
            tmp_path / "SKU_BX.xlsx",
            ["ORDEN", "SKU", "UN_BX", "LARGO_CM", "ANCHO_CM", "ALTO_CM"],
            [[1, "016763", 18, 40, 30, None]],
        )
        guia = leer_unbx(ruta)
        assert guia.caja == {}
        assert any("incompleta" in a for a in guia.avisos)

    def test_columna_faltante_es_fatal(self, tmp_path):
        from generar_catalogo_base import leer_unbx

        ruta = self._crear(
            tmp_path / "SKU_BX.xlsx",
            ["ORDEN", "SKU"],
            [[1, "016763"]],
        )
        with pytest.raises(ErrorContrato):
            leer_unbx(ruta)


class TestEmparejarSkus:
    """Calce exacto primero, sin prefijo numerico despues, sin adivinar."""

    def _emparejar(self):
        from contratos import emparejar_skus

        return emparejar_skus

    def test_exacta(self):
        emparejar = self._emparejar()
        match, st = emparejar({"CA001"}, {"CA001": "UND", "X": "KGR"})
        assert match == {"CA001": "CA001"}
        assert st == {"exactos": 1, "prefijo": 0, "ambiguos": 0, "sin_match": 0}

    def test_prefijo_numerico(self):
        # KARDEX guarda '01CA001' cuando el ERP dice 'CA001'.
        emparejar = self._emparejar()
        match, st = emparejar({"CA001"}, {"01CA001": "UND"})
        assert match == {"CA001": "01CA001"}
        assert st["prefijo"] == 1

    def test_ceros_no_se_pierden(self):
        # '016763' NO es '16763': sin letras no hay reduccion.
        emparejar = self._emparejar()
        match, st = emparejar({"16763"}, {"016763": "UND"})
        assert match == {}
        assert st["sin_match"] == 1

    def test_exacta_gana_a_prefijo(self):
        emparejar = self._emparejar()
        match, st = emparejar({"CA001"}, {"CA001": "UND", "01CA001": "KGR"})
        assert match == {"CA001": "CA001"}
        assert st["exactos"] == 1 and st["prefijo"] == 0

    def test_ambiguo_no_se_adivina(self):
        emparejar = self._emparejar()
        match, st = emparejar({"CA001"}, {"01CA001": "UND", "02CA001": "KGR"})
        assert match == {}
        assert st["ambiguos"] == 1


class TestUmEnCatalogo:
    def _prod(self, sku, um=""):
        return {
            "sku": sku,
            "nombre": "X",
            "ean13": "",
            "ean14": "",
            "peso_kg": 0.0,
            "linea": "01",
            "linea_nombre": "P",
            "grupo": "P",
            "tipo": "T",
            "familia": "F",
            "categoria": "VINIBALL",
            "precio": 1.0,
            "descontinuado": False,
            "linea_codigo": "01",
            "um": um,
            "origen": "erp",
        }

    def test_um_kardex_completa_al_producto(self, tmp_path):
        from generar_catalogo_base import generar_output

        res = generar_output(
            [self._prod("A")],
            {},
            {},
            {},
            str(tmp_path / "c.json"),
            um_kardex={"A": "UND"},
        )
        assert res["productos"][0]["um"] == "UND"
        assert res["metadata"]["estadisticas"]["con_um"] == 1

    def test_um_propia_manda_sobre_kardex(self, tmp_path):
        from generar_catalogo_base import generar_output

        res = generar_output(
            [self._prod("A", um="BST")],
            {},
            {},
            {},
            str(tmp_path / "c.json"),
            um_kardex={"A": "UND"},
        )
        assert res["productos"][0]["um"] == "BST"


class TestDimensionesEnCatalogo:
    def test_generar_output_publica_caja_y_fuentes(self, tmp_path):
        from generar_catalogo_base import generar_output

        producto = {
            "sku": "016763",
            "nombre": "PELOTA",
            "ean13": "",
            "ean14": "",
            "peso_kg": 0.0,
            "linea": "01",
            "linea_nombre": "PELOTAS",
            "grupo": "PELOTAS",
            "tipo": "PELOTA",
            "familia": "FUTBOL",
            "categoria": "VINIBALL",
            "precio": 10.0,
            "descontinuado": False,
            "linea_codigo": "01",
            "um": "",
            "origen": "erp",
        }
        caja = {
            "largo_cm": 40,
            "ancho_cm": 30,
            "alto_cm": 25,
            "m3_caja": 0.03,
            "m3_unidad": 0.001667,
            "peso_caja_kg": None,
        }
        salida = tmp_path / "catalogo.json"
        res = generar_output(
            [producto],
            {"016763": 18},
            {},
            {"016763": 1},
            str(salida),
            caja_map={"016763": caja},
            fuentes=[{"archivo": "PRODUCTOS.xls", "sha256": "abc"}],
        )
        item = res["productos"][0]
        assert item["dimensiones_caja"] == caja
        assert item["un_bx"] == 18
        assert res["metadata"]["fuentes"][0]["archivo"] == "PRODUCTOS.xls"
        assert res["metadata"]["estadisticas"]["con_caja"] == 1
        # Almacenes como VARIABLE: el metadata publica la config.
        assert res["metadata"]["almacenes"]["principal"] == "VES"
        assert "118" in res["metadata"]["almacenes"]["almacenes"]

    def test_sin_caja_publica_null(self, tmp_path):
        from generar_catalogo_base import generar_output

        producto = {
            "sku": "A",
            "nombre": "X",
            "ean13": "",
            "ean14": "",
            "peso_kg": 0.0,
            "linea": "01",
            "linea_nombre": "P",
            "grupo": "P",
            "tipo": "T",
            "familia": "F",
            "categoria": "VINIBALL",
            "precio": 1.0,
            "descontinuado": False,
            "linea_codigo": "01",
            "um": "",
            "origen": "erp",
        }
        res = generar_output([producto], {}, {}, {}, str(tmp_path / "c.json"))
        assert res["productos"][0]["dimensiones_caja"] is None


class TestClasificarGuia:
    """El motivo por el que un SKU manual no entra. Los SKU son EXACTOS:
    no hay 'similares' ni sugerencias: o el codigo esta en el maestro (o en
    KARDEX, con o sin prefijo) o no esta."""

    def test_en_erp_activo_entra(self):
        motivo, _ = clasificar_guia(
            "A00011", {"inactivo": False, "linea": "PELOTAS"}, False
        )
        assert motivo == "ok"

    def test_inactivo_en_erp_no_entra(self):
        motivo, detalle = clasificar_guia(
            "B0002", {"inactivo": True, "linea": "PELOTAS"}, False
        )
        assert motivo == "inactivo"
        assert "inactivo" in detalle.lower()

    def test_linea_de_proceso_no_entra(self):
        motivo, detalle = clasificar_guia(
            "C0003",
            {"inactivo": False, "linea": "PRODUCTOS EN PROCESO"},
            False,
        )
        assert motivo == "proceso"
        assert "proceso" in detalle.lower()

    def test_sin_similares_solo_exactos(self):
        # A00012 no existe: aunque A00011 se parezca, no se sugiere nada.
        motivo, detalle = clasificar_guia("A00012", None, False)
        assert motivo == "inexistente"
        assert "A00011" not in detalle
        assert "similar" not in detalle.lower()
        assert "tipeo" not in detalle.lower()

    def test_en_kardex_pero_no_en_erp(self):
        motivo, detalle = clasificar_guia("K0009", None, True)
        assert motivo == "kardex"
        assert "KARDEX" in detalle
        assert "similar" not in detalle.lower()

    def test_inexistente(self):
        motivo, detalle = clasificar_guia("ZZZ99", None, False)
        assert motivo == "inexistente"
        assert "ERP" in detalle and "KARDEX" in detalle


class TestGuiaIgnorados:
    def test_carga_y_normaliza(self, tmp_path):
        import json

        ruta = tmp_path / "guia_ignorados.json"
        ruta.write_text(
            json.dumps({"ignorados": {" 04058 ": "baja definitiva"}}),
            encoding="utf-8",
        )
        assert cargar_guia_ignorados(ruta) == {"04058": "baja definitiva"}

    def test_archivo_ausente_es_vacio(self, tmp_path):
        assert cargar_guia_ignorados(tmp_path / "no_existe.json") == {}


class TestFrescuraErp:
    """El paso 0 avisa si el export del ERP es viejo (catalogo rancio)."""

    def _erp(self, ruta, dias_atras=0):
        import os
        import time

        import xlwt

        libro = xlwt.Workbook(encoding="utf-8")
        hoja = libro.add_sheet("codigos productos")
        columnas = [
            "CODIGO",
            "NOMBRE",
            "LINEA",
            "GRUPO",
            "PRECIO",
            "FLG_INACTIVO",
            "FLG_DESCONTINUADO",
        ]
        for i, nombre in enumerate(columnas):
            hoja.write(0, i, nombre)
        hoja.write(1, 0, "016763")
        hoja.write(1, 1, "PELOTA")
        hoja.write(1, 2, "PELOTAS")
        hoja.write(1, 3, "PELOTAS")
        hoja.write(1, 4, "10")
        hoja.write(1, 5, "Unchecked")
        hoja.write(1, 6, "Unchecked")
        libro.save(str(ruta))
        if dias_atras:
            viejo = time.time() - dias_atras * 86400
            os.utime(ruta, (viejo, viejo))

    def test_erp_reciente_no_avisa_edad(self, tmp_path):
        from validar_encabezados import validar_erp

        ruta = tmp_path / "PRODUCTOS.xls"
        self._erp(ruta, dias_atras=5)
        bloque = validar_erp(ruta)
        assert bloque.estado in ("ok", "aviso")
        assert not any("dias" in a and "ERP tiene" in a for a in bloque.avisos)

    def test_erp_viejo_avisa_pero_no_bloquea(self, tmp_path):
        from validar_encabezados import validar_erp

        ruta = tmp_path / "PRODUCTOS.xls"
        self._erp(ruta, dias_atras=90)
        bloque = validar_erp(ruta)
        assert bloque.estado != "error"
        assert any("90 dias" in a for a in bloque.avisos)


class TestGuiaVsMaestros:
    """Integracion con archivos temporales: el bloque detecta cada caso."""

    def _erp(self, ruta):
        import xlwt

        libro = xlwt.Workbook(encoding="utf-8")
        hoja = libro.add_sheet("codigos productos")
        columnas = [
            "CODIGO",
            "NOMBRE",
            "LINEA",
            "GRUPO",
            "PRECIO",
            "FLG_INACTIVO",
            "FLG_DESCONTINUADO",
        ]
        for i, nombre in enumerate(columnas):
            hoja.write(0, i, nombre)
        filas = [
            ["A00011", "PROD ACTIVO", "PELOTAS", "G", "10", "Unchecked", "Unchecked"],
            ["B0002", "PROD INACTIVO", "PELOTAS", "G", "5", "Checked", "Unchecked"],
            [
                "C0003",
                "PROCESO",
                "PRODUCTOS EN PROCESO",
                "G",
                "7",
                "Unchecked",
                "Unchecked",
            ],
        ]
        for r, fila in enumerate(filas, start=1):
            for c, valor in enumerate(fila):
                hoja.write(r, c, valor)
        libro.save(str(ruta))

    def _xlsx(self, ruta, hoja_nombre, cabecera, filas):
        import openpyxl

        libro = openpyxl.Workbook()
        hoja = libro.active
        hoja.title = hoja_nombre
        hoja.append(cabecera)
        for fila in filas:
            hoja.append(fila)
        libro.save(ruta)

    def test_detecta_cada_caso(self, tmp_path):
        self._erp(tmp_path / "PRODUCTOS.xls")
        self._xlsx(
            tmp_path / "KARDEX_BASE.xlsx",
            "KARDEX",
            [
                "colIdAlmacen",
                "colNomAlmacen",
                "colIdArticulo",
                "colNomArticulo",
                "colIdLinea",
                "colNomLinea",
                "colIdUM",
            ],
            [["1", "A", "K0009", "N", "L", "L", "U"]],
        )
        self._xlsx(
            tmp_path / "SKU_BX.xlsx",
            "SKU_BX",
            ["ORDEN", "SKU", "UN_BX"],
            [
                [1, "A00011", 10],
                [2, "B0002", 5],
                [3, "C0003", 5],
                [4, "K0009", 5],
                [5, "ZZZ99", 5],
                [6, "A00012", 5],
            ],
        )
        bloque = validar_guia_vs_maestros(tmp_path)
        assert bloque.estado == "aviso"
        texto = "\n".join(bloque.avisos)
        assert "A00011 (SKU_BX)" not in texto  # en ERP activo: silencioso
        assert "B0002 (SKU_BX)" in texto and "inactivo" in texto.lower()
        assert "C0003 (SKU_BX)" in texto and "proceso" in texto.lower()
        assert "K0009 (SKU_BX)" in texto and "KARDEX" in texto
        assert "ZZZ99 (SKU_BX)" in texto
        # A00012 no existe: exacto, sin sugerencia de A00011.
        linea_a12 = next(
            aviso for aviso in bloque.avisos if aviso.startswith("A00012 ")
        )
        assert "mal escrito" in linea_a12
        assert "A00011" not in linea_a12


class TestCaidaUniverso:
    """Un universo parcial con HTTP 200 es invisible para la cobertura
    (se calcula contra ese mismo universo): se compara contra la corrida
    anterior y se publica la variacion en el metadata."""

    def _prod(self, sku):
        return {
            "sku": sku,
            "nombre": "X",
            "ean13": "",
            "ean14": "",
            "peso_kg": 0.0,
            "linea": "01",
            "linea_nombre": "P",
            "grupo": "P",
            "tipo": "T",
            "familia": "F",
            "categoria": "VINIBALL",
            "precio": 1.0,
            "descontinuado": False,
            "linea_codigo": "01",
            "um": "",
            "origen": "erp",
        }

    def _previo(self, ruta, skus_universo):
        import json

        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "metadata": {
                        "total_productos": 10,
                        "universo_stock": {
                            "incluido": True,
                            "skus": skus_universo,
                        },
                    },
                    "productos": [],
                },
                f,
            )

    def _universo(self, n):
        return {
            f"S{i:05d}": {"stock": 1, "predespacho": 0, "linea": "0178 - ARCHIVO"}
            for i in range(n)
        }

    def test_caida_fuerte_deja_alerta_en_metadata(self, tmp_path, capsys):
        from generar_catalogo_base import generar_output

        salida = tmp_path / "catalogo.json"
        self._previo(salida, 100)
        res = generar_output(
            [self._prod("A")],
            {},
            {},
            {},
            str(salida),
            universo=self._universo(80),
            universo_stock={"incluido": True, "skus": 80, "error": ""},
        )
        uni = res["metadata"]["universo_stock"]
        assert uni["previo_skus"] == 100
        assert uni["variacion"] == -0.2
        assert "alerta_caida" in uni
        assert "ALERTA" in capsys.readouterr().out

    def test_sin_caida_no_hay_alerta(self, tmp_path):
        from generar_catalogo_base import generar_output

        salida = tmp_path / "catalogo.json"
        self._previo(salida, 100)
        res = generar_output(
            [self._prod("A")],
            {},
            {},
            {},
            str(salida),
            universo=self._universo(100),
            universo_stock={"incluido": True, "skus": 100, "error": ""},
        )
        uni = res["metadata"]["universo_stock"]
        assert uni["previo_skus"] == 100
        assert uni["variacion"] == 0.0
        assert "alerta_caida" not in uni

    def test_sin_previo_no_compara(self, tmp_path):
        from generar_catalogo_base import generar_output

        salida = tmp_path / "catalogo.json"
        res = generar_output(
            [self._prod("A")],
            {},
            {},
            {},
            str(salida),
            universo=self._universo(50),
            universo_stock={"incluido": True, "skus": 50, "error": ""},
        )
        uni = res["metadata"]["universo_stock"]
        assert "previo_skus" not in uni
        assert "alerta_caida" not in uni

    def test_validador_frena_con_alerta_caida(self):
        from validar_taxonomia import validar

        catalogo = {
            "metadata": {
                "categorias_por_linea": {},
                "universo_stock": {
                    "incluido": True,
                    "skus": 80,
                    "previo_skus": 100,
                    "variacion": -0.2,
                    "alerta_caida": "el universo cayo -20% vs la corrida anterior",
                },
                "universo_skus": [],
                "cobertura_faltante": [],
            },
            "productos": [],
        }
        errores, _ = validar(catalogo, Path(__file__).resolve().parent.parent.parent)
        assert any("cayo -20%" in e for e in errores)


CABECERA_KARDEX = [
    "colIdAlmacen",
    "colNomAlmacen",
    "colIdArticulo",
    "colNomArticulo",
    "colNomArticulo",
    "colIdLinea",
    "colNomLinea",
    "colIdGrupo",
    "colNomGrupo",
    "colIdTipo",
    "colNomTipo",
    "colIdFamilia",
    "colNomFamilia",
    "colIdUM",
]


def _escribir_kardex(ruta, filas):
    import openpyxl

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "KARDEX"
    hoja.append(CABECERA_KARDEX)
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)
    return ruta


def _fila_k(
    almacen,
    sku,
    um="UND",
    lin=("CA", "LINEA"),
    gru=("G1", "GRUPO"),
    tip=("T1", "TIPO"),
    fam=("F1", "FAM"),
):
    return [
        almacen,
        "ALM",
        sku,
        "NOM " + sku,
        "NOM LARGO " + sku,
        lin[0],
        lin[1],
        gru[0],
        gru[1],
        tip[0],
        tip[1],
        fam[0],
        fam[1],
        um,
    ]


class TestLeerKardex:
    """Una sola lectura compartida: ficha completa + cache por archivo."""

    def test_ficha_completa(self, tmp_path):
        from contratos import leer_kardex

        _escribir_kardex(
            tmp_path / "KARDEX_BASE.xlsx",
            [
                _fila_k("A", "01CA001"),
                _fila_k("B", "03077", um="KGR"),
            ],
        )
        fichas, meta = leer_kardex(tmp_path / "KARDEX_BASE.xlsx")
        assert meta["articulos"] == 2
        assert fichas["01CA001"]["um"] == "UND"
        assert fichas["01CA001"]["linea"] == "LINEA"
        assert fichas["01CA001"]["nombre_largo"] == "NOM LARGO 01CA001"
        assert fichas["03077"]["um"] == "KGR"

    def test_segunda_lectura_usa_cache(self, tmp_path):
        from contratos import leer_kardex

        _escribir_kardex(tmp_path / "KARDEX_BASE.xlsx", [_fila_k("A", "K1")])
        leer_kardex(tmp_path / "KARDEX_BASE.xlsx")
        _, meta = leer_kardex(tmp_path / "KARDEX_BASE.xlsx")
        assert meta["nota"] == "indice cacheado"

    def test_conflicto_por_almacen_queda_registrado(self, tmp_path):
        from contratos import leer_kardex

        _escribir_kardex(
            tmp_path / "KARDEX_BASE.xlsx",
            [
                _fila_k("A", "K1", gru=("G1", "GRUPO UNO")),
                _fila_k("B", "K1", gru=("G1", "GRUPO DOS")),
            ],
        )
        fichas, _ = leer_kardex(tmp_path / "KARDEX_BASE.xlsx")
        assert fichas["K1"]["n_almacenes"] == 2
        assert fichas["K1"]["conflictos"].get("grupo") == ["GRUPO DOS", "GRUPO UNO"]

    def test_sin_archivo_devuelve_vacio(self, tmp_path):
        from contratos import leer_kardex

        fichas, meta = leer_kardex(tmp_path / "KARDEX_BASE.xlsx")
        assert fichas == {}
        assert meta["nota"] == "sin KARDEX"


class TestAuditarKardexErp:
    """El cruce ERP<->KARDEX muestra defectos de registro en vez de asumir."""

    def _erp(self, ruta):
        import xlwt

        libro = xlwt.Workbook(encoding="utf-8")
        hoja = libro.add_sheet("codigos productos")
        columnas = [
            "CODIGO",
            "NOMBRE",
            "LINEA",
            "GRUPO",
            "TIPO",
            "FAMILIA",
            "PRECIO",
            "FLG_INACTIVO",
            "FLG_DESCONTINUADO",
        ]
        for i, nombre in enumerate(columnas):
            hoja.write(0, i, nombre)
        filas = [
            [
                "IGUAL1",
                "N",
                "PELOTAS",
                "G1",
                "T1",
                "F1",
                "10",
                "Unchecked",
                "Unchecked",
            ],
            [
                "DIFER01",
                "N",
                "PELOTAS",
                "G1",
                "T1",
                "F1",
                "10",
                "Unchecked",
                "Unchecked",
            ],
            [
                "PREF01",
                "N",
                "PELOTAS",
                "G1",
                "T1",
                "F1",
                "10",
                "Unchecked",
                "Unchecked",
            ],
            [
                "SOLOERP",
                "N",
                "PELOTAS",
                "G1",
                "T1",
                "F1",
                "10",
                "Unchecked",
                "Unchecked",
            ],
        ]
        for r, fila in enumerate(filas, start=1):
            for c, valor in enumerate(fila):
                hoja.write(r, c, valor)
        libro.save(str(ruta))

    def test_detecta_diferencia_y_prefijo(self, tmp_path):
        from validar_encabezados import validar_kardex_vs_erp

        self._erp(tmp_path / "PRODUCTOS.xls")
        _escribir_kardex(
            tmp_path / "KARDEX_BASE.xlsx",
            [
                # igual en todo (ERP guarda el nombre: 'G1' == 'G1')
                _fila_k(
                    "A",
                    "IGUAL1",
                    lin=("01", "PELOTAS"),
                    gru=("G1", "G1"),
                    tip=("T1", "T1"),
                    fam=("F1", "F1"),
                ),
                # grupo distinto: ERP G1 vs KARDEX G9
                _fila_k(
                    "A",
                    "DIFER01",
                    lin=("01", "PELOTAS"),
                    gru=("G9", "G9"),
                    tip=("T1", "T1"),
                    fam=("F1", "F1"),
                ),
                # con prefijo numerico: ERP PREF01, KARDEX 01PREF01
                _fila_k(
                    "A",
                    "01PREF01",
                    lin=("01", "PELOTAS"),
                    gru=("G1", "G1"),
                    tip=("T1", "T1"),
                    fam=("F1", "F1"),
                ),
                # conflicto entre almacenes
                _fila_k(
                    "A",
                    "CONF01",
                    lin=("01", "PELOTAS"),
                    gru=("G1", "G1"),
                    tip=("T1", "T1"),
                    fam=("F1", "F1"),
                ),
                _fila_k(
                    "B",
                    "CONF01",
                    lin=("01", "PELOTAS"),
                    gru=("G2", "G2"),
                    tip=("T1", "T1"),
                    fam=("F1", "F1"),
                ),
            ],
        )
        bloque = validar_kardex_vs_erp(tmp_path)
        assert bloque.estado == "aviso"
        texto = "\n".join(bloque.avisos)
        assert "DIFER01" in texto
        assert "G1" in texto and "G9" in texto
        assert not any(a.startswith("  IGUAL1:") for a in bloque.avisos)
        assert any("CONF01" in a for a in bloque.avisos)

    def test_no_bloquea_y_sin_kardex_se_omite(self, tmp_path):
        from validar_encabezados import validar_kardex_vs_erp

        self._erp(tmp_path / "PRODUCTOS.xls")
        bloque = validar_kardex_vs_erp(tmp_path)
        assert bloque.estado == "skip"
