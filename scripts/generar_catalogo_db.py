#!/usr/bin/env python3
"""Genera data/catalogo.db (SQLite, regenerable) desde output/catalogo_productos.json.

Arquitectura
------------
ERP+KARDEX+SKU_BX+S1 -> generar_catalogo_base.py -> output/catalogo_productos.json
                                          -> generar_catalogo_db.py -> data/catalogo.db

Este script lee SOLO el JSON: cero red, cero Excel, cero API. Importa solo
stdlib (argparse, json, sqlite3, hashlib, os, sys, pathlib).

El .db se deriva del JSON y se regenera cada vez: nadie escribe en la BD salvo
el generador, y si difiere del JSON se regenera, nunca se edita. El .db nunca
se versiona (gitignore cubre /data/).

Salidas
-------
--json  JSON de entrada (default output/catalogo_productos.json)
--db    SQLite de salida (default data/catalogo.db)
--check verifica sin escribir: exit 1 con "BD obsoleta o dañada: regenerar"
--quiet suprime avisos de stderr (salvo mensaje fijo de fallo)

Codigos de salida: 0 ok | 1 BD obsoleta/dañada (--check) | 2 JSON ausente/ilegible
| 3 contrato roto | 4 invariante (sin_catalogo > 0, round-trip). Precedencia: 2 -> 3 -> 4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes del contrato
# ---------------------------------------------------------------------------

CONTRACT_VERSION = "3.8.0"
VERSION = "3.8.0"
PRODUCTO_COLUMNS = [
    "sku", "nombre", "nombre_corto", "ean13", "ean14", "categoria",
    "categoria_venta", "linea", "linea_nombre", "grupo", "grupo_id", "tipo",
    "tipo_id", "familia", "familia_id", "um", "almacenes", "un_bx", "orden",
    "estado_linea", "peso_kg", "dimensiones_caja", "precio", "descontinuado",
    "linea_codigo", "en_guia", "compromiso", "cotizable", "vigente",
    "por_activar", "derivado_de", "origen", "stock_snapshot",
    "predespacho_snapshot", "keywords",
]
NUMERIC_INT_COLUMNS = {"un_bx", "orden", "stock_snapshot", "predespacho_snapshot"}
NUMERIC_REAL_COLUMNS = {"peso_kg", "precio"}
BOOL_COLUMNS = {
    "descontinuado", "en_guia", "compromiso", "cotizable", "vigente", "por_activar",
}
JSON_LIST_COLUMNS = {"almacenes", "keywords"}
TEXT_COLUMNS = set(PRODUCTO_COLUMNS) - NUMERIC_INT_COLUMNS - NUMERIC_REAL_COLUMNS - BOOL_COLUMNS - {"dimensiones_caja"} - JSON_LIST_COLUMNS

METADATA_CLAVES_ESPERADAS = 20
USER_VERSION = 1

MSG_OBSOLETA = "BD obsoleta o dañada: regenerar"

# ---------------------------------------------------------------------------
# Normalizacion de valores segun §6.1
# ---------------------------------------------------------------------------

def normalizar_valor(clave, valor):
    """Normaliza un valor del JSON al tipo SQL del contrato.

    Regla de oro: bool se verifica ANTES que int (bool es subclase de int).
    Cualquier desvío del contrato => contrato roto (salida 3).
    """
    if clave == "dimensiones_caja":
        if valor is None:
            return None
        if isinstance(valor, dict):
            return json.dumps(valor, ensure_ascii=False)
        raise ValueError(f"tipo inesperado para dimensiones_caja: {type(valor).__name__}")

    if clave in JSON_LIST_COLUMNS:
        if not isinstance(valor, list):
            raise ValueError(f"{clave}: se esperaba list, se encontro {type(valor).__name__}")
        return json.dumps(valor, ensure_ascii=False)

    if clave in TEXT_COLUMNS:
        if not isinstance(valor, str):
            raise ValueError(f"{clave}: se esperaba str, se encontro {type(valor).__name__}")
        return valor

    if clave in NUMERIC_INT_COLUMNS:
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ValueError(f"{clave}: se esperaba int, se encontro {type(valor).__name__}")
        return int(valor)

    if clave in NUMERIC_REAL_COLUMNS:
        if isinstance(valor, bool):
            raise ValueError(f"{clave}: se esperaba float, se encontro {type(valor).__name__}")
        if not isinstance(valor, (int, float)):
            raise ValueError(f"{clave}: se esperaba float, se encontro {type(valor).__name__}")
        return float(valor)

    if clave in BOOL_COLUMNS:
        if not isinstance(valor, bool):
            raise ValueError(f"{clave}: se esperaba bool, se encontro {type(valor).__name__}")
        return 1 if valor else 0

    raise ValueError(f"clave desconocida en producto: {clave}")


# ---------------------------------------------------------------------------
# Lectura y validacion del JSON fuente
# ---------------------------------------------------------------------------

def leer_json(ruta_json: Path):
    """Lee el JSON de entrada. Salida 2 si no existe o es ilegible."""
    try:
        bytes_json = ruta_json.read_bytes()
    except OSError as exc:
        print(f"JSON no encontrado o ilegible: {ruta_json} ({exc})", file=sys.stderr)
        print("Regenerar con: actualizar_catalogo.bat", file=sys.stderr)
        sys.exit(2)
    try:
        doc = json.loads(bytes_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"JSON ilegible: {ruta_json} ({exc})", file=sys.stderr)
        print("Regenerar con: actualizar_catalogo.bat", file=sys.stderr)
        sys.exit(2)
    if not isinstance(doc, dict):
        print(f"JSON invalido: raiz no es objeto ({ruta_json})", file=sys.stderr)
        sys.exit(2)
    return doc, bytes_json


def validar_contrato(doc, bytes_json):
    """Valida el contrato de 20 claves de metadata y 35 claves de producto.

    Retorna (metadata, productos). Salida 3 si el contrato se rompe.
    """
    metadata = doc.get("metadata")
    productos = doc.get("productos")
    if not isinstance(metadata, dict):
        print("Contrato roto: metadata no es un objeto", file=sys.stderr)
        sys.exit(3)
    if not isinstance(productos, list):
        print("Contrato roto: productos no es un array", file=sys.stderr)
        sys.exit(3)

    # --- metadata: exactamente 20 claves ---
    claves_meta = set(metadata.keys())
    if len(claves_meta) != METADATA_CLAVES_ESPERADAS:
        print(
            f"Contrato roto: metadata tiene {len(claves_meta)} claves, se esperaban "
            f"{METADATA_CLAVES_ESPERADAS}",
            file=sys.stderr,
        )
        sys.exit(3)
    if metadata.get("version") != VERSION:
        print(
            f"Contrato roto: metadata.version != {VERSION}", file=sys.stderr
        )
        sys.exit(3)
    if metadata.get("contract_version") != CONTRACT_VERSION:
        print(
            f"Contrato roto: metadata.contract_version != {CONTRACT_VERSION}",
            file=sys.stderr,
        )
        sys.exit(3)
    if "generated_at" not in metadata or not isinstance(metadata["generated_at"], str):
        print("Contrato roto: metadata.generated_at ausente o no es str", file=sys.stderr)
        sys.exit(3)
    total = metadata.get("total_productos")
    if not isinstance(total, int) or isinstance(total, bool):
        print("Contrato roto: metadata.total_productos ausente o no es int", file=sys.stderr)
        sys.exit(3)
    if len(productos) != total:
        print(
            f"Contrato roto: total_productos={total} pero productos={len(productos)}",
            file=sys.stderr,
        )
        sys.exit(3)

    # --- producto: exactamente 35 claves, orden exacto, tipos segun §6.1 ---
    for p in productos:
        if not isinstance(p, dict):
            print("Contrato roto: un elemento de productos no es objeto", file=sys.stderr)
            sys.exit(3)
        if list(p.keys()) != PRODUCTO_COLUMNS:
            print(
                "Contrato roto: claves de producto fuera del orden/esquema de 35",
                file=sys.stderr,
            )
            sys.exit(3)
        for clave in PRODUCTO_COLUMNS:
            try:
                normalizar_valor(clave, p[clave])
            except ValueError as exc:
                print(f"Contrato roto ({clave}): {exc}", file=sys.stderr)
                sys.exit(3)

    return metadata, productos


# ---------------------------------------------------------------------------
# Construccion de la BD
# ---------------------------------------------------------------------------

SQL_PRODUCTO = (
    "CREATE TABLE producto ("
    "sku TEXT NOT NULL PRIMARY KEY, "
    "nombre TEXT NOT NULL, "
    "nombre_corto TEXT, "
    "ean13 TEXT, "
    "ean14 TEXT, "
    "categoria TEXT, "
    "categoria_venta TEXT, "
    "linea TEXT, "
    "linea_nombre TEXT, "
    "grupo TEXT, "
    "grupo_id TEXT, "
    "tipo TEXT, "
    "tipo_id TEXT, "
    "familia TEXT, "
    "familia_id TEXT, "
    "um TEXT, "
    "almacenes TEXT, "
    "un_bx INTEGER, "
    "orden INTEGER, "
    "estado_linea TEXT, "
    "peso_kg REAL, "
    "dimensiones_caja TEXT, "
    "precio REAL, "
    "descontinuado INTEGER NOT NULL CHECK (descontinuado IN (0,1)), "
    "linea_codigo TEXT, "
    "en_guia INTEGER NOT NULL CHECK (en_guia IN (0,1)), "
    "compromiso INTEGER NOT NULL CHECK (compromiso IN (0,1)), "
    "cotizable INTEGER NOT NULL CHECK (cotizable IN (0,1)), "
    "vigente INTEGER NOT NULL CHECK (vigente IN (0,1)), "
    "por_activar INTEGER NOT NULL CHECK (por_activar IN (0,1)), "
    "derivado_de TEXT, "
    "origen TEXT, "
    "stock_snapshot INTEGER, "
    "predespacho_snapshot INTEGER, "
    "keywords TEXT)"
)
SQL_IDX_LINEA_CODIGO = "CREATE INDEX idx_producto_linea_codigo ON producto(linea_codigo)"
SQL_IDX_CATEGORIA_VENTA = "CREATE INDEX idx_producto_categoria_venta ON producto(categoria_venta)"
SQL_IDX_ORIGEN = "CREATE INDEX idx_producto_origen ON producto(origen)"
SQL_IDX_ORDEN = "CREATE INDEX idx_producto_orden ON producto(orden)"

SQL_PRODUCTO_EAN = (
    "CREATE TABLE producto_ean ("
    "ean TEXT NOT NULL, "
    "tipo TEXT NOT NULL CHECK (tipo IN ('ean13','ean14')), "
    "sku TEXT NOT NULL REFERENCES producto(sku), "
    "PRIMARY KEY (ean, tipo, sku))"
)
SQL_IDX_EAN_SKU = "CREATE INDEX idx_producto_ean_sku ON producto_ean(sku)"

SQL_PRODUCTO_ALMACEN = (
    "CREATE TABLE producto_almacen ("
    "sku TEXT NOT NULL REFERENCES producto(sku), "
    "almacen_id TEXT NOT NULL, "
    "PRIMARY KEY (sku, almacen_id))"
)
SQL_IDX_ALMACEN = "CREATE INDEX idx_producto_almacen_almacen_id ON producto_almacen(almacen_id)"

SQL_ALMACEN = (
    "CREATE TABLE almacen ("
    "almacen_id TEXT PRIMARY KEY, "
    "nombre TEXT, "
    "tipo TEXT)"
)

SQL_CATALOGO_METADATA = (
    "CREATE TABLE catalogo_metadata ("
    "id INTEGER PRIMARY KEY CHECK (id=1), "
    "version TEXT NOT NULL, "
    "contract_version TEXT NOT NULL, "
    "generated_at TEXT NOT NULL, "
    "total_productos INTEGER NOT NULL, "
    "metadata_json TEXT NOT NULL, "
    "json_sha256 TEXT NOT NULL, "
    "json_bytes INTEGER NOT NULL, "
    "json_generated_at TEXT NOT NULL)"
)

SQL_S1_UNIVERSO = "CREATE TABLE s1_universo (sku TEXT PRIMARY KEY)"
SQL_CRUCE_S1 = (
    "CREATE TABLE cruce_s1 ("
    "sku TEXT PRIMARY KEY, "
    "en_catalogo INTEGER NOT NULL CHECK (en_catalogo IN (0,1)), "
    "en_universo INTEGER NOT NULL CHECK (en_universo IN (0,1)), "
    "motivo TEXT NOT NULL CHECK (motivo IN ('ok','sin_catalogo','sin_s1','sin_taxonomia_s1','sku_invalido')), "
    "origen TEXT)"
)
SQL_IDX_CRUCE_MOTIVO = "CREATE INDEX idx_cruce_s1_motivo ON cruce_s1(motivo)"


def crear_tablas(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute(SQL_PRODUCTO)
    cur.execute(SQL_IDX_LINEA_CODIGO)
    cur.execute(SQL_IDX_CATEGORIA_VENTA)
    cur.execute(SQL_IDX_ORIGEN)
    cur.execute(SQL_IDX_ORDEN)
    cur.execute(SQL_PRODUCTO_EAN)
    cur.execute(SQL_IDX_EAN_SKU)
    cur.execute(SQL_PRODUCTO_ALMACEN)
    cur.execute(SQL_IDX_ALMACEN)
    cur.execute(SQL_ALMACEN)
    cur.execute(SQL_CATALOGO_METADATA)
    cur.execute(SQL_S1_UNIVERSO)
    cur.execute(SQL_CRUCE_S1)
    cur.execute(SQL_IDX_CRUCE_MOTIVO)
    cur.execute("PRAGMA user_version = 1")
    conn.commit()


def insertar_producto(cur, p):
    fila = []
    for clave in PRODUCTO_COLUMNS:
        fila.append(normalizar_valor(clave, p[clave]))
    placeholders = ", ".join("?" for _ in PRODUCTO_COLUMNS)
    cur.execute(
        f"INSERT INTO producto ({', '.join(PRODUCTO_COLUMNS)}) VALUES ({placeholders})",
        fila,
    )


def insertar_eans(cur, p):
    sku = p["sku"]
    for clave_tipo in (("ean13", "ean13"), ("ean14", "ean14")):
        clave, tipo = clave_tipo
        ean = p[clave]
        if ean:  # vacio real -> no se inserta (no se convierte a NULL)
            cur.execute(
                "INSERT INTO producto_ean (ean, tipo, sku) VALUES (?, ?, ?)",
                (ean, tipo, sku),
            )


def insertar_almacenes_producto(cur, p):
    sku = p["sku"]
    for almacen_id in p["almacenes"]:
        cur.execute(
            "INSERT INTO producto_almacen (sku, almacen_id) VALUES (?, ?)",
            (sku, almacen_id),
        )


def insertar_almacenes(cur, nombres, publicados):
    for almacen_id, nombre in sorted(nombres.items()):
        tipo = publicados.get(almacen_id)  # None si no esta publicado
        cur.execute(
            "INSERT INTO almacen (almacen_id, nombre, tipo) VALUES (?, ?, ?)",
            (almacen_id, nombre, tipo),
        )


def insertar_metadata(cur, metadata, json_sha256, json_bytes):
    metadata_json = json.dumps(metadata, ensure_ascii=False)
    generado = metadata["generated_at"]
    cur.execute(
        "INSERT INTO catalogo_metadata "
        "(id, version, contract_version, generated_at, total_productos, "
        "metadata_json, json_sha256, json_bytes, json_generated_at) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            metadata["version"],
            metadata["contract_version"],
            generado,
            metadata["total_productos"],
            metadata_json,
            json_sha256,
            json_bytes,
            generado,  # json_generated_at lee el mismo metadata.generated_at
        ),
    )


def construir_cruce(productos, universo_skus, incluido):
    """Cruce §5.2: set en_catalogo, un cruce_s1 por SKU de la union.

    `sku_to_origen` evita el barrido O(n·m) sobre productos por cada SKU.
    `origen` preserva `""` verbatim; solo es NULL cuando el producto no existe
    en el catalogo (sin_catalogo) o el campo es None.
    """
    en_catalogo = {p["sku"] for p in productos}
    catalogo_skus = set(en_catalogo)
    sku_to_origen = {p["sku"]: p.get("origen") for p in productos}
    universo_set = set(universo_skus)
    union = catalogo_skus | universo_set
    filas = []
    for sku in sorted(union):
        en_cat = 1 if sku in catalogo_skus else 0
        en_uni = 1 if sku in universo_set else 0
        if en_cat and en_uni:
            motivo = "ok"
        elif not en_cat and en_uni:
            motivo = "sin_catalogo"
        elif en_cat and not en_uni:
            motivo = "sin_s1"
        else:
            motivo = "sku_invalido"
        origen = sku_to_origen.get(sku) if en_cat else None
        filas.append((sku, en_cat, en_uni, motivo, origen))
    return filas


def build_db(doc, bytes_json, db_path: Path, db_tmp: Path, quiet: bool):
    """Construye la BD en <db>.tmp y la mueve atomicos a <db>."""
    metadata, productos = validar_contrato(doc, bytes_json)
    json_sha256 = hashlib.sha256(bytes_json).hexdigest()
    json_bytes = len(bytes_json)

    # Cruce §5.2
    universo_stock = metadata.get("universo_stock") or {}
    incluido = bool(universo_stock.get("incluido", False))
    universo_skus = metadata.get("universo_skus") or []
    if not isinstance(universo_skus, list) or not all(isinstance(s, str) for s in universo_skus):
        print("Contrato roto: universo_skus no es lista de str", file=sys.stderr)
        sys.exit(3)

    # --- try/finally que limpia <db>.tmp ante cualquier fallo ---
    # El directorio padre de <db>.tmp debe existir (path anidado inexistente se crea).
    try:
        db_tmp.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"No se pudo crear directorio de destino: {db_tmp.parent} ({exc})", file=sys.stderr)
        sys.exit(3)
    conn = None
    try:
        conn = sqlite3.connect(str(db_tmp))
        crear_tablas(conn)
        cur = conn.cursor()

        # producto en orden de aparicion del array
        for p in productos:
            insertar_producto(cur, p)
        for p in productos:
            insertar_eans(cur, p)
            insertar_almacenes_producto(cur, p)

        # almacen: 169 filas verbatim de nombres; tipo para los 8 publicados, NULL para el resto
        nombres = metadata.get("almacenes", {}).get("nombres", {}) if isinstance(metadata.get("almacenes"), dict) else {}
        publicados = metadata.get("almacenes", {}).get("almacenes", {}) if isinstance(metadata.get("almacenes"), dict) else {}
        if not isinstance(nombres, dict):
            nombres = {}
        if not isinstance(publicados, dict):
            publicados = {}
        insertar_almacenes(cur, nombres, publicados)

        # advertir ids de producto.almacenes fuera de nombres (hoy 0, no fatal)
        ids_producto = set()
        for p in productos:
            ids_producto.update(p["almacenes"])
        fuera_nombres = sorted(ids_producto - set(nombres.keys()))
        if not quiet:
            detalle = (
                f" ({', '.join(fuera_nombres[:10])}{'...' if len(fuera_nombres) > 10 else ''})"
                if fuera_nombres
                else ""
            )
            print(f"almacenes_sin_nombre: {len(fuera_nombres)}{detalle}", file=sys.stderr)

        insertar_metadata(cur, metadata, json_sha256, json_bytes)

        # s1_universo y cruce_s1: cuando incluido=false ambas quedan vacías (exit 0).
        universo_set = set(universo_skus)
        if incluido:
            for sku in sorted(universo_set):
                cur.execute("INSERT INTO s1_universo (sku) VALUES (?)", (sku,))
            cruce_filas = construir_cruce(productos, universo_skus, incluido)
            for sku, en_cat, en_uni, motivo, origen in cruce_filas:
                cur.execute(
                    "INSERT INTO cruce_s1 (sku, en_catalogo, en_universo, motivo, origen) VALUES (?, ?, ?, ?, ?)",
                    (sku, en_cat, en_uni, motivo, origen),
                )
        else:
            cruce_filas = []

        # Invariante: sin_catalogo == 0 si cobertura consistente (solo cuando
        # el universo entra: incluido=true). Con incluido=false no hay universo
        # ni cruce que validar.
        if incluido:
            sin_catalogo = sum(1 for _, _, _, motivo, _ in cruce_filas if motivo == "sin_catalogo")
            if sin_catalogo > 0:
                print("Invariante rota: sin_catalogo > 0 (cobertura inconsistente)", file=sys.stderr)
                sys.exit(4)

        conn.commit()
    except SystemExit:
        # sys.exit(3)/4 (contrato/invariante) bypassan el except Exception que
        # hace unlink(); limpiar <db>.tmp aca para no dejar basura tras un kill
        # violento o un fallo de contrato/invariante.
        try:
            if db_tmp.exists():
                db_tmp.unlink()
        except OSError:
            pass
        raise
    except Exception as exc:  # fallo ruidoso: limpia tmp y avisa
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        try:
            if db_tmp.exists():
                db_tmp.unlink()
        except OSError:
            pass
        print(f"Fallo construyendo BD: {exc}", file=sys.stderr)
        sys.exit(3)
    finally:
        if conn:
            conn.close()

    # Reemplazo atomico
    try:
        os.replace(str(db_tmp), str(db_path))
    except OSError as exc:
        print(f"No se pudo reemplazar {db_path}: {exc}", file=sys.stderr)
        try:
            if db_tmp.exists():
                db_tmp.unlink()
        except OSError:
            pass
        sys.exit(3)

    if not quiet:
        print(
            f"BD generada: {db_path} ({len(productos)} productos, "
            f"sha256={json_sha256[:16]}..., bytes={json_bytes})"
        )


# ---------------------------------------------------------------------------
# --check: verificacion sin escritura
# ---------------------------------------------------------------------------

def check_db(doc, bytes_json, db_path: Path, metadata) -> bool:
    """Verifica que la BD refleje el JSON. Retorna True si esta al dia."""
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error:
        return False
    try:
        cur = conn.cursor()

        # (b) json_sha256 == sha256(bytes JSON) y json_bytes == tamaño archivo
        cur.execute("SELECT json_sha256, json_bytes FROM catalogo_metadata WHERE id=1")
        fila = cur.fetchone()
        if fila is None:
            return False
        sha_bd, bytes_bd = fila
        if sha_bd != hashlib.sha256(bytes_json).hexdigest():
            return False
        if bytes_bd != len(bytes_json):
            return False

        # (c) PRAGMA user_version == 1
        cur.execute("PRAGMA user_version")
        if cur.fetchone()[0] != USER_VERSION:
            return False

        # (d) existen las 7 tablas
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tablas = {r[0] for r in cur.fetchall()}
        requeridas = {
            "producto", "producto_ean", "producto_almacen", "almacen",
            "catalogo_metadata", "s1_universo", "cruce_s1",
        }
        if not requeridas <= tablas:
            return False

        # (e) COUNT(producto) == total_productos
        cur.execute("SELECT COUNT(*) FROM producto")
        if cur.fetchone()[0] != metadata["total_productos"]:
            return False

        # (f)/(g) s1_universo y cruce_s1 segun incluido
        universo_stock = metadata.get("universo_stock") or {}
        incluido = bool(universo_stock.get("incluido", False))
        universo_skus = metadata.get("universo_skus") or []
        cur.execute("SELECT COUNT(*) FROM s1_universo")
        count_s1 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM cruce_s1")
        count_cruce = cur.fetchone()[0]
        if incluido:
            if count_s1 != len(universo_skus):
                return False
            cruce_via_interseccion = cur.execute(
                "SELECT COUNT(*) FROM (SELECT sku FROM producto INTERSECT SELECT sku FROM s1_universo)"
            ).fetchone()[0]
            if count_cruce != cur.execute("SELECT COUNT(*) FROM producto").fetchone()[0] + count_s1 - cruce_via_interseccion:
                return False
        else:
            if count_s1 != 0 or count_cruce != 0:
                return False

        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Genera data/catalogo.db desde output/catalogo_productos.json (SQLite, regenerable, solo stdlib)."
    )
    parser.add_argument("--json", default="output/catalogo_productos.json", help="Ruta al JSON de entrada (default: output/catalogo_productos.json)")
    parser.add_argument("--db", default="data/catalogo.db", help="Ruta de la BD SQLite de salida (default: data/catalogo.db)")
    parser.add_argument("--check", action="store_true", help="Verifica que la BD refleje el JSON sin escribir nada")
    parser.add_argument("--quiet", action="store_true", help="Suprime avisos de stderr")
    return parser.parse_args(argv)


def _main(argv=None) -> int:
    args = parse_args(argv)
    ruta_json = Path(args.json)
    db_path = Path(args.db)
    db_tmp = Path(str(db_path) + ".tmp")

    # Build: borrar <db>.tmp preexistente al inicio (además del finally),
    # para que un kill violento no deje basura. Solo para build (no --check).
    if not args.check:
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"No se pudo crear directorio de destino: {db_path.parent} ({exc})", file=sys.stderr)
            return 2
        if db_tmp.exists():
            try:
                db_tmp.unlink()
            except OSError as exc:
                print(f"No se pudo borrar {db_tmp} preexistente: {exc}", file=sys.stderr)
                return 3

    doc, bytes_json = leer_json(ruta_json)
    metadata, productos = validar_contrato(doc, bytes_json)

    if args.check:
        ok = check_db(doc, bytes_json, db_path, metadata)
        if ok:
            return 0
        print(MSG_OBSOLETA, file=sys.stderr)
        return 1

    build_db(doc, bytes_json, db_path, db_tmp, args.quiet)
    return 0


def main(argv=None) -> int:
    """Punto de entrada: captura SystemExit (salidas 2/3/4) y los retorna como
    codigo para que los tests y el llamador los lean sin abortar el proceso."""
    try:
        return _main(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
