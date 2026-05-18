#!/usr/bin/env python3
"""
Tests unitarios para G360 Catalog Generator
Ejecutar: python -m pytest scripts/tests/ -v
"""
import sys
from pathlib import Path

# Agregar scripts al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generar_catalogo import generar_nombre_corto, validar_ean13


class TestGenerarNombreCorto:
    """Tests para la función generar_nombre_corto()"""
    
    def test_elimina_pelota_al_inicio(self):
        """Debe eliminar 'PELOTA' o 'PELOTA DE' al inicio"""
        assert generar_nombre_corto("PELOTA FUTBOL PERU") == "Futbol Peru"
        assert generar_nombre_corto("PELOTA DE PVC VOLEY") == "Voley"
    
    def test_elimina_materiales(self):
        """Debe eliminar materiales: GOMA, PVC, CUERO, PU"""
        assert generar_nombre_corto("FUTBOL GOMA FREE") == "Futbol Free"
        assert generar_nombre_corto("VOLEY CUERO COSIDO") == "Voley Cosido"
        assert generar_nombre_corto("BASQUET PVC AZUL") == "Basquet Azul"
        assert generar_nombre_corto("FUTBOL PU FUTURE") == "Futbol Future"
    
    def test_elimina_marcas(self):
        """Debe eliminar marcas: VINIFAN*, VFAN*"""
        assert generar_nombre_corto("CRAYONES VINIFAN DELGADO") == "Crayones Delgado"
        assert generar_nombre_corto("FORRO VINIFANCITO CRISTAL") == "Forro Cristal"
        assert generar_nombre_corto("LAPIZ VFAN TRIANGULAR") == "Lapiz Triangular"
    
    def test_elimina_n_sola(self):
        """Debe eliminar 'N' sola en cualquier posición"""
        assert generar_nombre_corto("N DEPORTIVA FUTBOL") == "Deportiva Futbol"
        assert generar_nombre_corto("FORRO N VINIFAN") == "Forro"
    
    def test_combina_reglas(self):
        """Debe aplicar múltiples reglas correctamente"""
        assert generar_nombre_corto("PELOTA DE PVC SEMIDEPORTIVA VOLEY STITCH") == "Semideportiva Voley Stitch"
        assert generar_nombre_corto("FUTBOL CUERO TERMOSELLADA PERU #5") == "Futbol Termosellada Peru #5"
    
    def test_vacio_retorna_vacio(self):
        """Debe retornar string vacío si recibe vacío o None"""
        assert generar_nombre_corto("") == ""
        assert generar_nombre_corto(None) == ""
    
    def test_capitaliza_correctamente(self):
        """Debe capitalizar primera letra de cada palabra"""
        assert generar_nombre_corto("futbol peru") == "Futbol Peru"


class TestValidarEan13:
    """Tests para la función validar_ean13()"""
    
    def test_ean_vacio_es_valido(self):
        """EAN vacío o '0' debe ser válido (no es error)"""
        assert validar_ean13("") is True
        assert validar_ean13("0") is True
        assert validar_ean13(None) is True
    
    def test_ean_valido(self):
        """EAN13 válido debe retornar True"""
        assert validar_ean13("7754807167277") is True
        assert validar_ean13("7754807020015") is True
    
    def test_ean_invalido_longitud(self):
        """EAN con longitud != 13 debe retornar False"""
        assert validar_ean13("123456789") is False
        assert validar_ean13("12345678901234") is False
    
    def test_ean_invalido_checksum(self):
        """EAN con checksum incorrecto debe retornar False"""
        assert validar_ean13("7754807167278") is False  # Último dígito incorrecto
    
    def test_ean_no_numerico(self):
        """EAN con caracteres no numéricos debe retornar False"""
        assert validar_ean13("775480716727A") is False


class TestCalculoDescuentos:
    """Tests para el cálculo de descuentos"""
    
    def test_descuento_simple(self):
        """Un descuento del 10% debe dar factor 0.9"""
        descuentos = [0.10]
        factor = 1
        for d in descuentos:
            if d > 0:
                factor *= (1 - d)
        assert round(factor, 2) == 0.90
    
    def test_descuento_consecutivo(self):
        """Descuentos consecutivos: 10% + 20% = 28% total"""
        descuentos = [0.10, 0.20]
        factor = 1
        for d in descuentos:
            if d > 0:
                factor *= (1 - d)
        desc_total = round((1 - factor) * 100, 1)
        assert desc_total == 28.0
    
    def test_sin_descuento(self):
        """Sin descuentos debe dar 0%"""
        descuentos = [0, 0, 0, 0]
        factor = 1
        for d in descuentos:
            if d > 0:
                factor *= (1 - d)
        desc_total = round((1 - factor) * 100, 1) if factor < 1 else 0
        assert desc_total == 0.0
    
    def test_descuento_cero_ignorado(self):
        """Descuento en 0 debe ser ignorado"""
        descuentos = [0.10, 0, 0.05, 0]
        factor = 1
        for d in descuentos:
            if d > 0:
                factor *= (1 - d)
        desc_total = round((1 - factor) * 100, 1)
        # 10% + 5% = 14.5%
        assert desc_total == 14.5


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])