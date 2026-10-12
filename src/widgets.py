"""
widgets.py — Reusable UI components shared across views.
"""
import time
import threading
import customtkinter as ctk
from . import theme as T


# ── DriveSelector ──────────────────────────────────────────────────────────────

class DriveSelector(ctk.CTkFrame):
    """
    Scrollable list of removable drives.  Call refresh() to reload.
    selected_drive() returns the currently selected DriveInfo or None.
    on_select(drive) callback fired when user picks a drive.
    """

    def __init__(self, master, on_select=None, **kwargs):
        super().__init__(master, fg_color=T.BG_CARD, corner_radius=8,
                         border_width=1, border_color=T.BORDER, **kwargs)
        self._on_select = on_select
        self._selected  = None
        self._rows      = []

        # header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(hdr, text="Target Drive", font=T.FONT_LABEL,
                     text_color=T.TEXT).pack(side="left")
        ctk.CTkButton(hdr, text="↺ Refresh", width=80, height=26,
                      font=T.FONT_SMALL, fg_color=T.BG_INPUT,
                      hover_color=T.BORDER, text_color=T.TEXT_DIM,
                      corner_radius=6, command=self.refresh).pack(side="right")

        self._list = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                            height=130)
        self._list.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._empty_lbl = ctk.CTkLabel(self._list,
                                       text="No removable drives detected.",
                                       font=T.FONT_SMALL, text_color=T.TEXT_DIM)
        self._empty_lbl.pack(pady=20)

    def refresh(self):
        """Non-blocking refresh — runs PowerShell in a background thread."""
        import threading
        from .disk import list_usb_drives

        # Clear existing rows immediately
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._selected = None
        self._empty_lbl.configure(text="Scanning…")
        self._empty_lbl.pack(pady=20)

        def _worker():
            drives = list_usb_drives()
            try:
                # Widget may have been destroyed if user switched tabs quickly
                if self.winfo_exists():
                    self.after(0, self._populate, drives)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _populate(self, drives):
        if not drives:
            self._empty_lbl.configure(text="No removable drives detected.")
            self._empty_lbl.pack(pady=20)
            return
        self._empty_lbl.pack_forget()
        for drive in drives:
            row = _DriveRow(self._list, drive, self._pick)
            row.pack(fill="x", pady=2, padx=2)
            self._rows.append(row)

    def _pick(self, drive, row):
        for r in self._rows:
            r.set_selected(False)
        row.set_selected(True)
        self._selected = drive
        if self._on_select:
            self._on_select(drive)

    def selected_drive(self):
        return self._selected


class _DriveRow(ctk.CTkFrame):
    def __init__(self, master, drive, on_click, **kwargs):
        super().__init__(master, fg_color=T.BG_INPUT, corner_radius=6,
                         cursor="hand2", **kwargs)
        self._drive    = drive
        self._on_click = on_click
        self._selected = False

        self._indicator = ctk.CTkFrame(self, width=4, fg_color=T.BORDER,
                                       corner_radius=2)
        self._indicator.pack(side="left", fill="y", padx=(6, 8), pady=6)

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, pady=8)

        top = f"{drive.name}   {drive.size_str}"
        bot = f"{drive.letters_str}   ·   Device: {drive.device}"
        ctk.CTkLabel(info, text=top, font=T.FONT_BODY, text_color=T.TEXT,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(info, text=bot, font=T.FONT_SMALL, text_color=T.TEXT_DIM,
                     anchor="w").pack(fill="x")

        self.bind("<Button-1>", self._click)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._click)
            for grandchild in child.winfo_children():
                grandchild.bind("<Button-1>", self._click)

    def _click(self, _=None):
        self._on_click(self._drive, self)

    def set_selected(self, val: bool):
        self._selected = val
        colour = T.ACCENT if val else T.BORDER
        self._indicator.configure(fg_color=colour)
        self.configure(fg_color=T.BG_ROW_SEL if val else T.BG_INPUT)


# ── ProgressPanel ─────────────────────────────────────────────────────────────

class ProgressPanel(ctk.CTkFrame):
    """
    Shows operation status, progress bar, speed, ETA, log, and cancel button.
    Call start() / update(done, total, speed) / finish() / error().
    """

    def __init__(self, master, on_cancel=None, **kwargs):
        super().__init__(master, fg_color=T.BG_CARD, corner_radius=8,
                         border_width=1, border_color=T.BORDER, **kwargs)
        self._on_cancel = on_cancel
        self._start_t   = None

        # Status row
        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.pack(fill="x", padx=14, pady=(12, 4))

        self._dot = ctk.CTkLabel(status_row, text="●", width=14,
                                 font=(T.FONT_FAMILY, 12), text_color=T.TEXT_DIM)
        self._dot.pack(side="left")
        self._status_lbl = ctk.CTkLabel(status_row, text="Ready",
                                        font=T.FONT_BODY, text_color=T.TEXT_DIM,
                                        anchor="w")
        self._status_lbl.pack(side="left", padx=(6, 0))
        self._cancel_btn = ctk.CTkButton(status_row, text="Cancel", width=70,
                                         height=26, font=T.FONT_SMALL,
                                         fg_color=T.BG_INPUT, text_color=T.WARN,
                                         hover_color=T.BORDER, corner_radius=6,
                                         command=self._cancel, state="disabled")
        self._cancel_btn.pack(side="right")

        # Progress bar + meta
        self._bar = ctk.CTkProgressBar(self, height=8, corner_radius=4,
                                       fg_color=T.BORDER,
                                       progress_color=T.ACCENT)
        self._bar.set(0)
        self._bar.pack(fill="x", padx=14, pady=(2, 0))

        meta_row = ctk.CTkFrame(self, fg_color="transparent")
        meta_row.pack(fill="x", padx=14, pady=(4, 8))
        self._pct_lbl   = ctk.CTkLabel(meta_row, text="", font=T.FONT_SMALL,
                                       text_color=T.TEXT_DIM)
        self._pct_lbl.pack(side="left")
        self._speed_lbl = ctk.CTkLabel(meta_row, text="", font=T.FONT_SMALL,
                                       text_color=T.TEXT_DIM)
        self._speed_lbl.pack(side="right")

        # Log
        self._log = ctk.CTkTextbox(self, height=90, font=T.FONT_MONO,
                                   fg_color=T.BG_MAIN, text_color=T.TEXT_DIM,
                                   border_width=0, wrap="word", state="disabled")
        self._log.pack(fill="x", padx=8, pady=(0, 10))

    # public API ───────────────────────────────────────────────────────────────

    def start(self, label="Working…"):
        self._start_t = time.time()
        self._bar.set(0)
        self._bar.configure(progress_color=T.ACCENT)
        self._dot.configure(text_color=T.ACCENT)
        self._status_lbl.configure(text=label, text_color=T.TEXT)
        self._cancel_btn.configure(state="normal")
        self._pct_lbl.configure(text="0%")
        self._speed_lbl.configure(text="")
        self._clear_log()

    def update(self, done: int, total: int, speed_bps: float, label: str = None):
        if label:
            self._status_lbl.configure(text=label)
        pct = done / total if total else 0
        self._bar.set(min(pct, 1.0))
        self._pct_lbl.configure(text=f"{pct*100:.1f}%")
        speed_mb = speed_bps / 1_048_576
        remaining = ((total - done) / speed_bps) if speed_bps > 0 and total else 0
        eta = _fmt_duration(remaining)
        self._speed_lbl.configure(text=f"{speed_mb:.1f} MB/s  ·  {eta}")

    def log(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def finish(self, label="Complete"):
        self._bar.set(1.0)
        elapsed = time.time() - self._start_t if self._start_t else 0
        self._status_lbl.configure(text=f"{label}  ({_fmt_duration(elapsed)})",
                                   text_color=T.SUCCESS)
        self._dot.configure(text_color=T.SUCCESS)
        self._cancel_btn.configure(state="disabled")
        self._speed_lbl.configure(text="")
        self._pct_lbl.configure(text="100%")

    def error(self, msg="Failed"):
        self._bar.configure(progress_color=T.ERROR)
        self._status_lbl.configure(text=msg, text_color=T.ERROR)
        self._dot.configure(text_color=T.ERROR)
        self._cancel_btn.configure(state="disabled")

    def reset(self):
        self._bar.set(0)
        self._bar.configure(progress_color=T.ACCENT)
        self._dot.configure(text_color=T.TEXT_DIM)
        self._status_lbl.configure(text="Ready", text_color=T.TEXT_DIM)
        self._cancel_btn.configure(state="disabled")
        self._pct_lbl.configure(text="")
        self._speed_lbl.configure(text="")
        self._clear_log()

    # private ──────────────────────────────────────────────────────────────────

    def _cancel(self):
        self._cancel_btn.configure(state="disabled")
        self._status_lbl.configure(text="Cancelling…", text_color=T.WARN)
        if self._on_cancel:
            self._on_cancel()

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


# ── FilePickRow ────────────────────────────────────────────────────────────────

class FilePickRow(ctk.CTkFrame):
    """Label + path entry + browse button, optional recent dropdown."""

    def __init__(self, master, label, mode="open", filetypes=None,
                 default_dir=None, recents=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._mode      = mode        # "open" or "save" or "dir"
        self._filetypes = filetypes or [("All files", "*.*")]
        self._default   = default_dir or ""
        self._recents   = recents or []

        ctk.CTkLabel(self, text=label, font=T.FONT_LABEL,
                     text_color=T.TEXT).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(row, font=T.FONT_BODY, fg_color=T.BG_INPUT,
                                   border_color=T.BORDER, text_color=T.TEXT,
                                   height=34, corner_radius=6)
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(row, text="Browse", width=72, height=34,
                      font=T.FONT_SMALL, fg_color=T.BG_INPUT,
                      hover_color=T.BORDER, text_color=T.TEXT_DIM,
                      corner_radius=6, command=self._browse).grid(row=0, column=1)

        if self._recents:
            recent_row = ctk.CTkFrame(self, fg_color="transparent")
            recent_row.pack(fill="x", pady=(4, 0))
            ctk.CTkLabel(recent_row, text="Recent:", font=T.FONT_SMALL,
                         text_color=T.TEXT_DIM).pack(side="left")
            opts = [r for r in self._recents if r][:5]
            if opts:
                om = ctk.CTkOptionMenu(recent_row, values=opts, width=420,
                                       height=26, font=T.FONT_SMALL,
                                       fg_color=T.BG_INPUT,
                                       button_color=T.BG_INPUT,
                                       dropdown_fg_color=T.BG_CARD,
                                       text_color=T.TEXT_DIM,
                                       dropdown_text_color=T.TEXT,
                                       command=self._pick_recent)
                om.pack(side="left", padx=(6, 0))

    def _browse(self):
        import tkinter.filedialog as fd
        if self._mode == "open":
            path = fd.askopenfilename(filetypes=self._filetypes,
                                      initialdir=self._default)
        elif self._mode == "dir":
            path = fd.askdirectory(initialdir=self._default)
        else:
            path = fd.asksaveasfilename(filetypes=self._filetypes,
                                        initialdir=self._default)
        if path:
            self.set(path)

    def _pick_recent(self, val):
        self.set(val)

    def get(self):
        return self._entry.get().strip()

    def set(self, path):
        self._entry.delete(0, "end")
        self._entry.insert(0, path)


# ── ConfirmEntry ───────────────────────────────────────────────────────────────

class ConfirmEntry(ctk.CTkFrame):
    """
    Safety field: shows a warning and requires the user to type
    a specific string before the confirm button becomes active.
    """

    def __init__(self, master, confirm_text: str, button_text="Confirm",
                 on_confirm=None, warn_msg=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._required   = confirm_text
        self._on_confirm = on_confirm

        warn = warn_msg or f"This will ERASE the drive.  Type  {confirm_text}  to confirm."
        ctk.CTkLabel(self, text=f"⚠  {warn}", font=T.FONT_SMALL,
                     text_color=T.WARN, wraplength=500, justify="left",
                     anchor="w").pack(anchor="w", pady=(0, 6))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        self._entry = ctk.CTkEntry(row, width=140, height=34, font=T.FONT_BODY,
                                   fg_color=T.BG_INPUT, border_color=T.BORDER,
                                   text_color=T.TEXT, corner_radius=6,
                                   placeholder_text=f"type {confirm_text}")
        self._entry.pack(side="left", padx=(0, 8))
        self._entry.bind("<KeyRelease>", self._check)

        self._btn = ctk.CTkButton(row, text=button_text, height=34, width=160,
                                  font=T.FONT_LABEL, fg_color=T.ACCENT_DIM,
                                  hover_color=T.ACCENT_DIM, text_color=T.TEXT,
                                  corner_radius=6, state="disabled",
                                  command=self._fire)
        self._btn.pack(side="left")

    def _check(self, _=None):
        ok = self._entry.get().strip() == self._required
        self._btn.configure(state="normal" if ok else "disabled",
                            fg_color=T.ACCENT if ok else T.ACCENT_DIM,
                            hover_color=T.ACCENT_HOVER if ok else T.ACCENT_DIM)

    def _fire(self):
        if self._on_confirm:
            self._on_confirm()
        self.reset()

    def reset(self):
        self._entry.delete(0, "end")
        self._btn.configure(state="disabled", fg_color=T.ACCENT_DIM,
                            hover_color=T.ACCENT_DIM)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_duration(secs: float) -> str:
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"
