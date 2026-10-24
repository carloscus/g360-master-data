import sys
from pathlib import Path
import flet as ft
from core.g360_theme import G360Theme

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class MigratedApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.theme = G360Theme()
        self._setup_page()
        self._build_ui()

    def _setup_page(self):
        self.page.title = self.theme.build_name()
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.theme.bg
        self.page.padding = 0
        self.page.window_width = 900
        self.page.window_height = 700
        self.page.window_resizable = True
        self.page.window_center()

    def _build_ui(self):
        self.page.add(
            ft.Column([
                self._build_header(),
                ft.Container(
                    content=self._build_content(),
                    expand=True,
                    padding=20,
                ),
                self.theme.footer_signature(),
            ], spacing=0, expand=True)
        )

    def _build_header(self):
        return self.theme.container(
            content=ft.Row([
                self.theme.logo_component(height=32),
                ft.Container(width=8),
                self.theme.styled_text("Migrated App", size=20, color=self.theme.muted),
                ft.Container(expand=True),
                ft.Text("from tkinter/ctkinter", size=14, color=self.theme.muted),
            ]),
            padding=20,
            bgcolor=self.theme.surface,
        )

    def _build_content(self):
        return ft.Column([
            self.theme.styled_text(
                "Panel de Controles (antes tk.Button)",
                size=20, weight=ft.FontWeight.BOLD,
            ),
            ft.Row([
                self.theme.accent_button("Aceptar"),
                ft.ElevatedButton("Cancelar", bgcolor=self.theme.error, color="#ffffff"),
                ft.ElevatedButton("Guardar", bgcolor="#00796B", color="#ffffff"),
            ], spacing=15),
            ft.Container(height=30),
            self.theme.styled_text(
                "Campos de Entrada (antes tk.Entry)",
                size=20, weight=ft.FontWeight.BOLD,
            ),
            ft.Column([
                ft.TextField(label="Usuario", hint_text="Ingrese usuario", width=300),
                ft.TextField(label="Contraseña", hint_text="Ingrese contraseña", password=True, width=300),
            ], spacing=15),
            ft.Container(height=30),
            self.theme.styled_text(
                "Casillas y Opciones (antes tk.Checkbutton/tk.Radiobutton)",
                size=20, weight=ft.FontWeight.BOLD,
            ),
            ft.Column([
                ft.Checkbox(label="Recordarme"),
                ft.Checkbox(label="Aceptar términos"),
            ], spacing=10),
        ], scroll=ft.ScrollMode.AUTO)


def main(page: ft.Page):
    MigratedApp(page)


if __name__ == "__main__":
    try:
        ft.run(main)
    except Exception as e:
        print(f"\n[FATAL] Error al iniciar la aplicacion: {e}", flush=True)
        import traceback
        traceback.print_exc()
        input("\nPresione Enter para salir...")
