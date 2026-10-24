import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


_KEYWORDS_ID = [
    "sku", "codigo", "cod_art", "articulo", "id_cliente", "doc_cliente",
    "id_vendedor", "id_linea", "id_grupo", "id_tipo", "id_familia",
    "id_articulo", "cod_sucursal", "serie_doc", "nro_doc", "id_guia",
    "id_pedido", "id_localidad_ubigeo",
]
_KEYWORDS_TEXTO = [
    "linea", "nombre", "razon_social", "descripcion", "departamento",
    "provincia", "distrito", "vendedor", "condicion", "division", "estado",
    "canal", "moneda", "referencia", "grupo", "tipo", "familia", "sucursal",
]
_KEYWORDS_DINERO = [
    "neto", "bruto", "venta", "valor", "total", "soles", "dolares",
]
_KEYWORDS_CANTIDAD = [
    "cantidad",
]
_KEYWORDS_FECHA = ["fecha", "fec_", "venc"]

_ENTITY_LABELS = {
    ("id_cliente", "nom_cliente"): "cliente_label",
    ("id_vendedor", "nom_vendedor"): "vendedor_label",
    ("id_articulo", "nom_articulo"): "articulo_label",
    ("id_linea", "nom_linea"): "linea_label",
    ("id_grupo", "nom_grupo"): "grupo_label",
    ("id_tipo", "nom_tipo"): "tipo_label",
    ("id_familia", "nom_familia"): "familia_label",
    ("cod_sucursal", "nom_sucursal"): "sucursal_label",
}

_MAPA_TPO_DOC = {
    "NCR": "NOTA DE CREDITO",
    "NDB": "NOTA DE DEBITO",
    "BDI": "BIEN / BOLETA",
    "FAC": "FACTURA",
    "NV":  "NOTA DE VENTA",
    "GV":  "GUIA DE VENTA",
    "FC":  "FACTURA CREDITO",
    "NC":  "NOTA DE CREDITO",
    "ND":  "NOTA DE DEBITO",
    "BO":  "BOLETA",
}

_MAPA_MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12,
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}

_PATRON_DIRECCION = re.compile(
    r'^(JR\.?\s|AV\.?\s|AVENIDA\s|CALLE\s|PASAJE\s|PSJE\.?\s|'
    r'CARRETERA\s|CARRE\.?\s|MZA\.?\s|LOTE\s|URB\.?\s|'
    r'FUNDO\s|SECTOR\s|PARQUE\s|PLAZA\s|ALAMEDA\s|JR|AV)\b',
    re.IGNORECASE,
)

_PATRON_REFERENCIA = re.compile(
    r'^([A-Za-z]+)(\d+)[/.-]?(\d{1,4})?[/.-]?(\d+)?$'
)


def _limpiar_cabecera(col: str) -> str:
    if not isinstance(col, str):
        col = str(col)
    col = col.strip().lower()
    col = "".join(
        c for c in unicodedata.normalize("NFD", col)
        if unicodedata.category(c) != "Mn"
    )
    col = col.replace(" ", "_").replace(".", "").replace("/", "_")
    col = re.sub(r"_+", "_", col)
    col = col.strip("_")
    return col


def _coincide_keywords(nombre_col: str, keywords: list[str]) -> bool:
    return any(kw in nombre_col for kw in keywords)


def _detectar_formato_numero(series: pd.Series) -> str:
    muestras = series.dropna().astype(str).head(50)
    coma_decimal = muestras.str.contains(r',\d{2}$', regex=True).sum()
    punto_decimal = muestras.str.contains(r'\.\d{2}$', regex=True).sum()
    if coma_decimal > punto_decimal:
        return "spring"
    if punto_decimal > coma_decimal:
        return "sap"
    return "simple"


def _normalizar_monetario(series: pd.Series) -> pd.Series:
    if series.dtype != object:
        return pd.to_numeric(series, errors="coerce").fillna(0.0)
    fmt = _detectar_formato_numero(series)
    if fmt == "spring":
        series = series.astype(str).str.replace(".", "", regex=False)
        series = series.str.replace(",", ".", regex=False)
    elif fmt == "sap":
        series = series.astype(str).str.replace(",", "", regex=False)
    series = (
        series.astype(str)
        .str.replace("S/.", "", regex=False)
        .str.replace("S//.", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("US$", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _parsear_referencia(series: pd.Series) -> pd.DataFrame:
    tipos: list[str | None] = []
    series_doc: list[str | None] = []
    periodos: list[str | None] = []
    numeros: list[str | None] = []
    for val in series:
        if pd.isna(val):
            tipos.append(None)
            series_doc.append(None)
            periodos.append(None)
            numeros.append(None)
            continue
        m = _PATRON_REFERENCIA.match(str(val).strip())
        if m:
            tipos.append(m.group(1).upper())
            series_doc.append(m.group(2))
            periodos.append(m.group(3))
            numeros.append(m.group(4))
        else:
            tipos.append(None)
            series_doc.append(None)
            periodos.append(None)
            numeros.append(None)
    return pd.DataFrame({
        "ref_tipo_doc": tipos,
        "ref_serie": series_doc,
        "ref_periodo": periodos,
        "ref_nro": numeros,
    })


def _extraer_nombre_desde_direccion(
    direccion: str,
    lugares: list[str],
) -> str | None:
    tokens = re.split(r'[,\s]+', direccion.strip())
    tokens = [t for t in tokens if t]
    for t in reversed(tokens):
        t_clean = t.strip(".").upper()
        if t_clean in lugares:
            return t_clean.capitalize()
    if tokens:
        return tokens[-1].capitalize()
    return None


def _es_direccion(val: object) -> bool:
    if pd.isna(val):
        return False
    s = str(val).strip()
    if not s:
        return False
    return bool(_PATRON_DIRECCION.match(s)) or "N°" in s or "NRO" in s.upper()


def _parsear_sucursal_fila(
    val: object, lugares: list[str]
) -> tuple[str | None, str | None]:
    if pd.isna(val):
        return None, None
    s = str(val).strip()
    if not s:
        return None, None
    if _es_direccion(s):
        nombre = _extraer_nombre_desde_direccion(s, lugares)
        return nombre, s
    return s, None


def _parsear_sucursal(
    df: pd.DataFrame,
    col_nom: str = "nom_sucursal",
    col_depto: str = "nom_departamento",
    col_prov: str = "nom_provincia",
    col_dist: str = "nom_distrito",
) -> pd.DataFrame:
    if col_nom not in df.columns:
        df["sucursal_nombre"] = None
        df["sucursal_direccion"] = None
        return df

    lugares: list[str] = []
    for c in [col_depto, col_prov, col_dist]:
        if c in df.columns:
            lugares.extend(
                str(v).strip().upper()
                for v in df[c].dropna().unique()
                if str(v).strip()
            )
    lugares = list(set(lugares))

    resultados = df[col_nom].apply(lambda v: _parsear_sucursal_fila(v, lugares))
    df["sucursal_nombre"] = resultados.apply(lambda x: x[0])
    df["sucursal_direccion"] = resultados.apply(lambda x: x[1])

    return df


def _clasificar_doc_cliente(val: object) -> tuple[str, str]:
    limpio = re.sub(r"\D", "", str(val))
    if len(limpio) == 11:
        return limpio, "RUC"
    elif len(limpio) == 8:
        return limpio.zfill(8), "DNI"
    elif len(limpio) > 0:
        return limpio, "OTRO"
    return "", "SIN_DOC"


def _parsear_mes(val: object) -> tuple[int | None, str | None]:
    if pd.isna(val):
        return None, None
    s = str(val).strip().upper()
    m = re.match(r'^(\d{1,2})[-/](\w+)$', s)
    if m:
        num = int(m.group(1))
        nombre = m.group(2).capitalize()
        return num, nombre
    if s.isdigit():
        return int(s), None
    if s in _MAPA_MESES:
        return _MAPA_MESES[s], s.capitalize()
    return None, None


def _clasificar_transaccion(row: dict) -> str:
    cant = row.get("cantidad", 0)
    cant_fae = row.get("cantidad_fae", 0)
    if cant > 0 and cant_fae == 0:
        return "venta"
    if cant < 0 and cant_fae == 0:
        return "devolucion"
    if cant == 0 and cant_fae != 0:
        return "regularizacion"
    if cant != 0 and cant_fae != 0:
        return "mixto"
    return "indefinido"


def _build_entity_labels(df: pd.DataFrame) -> pd.DataFrame:
    for (id_col, name_col), label_col in _ENTITY_LABELS.items():
        id_exists = id_col in df.columns
        name_exists = name_col in df.columns
        
        if id_exists and name_exists:
            id_vals = df[id_col].fillna("").astype(str).str.strip()
            name_vals = df[name_col].fillna("").astype(str).str.strip()
            df[label_col] = np.where(
                (id_vals != "") & (name_vals != ""),
                id_vals + " - " + name_vals,
                np.where(id_vals != "", id_vals, name_vals)
            )
        elif id_exists:
            df[label_col] = df[id_col].astype(str).str.strip()
        elif name_exists:
            df[label_col] = df[name_col].astype(str).str.strip()
    return df


def estabilizar_excel_crudo(ruta_archivo: str | Path) -> tuple[pd.DataFrame, dict]:
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {ruta}")

    sufijo = ruta.suffix.lower()
    if sufijo == ".xls":
        engine = "xlrd"
    elif sufijo in (".xlsx", ".xlsm"):
        engine = "openpyxl"
    else:
        engine = None

    transformaciones: list[str] = []
    alertas: list[str] = []

    df = pd.read_excel(ruta, engine=engine)
    transformaciones.append(f"lectura: {len(df)} filas, {len(df.columns)} columnas")

    cols_originales = list(df.columns)

    # ── 1. Normalizar cabeceras ──
    df.columns = [_limpiar_cabecera(c) for c in df.columns]
    transformaciones.append("cabeceras: normalizadas (lower, sin tildes, snake_case)")

    # ── 2. Resolver duplicados en cabeceras ──
    duplicados = [c for c in df.columns.tolist() if df.columns.tolist().count(c) > 1]
    if duplicados:
        vistos: dict[str, int] = {}
        nuevas: list[str] = []
        for c in df.columns:
            if c in vistos:
                vistos[c] += 1
                nuevas.append(f"{c}_{vistos[c]}")
            else:
                vistos[c] = 0
                nuevas.append(c)
        df.columns = nuevas
        transformaciones.append(f"cabeceras: {len(set(duplicados))} columna(s) duplicada(s) renombrada(s)")

    # ── 3. Eliminar filas totalmente vacías ──
    df = df.dropna(how="all").copy()
    transformaciones.append(f"filas: {len(df)} tras eliminar vacias totales")

    # ── 4. Parsear REFERENCIA ──
    if "referencia" in df.columns:
        ref_parsed = _parsear_referencia(df["referencia"])
        for c in ref_parsed.columns:
            df[c] = ref_parsed[c].values
        transformaciones.append("referencia: parseada en ref_tipo_doc, ref_serie, ref_periodo, ref_nro")

    # ── 5. Parsear NOM_SUCURSAL ──
    df = _parsear_sucursal(df)
    if "sucursal_nombre" in df.columns and "sucursal_direccion" in df.columns:
        transformaciones.append("sucursal: separada nombre/direccion")

    if ("nom_sucursal" in df.columns and "sucursal_nombre" in df.columns and
            df["sucursal_nombre"].isna().any()):
        alertas.append("sucursal: algunos nombres no pudieron determinarse")

    # ── 6. Normalizar MES ──
    if "mes" in df.columns:
        parsed = df["mes"].apply(_parsear_mes)
        df["mes_num"] = parsed.apply(lambda x: x[0])
        df["mes_nombre"] = parsed.apply(lambda x: x[1])
        transformaciones.append("mes: separado en mes_num y mes_nombre")

    # ── 7. Mapear TPO_DOC ──
    if "tpo_doc" in df.columns:
        df["tipo_doc_nombre"] = df["tpo_doc"].map(_MAPA_TPO_DOC)
        codigos_no_mapeados = df["tpo_doc"].dropna().unique()
        no_map = [c for c in codigos_no_mapeados if c not in _MAPA_TPO_DOC]
        if no_map:
            for c in no_map:
                limpio = re.sub(r'\d', '', str(c)).strip()
                _MAPA_TPO_DOC[c] = limpio if limpio else c
            df["tipo_doc_nombre"] = df["tpo_doc"].map(_MAPA_TPO_DOC).fillna("OTRO")
            alertas.append(f"tpo_doc: codigos sin mapeo: {', '.join(sorted(str(c) for c in no_map))}")
        transformaciones.append("tpo_doc: mapeado a nombre legible")

    # ── 8. Columnas ID ──
    for col in df.columns:
        if _coincide_keywords(col, _KEYWORDS_ID):
            was_numeric = pd.api.types.is_numeric_dtype(df[col])
            df[col] = (
                df[col].astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .str.strip()
            )
            if was_numeric:
                vals_clean = df[col].replace("nan", np.nan).dropna()
                if len(vals_clean) > 0:
                    max_len = int(vals_clean.str.len().max())
                    has_shorter = (vals_clean.str.len() < max_len).any()
                    if has_shorter and max_len > 1:
                        df[col] = df[col].str.zfill(max_len)
                        transformaciones.append(f"{col}: leading zeros restaurados (zfill={max_len})")
            df[col] = df[col].replace("nan", np.nan)

    # ── 9. Normalizar DOC_CLIENTE (despues de ID para tener strings limpios) ──
    for col in [c for c in df.columns if _coincide_keywords(c, ["doc_cliente"])]:
        parsed = df[col].apply(_clasificar_doc_cliente)
        tipo_col = f"tipo_{col}"
        clean_col = f"{col}_clean"
        df[clean_col] = parsed.apply(lambda x: x[0])
        df[tipo_col] = parsed.apply(lambda x: x[1])
        ruc_count = (df[tipo_col] == "RUC").sum()
        dni_count = (df[tipo_col] == "DNI").sum()
        transformaciones.append(
            f"{col}: normalizado ({ruc_count} RUC, {dni_count} DNI, "
            f"{(~df[tipo_col].isin(['RUC','DNI'])).sum()} otros)"
        )
    
    # ── 9b. CLIENTE_FULL_LABEL = ID + DOC_CLIENTE_CLEAN + NOMBRE ──
    if "id_cliente" in df.columns and "doc_cliente_clean" in df.columns:
        id_vals = df["id_cliente"].fillna("").astype(str).str.strip()
        doc_vals = df["doc_cliente_clean"].fillna("").astype(str).str.strip()
        name_vals = df["nom_cliente"].fillna("").astype(str).str.strip() if "nom_cliente" in df.columns else None
        
        if name_vals is not None:
            df["cliente_full_label"] = np.where(
                (id_vals != "") & (doc_vals != "") & (name_vals != ""),
                id_vals + " - " + doc_vals + " - " + name_vals,
                np.where((id_vals != "") & (doc_vals != ""), id_vals + " - " + doc_vals, id_vals)
            )
        else:
            df["cliente_full_label"] = id_vals + " - " + doc_vals
        transformaciones.append("cliente_full_label: ID + DOC_CLIENTE_CLEAN + NOM_CLIENTE")

    # ── 10. Columnas TEXTO ──
    for col in df.columns:
        if _coincide_keywords(col, _KEYWORDS_TEXTO):
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace("nan", np.nan)
            df[col] = df[col].apply(
                lambda v: unicodedata.normalize("NFC", v) if isinstance(v, str) else v
            )

    # ── 11. Columnas DINERO ──
    for col in df.columns:
        if _coincide_keywords(col, _KEYWORDS_DINERO):
            antes = df[col].dtype
            df[col] = _normalizar_monetario(df[col])
            if str(antes) != str(df[col].dtype):
                transformaciones.append(f"{col}: monetario normalizado a float64")
            nulos = (df[col] == 0.0).sum()
            if nulos > 0:
                transformaciones.append(f"{col}: {nulos} valor(es) zero por NaN original")

    # ── 12. Columnas CANTIDAD ──
    cols_cantidad = [c for c in df.columns if _coincide_keywords(c, _KEYWORDS_CANTIDAD)]
    for col in cols_cantidad:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        transformaciones.append(f"{col}: forzado a float64, NaN → 0.0")

    # ── 12b. PRECIO_BASE (precio unitario por fila) ──
    if "soles" in df.columns and cols_cantidad:
        cant_col = cols_cantidad[0]
        cant = df[cant_col].fillna(0)
        soles = df["soles"].fillna(0)
        df["precio_base"] = np.where(
            cant != 0,
            np.round(soles / cant.abs(), 4),
            np.nan
        )
        transformaciones.append(f"precio_base: SOLES / {cant_col}")

    # ── 13. cantidad + cantidad_fae → cantidad_total, tipo_transaccion ──
    if "cantidad" in df.columns:
        if "cantidad_fae" in df.columns:
            df["cantidad_total"] = df["cantidad"] + df["cantidad_fae"]
            transformaciones.append("cantidad_total: suma de cantidad + cantidad_fae")
        else:
            df["cantidad_total"] = df["cantidad"]
        df["tipo_transaccion"] = df.apply(_clasificar_transaccion, axis=1)
        t_counts = df["tipo_transaccion"].value_counts().to_dict()
        transformaciones.append(f"tipo_transaccion: {t_counts}")

    # ── 13b. Construir columnas _LABEL (ID - Nombre) para UI ──
    cols_before_labels = list(df.columns)
    df = _build_entity_labels(df)
    label_cols_added = [c for c in df.columns if c.endswith("_label") and c not in cols_before_labels]
    if label_cols_added:
        transformaciones.append(f"labels: {', '.join(label_cols_added)} generados")

    # ── 14. Columnas FECHA ──
    for col in df.columns:
        if _coincide_keywords(col, _KEYWORDS_FECHA) and col != "fec_":
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                continue
            antes_nulos = df[col].isna().sum()
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
            ahora_nulos = df[col].isna().sum()
            if ahora_nulos > antes_nulos:
                alertas.append(f"{col}: {ahora_nulos - antes_nulos} fecha(s) invalida(s) → NaT")
            df[col] = df[col].fillna(pd.Timestamp.now().normalize())
            transformaciones.append(f"{col}: datetime + NaT → today")

    # ── 15. Validar MONEDA ──
    if "moneda" in df.columns:
        monedas = df["moneda"].dropna().unique()
        monedas_str = [str(m).strip().upper() for m in monedas]
        validas = {"SOL", "S/.", "PEN", "S/."}
        if not all(m in validas for m in monedas_str):
            raras = [m for m in monedas_str if m not in validas]
            alertas.append(f"moneda: valores no esperados: {raras}")
        transformaciones.append(f"moneda: todas en soles ({', '.join(monedas_str)})")
        df["moneda_cod"] = "PEN"

    # ── 16. Purga filas basura ──
    for col in df.columns:
        if df[col].dtype == object:
            muestra = df[col].dropna().head(20).astype(str).tolist()
            if any(
                isinstance(v, str) and v.lower().strip() in ("total", "general", "totales", "acumulado")
                for v in muestra
            ):
                mascara = df[col].astype(str).str.lower().str.strip().isin(
                    ["total", "general", "totales", "acumulado"]
                )
                n = mascara.sum()
                df = df[~mascara].copy()
                if n:
                    transformaciones.append(f"basura: {n} fila(s) 'total/general' eliminadas")

    cols_id_presentes = [c for c in df.columns if _coincide_keywords(c, _KEYWORDS_ID)]
    if cols_id_presentes:
        mascara_ids_nulos = df[cols_id_presentes].isna().all(axis=1) | (
            df[cols_id_presentes].astype(str).replace("nan", "") == ""
        ).all(axis=1)
        mascara_dinero_cero = True
        cols_dinero_presentes = [
            c for c in df.columns if _coincide_keywords(c, _KEYWORDS_DINERO)
        ]
        if cols_dinero_presentes:
            mascara_dinero_cero = (df[cols_dinero_presentes] == 0.0).all(axis=1)
        cols_cant_presentes = [c for c in df.columns if _coincide_keywords(c, _KEYWORDS_CANTIDAD)]
        if cols_cant_presentes:
            mascara_dinero_cero = mascara_dinero_cero & (df[cols_cant_presentes] == 0.0).all(axis=1)
        mascara_fila_total = mascara_ids_nulos & (
            ~mascara_dinero_cero if isinstance(mascara_dinero_cero, pd.Series) else True
        )
        n_purge = mascara_fila_total.sum()
        df = df[~mascara_fila_total].copy()
        if n_purge:
            transformaciones.append(f"basura: {n_purge} fila(s) sin ID y con dinero eliminadas")

    df = df.reset_index(drop=True)

    metadata = {
        "archivo": str(ruta),
        "filas_originales": len(df) + sum(
            1 for t in transformaciones if "eliminadas" in t
        ),
        "filas_estabilizadas": len(df),
        "columnas_originales": cols_originales,
        "columnas_finales": list(df.columns),
        "columnas_nuevas": [
            c for c in df.columns if c not in [_limpiar_cabecera(x) for x in cols_originales]
        ],
        "transformaciones": transformaciones,
        "alertas": alertas,
        "moneda": "PEN",
    }

    return df, metadata
