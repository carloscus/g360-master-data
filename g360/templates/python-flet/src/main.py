import sys
from pathlib import Path
import flet as ft
from core.g360_theme import G360Theme
from ui.ingestion_panel import IngestionPanel

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class G360App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.theme = G360Theme()
        self.df = None
        self.metadata = None
        self._setup_page()
        self._build_ui()

    def _on_data_loaded(self, df, metadata):
        self.df = df
        self.metadata = metadata

    def _setup_page(self):
        self.page.title = self.theme.build_name()
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.theme.bg
        self.page.padding = 0
        self.page.window_width = 1350
        self.page.window_height = 900
        self.page.window_resizable = True
        self.page.window_center()

    def _build_ui(self):
        self.loading = self.theme.loading_overlay()
        self.ingestion_panel = IngestionPanel(
            self.theme, on_data_loaded=self._on_data_loaded
        )
        self.page.overlay.append(self.ingestion_panel.file_picker)
        self.page.add(
            ft.Stack(
                controls=[
                    ft.Column(
                        controls=[
                            self._build_header(),
                            ft.Container(
                                content=self._build_content(),
                                expand=True,
                                padding=20,
                            ),
                            self.theme.footer_signature(),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    self.loading,
                ],
                expand=True,
            )
        )

    def show_loading(self, message="Procesando..."):
        self.loading.content.controls[2].value = message
        self.loading.visible = True
        self.page.update()

    def hide_loading(self):
        self.loading.visible = False
        self.page.update()

    def _build_header(self):
        return self.theme.container(
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            self.theme.logo_component(height=32),
                            ft.Container(width=8),
                            self.theme.styled_text(
                                "Desktop App", size=20, color=self.theme.muted
                            ),
                        ],
                        spacing=0,
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.icons.SETTINGS,
                        on_click=lambda _: print("Settings"),
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=20,
            bgcolor=self.theme.surface,
        )

    def _build_content(self):
        return ft.Column(
            controls=[
                self.theme.styled_text(
                    "Ingesta de Datos - Escudo de Saneamiento",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Container(height=8),
                self.theme.styled_text(
                    "Carga tu archivo .xls/.xlsx del ERP. Los datos se normalizan automaticamente.",
                    size=14,
                    color=self.theme.muted,
                ),
                ft.Container(height=16),
                self.ingestion_panel,
                ft.Container(height=20),
                ft.Row(
                    controls=[
                        self._build_card(
                            "Usuarios", "Gestion de usuarios", ft.icons.PEOPLE
                        ),
                        self._build_card(
                            "Reportes", "Ver reportes", ft.icons.ANALYTICS
                        ),
                        self._build_card(
                            "Configuracion", "Ajustes del sistema", ft.icons.SETTINGS
                        ),
                    ],
                    spacing=20,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    def _build_card(self, title, subtitle, icon):
        return self.theme.container(
            content=ft.Column(
                controls=[
                    ft.Icon(icon, size=48, color=self.theme.accent),
                    self.theme.styled_text(
                        title, size=18, weight=ft.FontWeight.BOLD
                    ),
                    self.theme.styled_text(
                        subtitle, size=14, color=self.theme.muted
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            width=220,
            height=190,
            alignment=ft.alignment.center,
        )


def main(page: ft.Page):
    G360App(page)


if __name__ == "__main__":
    try:
        ft.run(main)
    except Exception as e:
        print(f"\n[FATAL] Error al iniciar la aplicacion: {e}", flush=True)
        import traceback
        traceback.print_exc()
        input("\nPresione Enter para salir...")