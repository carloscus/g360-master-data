from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Import pip-system-certs to fix SSL issues on Windows corporate networks
try:
    import pip_system_certs
    pip_system_certs.install()
except ImportError:
    pass  # Not available, continue without it

import flet as ft

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.app import G360App  # noqa: E402
from src.core.constants import LOG_PATH  # noqa: E402


_logger = logging.getLogger("g360.app")
if not _logger.handlers:
    _fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    _handler = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    _handler.setFormatter(_fmt)
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


def _log(msg: str):
    _logger.info(msg)


def main(page: ft.Page):
    app = G360App(page)
    page.on_close = lambda _: app.shutdown() if hasattr(app, "shutdown") else None


if __name__ == "__main__":
    _log("MAIN_START: __name__ == __main__")
    try:
        _log("PRE: llamando a ft.app(main) desktop...")
        ft.app(main, view=ft.AppView.FLET_APP)
        _log("POST: ft.app(main) retorno OK")
    except Exception as e:
        _log(f"[FATAL] Error en ft.run:\n{traceback.format_exc()}")
        print(f"\n[FATAL] Error al iniciar la aplicacion: {e}", flush=True)
        traceback.print_exc()
        input("\nPresione Enter para salir...")
