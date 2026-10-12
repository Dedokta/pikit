"""
app.py — Main PiKit window with sidebar navigation.

Views are lazy-loaded — only instantiated on first visit, so startup
only pays the cost of the Flash view (the default).
"""
import os
import queue
import threading
import customtkinter as ctk

from . import theme as T
from .settings_mgr import Settings
from .version import APP_VERSION

from .logger import log

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

_NAV = [
    ("⚡  Flash",    "flash"),
    ("💾  Backup",   "backup"),
    ("⚙   Settings", "settings"),
]

# Lazy imports — only pulled in when the view is first opened
def _view_class(key):
    if key == "flash":
        from .views.flash    import FlashView;    return FlashView
    if key == "backup":
        from .views.backup   import BackupView;   return BackupView
    if key == "settings":
        from .views.settings import SettingsView; return SettingsView


class PiKitApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=T.BG_MAIN)
        self.title("PiKit")
        self.minsize(920, 640)

        self._settings    = Settings()
        self._views       = {}
        self._nav_btns    = {}
        self._active      = None
        self._update_btn  = None
        self._pending_upd = None
        self._update_q    = queue.SimpleQueue()

        geom = self._settings.get("window_geometry") or "1020x680"
        self.geometry(geom)
        self.bind("<Configure>", self._on_resize)

        self._build_layout()
        self._switch("flash")
        self._poll_update_q()

        # Check for updates 2 s after launch
        self.after(2000, self._start_update_check)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._sidebar = ctk.CTkFrame(self, width=190, fg_color=T.BG_SIDEBAR,
                                     corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="nsw")
        self._sidebar.grid_propagate(False)

        # Wordmark
        logo = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        logo.pack(pady=(24, 20), padx=16, anchor="w")
        ctk.CTkLabel(logo, text="Pi", font=(T.FONT_FAMILY, 22, "bold"),
                     text_color=T.ACCENT).pack(side="left")
        ctk.CTkLabel(logo, text="Kit", font=(T.FONT_FAMILY, 22, "bold"),
                     text_color=T.TEXT).pack(side="left")

        ctk.CTkFrame(self._sidebar, height=1, fg_color=T.BORDER).pack(
            fill="x", padx=16, pady=(0, 12))

        # Nav buttons
        for label, key in _NAV:
            btn = ctk.CTkButton(
                self._sidebar, text=label, anchor="w", height=40,
                corner_radius=8, font=T.FONT_BODY,
                fg_color="transparent", hover_color=T.BG_CARD,
                text_color=T.TEXT_DIM,
                command=lambda k=key: self._switch(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = btn

        # Bottom bar — update button + version
        self._sidebar_bottom = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        self._sidebar_bottom.pack(side="bottom", fill="x", padx=10, pady=10)
        self._ver_lbl = ctk.CTkLabel(self._sidebar_bottom, text=f"v{APP_VERSION}",
                                     font=T.FONT_SMALL, text_color=T.TEXT_MUTED)
        self._ver_lbl.pack(pady=(0, 4))

        # Content area
        self._content = ctk.CTkFrame(self, fg_color=T.BG_MAIN, corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

    # ── Navigation (lazy view creation) ──────────────────────────────────────

    def _switch(self, key: str):
        if self._active == key:
            return

        if self._active:
            self._views[self._active].grid_remove()
            self._nav_btns[self._active].configure(
                fg_color="transparent", text_color=T.TEXT_DIM)

        # Create view on first visit
        if key not in self._views:
            log.debug(f"Creating view: {key}")
            try:
                cls  = _view_class(key)
                view = cls(self._content, self._settings)
                view.grid(row=0, column=0, sticky="nsew", padx=28, pady=20)
                view.grid_remove()
                self._views[key] = view
                log.debug(f"View created OK: {key}")
            except Exception:
                log.exception(f"CRASH creating view: {key}")
                raise

        self._active = key
        self._views[key].grid()
        self._nav_btns[key].configure(fg_color=T.BG_CARD, text_color=T.TEXT)

        log.debug(f"Switched to: {key}")
        # Defer on_activate so the frame renders before any blocking calls
        if hasattr(self._views[key], "on_activate"):
            self.after(50, self._views[key].on_activate)

    # ── Update checker ────────────────────────────────────────────────────────

    def _poll_update_q(self):
        """Drain update callbacks on the main thread — avoids threading issues."""
        try:
            while True:
                fn, args = self._update_q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(100, self._poll_update_q)

    def _start_update_check(self):
        self._ver_lbl.configure(text=f"v{APP_VERSION}  checking…", text_color=T.TEXT_DIM)
        from .updater import check_for_update
        check_for_update(
            on_update_available=lambda v, n, u: self._update_q.put(
                (self._show_update_banner, (v, n, u))),
            on_up_to_date=lambda v: self._update_q.put(
                (self._show_up_to_date, ())),
            on_error=lambda e: self._update_q.put(
                (self._show_up_to_date, ())),
        )

    def _show_up_to_date(self):
        self._ver_lbl.configure(text=f"v{APP_VERSION}  ✓", text_color=T.SUCCESS)

    def _show_update_banner(self, version, notes, download_url):
        self._ver_lbl.configure(text=f"v{APP_VERSION}", text_color=T.TEXT_MUTED)
        if self._update_btn:
            return
        self._pending_upd = (version, notes, download_url)
        self._update_btn  = ctk.CTkButton(
            self._sidebar_bottom,
            text=f"↑  v{version} available",
            height=32, corner_radius=6, font=T.FONT_SMALL,
            fg_color=T.ACCENT_DIM, hover_color=T.ACCENT, text_color=T.TEXT,
            command=self._open_update_dialog,
        )
        self._update_btn.pack(fill="x", pady=(0, 4))

    def _open_update_dialog(self):
        version, notes, url = self._pending_upd
        _UpdateDialog(self, version, notes, url)

    # ── Resize ────────────────────────────────────────────────────────────────

    def _on_resize(self, _):
        geom = f"{self.winfo_width()}x{self.winfo_height()}"
        self._settings.set("window_geometry", geom)


# ── Update dialog ──────────────────────────────────────────────────────────────

class _UpdateDialog(ctk.CTkToplevel):
    def __init__(self, parent, version, notes, download_url):
        super().__init__(parent, fg_color=T.BG_MAIN)
        self.title(f"PiKit {version} available")
        self.geometry("520x400")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus()

        self._download_url = download_url

        # Header
        hdr = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=0)
        hdr.pack(fill="x")
        hi  = ctk.CTkFrame(hdr, fg_color="transparent")
        hi.pack(padx=20, pady=16)
        ctk.CTkLabel(hi, text=f"PiKit v{version} is available",
                     font=T.FONT_TITLE, text_color=T.TEXT).pack(anchor="w")
        ctk.CTkLabel(hi, text=f"You are on v{APP_VERSION}",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM).pack(anchor="w")

        # Release notes
        ctk.CTkLabel(self, text="What's new:", font=T.FONT_LABEL,
                     text_color=T.TEXT_DIM).pack(anchor="w", padx=20, pady=(14, 4))
        box = ctk.CTkTextbox(self, height=140, font=T.FONT_MONO,
                             fg_color=T.BG_CARD, text_color=T.TEXT,
                             border_width=0, wrap="word")
        box.pack(fill="x", padx=20)
        box.insert("end", notes.strip() or "No release notes.")
        box.configure(state="disabled")

        # Progress bar (hidden until download starts)
        self._bar = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                       fg_color=T.BORDER, progress_color=T.ACCENT)
        self._bar.set(0)
        self._bar.pack(fill="x", padx=20, pady=(12, 0))
        self._bar.pack_forget()

        self._status = ctk.CTkLabel(self, text="", font=T.FONT_SMALL,
                                    text_color=T.TEXT_DIM)
        self._status.pack(pady=(4, 0))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=14)
        ctk.CTkButton(btn_row, text="Not now", width=100, height=36,
                      font=T.FONT_BODY, fg_color=T.BG_INPUT,
                      hover_color=T.BORDER, text_color=T.TEXT_DIM,
                      corner_radius=6, command=self.destroy).pack(side="left")
        self._dl_btn = ctk.CTkButton(btn_row, text="Download & Install",
                                     height=36, font=T.FONT_LABEL,
                                     fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                                     text_color="#000", corner_radius=6,
                                     command=self._download)
        self._dl_btn.pack(side="right")

    def _download(self):
        self._dl_btn.configure(state="disabled", text="Downloading…")
        self._bar.pack(fill="x", padx=20, pady=(12, 0))
        self._bar.set(0)

        def worker():
            from .updater import download_installer, set_pending_update
            try:
                def progress(done, total):
                    pct = done / total if total else 0
                    self.after(0, self._bar.set, pct)
                    self.after(0, self._status.configure,
                               {"text": f"Downloading… {done/1_048_576:.1f} MB"})

                path = download_installer(self._download_url, progress_cb=progress)
                set_pending_update(path)

                self.after(0, self._on_downloaded)
            except Exception as e:
                self.after(0, self._status.configure,
                           {"text": f"Download failed: {e}", "text_color": T.ERROR})
                self.after(0, self._dl_btn.configure,
                           {"state": "normal", "text": "Retry"})

        threading.Thread(target=worker, daemon=True).start()

    def _on_downloaded(self):
        """Download complete — tell user to restart, keep PiKit open."""
        self._bar.set(1.0)
        self._status.configure(text="Downloaded — restart PiKit to install.",
                               text_color=T.SUCCESS)
        self._dl_btn.configure(state="normal", text="Restart Now",
                               fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                               command=self._restart_now)

    def _restart_now(self):
        """User clicked Restart Now — just exit, update applies on next launch."""
        import os
        self.master.destroy()
        os._exit(0)
