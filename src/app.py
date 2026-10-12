"""
app.py — Main PiKit window with sidebar navigation.
"""
import customtkinter as ctk

from . import theme as T
from .settings_mgr import Settings
from .views.flash    import FlashView
from .views.backup   import BackupView
from .views.pipeline import PipelineView
from .views.settings import SettingsView

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

_NAV = [
    ("⚡  Flash",    "flash"),
    ("💾  Backup",   "backup"),
    ("🔄  Pipeline", "pipeline"),
    ("⚙   Settings", "settings"),
]


class PiKitApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=T.BG_MAIN)
        self.title("PiKit")
        self.minsize(920, 640)

        self._settings = Settings()
        self._views    = {}
        self._nav_btns = {}
        self._active   = None

        geom = self._settings.get("window_geometry") or "1020x680"
        self.geometry(geom)
        self.bind("<Configure>", self._on_resize)

        self._build_layout()
        self._switch("flash")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._sidebar = ctk.CTkFrame(self, width=190, fg_color=T.BG_SIDEBAR,
                                     corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="nsw")
        self._sidebar.grid_propagate(False)
        self._sidebar.grid_rowconfigure(10, weight=1)

        # Logo / wordmark
        logo_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        logo_frame.pack(pady=(24, 20), padx=16, anchor="w")
        ctk.CTkLabel(logo_frame, text="Pi", font=(T.FONT_FAMILY, 22, "bold"),
                     text_color=T.ACCENT).pack(side="left")
        ctk.CTkLabel(logo_frame, text="Kit", font=(T.FONT_FAMILY, 22, "bold"),
                     text_color=T.TEXT).pack(side="left")

        # Divider
        ctk.CTkFrame(self._sidebar, height=1, fg_color=T.BORDER).pack(
            fill="x", padx=16, pady=(0, 12))

        # Nav buttons
        for label, key in _NAV:
            btn = ctk.CTkButton(
                self._sidebar,
                text=label,
                anchor="w",
                height=40,
                corner_radius=8,
                font=T.FONT_BODY,
                fg_color="transparent",
                hover_color=T.BG_CARD,
                text_color=T.TEXT_DIM,
                command=lambda k=key: self._switch(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = btn

        # Version at bottom
        ctk.CTkLabel(self._sidebar, text="v1.0.0", font=T.FONT_SMALL,
                     text_color=T.TEXT_MUTED).pack(side="bottom", pady=14)

        # Content area
        self._content = ctk.CTkFrame(self, fg_color=T.BG_MAIN, corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        # Build all views (hidden until activated)
        self._views["flash"]    = FlashView(self._content,    self._settings)
        self._views["backup"]   = BackupView(self._content,   self._settings)
        self._views["pipeline"] = PipelineView(self._content, self._settings)
        self._views["settings"] = SettingsView(self._content, self._settings)

        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew",
                      padx=28, pady=20)
            view.grid_remove()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _switch(self, key: str):
        if self._active == key:
            return

        # Hide current
        if self._active and self._active in self._views:
            self._views[self._active].grid_remove()
            self._nav_btns[self._active].configure(
                fg_color="transparent", text_color=T.TEXT_DIM)

        # Show new
        self._active = key
        self._views[key].grid()
        self._nav_btns[key].configure(
            fg_color=T.BG_CARD, text_color=T.TEXT)

        if hasattr(self._views[key], "on_activate"):
            self._views[key].on_activate()

    # ── Persist window size ───────────────────────────────────────────────────

    def _on_resize(self, _):
        geom = f"{self.winfo_width()}x{self.winfo_height()}"
        self._settings.set("window_geometry", geom)
