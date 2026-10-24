"""
G360 Dashboard - Template base con patrones pulidos.

Patrones disponibles:
- Sidebar colapsable con chips de filtro
- KPIs con glow backlight por color
- Buscador flotante con debounce
- Tablas paginadas con sort en headers
- Export a Excel con openpyxl
- Health filter por umbrales configurables
- Stale data detection
"""
from __future__ import annotations

import threading
from datetime import datetime

import flet as ft
from src.config.theme import get_colors, rgba
from src.ui.kpi_card import KPICard
from src.ui.search_overlay import SearchOverlay


class Dashboard:
    def __init__(self, page: ft.Page, theme_mode: str = "dark"):
        self.page = page
        self._theme_mode = theme_mode
        self.c = get_colors(self._theme_mode)
        self._search_timer = None
        self._theme_button: ft.IconButton | None = None

        # State
        self._raw_data: dict | None = None
        self._kpis: dict | None = None
        self._cache_timestamp: str | None = None
        self._stale_data: bool = False

        # UI refs
        self._kpi_row: ft.Row | None = None
        self._main_content: ft.Container | None = None
        self._sidebar: ft.Container | None = None
        self._status_text = ft.Text(
            "Cargue datos para comenzar",
            size=13, color=self.c["text_muted"], weight=ft.FontWeight.W_500,
        )
        self._ts_text = ft.Text("", size=11, color=self.c["text_muted"], weight=ft.FontWeight.W_500)
        self._stale_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER, size=14, color=self.c["warning"]),
                ft.Text("Datos en caché", size=11, color=self.c["warning"], weight=ft.FontWeight.W_500),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            visible=False,
            padding=ft.padding.only(left=10, right=10, top=5, bottom=5),
            bgcolor=rgba(self.c["warning"], 0.07),
            border_radius=8,
        )
        self._empty_state = ft.Container(
            visible=False,
            content=ft.Column([
                ft.Icon(ft.Icons.CLOUD_OFF, size=48, color=rgba(self.c["text_muted"], 0.35)),
                ft.Text("Sin datos disponibles", size=16, color=self.c["text_muted"], weight=ft.FontWeight.W_600),
                ft.Text("Verificando conexión...", size=13, color=rgba(self.c["text_muted"], 0.65)),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
        )
        self._loading_overlay = ft.Container(
            visible=False,
            content=ft.Column([
                ft.ProgressRing(width=40, height=40, color=self.c["accent"]),
                ft.Container(height=12),
                ft.Text("Cargando...", size=14, color=self.c["text_primary"]),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            bgcolor=rgba(self.c["background"], 0.85),
            expand=True,
            alignment=ft.alignment.center,
        )

        # Callbacks
        self._on_theme_toggle = None
        self._on_refresh = None
        self._file_picker = ft.FilePicker()

    def set_on_theme_toggle(self, cb):
        self._on_theme_toggle = cb

    def set_on_refresh(self, cb):
        self._on_refresh = cb

    def register_overlay(self):
        self.page.overlay.append(self._file_picker)

    def build(self) -> ft.Container:
        self._sidebar = self._build_sidebar()
        self._main_content = self._build_main_content()

        return ft.Row(
            controls=[
                self._sidebar,
                ft.VerticalDivider(width=1, color=self.c["border"]),
                self._main_content,
            ],
            expand=True,
        )

    def _build_header(self) -> ft.Container:
        theme_icon = ft.Icons.DARK_MODE if self._theme_mode == "dark" else ft.Icons.LIGHT_MODE
        self._theme_button = ft.IconButton(
            icon=theme_icon,
            icon_size=18,
            tooltip="Cambiar tema",
            on_click=lambda _: self._on_theme_toggle() if self._on_theme_toggle else None,
        )

        return ft.Container(
            content=ft.Row([
                ft.Text("G360 Dashboard", size=16, weight=ft.FontWeight.W_700, color=self.c["text_primary"]),
                ft.Container(expand=True),
                self._ts_text,
                ft.Container(width=16),
                self._stale_badge,
                ft.Container(width=16),
                self._status_text,
                ft.Container(width=16),
                self._theme_button,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(left=20, right=20, top=12, bottom=12),
            bgcolor=self.c["surface"],
            border_bottom=ft.BorderSide(1, self.c["border"]),
        )

    def _build_kpi_row(self, kpis: dict) -> ft.Row:
        kpi_keys = ["almacenes", "skus", "disponible", "predespacho", "sin_catalogo", "alertas", "criticos", "alto_stock"]
        kpi_colors = self.c.get("kpis", {})

        controls = []
        for i, key in enumerate(kpi_keys):
            data = kpis.get(key, {})
            card = KPICard(
                label=key.replace("_", " ").title(),
                value=str(data.get("value", "-")),
                color=kpi_colors.get(key, list(kpi_colors.values())[0]),
                subtext=data.get("subtext", ""),
            )
            controls.append(card)
            if i < len(kpi_keys) - 1:
                controls.append(ft.Container(width=8))

        return ft.Row(
            controls=controls,
            wrap=True,
            spacing=0,
            run_spacing=8,
        )

    def _build_sidebar(self) -> ft.Container:
        search_field = ft.TextField(
            hint_text="Buscar SKU, descripción...",
            border_radius=8,
            height=36,
            text_size=12,
            dense=True,
            border=ft.InputBorder.OUTLINE,
            border_color=self.c["border"],
            focused_border_color=self.c["accent"],
            cursor_color=self.c["accent"],
            hint_style=ft.TextStyle(size=11, color=self.c["text_muted"]),
            suffix_icon=ft.Icon(ft.Icons.KEYBOARD_RETURN, size=14, color=rgba(self.c["text_muted"], 0.5)),
        )

        return ft.Container(
            content=ft.Column([
                ft.Container(height=16),
                ft.Text("Filtros", size=12, weight=ft.FontWeight.W_600, color=self.c["text_muted"]),
                ft.Container(height=8),
                search_field,
                ft.Container(height=16),
                ft.Divider(color=self.c["border"]),
                ft.Container(height=8),
                ft.Text("Almacenes", size=12, weight=ft.FontWeight.W_600, color=self.c["text_muted"]),
                ft.Container(height=8),
                ft.Column([], scroll=ft.ScrollMode.AUTO, expand=True, id="sidebar_alms"),
            ], spacing=0, expand=True),
            width=220,
            bgcolor=self.c["surface"],
            padding=ft.Padding(left=12, right=12, top=16, bottom=12),
        )

    def _build_main_content(self) -> ft.Container:
        return ft.Container(
            content=ft.Column([
                self._build_header(),
                ft.Container(content=self._kpi_row if self._kpi_row else self._build_kpi_row({}), expand=False),
                ft.Container(height=12),
                ft.Container(
                    content=ft.Column([], scroll=ft.ScrollMode.AUTO, expand=True, id="main_cards"),
                    expand=True,
                ),
                self._empty_state,
                self._loading_overlay,
            ], spacing=0, expand=True),
            expand=True,
            bgcolor=self.c["background"],
            padding=ft.Padding(left=16, right=16, top=16, bottom=16),
        )

    # --- Update methods ---

    def update_data(self, raw_data: dict, cache_timestamp: str | None = None, api_timestamp: str | None = None, stale: bool = False):
        self._raw_data = raw_data
        self._cache_timestamp = cache_timestamp
        self._stale_data = stale
        # Subclases implementan la logica de renderizado
        self._render()

    def _render(self):
        # Implementar en subclase segun el dominio
        pass

    def update_theme(self, mode: str):
        self._theme_mode = mode
        self.c = get_colors(mode)
        # Reconstruir UI con nuevos colores
        self.page.bgcolor = self.c["background"]
        self._rebuild_ui()

    def _rebuild_ui(self):
        if self._main_content:
            self._main_content.content = self._build_main_content().content
            self.page.update()

    def set_loading(self, loading: bool, message: str = "Cargando..."):
        self._loading_overlay.visible = loading
        if loading:
            self._loading_overlay.content.controls[2].value = message
        self.page.update()

    def set_offline(self, offline: bool):
        if offline:
            self._status_text.value = "Sin conexión"
            self._status_text.color = self.c["error"]
        else:
            self._status_text.value = "Conectado"
            self._status_text.color = self.c["success"]
        self.page.update()

    def _show_snack(self, msg: str, is_error: bool = False):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(msg, size=13),
            bgcolor=self.c["error"] if is_error else self.c["accent"],
            duration=3000,
        )
        self.page.open(self.page.snack_bar)

    def _show_empty_state(self, title: str, subtitle: str = ""):
        self._empty_state.content.controls[1].value = title
        if subtitle:
            if len(self._empty_state.content.controls) > 2:
                self._empty_state.content.controls[2].value = subtitle
            else:
                self._empty_state.content.controls.append(
                    ft.Text(subtitle, size=13, color=rgba(self.c["text_muted"], 0.65))
                )
        self._empty_state.visible = True
        self.page.update()

    def _hide_empty_state(self):
        self._empty_state.visible = False
        self.page.update()

    def _set_empty_state_status(self, msg: str, color: str):
        for ctrl in self._empty_state.content.controls:
            if isinstance(ctrl, ft.Text) and ctrl.size == 13:
                ctrl.value = msg
                ctrl.color = color
                break
        self.page.update()

    def _update_refresh_status(self, cache_ts: str | None):
        if cache_ts:
            try:
                dt = datetime.fromisoformat(cache_ts)
                age_min = (datetime.now() - dt).total_seconds() / 60
                self._ts_text.value = f"Hace {int(age_min)} min"
            except Exception:
                self._ts_text.value = ""
        else:
            self._ts_text.value = ""

    def format_cache_timestamp(self, ts: str | None) -> str:
        if not ts:
            return ""
        try:
            return datetime.fromisoformat(ts).strftime("%H:%M:%S")
        except Exception:
            return ts[:19]

    def _show_stale_warning(self):
        self._stale_badge.visible = True
        self.page.update()

    def _hide_stale_warning(self):
        self._stale_badge.visible = False
        self.page.update()

    def show_search_overlay(self):
        """Abre el buscador flotante."""
        overlay = SearchOverlay(self.page, self.c)
        self.page.overlay.append(overlay)
        self.page.open(overlay)
