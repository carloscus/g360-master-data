import json
from pathlib import Path


class G360Theme:
    def __init__(self, skill_path=None):
        self._search_paths(skill_path)
        self._load_colors()
        self._load_effects()

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
            / "customtkinter-desktop.json",
        ]
        for c in candidates:
            if c.exists():
                self.config_path = c
                return
        raise FileNotFoundError(
            "skill.json not found. Run: g360 init <name> --skill customtkinter-desktop"
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

    def apply_ctk(self):
        import customtkinter as ctk

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

    def build_name(self):
        build_cfg = self.config.get("build", {})
        return build_cfg.get("name", "G360-App")

    def glass_frame(self, parent, **kwargs):
        import customtkinter as ctk

        kwargs.setdefault("fg_color", self.surface)
        kwargs.setdefault("corner_radius", self.rounded)
        if self.glassmorphism:
            kwargs.setdefault("border_width", 1)
            kwargs.setdefault("border_color", f"{self.accent}40")
        return ctk.CTkFrame(parent, **kwargs)

    def accent_button(self, parent, text="", command=None, **kwargs):
        import customtkinter as ctk

        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=self.accent,
            text_color=self.bg,
            hover_color="#00b070",
            corner_radius=8,
            **kwargs,
        )

    def styled_label(self, parent, text="", size=14, color=None, **kwargs):
        import customtkinter as ctk

        return ctk.CTkLabel(
            parent,
            text=text,
            font=("Segoe UI", size),
            text_color=color or self.text,
            **kwargs,
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
