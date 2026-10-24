import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import pandas as pd

from core.ingestion import estabilizar_excel_crudo, _limpiar_cabecera, _coincide_keywords


class TestLimpiarCabecera(unittest.TestCase):
    def test_espacios_y_mayusculas(self):
        self.assertEqual(_limpiar_cabecera("  NOM_CLIENTE  "), "nom_cliente")

    def test_tildes(self):
        self.assertEqual(_limpiar_cabecera("División"), "division")
        self.assertEqual(_limpiar_cabecera("Línea"), "linea")

    def test_espacios_intermedios(self):
        self.assertEqual(_limpiar_cabecera("CANAL DE DISTRIBUCION"), "canal_de_distribucion")

    def test_puntos(self):
        self.assertEqual(_limpiar_cabecera("DOC_CLIENTE.1"), "doc_cliente1")

    def test_barras(self):
        self.assertEqual(_limpiar_cabecera("S/PRECIO"), "s_precio")

    def test_guiones_dobles(self):
        self.assertEqual(_limpiar_cabecera("NOM  CLIENTE"), "nom_cliente")

    def test_no_string(self):
        self.assertEqual(_limpiar_cabecera(42), "42")


class TestCoincideKeywords(unittest.TestCase):
    def test_id(self):
        self.assertTrue(_coincide_keywords("id_cliente", ["id_cliente", "doc"]))

    def test_parcial(self):
        self.assertTrue(_coincide_keywords("soles", ["soles", "dolares"]))

    def test_no_coincide(self):
        self.assertFalse(_coincide_keywords("nombre", ["soles", "dolares"]))


_SAMPLE_DF = pd.DataFrame({
    "ANHO": [2026.0, 2026.0, np.nan],
    "ID_ARTICULO": ["11030", "78456", np.nan],
    "NOM_CLIENTE": ["  CLIENTE A  ", "CLIENTE B", np.nan],
    "ID_CLIENTE": ["001", "002", np.nan],
    "DOC_CLIENTE": ["20491653745", "12345678", np.nan],
    "SOLES": [1172.10, "S/.2,500.50", np.nan],
    "FECHA_ORIG": ["24/06/2026", "20/06/2026", np.nan],
    "ID_LINEA": ["0111", "0178", np.nan],
    "NOM_LINEA": ["LINEA A", "LINEA B", np.nan],
})


def _patched_ingestion(df_data, ruta="fake.xls"):
    with patch("core.ingestion.pd.read_excel", return_value=df_data.copy()), \
         patch.object(Path, "exists", return_value=True):
        return estabilizar_excel_crudo(ruta)


class TestEstabilizarExcelCrudo(unittest.TestCase):

    def test_normalizacion_completa(self):
        df, meta = _patched_ingestion(_SAMPLE_DF)

        self.assertIn("anho", df.columns)
        self.assertIn("id_articulo", df.columns)
        self.assertIn("nom_cliente", df.columns)
        self.assertIn("soles", df.columns)
        self.assertIn("fecha_orig", df.columns)
        self.assertIn("id_linea", df.columns)
        self.assertEqual(df["id_linea"].iloc[0], "0111")
        self.assertEqual(df["id_linea"].iloc[1], "0178")

    def test_ids_como_texto_sin_ceros_perdidos(self):
        df, _ = _patched_ingestion(_SAMPLE_DF)
        self.assertEqual(df["id_articulo"].iloc[0], "11030")
        self.assertEqual(df["id_articulo"].iloc[1], "78456")

    def test_dinero_limpio(self):
        df, _ = _patched_ingestion(_SAMPLE_DF)
        self.assertAlmostEqual(df["soles"].iloc[0], 1172.10, places=2)
        self.assertAlmostEqual(df["soles"].iloc[1], 2500.50, places=2)

    def test_fechas_como_datetime(self):
        df, _ = _patched_ingestion(_SAMPLE_DF)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["fecha_orig"]))

    def test_filas_vacias_eliminadas(self):
        df, _ = _patched_ingestion(_SAMPLE_DF)
        self.assertEqual(len(df), 2)

    def test_metadata_creada(self):
        df, meta = _patched_ingestion(_SAMPLE_DF)
        self.assertIn("filas_estabilizadas", meta)
        self.assertIn("columnas_finales", meta)
        self.assertEqual(meta["filas_estabilizadas"], 2)

    def test_soles_sin_nan(self):
        df, _ = _patched_ingestion(_SAMPLE_DF)
        self.assertFalse(df["soles"].isna().any())

    def test_archivo_no_existe(self):
        with self.assertRaises(FileNotFoundError):
            estabilizar_excel_crudo("no_existe_archivo_falso_999.xls")

    def test_cliente_full_label_creado(self):
        df, _ = _patched_ingestion(_SAMPLE_DF)
        self.assertIn("cliente_full_label", df.columns)
        self.assertEqual(df["cliente_full_label"].iloc[0], "001 - 20491653745 - CLIENTE A")

    def test_labels_generados(self):
        df, meta = _patched_ingestion(_SAMPLE_DF)
        self.assertIn("cliente_label", df.columns)
        self.assertIn("linea_label", df.columns)
        self.assertIn("cliente_full_label", df.columns)


class TestColumnasDuplicadas(unittest.TestCase):
    def test_duplicados_se_sufijan(self):
        df_dup = pd.DataFrame({
            "DOC_CLIENTE": [1.0, 2.0],
            "DOC_CLIENTE.1": [1.0, 2.0],
            "SOLES": [100.0, 200.0],
        })
        df, meta = _patched_ingestion(df_dup)
        cols = list(df.columns)
        self.assertEqual(len(set(cols)), len(cols), f"Columnas duplicadas: {cols}")


if __name__ == "__main__":
    unittest.main()
