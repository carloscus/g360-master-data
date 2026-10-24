"""
G360 Search Overlay - Buscador flotante con debounce.

Busqueda contextual en tiempo real con resultados en vivo.
Enter abre el primer resultado, Escape o click fuera cierra.
Auto-limpieza al enfocar con texto previo.
"""
from __future__ import annotations

import asyncio

import flet as ft
from src.config.theme import rgba


class SearchOverlay(ft.Container):
    def __init__(self, page: ft.Page, colors: dict):
        super().__init__()
        self.page = page
        self.c = colors
        self._results: list[dict] = []
        self._debounce_task = None
        self._selected_index = 0

        self.field = ft.TextField(
            hint_text="Buscar SKU, descripción, línea...",
            border_radius=10,
            height=44,
            text_size=13,
            dense=True,
            border=ft.InputBorder.OUTLINE,
            border_color=self.c["border"],
            focused_border_color=self.c["accent"],
            cursor_color=self.c["accent"],
            hint_style=ft.TextStyle(size=12, color=self.c["text_muted"]),
            autofocus=True,
            on_change=self._on_change,
            on_submit=self._on_submit,
            on_focus=self._on_focus,
        )

        self.content = ft.Column(
            controls=[
                self.field,
                ft.Container(
                    content=ft.Column([], scroll=ft.ScrollMode.AUTO, max_height=300, id="search_results"),
                    bgcolor=self.c["surface"],
                    border_radius=ft.BorderRadius.only(bottom_left=10, bottom_right=10),
                    border=ft.border.only(top=ft.BorderSide(1, color=self.c["border"])),
                    visible=False,
                    padding=ft.padding.only(left=0, right=0, top=0, bottom=0),
                    max_height=300,
                    height=300,
                ),
            ],
            spacing=0,
        )

        self.bgcolor = self.c["surface"]
        self.border_radius = 10
        self.padding = ft.padding.only(left=16, right=16, top=12, bottom=12)
        self.width = 480
        self.alignment = ft.alignment.top_center
        self.margin = ft.margin.only(top=60)

    def _on_focus(self, e):
        if self.field.value:
            self.field.value = ""
            self.field.update()

    async def _on_change(self, e):
        query = (e.control.value or "").strip().lower()
        if self._debounce_task:
            self._debounce_task.cancel()
        if len(query) < 2:
            self._hide_results()
            return
        self._debounce_task = asyncio.create_task(self._debounce_search(query))

    async def _debounce_search(self, query: str):
        await asyncio.sleep(0.25)
        self._results = await self._do_search(query)
        self._show_results(self._results)

    async def _do_search(self, query: str) -> list[dict]:
        """Implementar en subclase. Retorna lista de dicts {sku, desc, ...}."""
        return []

    def _show_results(self, results: list[dict]):
        if not results:
            self._hide_results()
            return
        controls = []
        for i, item in enumerate(results[:10]):
            is_selected = i == self._selected_index
            controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text(item.get("sku", ""), size=12, color=self.c["accent"], weight=ft.FontWeight.W_600),
                        ft.Container(width=8),
                        ft.Text(item.get("desc", item.get("descripcion", "")), size=12, color=self.c["text_primary"]),
                    ], spacing=0),
                    bgcolor=rgba(self.c["accent"], 0.1) if is_selected else "transparent",
                    border_radius=6,
                    padding=ft.padding.only(left=12, right=12, top=8, bottom=8),
                    on_click=lambda _, r=item: self._on_select(r),
                    mouse_cursor=ft.CursorType.CLICK,
                )
            )
        results_col = self.content.controls[1]
        results_col.content.controls = controls
        results_col.visible = True
        self.update()

    def _hide_results(self):
        results_col = self.content.controls[1]
        results_col.content.controls = []
        results_col.visible = False
        self.update()

    def _on_submit(self, e):
        if self._results:
            self._on_select(self._results[self._selected_index])

    def _on_select(self, item: dict):
        self._hide_results()
        self.page.close(self)

    def did_mount(self):
        """Captura Escape para cerrar."""
        def on_keyboard(e: ft.KeyboardEvent):
            if e.key == "Escape":
                self.page.close(self)
            elif e.key == "ArrowDown":
                self._selected_index = min(self._selected_index + 1, len(self._results) - 1)
                self._show_results(self._results)
            elif e.key == "ArrowUp":
                self._selected_index = max(self._selected_index - 1, 0)
                self._show_results(self._results)
            elif e.key == "Enter" and self._results:
                self._on_select(self._results[self._selected_index])

        self.page.on_keyboard_event = on_keyboard
