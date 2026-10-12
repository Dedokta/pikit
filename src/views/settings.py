"""Settings view."""
import os
import queue
import threading
import customtkinter as ctk

from .. import theme as T
from ..settings_mgr import Settings, DEFAULTS


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, settings: Settings, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._settings = settings
        self._q = queue.SimpleQueue()
        self._poll_q()

        ctk.CTkLabel(self, text="Settings", font=T.FONT_H1,
                     text_color=T.TEXT).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(self, text="Saved automatically to %APPDATA%\\PiKit\\settings.json",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 16))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._build(scroll)

    def _build(self, parent):
        s = self._settings

        # ── Folders ───────────────────────────────────────────────────────────
        self._section(parent, "Default Locations")

        self._folder_var = ctk.StringVar(value=s.get("default_image_folder"))
        self._folder_row(parent, "Image Folder", self._folder_var,
                         "default_image_folder")

        # ── Compression ───────────────────────────────────────────────────────
        self._section(parent, "Compression")
        ctk.CTkLabel(parent, text="Level  (higher = smaller file, slower)",
                     font=T.FONT_BODY, text_color=T.TEXT_DIM,
                     anchor="w").pack(fill="x", pady=(0, 4))

        level_row = ctk.CTkFrame(parent, fg_color="transparent")
        level_row.pack(fill="x", pady=(0, 12))
        self._level_seg = ctk.CTkSegmentedButton(
            level_row,
            values=["1 — Fast", "6 — Balanced", "9 — Best"],
            font=T.FONT_BODY,
            fg_color=T.BG_INPUT,
            selected_color=T.ACCENT,
            selected_hover_color=T.ACCENT_HOVER,
            unselected_color=T.BG_INPUT,
            unselected_hover_color=T.BORDER,
            text_color=T.TEXT,
            command=self._level_changed,
        )
        level_map = {1: "1 — Fast", 6: "6 — Balanced", 9: "9 — Best"}
        self._level_seg.set(level_map.get(s.get("compression_level"), "6 — Balanced"))
        self._level_seg.pack(side="left")

        # ── Flash ─────────────────────────────────────────────────────────────
        self._section(parent, "Flash")
        self._bool_row(parent, "Verify after flash  (re-read and checksum)",
                       "verify_after_flash")

        # ── Backup ────────────────────────────────────────────────────────────
        self._section(parent, "Backup")
        self._bool_row(parent, "Smart backup by default  (stop at last partition)",
                       "smart_backup")
        self._bool_row(parent, "Shrink by default  (requires WSL)",
                       "shrink_before_compress")
        self._bool_row(parent, "Auto-name backups with date",
                       "auto_name_with_date")

        # ── Safety ────────────────────────────────────────────────────────────
        self._section(parent, "Safety")
        self._bool_row(parent, "Show removable drives only  (strongly recommended)",
                       "removable_only")

        # ── WSL ───────────────────────────────────────────────────────────────
        self._section(parent, "WSL")
        self._wsl_status(parent)

        # ── Updates ───────────────────────────────────────────────────────────
        self._section(parent, "Updates")
        from ..version import APP_VERSION, GITHUB_REPO
        ctk.CTkLabel(parent, text=f"Installed: v{APP_VERSION}   ·   {GITHUB_REPO}",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM,
                     anchor="w").pack(anchor="w", pady=(0, 8))

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(0, 6))
        self._check_btn = ctk.CTkButton(btn_row, text="Check for updates",
                                        height=34, width=160, font=T.FONT_BODY,
                                        fg_color=T.BG_INPUT, hover_color=T.BORDER,
                                        text_color=T.TEXT, corner_radius=6,
                                        command=self._manual_check)
        self._check_btn.pack(side="left")
        self._update_status = ctk.CTkLabel(btn_row, text="", font=T.FONT_SMALL,
                                           text_color=T.TEXT_DIM)
        self._update_status.pack(side="left", padx=(12, 0))

        # ── Reset ─────────────────────────────────────────────────────────────
        self._section(parent, "Reset")
        ctk.CTkButton(parent, text="Reset all settings to defaults",
                      height=34, font=T.FONT_BODY,
                      fg_color=T.BG_INPUT, hover_color=T.BORDER,
                      text_color=T.WARN, corner_radius=6,
                      command=self._reset).pack(anchor="w")

    # ── Thread-safe dispatch ──────────────────────────────────────────────────

    def _poll_q(self):
        try:
            while True:
                fn, args = self._q.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.after(30, self._poll_q)

    def _dispatch(self, fn, *args):
        self._q.put((fn, args))

    def _maybe_show_banner(self, version, notes, url):
        root = self.winfo_toplevel()
        if hasattr(root, "_show_update_banner"):
            root._show_update_banner(version, notes, url)

    # ── Widget helpers ─────────────────────────────────────────────────────────

    def _section(self, parent, title):
        ctk.CTkFrame(parent, height=1, fg_color=T.BORDER).pack(fill="x",
                                                                 pady=(14, 10))
        ctk.CTkLabel(parent, text=title, font=T.FONT_LABEL,
                     text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 8))

    def _bool_row(self, parent, label, key):
        var = ctk.BooleanVar(value=self._settings.get(key))

        def changed():
            self._settings.set(key, var.get())

        ctk.CTkCheckBox(parent, text=label, variable=var, command=changed,
                        font=T.FONT_BODY, text_color=T.TEXT,
                        fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                        checkmark_color="#000").pack(anchor="w", pady=3)

    def _folder_row(self, parent, label, var, key):
        ctk.CTkLabel(parent, text=label, font=T.FONT_BODY,
                     text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 4))
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        row.columnconfigure(0, weight=1)
        entry = ctk.CTkEntry(row, textvariable=var, font=T.FONT_BODY,
                             fg_color=T.BG_INPUT, border_color=T.BORDER,
                             text_color=T.TEXT, height=34, corner_radius=6)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        entry.bind("<FocusOut>", lambda _: self._settings.set(key, var.get()))

        def browse():
            import tkinter.filedialog as fd
            p = fd.askdirectory(initialdir=var.get())
            if p:
                var.set(p)
                self._settings.set(key, p)

        ctk.CTkButton(row, text="Browse", width=72, height=34,
                      font=T.FONT_SMALL, fg_color=T.BG_INPUT,
                      hover_color=T.BORDER, text_color=T.TEXT_DIM,
                      corner_radius=6, command=browse).grid(row=0, column=1)

    def _level_changed(self, val):
        level_map = {"1 — Fast": 1, "6 — Balanced": 6, "9 — Best": 9}
        self._settings.set("compression_level", level_map.get(val, 6))

    def _wsl_status(self, parent):
        from ..shrink import check_wsl
        # Placeholder label updated once the background check finishes
        self._wsl_lbl = ctk.CTkLabel(parent, text="Checking WSL…",
                                     font=T.FONT_SMALL, text_color=T.TEXT_DIM,
                                     justify="left", anchor="w")
        self._wsl_lbl.pack(anchor="w")

        def _worker():
            ok, distros = check_wsl()
            colour = T.SUCCESS if ok else T.WARN
            msg = ("WSL detected — shrink step available.\nDistros: " +
                   ", ".join(distros)) if ok else \
                  ("WSL not detected.  Install WSL to enable the shrink step.\n"
                   "Run:  wsl --install  in an admin terminal.")
            self._dispatch(self._wsl_lbl.configure, {"text": msg, "text_color": colour})
        threading.Thread(target=_worker, daemon=True).start()

    def _manual_check(self):
        self._check_btn.configure(state="disabled")
        self._update_status.configure(text="Checking…", text_color=T.TEXT_DIM)

        from ..updater import check_for_update

        def up_to_date(latest):
            self._dispatch(self._update_status.configure,
                           {"text": f"✓  You're on the latest version (v{latest})",
                            "text_color": T.SUCCESS})
            self._dispatch(self._check_btn.configure, {"state": "normal"})

        def update_available(version, notes, url):
            self._dispatch(self._update_status.configure,
                           {"text": f"↑  v{version} is available",
                            "text_color": T.WARN})
            self._dispatch(self._check_btn.configure, {"state": "normal"})
            self._dispatch(self._maybe_show_banner, version, notes, url)

        def error(msg):
            self._dispatch(self._update_status.configure,
                           {"text": f"✗  {msg}", "text_color": T.ERROR})
            self._dispatch(self._check_btn.configure, {"state": "normal"})

        check_for_update(
            on_update_available=update_available,
            on_up_to_date=up_to_date,
            on_error=error,
        )

    def _reset(self):
        for key, val in DEFAULTS.items():
            self._settings.set(key, val)
        # Rebuild the view (simplest approach)
        for child in self.winfo_children():
            child.destroy()
        ctk.CTkLabel(self, text="Settings", font=T.FONT_H1,
                     text_color=T.TEXT).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(self, text="Saved automatically to %APPDATA%\\PiKit\\settings.json",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 16))
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        self._build(scroll)

    def on_activate(self):
        pass
