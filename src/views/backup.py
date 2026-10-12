"""Backup view — read SD card to .img, then optionally shrink + compress."""
import os
import threading
import datetime
import customtkinter as ctk

from .. import theme as T
from ..widgets import DriveSelector, ProgressPanel
from ..settings_mgr import Settings


class BackupView(ctk.CTkFrame):
    def __init__(self, master, settings: Settings, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._settings  = settings
        self._cancel_ev = threading.Event()
        self._running   = False

        # ── Title ──────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Backup SD Card", font=T.FONT_H1,
                     text_color=T.TEXT).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(self,
                     text="Read a Pi SD card to a .img.gz file.  Only copies used partition data.",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 16))

        # ── Drive selector ────────────────────────────────────────────────────
        self._drives = DriveSelector(self, on_select=self._on_drive_selected)
        self._drives.pack(fill="x", pady=(0, 12))

        # ── Output location ───────────────────────────────────────────────────
        out_card = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=8,
                                border_width=1, border_color=T.BORDER)
        out_card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(out_card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(inner, text="Save To", font=T.FONT_LABEL,
                     text_color=T.TEXT).pack(anchor="w", pady=(0, 6))

        folder_row = ctk.CTkFrame(inner, fg_color="transparent")
        folder_row.pack(fill="x", pady=(0, 8))
        folder_row.columnconfigure(0, weight=1)

        self._folder_entry = ctk.CTkEntry(folder_row, font=T.FONT_BODY,
                                          fg_color=T.BG_INPUT, border_color=T.BORDER,
                                          text_color=T.TEXT, height=34, corner_radius=6)
        self._folder_entry.insert(0, settings.get("default_image_folder"))
        self._folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(folder_row, text="Browse", width=72, height=34,
                      font=T.FONT_SMALL, fg_color=T.BG_INPUT, hover_color=T.BORDER,
                      text_color=T.TEXT_DIM, corner_radius=6,
                      command=self._browse_folder).grid(row=0, column=1)

        name_row = ctk.CTkFrame(inner, fg_color="transparent")
        name_row.pack(fill="x")
        name_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(name_row, text="Filename:", font=T.FONT_BODY,
                     text_color=T.TEXT_DIM, width=70).grid(row=0, column=0, sticky="w")
        self._name_entry = ctk.CTkEntry(name_row, font=T.FONT_BODY,
                                        fg_color=T.BG_INPUT, border_color=T.BORDER,
                                        text_color=T.TEXT, height=34, corner_radius=6)
        self._name_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(name_row, text=".img.gz", font=T.FONT_BODY,
                     text_color=T.TEXT_DIM).grid(row=0, column=2, padx=(6, 0))

        self._refresh_name()

        # ── Options ───────────────────────────────────────────────────────────
        opt_card = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=8,
                                border_width=1, border_color=T.BORDER)
        opt_card.pack(fill="x", pady=(0, 12))
        opts = ctk.CTkFrame(opt_card, fg_color="transparent")
        opts.pack(padx=14, pady=12, fill="x")

        ctk.CTkLabel(opts, text="Pipeline", font=T.FONT_LABEL,
                     text_color=T.TEXT).pack(anchor="w", pady=(0, 8))

        self._smart_var = ctk.BooleanVar(value=settings.get("smart_backup"))
        ctk.CTkCheckBox(opts,
                        text="Smart backup — stop at last partition boundary (recommended)",
                        variable=self._smart_var, font=T.FONT_BODY, text_color=T.TEXT,
                        fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                        checkmark_color="#000").pack(anchor="w", pady=(0, 4))

        self._shrink_var = ctk.BooleanVar(value=settings.get("shrink_before_compress"))
        self._shrink_cb = ctk.CTkCheckBox(opts,
                        text="Shrink — remove unused filesystem space  (requires WSL)",
                        variable=self._shrink_var, font=T.FONT_BODY, text_color=T.TEXT,
                        fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                        checkmark_color="#000")
        self._shrink_cb.pack(anchor="w", pady=(0, 4))

        self._compress_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts, text="Compress to .img.gz",
                        variable=self._compress_var, font=T.FONT_BODY,
                        text_color=T.TEXT, fg_color=T.ACCENT,
                        hover_color=T.ACCENT_HOVER,
                        checkmark_color="#000").pack(anchor="w", pady=(0, 4))

        self._keep_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="Keep uncompressed .img",
                        variable=self._keep_var, font=T.FONT_BODY,
                        text_color=T.TEXT_DIM, fg_color=T.ACCENT,
                        hover_color=T.ACCENT_HOVER,
                        checkmark_color="#000").pack(anchor="w")

        # ── Start button ──────────────────────────────────────────────────────
        self._start_btn = ctk.CTkButton(self, text="💾  Start Backup", height=42,
                                         font=T.FONT_TITLE, fg_color=T.ACCENT,
                                         hover_color=T.ACCENT_HOVER,
                                         text_color="#000", corner_radius=8,
                                         command=self._start)
        self._start_btn.pack(fill="x", pady=(0, 12))

        # ── Progress ──────────────────────────────────────────────────────────
        self._progress = ProgressPanel(self, on_cancel=self._cancel)
        self._progress.pack(fill="x")

        self._check_wsl()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_name(self):
        self._name_entry.delete(0, "end")
        date = datetime.date.today().strftime("%Y%m%d")
        self._name_entry.insert(0, f"Pi_Backup_{date}")

    def _browse_folder(self):
        import tkinter.filedialog as fd
        p = fd.askdirectory(initialdir=self._folder_entry.get())
        if p:
            self._folder_entry.delete(0, "end")
            self._folder_entry.insert(0, p)

    def _check_wsl(self):
        from ..shrink import check_wsl
        ok, _ = check_wsl()
        if not ok:
            self._shrink_var.set(False)
            self._shrink_cb.configure(state="disabled",
                                      text="Shrink — WSL not detected (install WSL to enable)")

    def _on_drive_selected(self, drive):
        pass

    # ── Backup logic ──────────────────────────────────────────────────────────

    def _start(self):
        if self._running:
            return
        drive = self._drives.selected_drive()
        if not drive:
            self._progress.error("No drive selected")
            return

        folder = self._folder_entry.get().strip()
        name   = self._name_entry.get().strip()
        if not folder or not name:
            self._progress.error("Folder / filename missing")
            return

        os.makedirs(folder, exist_ok=True)

        opts = {
            "smart":    self._smart_var.get(),
            "shrink":   self._shrink_var.get(),
            "compress": self._compress_var.get(),
            "keep_img": self._keep_var.get(),
            "folder":   folder,
            "name":     name,
        }

        self._settings.set("default_image_folder", folder)
        self._settings.set("smart_backup", opts["smart"])
        self._settings.set("shrink_before_compress", opts["shrink"])

        self._cancel_ev.clear()
        self._running = True
        self._start_btn.configure(state="disabled")
        self._progress.start("Starting backup…")

        threading.Thread(target=self._worker, args=(drive, opts), daemon=True).start()

    def _worker(self, drive, opts):
        import datetime
        folder   = opts["folder"]
        name     = opts["name"]
        img_path = os.path.join(folder, f"{name}.img")
        gz_path  = os.path.join(folder, f"{name}.img.gz")

        try:
            # Step 1: backup
            from ..disk import backup_disk
            step = "Step 1/3: Backing up…" if (opts["shrink"] or opts["compress"]) else "Backing up…"

            def cb(done, total, speed):
                self.after(0, self._progress.update, done, total, speed, step)

            self.after(0, self._progress.log, f"Reading {drive.device} → {img_path}")
            if opts["smart"]:
                self.after(0, self._progress.log, "Smart mode: stopping at last partition boundary")

            backup_disk(drive, img_path, smart=opts["smart"],
                        progress_cb=cb, cancel_event=self._cancel_ev)

            if self._cancel_ev.is_set():
                raise InterruptedError()

            sz = os.path.getsize(img_path)
            self.after(0, self._progress.log,
                       f"Backup done — {sz/1_073_741_824:.2f} GB written")

            # Step 2: shrink
            if opts["shrink"]:
                self.after(0, self._progress.log, "Step 2: Shrinking with PiShrink…")
                self.after(0, self._progress.update, 0, 1, 0, "Step 2/3: Shrinking…")
                from ..shrink import shrink_image

                def log_cb(line):
                    self.after(0, self._progress.log, line)

                ok = shrink_image(img_path, log_cb=log_cb,
                                  cancel_event=self._cancel_ev)
                if not ok:
                    raise RuntimeError("PiShrink failed — see log")
                sz2 = os.path.getsize(img_path)
                self.after(0, self._progress.log,
                           f"After shrink: {sz2/1_073_741_824:.2f} GB")

            if self._cancel_ev.is_set():
                raise InterruptedError()

            # Step 3: compress
            if opts["compress"]:
                self.after(0, self._progress.log, "Step 3: Compressing…")
                from ..compress import compress_image

                def cb2(done, total, speed):
                    self.after(0, self._progress.update, done, total, speed,
                               "Step 3/3: Compressing…")

                compress_image(img_path, gz_path,
                               level=self._settings.get("compression_level"),
                               progress_cb=cb2, cancel_event=self._cancel_ev)

                sz3 = os.path.getsize(gz_path)
                self.after(0, self._progress.log,
                           f"Compressed: {sz3/1_073_741_824:.2f} GB → {gz_path}")
                self._settings.add_recent_image(gz_path)

                if not opts["keep_img"] and os.path.exists(img_path):
                    os.remove(img_path)
                    self.after(0, self._progress.log, "Removed uncompressed .img")
            else:
                self._settings.add_recent_image(img_path)

            self.after(0, self._progress.finish, "Backup complete")

        except InterruptedError:
            self.after(0, self._progress.error, "Cancelled")
            self._cleanup(img_path)
        except Exception as e:
            self.after(0, self._progress.error, f"Error: {e}")
        finally:
            self._running = False
            self.after(0, self._start_btn.configure, {"state": "normal"})

    def _cleanup(self, img_path):
        try:
            if os.path.exists(img_path):
                os.remove(img_path)
        except Exception:
            pass

    def _cancel(self):
        self._cancel_ev.set()

    def on_activate(self):
        self._drives.refresh()
        self._check_wsl()
