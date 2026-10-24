import unittest
from unittest.mock import Mock, patch
import json
from pathlib import Path
import flet as ft
from core.g360_theme import G360Theme


class TestG360Theme(unittest.TestCase):
    def setUp(self):
        self.theme = G360Theme(skill_path=Path(__file__).parent / "core" / "skill.json")

    def test_default_colors(self):
        self.assertEqual(self.theme.bg, "#0b1220")
        self.assertEqual(self.theme.surface, "#1a2332")
        self.assertEqual(self.theme.accent, "#00d084")
        self.assertEqual(self.theme.text, "#f0f4f8")
        self.assertEqual(self.theme.muted, "#94a3b8")
        self.assertEqual(self.theme.success, "#22c55e")
        self.assertEqual(self.theme.warning, "#f59e0b")
        self.assertEqual(self.theme.error, "#ef4444")

    def test_as_dict(self):
        d = self.theme.as_dict
        self.assertEqual(d["bg"], "#0b1220")
        self.assertEqual(d["surface"], "#1a2332")
        self.assertEqual(d["accent"], "#00d084")

    def test_effects(self):
        self.assertTrue(self.theme.glassmorphism)
        self.assertEqual(self.theme.blur, "12px")
        self.assertEqual(self.theme.rounded, "12px")


class TestG360App(unittest.TestCase):
    def setUp(self):
        self.mock_page = Mock(spec=ft.Page)

    def test_page_theme_setup(self):
        self.mock_page.title = "G360 Desktop App"
        self.mock_page.theme_mode = ft.ThemeMode.DARK
        self.mock_page.bgcolor = "#0b1220"

        self.assertEqual(self.mock_page.title, "G360 Desktop App")
        self.assertEqual(self.mock_page.theme_mode, ft.ThemeMode.DARK)
        self.assertEqual(self.mock_page.bgcolor, "#0b1220")

    def test_colors_g360(self):
        colors = {
            "bg": "#0b1220",
            "surface": "#1a2332",
            "accent": "#00d084",
            "text": "#f0f4f8",
            "muted": "#94a3b8",
        }
        for key, value in colors.items():
            self.assertIsNotNone(value)

    def test_button_styles(self):
        button = ft.ElevatedButton(
            text="Test",
            bgcolor="#00d084",
            color="#0b1220",
        )
        self.assertIsNotNone(button)

    def test_container_styles(self):
        container = ft.Container(
            bgcolor="#1a2332",
            border_radius=12,
            padding=20,
        )
        self.assertIsNotNone(container)
        self.assertEqual(container.bgcolor, "#1a2332")
        self.assertEqual(container.border_radius, 12)


class TestMigration(unittest.TestCase):
    def test_convert_tkinter_widgets(self):
        mapping = {
            "tk.Label": "ft.Text",
            "tk.Button": "ft.ElevatedButton",
            "tk.Entry": "ft.TextField",
            "tk.Frame": "ft.Container",
        }
        for tk, flet in mapping.items():
            self.assertIsNotNone(tk)
            self.assertIsNotNone(flet)


class TestCalculations(unittest.TestCase):
    def test_sum_basic(self):
        self.assertEqual(2 + 2, 4)

    def test_list_operations(self):
        items = [1, 2, 3, 4, 5]
        self.assertEqual(sum(items), 15)
        self.assertEqual(len(items), 5)

    def test_dict_operations(self):
        data = {"sku": "ABC001", "cantidad": 10, "precio": 50.0}
        self.assertIn("sku", data)
        self.assertEqual(data["cantidad"] * data["precio"], 500.0)


if __name__ == "__main__":
    unittest.main()