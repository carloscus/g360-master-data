from __future__ import annotations

import hashlib
import json
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import flet as ft

from src.config.theme import get_colors, load_theme_preference, save_theme_preference
from src.core.constants import (
    AUTO_REFRESH_INTERVAL,
    CACHE_FILE,
    VERSION_CACHE_FILE,
    VERSION_CHECK_INTERVAL,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    get_local_version,
    get_app_name,
)
from src.ui.dashboard import Dashboard
from src.core.g360_registry import register_g360_app, get_event_bus

import logging
_log_logger = logging.getLogger("g360.app")
if not _log_logger.handlers:
    from logging.handlers import RotatingFileHandler
    _log_path = Path(__file__).resolve().parent.parent.parent / "run_log.txt"
    _fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    _handler = RotatingFileHandler(_log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    _handler.setFormatter(_fmt)
    _log_logger.addHandler(_handler)
    _log_logger.setLevel(logging.INFO)


def _log(msg: str):
    _log_logger.info(msg)


def _load_cache() -> tuple[dict, str | None]:
    """Carga el cache persistente. Retorna (raw_data, timestamp)."""
    if not CACHE_FILE.exists():
        return {}, None
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("raw_data", {})
        ts = data.get("timestamp")
        if raw:
            return raw, ts
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        _log(f"_load_cache: corrupt cache file, removing: {ex}")
        try:
            CACHE_FILE.unlink(missing_ok=True)
        except Exception as ex:
            _log(f"_load_cache: could not remove corrupt cache: {ex}")
    except Exception as ex:
        _log(f"_load_cache: unexpected error, starting with empty data: {ex}")
    return {}, None


def _hash_data(raw_data: dict) -> str:
    """SHA-256 del raw_data para detectar cambios sin descargar dos veces."""
    serialized = json.dumps(raw_data, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(serialized).hexdigest()[:16]


def _data_changed(new_data: dict, last_hash: str | None) -> tuple[bool, str]:
    """Retorna (changed, nuevo_hash)."""
    h = _hash_data(new_data)
    return h != last_hash, h


def _save_cache(raw_data: dict, api_timestamp: str | None = None):
    """Guarda raw_data completo."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "raw_data": raw_data,
            "timestamp": api_timestamp or datetime.now().isoformat(),
            "api_timestamp": api_timestamp,
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as ex:
        _log(f"_save_cache: ERROR {ex}")


class G360App:
    """
    Clase principal de la aplicacion G360 con Flet.

    Patrones implementados:
    - Dual theme (dark/light) con persistencia en ~/.g360/
    - Auto-refresh con lock thread-safe
    - Cache con hash diff para evitar rebuild innecesarios
    - Logger RotatingFileHandler
    - Shutdown limpio via page.on_close
    """

    def __init__(self, page: ft.Page):
        try:
            self.page = page
            self._raw_data: dict = {}
            self._theme_mode = load_theme_preference()
            self._setup_page()
            self.dashboard = Dashboard(page, self._theme_mode)
            if hasattr(self.dashboard, "set_on_theme_toggle"):
                self.dashboard.set_on_theme_toggle(self._toggle_theme)
            self.dashboard.set_on_refresh(self._on_refresh)
            self._cache_timestamp: str | None = None
            self._stale_data: bool = False
            self._local_version = get_local_version()
            self._last_auto_refresh: float = 0.0
            self._auto_refresh_stop: threading.Event | None = None
            self._download_lock = threading.Lock()
            self._last_data_hash: str | None = None
            self._build()
        except Exception:
            _log(f"[FATAL] G360App.__init__:\n{traceback.format_exc()}")
            raise

    def _setup_page(self):
        app_name = get_app_name()
        self.page.title = f"{app_name.title()} - G360"
        self.page.theme_mode = ft.ThemeMode.DARK if self._theme_mode == "dark" else ft.ThemeMode.LIGHT
        self.page.bgcolor = get_colors(self._theme_mode)["background"]
        self.page.padding = 0
        self.page.window_width = WINDOW_WIDTH
        self.page.window_height = WINDOW_HEIGHT
        self.page.window_min_width = WINDOW_MIN_WIDTH
        self.page.window_min_height = WINDOW_MIN_HEIGHT
        try:
            self.page.window_center()
        except AttributeError:
            _log("_setup_page: window_center() not available in this Flet version")

        fonts_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
        self.page.fonts = {
            "Inter": str(fonts_dir / "Inter-Variable.ttf"),
            "JetBrains Mono": str(fonts_dir / "JetBrainsMono-Variable.ttf"),
        }
        self.page.theme = ft.Theme(font_family="Inter")

    def _build(self):
        _log("_build: starting dashboard.build()...")
        view = self.dashboard.build()
        _log("_build: dashboard.build() OK")
        self.page.add(view)
        self.page.update()
        _log("_build: page.add + update OK")
        self.dashboard.register_overlay()
        _log("_build: overlay (FilePickers) registrado")

        # Registrar app en registry G360
        self._register_app()

        sample_path = Path(__file__).resolve().parent.parent / "assets" / "data" / "sample_data.json"
        cache, ts = _load_cache()
        if cache:
            _log(f"_build: loading cached data...")
            self._raw_data = cache
            self._cache_timestamp = ts
            _, initial_hash = _data_changed(cache, None)
            self._last_data_hash = initial_hash
            self.dashboard.update_data(cache, cache_timestamp=ts)
            self.page.update()
            _log(f"_build: cache loaded OK ({len(cache)} items)")
        elif sample_path.exists():
            _log("_build: cache empty, loading sample_data.json...")
            with open(sample_path, encoding="utf-8") as f:
                raw = json.load(f)
            self._raw_data = raw
            self.dashboard.update_data(raw)
            self.page.update()
            _log("_build: sample_data loaded OK")
        else:
            _log("_build: neither cache nor sample_data.json found")
            self.dashboard._show_empty_state("Sin datos disponibles")
            self.dashboard._set_empty_state_status("Esperando datos", self.dashboard.c["warning"])

        _log("_build: scheduling _delayed_load...")
        self.page.run_task(self._delayed_load)
        self._start_auto_refresh()
        _log("_build: done")

    def _toggle_theme(self):
        self._theme_mode = "light" if self._theme_mode == "dark" else "dark"
        save_theme_preference(self._theme_mode)
        self.page.theme_mode = ft.ThemeMode.DARK if self._theme_mode == "dark" else ft.ThemeMode.LIGHT
        self.page.bgcolor = get_colors(self._theme_mode)["background"]
        self.dashboard.update_theme(self._theme_mode)
        self.page.update()

    async def _delayed_load(self):
        import asyncio
        await asyncio.sleep(0.5)
        await self._load_data()

    async def _on_refresh(self):
        await self._load_data(is_manual=True)

    def _start_auto_refresh(self):
        try:
            self._auto_refresh_stop = threading.Event()
            t = threading.Thread(
                target=self._auto_refresh_loop,
                daemon=True,
                name="auto-refresh",
            )
            t.start()
            self._auto_refresh_thread = t
            _log(f"_start_auto_refresh: hilo iniciado ({AUTO_REFRESH_INTERVAL}s)")
        except Exception as ex:
            _log(f"_start_auto_refresh: ERROR {ex}")

    def _register_app(self):
        """Registrar la app en el registry G360."""
        try:
            skill_data = self._load_skill_config()
            events = skill_data.get("events", [])
            endpoints = skill_data.get("endpoints", {})
            
            register_g360_app(
                name=get_app_name(),
                version=self._local_version,
                skill=skill_data.get("skill", "custom"),
                framework="flet",
                events=events,
                endpoints=endpoints,
                description=skill_data.get("description", ""),
            )
            _log(f"_register_app: {get_app_name()} registrado en G360 registry")
        except Exception as ex:
            _log(f"_register_app: ERROR {ex}")

    def _load_skill_config(self) -> dict:
        """Cargar config del skill actual."""
        import json
        from pathlib import Path
        skill_path = Path(__file__).resolve().parent.parent.parent / "skill.json"
        if skill_path.exists():
            with open(skill_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def shutdown(self):
        """Detiene el auto-refresh y desregistra la app antes de cerrar."""
        if self._auto_refresh_stop:
            _log("_shutdown: deteniendo auto-refresh...")
            self._auto_refresh_stop.set()
            t = getattr(self, "_auto_refresh_thread", None)
            if t and t.is_alive():
                t.join(timeout=3)
            _log("_shutdown: auto-refresh detenido")
        
        # Desregistrar del registry
        try:
            from src.core.g360_registry import get_app_registry
            registry = get_app_registry()
            registry.update_status(get_app_name(), "offline")
            _log(f"_shutdown: {get_app_name()} desregistrado")
        except Exception as ex:
            _log(f"_shutdown: ERROR desregistrando {ex}")

    def _auto_refresh_loop(self):
        while not self._auto_refresh_stop.is_set():
            time.sleep(1)
            try:
                self._on_auto_refresh_tick()
            except Exception as ex:
                _log(f"_auto_refresh_loop: ERROR {ex}")

    def _on_auto_refresh_tick(self):
        try:
            if not self._cache_timestamp:
                return
            self.dashboard._update_refresh_status(self._cache_timestamp)
            if time.time() - self._last_auto_refresh < AUTO_REFRESH_INTERVAL:
                return
            self._last_auto_refresh = time.time()
            _log("_on_auto_refresh_tick: ejecutando auto-refresh")
            self.page.run_task(self._load_data, is_manual=False)
        except Exception as ex:
            _log(f"_on_auto_refresh_tick: ERROR {ex}")

    async def _load_data(self, is_manual=False):
        import time
        _t0 = time.time()
        _log(f"_load_data: start is_manual={is_manual}")
        self.dashboard.set_loading(True, "Descargando datos...")

        if not self._download_lock.acquire(blocking=False):
            _log("_load_data: otra descarga en curso, omitiendo")
            self.dashboard.set_loading(False)
            return

        try:
            import asyncio
            loop = asyncio.get_running_loop()
            _log("_load_data: calling _fetch_data in executor...")
            raw = await loop.run_in_executor(None, self._fetch_data)
            _log(f"_load_data: _fetch_data returned {type(raw).__name__}")

            if not raw:
                self.dashboard.set_loading(False)
                self.dashboard.status_text.value = "No se obtuvieron datos"
                self.dashboard.status_text.color = "#ef4444"
                self.dashboard._show_snack("Error: No se obtuvieron datos", is_error=True)
                if not self._raw_data:
                    self.dashboard._set_empty_state_status("Sin datos - API no disponible", self.dashboard.c["error"])
                _log("_load_data: no data, showing error")
                return

            changed, new_hash = _data_changed(raw, self._last_data_hash)
            if not changed:
                _log("_load_data: datos identicos, omitiendo UI refresh")
                self.dashboard.set_loading(False)
                self._download_lock.release()
                return

            self._raw_data = raw
            self._last_data_hash = new_hash
            _save_cache(raw)
            self._cache_timestamp = datetime.now().isoformat()
            self._last_auto_refresh = time.time()
            _log("_load_data: cache saved")
            self.dashboard.update_data(raw, cache_timestamp=self._cache_timestamp, stale=self._stale_data)
            self.dashboard._hide_empty_state()
            _log("_load_data: data updated in dashboard")
            if is_manual:
                self.dashboard._show_snack("Datos actualizados correctamente")
        except Exception as ex:
            _log(f"_load_data: EXCEPTION: {traceback.format_exc()}")
            self.dashboard.status_text.value = f"Error: {str(ex)}"
            self.dashboard.status_text.color = "#ef4444"
            self.dashboard._show_snack(f"Fallo en la descarga: {str(ex)}", is_error=True)
            self.dashboard.set_offline(True)
            if not self._raw_data:
                self.dashboard._set_empty_state_status("Error de conexión", self.dashboard.c["error"])
        finally:
            elapsed = time.time() - _t0
            _log(f"_load_data: elapsed={elapsed:.1f}s")
            self._download_lock.release()
            if elapsed < 2:
                self.dashboard.set_loading(True, "Actualizando vista...")
                self.page.update()
                import asyncio
                await asyncio.sleep(2 - elapsed)
            ts = self.dashboard.format_cache_timestamp(self._cache_timestamp) if not is_manual else ""
            self.dashboard._ts_text.value = f"Ultima act. {ts}"
            if self._stale_data:
                self.dashboard._ts_text.color = self.dashboard.c["warning"]
                self.dashboard._ts_text.value += " (caché)"
                self.dashboard.status_text.value = "Datos en caché (fuera de horario)"
                self.dashboard.status_text.color = self.dashboard.c["warning"]
                self.dashboard._show_stale_warning()
            else:
                self.dashboard._ts_text.color = self.dashboard.c["accent"]
                self.dashboard.status_text.value = "Datos actualizados"
                self.dashboard.status_text.color = self.dashboard.c["accent"]
                self.dashboard._hide_stale_warning()
            self.dashboard._update_refresh_status(self._cache_timestamp)
            self.dashboard.set_offline(False)
            self.dashboard.set_loading(False)
            self.page.update()
            _log("_load_data: done")

    def _fetch_data(self) -> dict | None:
        """
        Metodo que debe ser sobrescrito por subclases.
        Implementa la logica de descarga/fetch de datos.
        Retorna dict con los datos crudos o None si falla.
        """
        # Default: retorna None (no hay data)
        # Subclases deben override这个方法
        return None


def main(page: ft.Page):
    G360App(page)
