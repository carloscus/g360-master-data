import json
import base64
from pathlib import Path


class G360Theme:
    def __init__(self, skill_path=None):
        self._search_paths(skill_path)
        self._load_colors()
        self._load_effects()
        self._load_logo()

    def _search_paths(self, skill_path):
        if skill_path and Path(skill_path).exists():
            self.config_path = Path(skill_path)
            return
        candidates = [
            Path("skill.json"),
            Path("src/core/skill.json"),
            Path(__file__).resolve().parent.parent.parent / "skill.json",
            Path(__file__).resolve().parent / "skill.json",
            Path(__file__).resolve().parent.parent
            / "g360"
            / "skills"
            / "flet-desktop.json",
        ]
        for c in candidates:
            if c.exists():
                self.config_path = c
                return
        raise FileNotFoundError(
            "skill.json not found. Run: g360 init <name> --skill flet-desktop"
        )

    def _load_colors(self):
        with open(self.config_path, encoding="utf-8") as f:
            self.config = json.load(f)
        colors = self.config.get("colors", {})
        self.bg = colors.get("bg", "#0b1220")
        self.surface = colors.get("surface", "#1a2332")
        self.accent = colors.get("accent", "#00d084")
        self.accent_strong = colors.get("accentStrong", "#047857")
        self.accent_bright = colors.get("accentBright", "#34d399")
        self.accent_soft = colors.get("accentSoft", "rgba(0, 208, 132, 0.12)")
        self.on_accent = colors.get("onAccent", "#06281c")
        self.text = colors.get("text", "#f0f4f8")
        self.muted = colors.get("muted", "#94a3b8")
        self.border = colors.get("border", "rgba(255, 255, 255, 0.10)")
        self.info = colors.get("info", "#3b82f6")
        self.success = colors.get("success", "#22c55e")
        self.warning = colors.get("warning", "#f59e0b")
        self.error = colors.get("error", "#ef4444")
        self.overlay = colors.get("overlay", "rgba(11, 18, 32, 0.90)")
        self.brand = self.config.get("brand", "g360")

    def _load_effects(self):
        effects = self.config.get("effects", {})
        self.glassmorphism = effects.get("glassmorphism", True)
        self.blur = effects.get("blur", "12px")
        self.rounded = int(effects.get("rounded", "12px").replace("px", ""))

    def _load_logo(self):
        logo_name = None
        guidelines = self.config.get("guidelines", {})
        if guidelines.get("logo"):
            logo_name = guidelines["logo"]
        if not logo_name:
            logo_name = "logo-g360-dark.svg"
        paths = [
            Path("assets/images") / logo_name,
            Path(__file__).resolve().parent.parent.parent
            / "assets"
            / "images"
            / logo_name,
        ]
        self._logo_path = None
        for p in paths:
            if p.exists():
                self._logo_path = p
                break
        self._logo_b64 = None

    def logo_src(self, page=None):
        if self._logo_path and self._logo_path.exists():
            return str(self._logo_path)
        return None

    def logo_base64(self):
        if self._logo_b64:
            return self._logo_b64
        if self._logo_path and self._logo_path.exists():
            raw = self._logo_path.read_bytes()
            ext = self._logo_path.suffix.lower()
            mime = "image/svg+xml" if ext == ".svg" else f"image/{ext[1:]}"
            self._logo_b64 = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
            return self._logo_b64
        brand_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "images"
        fallback = brand_dir / "logo-g360-dark.svg"
        if fallback.exists():
            raw = fallback.read_bytes()
            self._logo_b64 = (
                f"data:image/svg+xml;base64,{base64.b64encode(raw).decode()}"
            )
            return self._logo_b64
        return None

    def build_name(self):
        build_cfg = self.config.get("build", {})
        return build_cfg.get("name", "G360-App")

    def logo_component(self, height=40):
        import flet as ft

        src = self.logo_base64()
        if src:
            return ft.Image(src_base64=src, height=height, fit=ft.ImageFit.CONTAIN)
        return ft.Text(
            self.build_name(), size=18, weight=ft.FontWeight.BOLD, color=self.accent
        )

    def container(self, content=None, **kwargs):
        kwargs.setdefault("bgcolor", self.surface)
        kwargs.setdefault("border_radius", self.rounded)
        kwargs.setdefault("padding", 15)
        if self.glassmorphism and "shadow" not in kwargs:
            import flet as ft

            kwargs["shadow"] = ft.BoxShadow(
                spread_radius=1,
                blur_radius=20,
                color=f"{self.accent}20",
            )
        import flet as ft

        return ft.Container(content=content, **kwargs)

    def accent_button(self, text="", on_click=None, **kwargs):
        import flet as ft

        return ft.ElevatedButton(
            text=text,
            on_click=on_click,
            style=ft.ButtonStyle(
                bgcolor=self.accent,
                color=self.bg,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=15,
            ),
            **kwargs,
        )

    def styled_text(self, value="", size=14, color=None, weight=None, **kwargs):
        import flet as ft

        return ft.Text(
            value=value,
            size=size,
            color=color or self.text,
            weight=weight,
            **kwargs,
        )

    def loading_overlay(self, message="Cargando..."):
        import flet as ft

        return ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(width=48, height=48, color=self.accent),
                    ft.Container(height=16),
                    ft.Text(message, size=16, color=self.text),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=f"{self.bg}E0",
            expand=True,
            alignment=ft.alignment.center,
            visible=False,
        )

    def footer_signature(self):
        import flet as ft

        try:
            from core.components.g360_signature import g360_footer

            mode = self.config.get("signature", {}).get("mode", "powered")
            version = self.config.get("signature", {}).get("version", None)
            return g360_footer(version=version)
        except ImportError:
            # Fallback si g360_signature no esta instalado
            mode = self.config.get("signature", {}).get("mode", "powered")
            text = self.config.get("signature", {}).get("text", "powered by G360")
            return ft.Container(
                content=ft.Row(
                    [
                        self.logo_component(height=16),
                        ft.Container(width=8),
                        ft.Text(text, size=10, color=self.muted),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=8,
                bgcolor=self.surface,
            )

    @property
    def as_dict(self):
        return {
            "bg": self.bg,
            "surface": self.surface,
            "accent": self.accent,
            "text": self.text,
            "muted": self.muted,
            "success": self.success,
            "warning": self.warning,
            "error": self.error,
            "brand": self.brand,
        }
