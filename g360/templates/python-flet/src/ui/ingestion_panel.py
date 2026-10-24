import threading
from pathlib import Path

import flet as ft
import pandas as pd

try:
    from g360_core.ingestion import estabilizar_excel_crudo
except ImportError:
    from core.ingestion import estabilizar_excel_crudo


class IngestionPanel(ft.Container):
    def __init__(self, theme, on_data_loaded=None):
        super().__init__()
        self.theme = theme
        self.on_data_loaded = on_data_loaded
        self.df: pd.DataFrame | None = None
        self.metadata: dict | None = None
        self._build()

    def _build(self):
        self.file_picker = ft.FilePicker(on_result=self._on_file_result)
        self.status_text = ft.Text(
            "Selecciona un archivo .xls o .xlsx del ERP",
            size=14,
            color=self.theme.muted,
        )
        self.stats_container = ft.Column(spacing=4, visible=False)
        self.alertas_container = ft.Column(spacing=2, visible=False)
        self.preview_table = ft.Column(scroll=ft.ScrollMode.AUTO, visible=False)

        self.content = ft.Column(
            controls=[
                self.file_picker,
                ft.Row(
                    controls=[
                        self.theme.accent_button(
                            text="Cargar Archivo Excel",
                            on_click=self._open_picker,
                        ),
                        ft.Container(width=12),
                        self.status_text,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=12),
                self.stats_container,
                ft.Container(height=8),
                self.alertas_container,
                ft.Container(height=8),
                self.preview_table,
            ],
            spacing=0,
        )
        self.bgcolor = self.theme.surface
        self.border_radius = self.theme.rounded
        self.padding = 20
        self.expand = True

    def _open_picker(self, e):
        self.file_picker.pick_files(
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xls", "xlsx", "xlsm"],
            dialog_title="Seleccionar reporte del ERP",
        )

    def _on_file_result(self, e: ft.FilePickerResultEvent):
        if not e.files:
            self.status_text.value = "No se selecciono ningun archivo."
            self.status_text.color = self.theme.warning
            self.update()
            return

        archivo = e.files[0]
        ruta = archivo.path
        nombre = archivo.name
        self.status_text.value = f"Procesando: {nombre}..."
        self.status_text.color = self.theme.text
        self.update()

        self._show_loading(True)

        def _procesar():
            try:
                df, metadata = estabilizar_excel_crudo(ruta)
                self.df = df
                self.metadata = metadata
                self._mostrar_resultado(df, metadata, nombre)
                if self.on_data_loaded:
                    self.on_data_loaded(df, metadata)
            except Exception as exc:
                self.status_text.value = f"Error: {exc}"
                self.status_text.color = self.theme.error
                self._show_loading(False)
                self.update()

        thread = threading.Thread(target=_procesar, daemon=True)
        thread.start()

    def _show_loading(self, visible: bool):
        pass

    def _mostrar_resultado(self, df: pd.DataFrame, metadata: dict, nombre: str):
        self.status_text.value = f"OK: {nombre} ({len(df):,} filas)"
        self.status_text.color = self.theme.success

        columnas = metadata.get("columnas_finales", metadata.get("columnas", []))
        transformaciones = metadata.get("transformaciones", [])
        alertas = metadata.get("alertas", [])
        columnas_nuevas = metadata.get("columnas_nuevas", [])

        self.stats_container.controls = [
            ft.Text("Resumen de Ingesta", size=16, weight=ft.FontWeight.BOLD, color=self.theme.text),
            ft.Text(f"Filas estabilizadas: {len(df):,}", size=13, color=self.theme.muted),
            ft.Text(f"Columnas originales: {metadata.get('filas_originales', 0)}", size=13, color=self.theme.muted),
            ft.Text(f"Columnas finales: {len(columnas)}", size=13, color=self.theme.muted),
            ft.Text(f"Archivo: {metadata.get('archivo', 'N/A')}", size=13, color=self.theme.muted),
            ft.Text(f"Moneda: {metadata.get('moneda', 'N/A')}", size=13, color=self.theme.muted),
            ft.Divider(color=self.theme.bg, height=8),
        ]

        if columnas_nuevas:
            nuevas_text = ft.Text(
                "Columnas derivadas:",
                size=13, weight=ft.FontWeight.BOLD, color=self.theme.accent,
            )
            chips = ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Text(col, size=10, color=self.theme.bg),
                        bgcolor=self.theme.accent,
                        border_radius=12,
                        padding=ft.padding.only(left=8, right=8, top=3, bottom=3),
                    )
                    for col in columnas_nuevas
                ],
                spacing=6,
                wrap=True,
            )
            self.stats_container.controls.extend([nuevas_text, chips])

        if transformaciones:
            self.stats_container.controls.append(
                ft.Divider(color=self.theme.bg, height=8)
            )
            self.stats_container.controls.append(
                ft.Text("Transformaciones:", size=13, weight=ft.FontWeight.BOLD, color=self.theme.text)
            )
            for t in transformaciones[-8:]:
                self.stats_container.controls.append(
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Text(">", size=11, color=self.theme.accent),
                                width=16,
                            ),
                            ft.Text(t, size=11, color=self.theme.muted),
                        ],
                        spacing=0,
                    )
                )

        self.stats_container.visible = True

        if alertas:
            self.alertas_container.controls = [
                ft.Divider(color=self.theme.bg, height=4),
                ft.Text("Alertas:", size=13, weight=ft.FontWeight.BOLD, color=self.theme.warning),
            ]
            for a in alertas:
                self.alertas_container.controls.append(
                    ft.Row(
                        controls=[
                            ft.Icon(ft.icons.WARNING_AMBER_ROUNDED, size=14, color=self.theme.warning),
                            ft.Text(a, size=11, color=self.theme.warning),
                        ],
                        spacing=4,
                    )
                )
            self.alertas_container.visible = True

        filas_preview = df.head(5)
        columnas_preview = columnas[:8]

        data_rows = []
        for _, row in filas_preview.iterrows():
            cells = []
            for col in columnas_preview:
                val = row.get(col, "")
                v_str = str(val)[:30] if not pd.isna(val) else "-"
                cells.append(
                    ft.DataCell(ft.Text(v_str, size=10, color=self.theme.text))
                )
            data_rows.append(ft.DataRow(cells=cells))

        header_cells = [
            ft.DataColumn(ft.Text(col[:16], size=10, color=self.theme.accent, weight=ft.FontWeight.BOLD))
            for col in columnas_preview
        ]

        tabla = ft.DataTable(
            columns=header_cells,
            rows=data_rows,
            heading_text_color=self.theme.accent,
            horizontal_margin=4,
            column_spacing=16,
        )

        self.preview_table.controls = [
            ft.Text("Vista previa (5 primeras filas):", size=13, weight=ft.FontWeight.BOLD, color=self.theme.text),
            ft.Container(
                content=tabla,
                bgcolor=self.theme.bg,
                border_radius=8,
                padding=8,
            ),
        ]
        self.preview_table.visible = True
        self.update()
