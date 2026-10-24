"""
G360 KPI Card - Componente reutilizable para indicadores clave.

Patron: Card con glow backlight por color, valor numerico grande,
subtexto opcional. Clickable para abrir dialogos detallados.
"""
from __future__ import annotations

import flet as ft
from src.config.theme import rgba


class KPICard(ft.Container):
    def __init__(
        self,
        label: str,
        value: str,
        color: str,
        subtext: str = "",
        on_click=None,
    ):
        super().__init__()
        self._label = label
        self._value = value
        self._color = color
        self._subtext = subtext
        self._on_click = on_click

        self.content = ft.Column(
            controls=[
                ft.Text(label, size=11, color=rgba(color, 0.8), weight=ft.FontWeight.W_500),
                ft.Container(height=4),
                ft.Text(
                    value,
                    size=22,
                    color=color,
                    weight=ft.FontWeight.W_700,
                    font_family="JetBrains Mono",
                ),
                ft.Container(height=2),
                ft.Text(subtext, size=10, color=rgba(color, 0.6)),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )
        self.padding = ft.padding.only(left=14, right=14, top=10, bottom=10)
        self.bgcolor = rgba(color, 0.08)
        self.border_radius = 10
        self.shadow = ft.BoxShadow(
            spread_radius=0.5,
            blur_radius=12,
            color=rgba(color, 0.15),
            offset=ft.Offset(0, 2),
        )
        self.border = ft.Border(bottom=ft.BorderSide(2, rgba(color, 0.4)))
        self.cursor_type = ft.CursorType.CLICK if on_click else ft.CursorType.NONE

        if on_click:
            self.on_click = on_click
        else:
            self.on_click = None

    def update_value(self, value: str, subtext: str = ""):
        self._value = value
        self._subtext = subtext
        self.content.controls[2].value = value
        if len(self.content.controls) > 3:
            self.content.controls[3].value = subtext
        self.update()
