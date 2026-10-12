"""Backup view — read SD card to .img, then optionally shrink + compress."""
import os
import queue
import threading
import datetime
import customtkinter as ctk

from .. import theme as T
from ..widgets import DriveSelector, ProgressPanel
from ..settings_mgr import Settings
from ..logger import log


class BackupView(ctk.CTkFrame):
    def __init__(self, master, settings: Settings, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._settings  = settings
        self._cancel_ev = threading.Event()
        self._running   = False
        self._q         = queue.SimpleQueue()
        self._poll_q()

        # ── Title ──────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Backup SD Card", font=T.FONT_H1,
                     text_color=T.TEXT).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(self,
                     text="Read a Pi SD card to a .img.gz file.  Only copies used partition data.",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 16))

        # ── Drive selector ────────────────────────────────────────────────────
        self._drives = DriveSelector(self, on_select=self._on_drive_selected,
                                     label="Source Drive")
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

        ctk.CTkLabel(opts, text="Steps", font=T.FONT_LABEL,
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
        ctk.CTkCheckBox(opts, text="Keep uncompressed .img after compressing",
                        variable=self._keep_var, font=T.FONT_BODY,
                        text_color=T.TEXT_DIM, fg_color=T.ACCENT,
                        hover_color=T.ACCENT_HOVER,
                        checkmark_color="#000").pack(anchor="w")

        # ── Step status indicators ─────────────────────────────────────────────
        status_card = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=8,
                                   border_width=1, border_color=T.BORDER)
        status_card.pack(fill="x", pady=(0, 12))
        status_inner = ctk.CTkFrame(status_card, fg_color="transparent")
        status_inner.pack(padx=14, pady=10, fill="x")

        self._step_status = []
        for name in ["Backup", "Shrink", "Compress"]:
            row = ctk.CTkFrame(status_inner, fg_color="transparent")
            row.pack(fill="x", pady=2)
            dot = ctk.CTkLabel(row, text="○", width=18, font=(T.FONT_FAMILY, 13),
                               text_color=T.TEXT_MUTED)
            dot.pack(side="left")
            lbl = ctk.CTkLabel(row, text=name, font=T.FONT_BODY,
                               text_color=T.TEXT_MUTED, anchor="w")
            lbl.pack(side="left", padx=(4, 0))
            dur = ctk.CTkLabel(row, text="", font=T.FONT_SMALL,
                               text_color=T.TEXT_DIM)
            dur.pack(side="right")
            self._step_status.append((dot, lbl, dur))

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

    # ── Thread-safe dispatch ──────────────────────────────────────────────────

    def _poll_q(self):
        """Drain the UI-update queue on the main thread (runs every 30 ms)."""
        try:
            while True:
                fn, args = self._q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(30, self._poll_q)

    def _dispatch(self, fn, *args):
        """Schedule a UI call safely from any thread."""
        self._q.put((fn, args))

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
        def _worker():
            ok, _ = check_wsl()
            if not ok:
                try:
                    if self.winfo_exists():
                        self._dispatch( self._shrink_var.set, False)
                        self._dispatch( self._shrink_cb.configure, {
                            "state": "disabled",
                            "text": "Shrink — WSL not detected (install WSL to enable)"})
                except Exception:
                    pass
        threading.Thread(target=_worker, daemon=True).start()

    def _set_step_state(self, idx, state):
        """state: 'waiting'|'running'|'done'|'skipped'|'error'"""
        dot, lbl, dur = self._step_status[idx]
        colours = {
            "waiting": (T.TEXT_MUTED, "○", T.TEXT_MUTED),
            "running": (T.ACCENT,     "↻", T.TEXT),
            "done":    (T.SUCCESS,    "✓", T.TEXT),
            "skipped": (T.TEXT_DIM,   "—", T.TEXT_DIM),
            "error":   (T.ERROR,      "✗", T.ERROR),
        }
        c, sym, tc = colours.get(state, colours["waiting"])
        self._dispatch( dot.configure, {"text": sym, "text_color": c})
        self._dispatch( lbl.configure, {"text_color": tc})

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

        log.info(f"BackupView._start: drive={drive}  folder={folder}  name={name}")
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

        for i in range(3):
            self._set_step_state(i, "waiting")

        threading.Thread(target=self._worker, args=(drive, opts), daemon=True).start()

    def _worker(self, drive, opts):
        import time
        folder   = opts["folder"]
        name     = opts["name"]
        img_path = os.path.join(folder, f"{name}.img")
        gz_path  = os.path.join(folder, f"{name}.img.gz")

        log.info(f"BackupView._worker starting: {drive.device} → {img_path}")
        try:
            # Step 1: backup
            self._set_step_state(0, "running")
            t0 = time.time()
            from ..disk import backup_disk

            def cb(done, total, speed):
                self._dispatch( self._progress.update, done, total, speed, "Backing up…")

            self._dispatch( self._progress.log, f"Reading {drive.device} → {img_path}")
            if opts["smart"]:
                self._dispatch( self._progress.log, "Smart mode: stopping at last partition boundary")

            backup_disk(drive, img_path, smart=opts["smart"],
                        progress_cb=cb, cancel_event=self._cancel_ev)

            if self._cancel_ev.is_set():
                raise InterruptedError()

            dur0 = time.time() - t0
            self._dispatch( self._step_status[0][2].configure, {"text": f"{dur0/60:.1f}m"})
            self._set_step_state(0, "done")
            sz = os.path.getsize(img_path)
            self._dispatch( self._progress.log,
                       f"Backup done — {sz/1_073_741_824:.2f} GB written")

            # Step 2: shrink
            if opts["shrink"]:
                self._set_step_state(1, "running")
                t1 = time.time()
                self._dispatch( self._progress.log, "Shrinking with PiShrink…")
                from ..shrink import shrink_image

                def log_cb(line):
                    log.info(f"PiShrink: {line}")
                    self._dispatch( self._progress.log, line)

                self._dispatch( self._progress.update, 0, 1, 0, "Shrinking…")
                ok = shrink_image(img_path, log_cb=log_cb,
                                  cancel_event=self._cancel_ev)
                if not ok:
                    raise RuntimeError("PiShrink failed — see log")
                dur1 = time.time() - t1
                self._dispatch( self._step_status[1][2].configure, {"text": f"{dur1/60:.1f}m"})
                self._set_step_state(1, "done")
                sz2 = os.path.getsize(img_path)
                self._dispatch( self._progress.log,
                           f"After shrink: {sz2/1_073_741_824:.2f} GB")
            else:
                self._set_step_state(1, "skipped")

            if self._cancel_ev.is_set():
                raise InterruptedError()

            # Step 3: compress
            if opts["compress"]:
                self._set_step_state(2, "running")
                t2 = time.time()
                self._dispatch( self._progress.log, "Compressing…")
                from ..compress import compress_image

                def cb2(done, total, speed):
                    self._dispatch( self._progress.update, done, total, speed,
                               "Compressing…")

                compress_image(img_path, gz_path,
                               level=self._settings.get("compression_level"),
                               progress_cb=cb2, cancel_event=self._cancel_ev)

                dur2 = time.time() - t2
                self._dispatch( self._step_status[2][2].configure, {"text": f"{dur2/60:.1f}m"})
                self._set_step_state(2, "done")
                sz3 = os.path.getsize(gz_path)
                self._dispatch( self._progress.log,
                           f"Compressed: {sz3/1_073_741_824:.2f} GB → {gz_path}")
                self._settings.add_recent_image(gz_path)

                if not opts["keep_img"] and os.path.exists(img_path):
                    os.remove(img_path)
                    self._dispatch( self._progress.log, "Removed uncompressed .img")
            else:
                self._set_step_state(2, "skipped")
                self._settings.add_recent_image(img_path)

            self._dispatch( self._progress.finish, "Backup complete")

        except InterruptedError:
            log.info("BackupView._worker: cancelled")
            self._dispatch( self._progress.error, "Cancelled")
            self._cleanup(img_path)
        except Exception as e:
            log.exception(f"BackupView._worker failed: {e}")
            self._dispatch( self._progress.error, f"Error: {e}")
            for i in range(3):
                dot, _, _ = self._step_status[i]
                if dot.cget("text") == "↻":
                    self._set_step_state(i, "error")
        finally:
            self._running = False
            self._dispatch( self._start_btn.configure, {"state": "normal"})

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
