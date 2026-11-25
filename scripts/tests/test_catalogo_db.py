#!/usr/bin/env python3
"""Tests de generar_catalogo_db.py: round-trip real sobre el JSON versionado
(sin modificar output/), casos sinteticos y verificación --check.

Ejecutar: python -m pytest scripts/tests/test_catalogo_db.py -q
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generar_catalogo_db import (  # noqa: E402
    MSG_OBSOLETA,
    USER_VERSION,
    build_db,
    main,
)

RAIZ = Path(__file__).resolve().parent.parent.parent
JSON_VERSIONADO = RAIZ / "output" / "catalogo_productos.json"

PRODUCTO_COLUMNS = [
    "sku", "nombre", "nombre_corto", "ean13", "ean14", "categoria",
    "categoria_venta", "linea", "linea_nombre", "grupo", "grupo_id", "tipo",
    "tipo_id", "familia", "familia_id", "um", "almacenes", "un_bx", "orden",
    "estado_linea", "peso_kg", "dimensiones_caja", "precio", "descontinuado",
    "linea_codigo", "en_guia", "compromiso", "cotizable", "vigente",
    "por_activar", "derivado_de", "origen", "stock_snapshot",
    "predespacho_snapshot", "keywords",
]


# ---------------------------------------------------------------------------
# Fixtures y helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def json_versionado():
    """El JSON de output/ (solo lectura, nunca se toca)."""
    datos = json.loads(JSON_VERSIONADO.read_bytes().decode("utf-8"))
    return datos, JSON_VERSIONADO.read_bytes()


@pytest.fixture
def tmp_json(tmp_path):
    """Copia del JSON versionado en tmp_path para tests de build/--check."""
    p = tmp_path / "catalogo_productos.json"
    p.write_bytes(JSON_VERSIONADO.read_bytes())
    return p


# ---------------------------------------------------------------------------
# Round-trip real: 3550 dicts idénticos con type(v) is T
# ---------------------------------------------------------------------------

class TestRoundTripReal:
    def _esperado_sql(self, p):
        """Valor que debe leerse de la BD para cada clave."""
        esperado = {}
        for c in PRODUCTO_COLUMNS:
            v = p[c]
            if c == "dimensiones_caja":
                esperado[c] = None  # None -> SQL NULL -> lee None
            elif c in ("almacenes", "keywords"):
                esperado[c] = json.dumps(v, ensure_ascii=False)
            elif c in ("descontinuado", "en_guia", "compromiso", "cotizable", "vigente", "por_activar"):
                esperado[c] = 1 if v else 0
            elif c in ("un_bx", "orden", "stock_snapshot", "predespacho_snapshot"):
                esperado[c] = int(v)
            elif c in ("peso_kg", "precio"):
                esperado[c] = float(v)
            else:
                esperado[c] = v
        return esperado

    def test_3550_dicts_idénticos_tipos_y_orden(self, json_versionado, tmp_path):
        """Round-trip real: todos los productos, type(v) is T, orden de claves,
        marcadores (vacíos, REAL enteros), sha256 y json_bytes."""
        datos, bytes_json = json_versionado
        productos = datos["productos"]
        assert len(productos) == 3550
        db = tmp_path / "rt.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)

        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM producto ORDER BY sku")
            columnas = [d[0] for d in cur.description]
            assert columnas == PRODUCTO_COLUMNS, f"orden de columnas: {columnas}"
            filas = cur.fetchall()
        finally:
            conn.close()

        assert len(filas) == 3550
        por_sku = {p["sku"]: p for p in productos}
        for fila in filas:
            p = por_sku[fila[0]]
            esperado = self._esperado_sql(p)
            for i, c in enumerate(PRODUCTO_COLUMNS):
                v = fila[i]
                ev = esperado[c]
                if c == "dimensiones_caja":
                    assert v is None, f"{p['sku']}.{c} espera None, obtuvo {v!r}"
                elif c in ("almacenes", "keywords"):
                    assert isinstance(v, str)
                    assert json.loads(v) == json.loads(ev), f"{p['sku']}.{c}"
                else:
                    assert type(v) is type(ev), f"{p['sku']}.{c}: {type(v).__name__} != {type(ev).__name__}"
                    assert v == ev, f"{p['sku']}.{c}: {v!r} != {ev!r}"

    def test_sha256_y_json_bytes(self, json_versionado, tmp_path):
        datos, bytes_json = json_versionado
        sha = hashlib.sha256(bytes_json).hexdigest()
        assert sha.lower() == "e5f0c954e7af06d09f5bebf9fa2d0d2d7e70be4b883cc4360c65837c96de1dea"
        assert len(bytes_json) == 4778558
        db = tmp_path / "sha.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT json_sha256, json_bytes FROM catalogo_metadata WHERE id=1")
            sb, bb = cur.fetchone()
        finally:
            conn.close()
        assert sb == sha
        assert bb == len(bytes_json)

    def test_usuario_version(self, json_versionado, tmp_path):
        datos, bytes_json = json_versionado
        db = tmp_path / "uv.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA user_version")
            uv = cur.fetchone()[0]
        finally:
            conn.close()
        assert uv == USER_VERSION

    def test_7_tablas_orden(self, json_versionado, tmp_path):
        datos, bytes_json = json_versionado
        db = tmp_path / "t.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tablas = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
        assert tablas == [
            "almacen", "catalogo_metadata", "cruce_s1", "producto",
            "producto_almacen", "producto_ean", "s1_universo",
        ]

    def test_sku_ceros_preservados(self, json_versionado, tmp_path):
        """016763 != 16763: sku TEXT preserva ceros a la izquierda."""
        datos, bytes_json = json_versionado
        skus = {p["sku"] for p in datos["productos"]}
        assert "016763" in skus
        assert "16763" not in skus or "016763" in skus
        db = tmp_path / "ceros.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT sku FROM producto WHERE sku=?", ("016763",))
            assert cur.fetchone() is not None
            cur.execute("SELECT sku FROM producto WHERE sku=?", ("16763",))
            assert cur.fetchone() is None
        finally:
            conn.close()

    def test_ean_compartido_maximo_5(self, json_versionado, tmp_path):
        """EAN13: hay grupos repetidos (27) y el maximo es <= 5 (spec). producto_ean
        no tiene UNIQUE, así que un ean repetido genera varias filas."""
        datos, bytes_json = json_versionado
        from collections import Counter
        c = Counter(p["ean13"] for p in datos["productos"] if p["ean13"])
        repetidos = {e: n for e, n in c.items() if n > 1}
        assert len(repetidos) == 27, f"esperaba 27 grupos ean13 repetidos, obtuvo {len(repetidos)}"
        assert max(c.values()) <= 5, f"maximo ean13 repetido > 5: {max(c.values())}"
        # El ean mas repetido aparece N veces en producto_ean (sin UNIQUE).
        ean, n = max(c.items(), key=lambda kv: kv[1])
        db = tmp_path / "ean.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM producto_ean WHERE ean=? AND tipo='ean13'", (ean,))
            assert cur.fetchone()[0] == n
        finally:
            conn.close()

    def test_ean13_vacio_no_inserto(self, json_versionado, tmp_path):
        """ean13='' no genera fila en producto_ean (no se convierte a NULL)."""
        datos, bytes_json = json_versionado
        vacios = [p for p in datos["productos"] if p["ean13"] == ""]
        assert vacios, "esperaba productos con ean13 vacio"
        db = tmp_path / "eanv.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM producto_ean WHERE tipo='ean13' AND ean=''")
            assert cur.fetchone()[0] == 0
        finally:
            conn.close()

    def test_almacen_s_estrella(self, json_versionado, tmp_path):
        """Almacen id 'S*' se guarda verbatim (texto)."""
        datos, bytes_json = json_versionado
        usado = set()
        for p in datos["productos"]:
            usado.update(p["almacenes"])
        s_ids = [a for a in usado if a.startswith("S")]
        assert s_ids, "esperaba ids de almacen empezando en S"
        db = tmp_path / "s.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            for sid in s_ids[:3]:
                cur.execute("SELECT COUNT(*) FROM producto_almacen WHERE almacen_id=?", (sid,))
                assert cur.fetchone()[0] >= 1
        finally:
            conn.close()

    def test_va_cadena_vacia_no_null(self, json_versionado, tmp_path):
        """'VA':'' es dato real: nombre TEXT='' no NULL."""
        datos, bytes_json = json_versionado
        nombres = datos["metadata"]["almacenes"]["nombres"]
        assert nombres.get("VA") == ""
        db = tmp_path / "va.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT nombre FROM almacen WHERE almacen_id='VA'")
            fila = cur.fetchone()
            assert fila is not None
            assert fila[0] == ""
            cur.execute("SELECT nombre FROM almacen WHERE almacen_id='VA' AND nombre IS NULL")
            assert cur.fetchone() is None
        finally:
            conn.close()

    def test_id_fuera_de_nombres_cero_hoy(self, json_versionado, tmp_path, capsys):
        """Id de producto.almacenes fuera de nombres: 0 hoy, advertencia en stderr."""
        datos, bytes_json = json_versionado
        nombres = set(datos["metadata"]["almacenes"]["nombres"])
        usado = set()
        for p in datos["productos"]:
            usado.update(p["almacenes"])
        fuera = sorted(usado - nombres)
        assert fuera == [], "hoy debe ser 0"
        db = tmp_path / "fn.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=False)
        out = capsys.readouterr().err
        assert "almacenes_sin_nombre: 0" in out

    def test_dimensiones_caja_null(self, json_versionado, tmp_path):
        """dimensiones_caja None -> SQL NULL."""
        datos, bytes_json = json_versionado
        assert all(p["dimensiones_caja"] is None for p in datos["productos"])
        db = tmp_path / "dim.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM producto WHERE dimensiones_caja IS NULL")
            assert cur.fetchone()[0] == 3550
        finally:
            conn.close()

    def test_dimensiones_caja_dict_json(self, tmp_path):
        """dimensiones_caja dict futuro -> json.dumps."""
        datos = json.loads(JSON_VERSIONADO.read_bytes().decode("utf-8"))
        p = dict(datos["productos"][0])
        p["dimensiones_caja"] = {"largo_cm": 10}
        m = dict(datos["metadata"])
        m["total_productos"] = 1
        m["universo_stock"] = dict(m["universo_stock"], incluido=False)
        m["universo_skus"] = []
        doc = {"metadata": m, "productos": [p]}
        db = tmp_path / "dimdict.db"
        build_db(doc, json.dumps(doc, ensure_ascii=False).encode("utf-8"), db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT dimensiones_caja FROM producto WHERE sku=?", (p["sku"],))
            v = cur.fetchone()[0]
            assert v == '{"largo_cm": 10}'
        finally:
            conn.close()

    def test_origen_erp_s1(self, json_versionado, tmp_path):
        """origen erp 3044 / s1 506."""
        datos, bytes_json = json_versionado
        from collections import Counter
        o = Counter(p["origen"] for p in datos["productos"])
        assert o["erp"] == 3044
        assert o["s1"] == 506

    def test_incluido_true_universo_cruce(self, json_versionado, tmp_path):
        """incluido=true: s1_universo 2257, cruce 3550, cruce ok 2257, sin_s1 1293."""
        datos, bytes_json = json_versionado
        m = datos["metadata"]
        assert m["universo_stock"]["incluido"] is True
        assert len(m["universo_skus"]) == 2257
        db = tmp_path / "incl.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM s1_universo")
            assert cur.fetchone()[0] == 2257
            cur.execute("SELECT COUNT(*) FROM cruce_s1")
            assert cur.fetchone()[0] == 3550
            cur.execute("SELECT COUNT(*) FROM cruce_s1 WHERE motivo='ok'")
            assert cur.fetchone()[0] == 2257
            cur.execute("SELECT COUNT(*) FROM cruce_s1 WHERE motivo='sin_s1'")
            assert cur.fetchone()[0] == 1293
            cur.execute("SELECT COUNT(*) FROM cruce_s1 WHERE motivo='sin_catalogo'")
            assert cur.fetchone()[0] == 0
        finally:
            conn.close()

    def test_metadata_20_claves_generated_at_no_en_raiz(self, json_versionado, tmp_path):
        """metadata 20 claves, generated_at en metadata no en raiz."""
        datos, bytes_json = json_versionado
        m = datos["metadata"]
        assert len(m) == 20
        assert "generated_at" in m
        assert "generated_at" not in datos  # no en raiz
        db = tmp_path / "meta.db"
        build_db(datos, bytes_json, db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("SELECT metadata_json FROM catalogo_metadata WHERE id=1")
            mj = json.loads(cur.fetchone()[0])
            assert len(mj) == 20
            assert mj["generated_at"] == m["generated_at"]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Casos sinteticos: incluido=false, salida 3, salida 4, salida 2, --check
# ---------------------------------------------------------------------------

class TestSinteticos:
    def _base_doc(self, total=2, incluido=True):
        base = json.loads(JSON_VERSIONADO.read_bytes().decode("utf-8"))
        ps = base["productos"][:total]
        m = dict(base["metadata"])
        m["total_productos"] = total
        m["universo_stock"] = dict(m["universo_stock"], incluido=incluido)
        if incluido:
            m["universo_skus"] = [p["sku"] for p in ps] + ["SINENCATALOGO01"]
        else:
            m["universo_skus"] = []
        return {"metadata": m, "productos": ps}

    def test_incluido_false_sin_asserts_2257(self, tmp_path):
        """incluido=false: build permitido, s1_universo/cruce vacias, exit 0."""
        doc = self._base_doc(incluido=False)
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "x.json"
        j.write_bytes(b)
        db = tmp_path / "nf.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 0
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            # producto sigue completo (2 filas), solo s1_universo/cruce vacias
            cur.execute("SELECT COUNT(*) FROM producto")
            assert cur.fetchone()[0] == 2
            cur.execute("SELECT sku, nombre FROM producto LIMIT 1")
            fila = cur.fetchone()
            assert fila is not None and fila[0] and fila[1]
            cur.execute("SELECT COUNT(*) FROM s1_universo")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT COUNT(*) FROM cruce_s1")
            assert cur.fetchone()[0] == 0
        finally:
            conn.close()

    def test_cobertura_contradicha_salida_3(self, tmp_path):
        """Cobertura contradicha (total_productos != len(productos)) -> 3."""
        doc = self._base_doc()
        doc["metadata"]["total_productos"] = 999
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "c.json"
        j.write_bytes(b)
        db = tmp_path / "c.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 3

    def test_key_faltante_salida_3(self, tmp_path):
        """Producto sin una clave -> 3."""
        doc = self._base_doc()
        p = dict(doc["productos"][0])
        del p["ean13"]
        doc["productos"] = [p, doc["productos"][1]]
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "k.json"
        j.write_bytes(b)
        db = tmp_path / "k.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 3

    def test_key_extra_salida_3(self, tmp_path):
        """Producto con clave extra -> 3."""
        doc = self._base_doc()
        p = dict(doc["productos"][0])
        p["campo_extra"] = "x"
        doc["productos"] = [p]
        doc["metadata"]["total_productos"] = 1
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "ke.json"
        j.write_bytes(b)
        db = tmp_path / "ke.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 3

    def test_tipo_inesperado_salida_3(self, tmp_path):
        """un_bx como str -> 3."""
        doc = self._base_doc()
        p = dict(doc["productos"][0])
        p["un_bx"] = "dieciocho"
        doc["productos"] = [p]
        doc["metadata"]["total_productos"] = 1
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "t.json"
        j.write_bytes(b)
        db = tmp_path / "t.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 3

    def test_bool_antes_que_int(self, tmp_path):
        """bool no se cuela como int: un_bx true -> 3."""
        doc = self._base_doc()
        p = dict(doc["productos"][0])
        p["un_bx"] = True
        doc["productos"] = [p]
        doc["metadata"]["total_productos"] = 1
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "b.json"
        j.write_bytes(b)
        db = tmp_path / "b.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 3

    def test_sin_catalogo_mas_cobertura_consistente_salida_4(self, tmp_path):
        """sin_catalogo>0 con cobertura consistente -> 4."""
        base = json.loads(JSON_VERSIONADO.read_bytes().decode("utf-8"))
        m = dict(base["metadata"])
        # universo con un SKU que no esta en catalogo, cobertura consistente
        m["universo_skus"] = list(base["metadata"]["universo_skus"]) + ["ZZZ99999"]
        m["total_productos"] = len(base["productos"])
        doc = {"metadata": m, "productos": base["productos"]}
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "sc.json"
        j.write_bytes(b)
        db = tmp_path / "sc.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 4

    def test_sin_catalogo_con_cobertura_contradicha_gana_3(self, tmp_path):
        """Cobertura contradictiada y sin_catalogo>0 a la vez -> gana 3."""
        doc = self._base_doc()
        doc["metadata"]["total_productos"] = 5  # contradicha
        doc["metadata"]["universo_skus"] = ["ZZZ99999"]
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "cc.json"
        j.write_bytes(b)
        db = tmp_path / "cc.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 3

    def test_json_ausente_salida_2(self, tmp_path):
        """JSON ausente -> 2 con mensaje accionable."""
        db = tmp_path / "na.db"
        rc = main(["--json", str(tmp_path / "no_existe.json"), "--db", str(db), "--quiet"])
        assert rc == 2

    def test_check_obsoleto_salida_1(self, tmp_path, tmp_json):
        """BD obsoleta (fila borrada) -> --check exit 1 con mensaje fijo."""
        db = tmp_path / "ob.db"
        datos = json.loads(tmp_json.read_bytes().decode("utf-8"))
        build_db(datos, tmp_json.read_bytes(), db, db.with_suffix(".tmp"), quiet=True)
        # Borrar una fila de producto (huella intacta, conteo distinto)
        sku_a_borrar = datos["productos"][0]["sku"]
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM producto WHERE sku=?", (sku_a_borrar,))
            conn.commit()
        finally:
            conn.close()
        rc = main(["--json", str(tmp_json), "--db", str(db), "--check", "--quiet"])
        assert rc == 1

    def test_check_mensaje_fijo(self, tmp_path, tmp_json, capsys):
        """--check obsoleto imprime el mensaje fijo en stderr."""
        db = tmp_path / "msg.db"
        datos = json.loads(tmp_json.read_bytes().decode("utf-8"))
        build_db(datos, tmp_json.read_bytes(), db, db.with_suffix(".tmp"), quiet=True)
        sku_a_borrar = datos["productos"][0]["sku"]
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM producto WHERE sku=?", (sku_a_borrar,))
            conn.commit()
        finally:
            conn.close()
        rc = main(["--json", str(tmp_json), "--db", str(db), "--check", "--quiet"])
        assert rc == 1
        err = capsys.readouterr().err
        assert MSG_OBSOLETA in err

    def test_check_user_version_alterado_salida_1(self, tmp_path, tmp_json, monkeypatch):
        """--check con user_version alterado -> 1."""
        db = tmp_path / "uv2.db"
        datos = json.loads(tmp_json.read_bytes().decode("utf-8"))
        build_db(datos, tmp_json.read_bytes(), db, db.with_suffix(".tmp"), quiet=True)
        conn = sqlite3.connect(str(db))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA user_version = 99")
            conn.commit()
        finally:
            conn.close()
        rc = main(["--json", str(tmp_json), "--db", str(db), "--check", "--quiet"])
        assert rc == 1

    def test_check_integro_salida_0(self, tmp_path, tmp_json):
        """--check sobre BD íntegra -> 0."""
        db = tmp_path / "ok.db"
        datos = json.loads(tmp_json.read_bytes().decode("utf-8"))
        build_db(datos, tmp_json.read_bytes(), db, db.with_suffix(".tmp"), quiet=True)
        rc = main(["--json", str(tmp_json), "--db", str(db), "--check", "--quiet"])
        assert rc == 0

    def test_doble_build_dump_logico_idéntico(self, tmp_path, tmp_json):
        """Doble build con dump lógico idéntico (7 tablas ordenadas por PK, filas con repr())."""
        datos = json.loads(tmp_json.read_bytes().decode("utf-8"))
        b = tmp_json.read_bytes()
        dbs = [tmp_path / "d1.db", tmp_path / "d2.db"]
        for d in dbs:
            build_db(datos, b, d, d.with_suffix(".tmp"), quiet=True)

        def dump(path):
            conn = sqlite3.connect(str(path))
            try:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tablas = [r[0] for r in cur.fetchall()]
                lineas = []
                for t in tablas:
                    cur.execute(f"SELECT * FROM {t} ORDER BY 1")
                    for fila in cur.fetchall():
                        lineas.append(f"{t}: " + "|".join(repr(x) for x in fila))
                return "\n".join(lineas)
            finally:
                conn.close()

        assert dump(dbs[0]) == dump(dbs[1])

    def test_path_anidado_inexistente_se_crea(self, tmp_path, tmp_json):
        """Ruta anidada inexistente se crea."""
        datos = json.loads(tmp_json.read_bytes().decode("utf-8"))
        b = tmp_json.read_bytes()
        db = tmp_path / "a" / "b" / "c.db"
        build_db(datos, b, db, db.with_suffix(".tmp"), quiet=True)
        assert db.exists()

    def test_db_tmp_limpio_tras_fallo(self, tmp_path):
        """<db>.tmp se elimina tras un fallo de build."""
        doc = self._base_doc()
        doc["metadata"]["total_productos"] = 999  # fuerza salida 3
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "f.json"
        j.write_bytes(b)
        db = tmp_path / "f.db"
        tmp_ = Path(str(db) + ".tmp")
        # crear un tmp preexistente sucio para que build lo borre al inicio
        tmp_.write_text("basura")
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 3
        assert not tmp_.exists(), f"tmp residual: {tmp_}"

    def test_token_falso_no_appears_en_stderr(self, tmp_path, capsys):
        """Token falso en metadata.fuentes no aparece en stdout ni stderr."""
        base = json.loads(JSON_VERSIONADO.read_bytes().decode("utf-8"))
        m = dict(base["metadata"])
        token = "G360-SECRETO-PRUEBA-XYZ"
        m["fuentes"] = [{"archivo": "x", "bytes": 1, "sha256": token, "modificado": "2026-01-01"}]
        m["universo_stock"] = dict(m["universo_stock"], incluido=False)
        m["universo_skus"] = []
        doc = {"metadata": m, "productos": base["productos"][:2]}
        doc["metadata"]["total_productos"] = 2
        b = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        j = tmp_path / "tk.json"
        j.write_bytes(b)
        db = tmp_path / "tk.db"
        rc = main(["--json", str(j), "--db", str(db), "--quiet"])
        assert rc == 0
        out = capsys.readouterr()
        assert token not in out.out
        assert token not in out.err
