from pathlib import Path
import logging
import os

_logger = logging.getLogger("g360.app")

try:
    import tomllib
except ImportError:
    import tomli as tomllib

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR = ASSETS_DIR / "data"

WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 600

AUTO_REFRESH_INTERVAL = 900

CACHE_FILE = DATA_DIR / ".last_raw.json"
VERSION_CACHE_FILE = DATA_DIR / ".version_check.json"
VERSION_CHECK_INTERVAL = 86400

LOG_PATH = BASE_DIR / "run_log.txt"


def get_local_version() -> str:
    pyproject = BASE_DIR / "pyproject.toml"
    if not pyproject.exists():
        return "0.0.0"
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        return str(data.get("project", {}).get("version", "0.0.0"))
    except Exception:
        return "0.0.0"


def get_app_name() -> str:
    skill_path = BASE_DIR / "skill.json"
    if skill_path.exists():
        try:
            with open(skill_path, encoding="utf-8") as f:
                import json
                data = json.load(f)
                return data.get("name", "g360-app")
        except Exception as ex:
            _logger.debug("constants: app name not loaded from skill.json: %s", ex)
    return BASE_DIR.name
