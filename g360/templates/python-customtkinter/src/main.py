#!/usr/bin/env python3
"""
G360 CustomTkinter Desktop Application
Modern GUI with G360 theme
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import customtkinter as ctk
from core.g360_theme import G360Theme


class G360App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.theme = G360Theme()
        self.theme.apply_ctk()
        
        self.title(self.theme.build_name())
        self.geometry("900x700")
        self.configure(fg_color=self.theme.bg)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self._build_header()
        self._build_content()
        self._build_footer()
    
    def _build_header(self):
        header = self.theme.glass_frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        self.theme.styled_label(
            header,
            text=self.theme.build_name(),
            size=20,
            color=self.theme.accent
        ).pack(side="left", padx=20, pady=10)
        
        self.theme.accent_button(
            header,
            text="Settings",
            command=self._on_settings
        ).pack(side="right", padx=20, pady=10)
    
    def _build_content(self):
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        
        card = self.theme.glass_frame(content)
        card.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.theme.styled_label(
            card,
            text="G360 Application\nReady to build",
            size=18
        ).pack(pady=40)
        
        self.theme.accent_button(
            card,
            text="Start",
            command=self._on_start
        ).pack(pady=20)
    
    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        self.theme.styled_label(
            footer,
            text=f"v{self.theme.config.get('version', '1.0.0')}",
            size=12,
            color=self.theme.muted
        ).pack(side="left", padx=20)
        
        self.theme.styled_label(
            footer,
            text="powered by G360",
            size=10,
            color=self.theme.muted
        ).pack(side="right", padx=20)
    
    def _on_settings(self):
        print("Settings clicked")
    
    def _on_start(self):
        print("Start clicked")


def main():
    app = G360App()
    app.mainloop()


if __name__ == "__main__":
    main()
