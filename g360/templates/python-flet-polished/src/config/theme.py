import json
import logging
from pathlib import Path

_logger = logging.getLogger("g360.app")

# ---------------------------------------------------------------------------
# Paleta desde los tokens G360
#
# Los tokens se generan con `g360 tokens` (o `g360 set-accent <familia>`) y
# quedan en src/core/g360_tokens.py. Este modulo solo los adapta a los roles
# que usa la app: no hay ningun color escrito a mano.
#
#   from src.core.g360_tokens import TOKENS
# ---------------------------------------------------------------------------

try:
    from src.core.g360_tokens import TOKENS
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "Faltan los design tokens (src/core/g360_tokens.py). "
        "Generalos con: g360 tokens --project ."
    ) from _exc


def _mix(a: str, b: str, ratio: float) -> str:
    """Mezcla dos colores hex (ratio 0 = a, 1 = b)."""

    def channels(value):
        value = value.lstrip("#")
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        return [int(value[i : i + 2], 16) for i in (0, 2, 4)]

    ca, cb = channels(a), channels(b)
    mixed = [round(ca[i] * (1 - ratio) + cb[i] * ratio) for i in range(3)]
    return "#" + "".join(f"{c:02X}" for c in mixed)


def _rgba(hex_color: str, opacity: float) -> str:
    """Color hex con alpha en formato #RRGGBBAA."""
    value = hex_color.lstrip("#")
    if len(value) == 8:
        return f"#{value.upper()}"
    alpha = int(max(0.0, min(1.0, opacity)) * 255)
    return f"#{alpha:02X}{value.upper()}"


def _build_palette(mode: str) -> dict:
    """Construye la paleta de la app a partir de los tokens del tema."""
    tokens = TOKENS.get(mode, TOKENS["dark"])
    chart = TOKENS.get("chart", {}).get(mode, [])

    def chart_color(index: int) -> str:
        """Color de la serie `index` de la paleta categorica."""
        return chart[index].upper() if index < len(chart) else palette_accent

    surface = tokens["surface"]
    background = tokens["bg"]
    text = tokens["text"]
    muted = tokens["textMuted"]
    palette_accent = tokens["accent"].upper()
    palette = {
        # Acento (roles canonicos)
        "accent": tokens["accent"].upper(),
        "accent_dark": tokens["accentStrong"].upper(),
        "accent_bright": tokens["accentBright"].upper(),
        "accent_soft": tokens["accentSoft"],
        "accent_hover": tokens["accentHover"].upper(),
        "on_accent": tokens["onAccent"].upper(),
        # Estados
        "success": tokens["success"].upper(),
        "warning": tokens["warning"].upper(),
        "error": tokens["error"].upper(),
        "info": tokens["info"].upper(),
        # Superficies
        "background": background.upper(),
        "surface": surface.upper(),
        "surface_variant": tokens["surfaceAlt"].upper(),
        "surface_sunken": _mix(surface, background, 0.45),
        "border": tokens["border"],
        # Texto
        "text_primary": text.upper(),
        "text_secondary": _mix(text, muted, 0.45),
        "text_muted": muted.upper(),
        # Series de datos (paleta categorica)
        "cyan": chart_color(0),
        "violet": chart_color(1),
        "pink": chart_color(4),
        "orange": chart_color(7),
    }

    # Escala de KPIs: una serie por rol, para que cada grafico tenga color propio.
    kpi_roles = [
        "primary",
        "secondary",
        "tertiary",
        "quaternary",
        "quinary",
        "senary",
        "septenary",
        "octonary",
    ]
    palette["kpis"] = {role: chart_color(index) for index, role in enumerate(kpi_roles)}

    return palette


def get_colors(mode: str = None, skill_path: Path = None) -> dict:
    """
    Carga la paleta de colores para el modo especificado.

    Prioridad:
    1. skill.json del proyecto (si define colores propios)
    2. Tokens generados (src/core/g360_tokens.py)

    Args:
        mode: 'dark' o 'light'. Si es None, lee de la preferencia guardada.
        skill_path: Ruta al skill.json. Si es None, busca automaticamente.

    Returns:
        dict con los colores aplicados
    """
    if mode is None:
        mode = load_theme_preference()

    defaults = _build_palette(mode)

    skill_colors = _load_skill_colors(skill_path)

    if not skill_colors:
        return defaults

    # Los tokens son la fuente de la paleta (acentos y neutros por tema).
    # El skill.json solo puede ajustar la paleta de series (kpis): sobreescribir
    # el acento ahi pisaria el tono claro con el oscuro.
    colors = dict(defaults)
    if "kpis" in skill_colors:
        colors["kpis"] = {**defaults.get("kpis", {}), **skill_colors["kpis"]}

    return colors


def _load_skill_colors(skill_path: Path = None) -> dict | None:
    """Carga colores desde skill.json del proyecto."""
    try:
        if skill_path is None:
            skill_path = _find_skill_json()

        if skill_path and skill_path.exists():
            with open(skill_path, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("colors", {})
    except Exception as ex:
        _logger.debug("theme: skill colors not loaded: %s", ex)
    return None


def _find_skill_json() -> Path | None:
    """Busca skill.json en las ubicaciones posibles."""
    candidates = [
        Path("skill.json"),
        Path("src/core/skill.json"),
        Path(__file__).resolve().parent.parent.parent / "skill.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def rgba(color: str, opacity: float) -> str:
    """Convierte un color hex a rgba con la opacidad especificada."""
    if color.startswith("#") and len(color) == 9:
        return color  # Ya tiene alpha
    if color.startswith("#") and len(color) == 7:
        hex_color = color[1:]
        alpha = int(max(0.0, min(1.0, opacity)) * 255)
        return f"#{alpha:02x}{hex_color}"
    return color  # Retornar como esta si no es hex valido


def get_theme_file() -> Path:
    """Retorna la ruta del archivo de preferencia de tema."""
    app_name = _get_app_name()
    return Path.home() / ".g360" / f"{app_name}_config.json"


def _get_app_name() -> str:
    """Obtiene el nombre de la app desde skill.json o el nombre del directorio."""
    try:
        skill_path = _find_skill_json()
        if skill_path and skill_path.exists():
            with open(skill_path, encoding="utf-8") as f:
                data = json.load(f)
                name = data.get("build", {}).get("name") or data.get("name")
                if name:
                    return str(name)
    except Exception as ex:
        _logger.debug("theme: app name not loaded from skill.json: %s", ex)
    return Path.cwd().name


def load_theme_preference() -> str:
    """Lee el modo de tema preferido (dark por defecto)."""
    try:
        config_file = get_theme_file()
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)
                return config.get("theme_mode", "dark")
    except Exception as ex:
        _logger.debug("theme: preference not loaded: %s", ex)
    return "dark"


def save_theme_preference(mode: str):
    """Guarda el modo de tema preferido."""
    try:
        config_file = get_theme_file()
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)
        config["theme_mode"] = mode
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as ex:
        _logger.debug("theme: could not save preference: %s", ex)
