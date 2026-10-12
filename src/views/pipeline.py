"""Pipeline view — Full end-to-end: backup → shrink → compress, hands-off."""
import os
import threading
import datetime
import customtkinter as ctk

from .. import theme as T
from ..widgets import DriveSelector, ProgressPanel
from ..settings_mgr import Settings


class PipelineView(ctk.CTkFrame):
    def __init__(self, master, settings: Settings, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._settings  = settings
        self._cancel_ev = threading.Event()
        self._running   = False

        # ── Title ──────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Full Pipeline", font=T.FONT_H1,
                     text_color=T.TEXT).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(self,
                     text="Backup → Shrink → Compress  in one click.  Walk away.",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 16))

        # ── Drive ─────────────────────────────────────────────────────────────
        self._drives = DriveSelector(self, on_select=None)
        self._drives.pack(fill="x", pady=(0, 12))
        self._drives.refresh()

        # ── Output ────────────────────────────────────────────────────────────
        out_card = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=8,
                                border_width=1, border_color=T.BORDER)
        out_card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(out_card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(inner, text="Output", font=T.FONT_LABEL,
                     text_color=T.TEXT).pack(anchor="w", pady=(0, 8))

        folder_row = ctk.CTkFrame(inner, fg_color="transparent")
        folder_row.pack(fill="x", pady=(0, 6))
        folder_row.columnconfigure(0, weight=1)
        self._folder_entry = ctk.CTkEntry(folder_row, font=T.FONT_BODY,
                                          fg_color=T.BG_INPUT, border_color=T.BORDER,
                                          text_color=T.TEXT, height=34, corner_radius=6,
                                          placeholder_text="Output folder")
        self._folder_entry.insert(0, settings.get("default_image_folder"))
        self._folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(folder_row, text="Browse", width=72, height=34,
                      font=T.FONT_SMALL, fg_color=T.BG_INPUT, hover_color=T.BORDER,
                      text_color=T.TEXT_DIM, corner_radius=6,
                      command=self._browse).grid(row=0, column=1)

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

        # ── Steps ─────────────────────────────────────────────────────────────
        steps_card = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=8,
                                  border_width=1, border_color=T.BORDER)
        steps_card.pack(fill="x", pady=(0, 12))
        steps_inner = ctk.CTkFrame(steps_card, fg_color="transparent")
        steps_inner.pack(padx=14, pady=12, fill="x")

        ctk.CTkLabel(steps_inner, text="Steps", font=T.FONT_LABEL,
                     text_color=T.TEXT).pack(anchor="w", pady=(0, 8))

        self._step_vars = []
        self._step_labels = []
        steps = [
            ("1", "Backup — smart read (stop at last partition)", True,  True),
            ("2", "Shrink — PiShrink via WSL",                   True,  True),
            ("3", "Compress to .img.gz",                          True,  True),
            ("4", "Delete uncompressed .img when done",           False, False),
        ]
        for num, text, default, _ in steps:
            var = ctk.BooleanVar(value=default)
            self._step_vars.append(var)
            cb = ctk.CTkCheckBox(steps_inner, text=f"  {num}.  {text}",
                                 variable=var, font=T.FONT_BODY, text_color=T.TEXT,
                                 fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                                 checkmark_color="#000")
            cb.pack(anchor="w", pady=2)
            self._step_labels.append(cb)

        # ── Step status indicators ─────────────────────────────────────────────
        self._step_status = []
        status_card = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=8,
                                   border_width=1, border_color=T.BORDER)
        status_card.pack(fill="x", pady=(0, 12))
        status_inner = ctk.CTkFrame(status_card, fg_color="transparent")
        status_inner.pack(padx=14, pady=10, fill="x")

        step_names = ["Backup", "Shrink", "Compress", "Cleanup"]
        for name in step_names:
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

        # ── Run button ────────────────────────────────────────────────────────
        self._run_btn = ctk.CTkButton(self, text="🔄  Run Full Pipeline", height=42,
                                      font=T.FONT_TITLE, fg_color=T.ACCENT,
                                      hover_color=T.ACCENT_HOVER,
                                      text_color="#000", corner_radius=8,
                                      command=self._start)
        self._run_btn.pack(fill="x", pady=(0, 12))

        # ── Progress ──────────────────────────────────────────────────────────
        self._progress = ProgressPanel(self, on_cancel=self._cancel)
        self._progress.pack(fill="x")

        self._check_wsl()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_name(self):
        self._name_entry.delete(0, "end")
        date = datetime.date.today().strftime("%Y%m%d")
        self._name_entry.insert(0, f"Pi_Backup_{date}")

    def _browse(self):
        import tkinter.filedialog as fd
        p = fd.askdirectory(initialdir=self._folder_entry.get())
        if p:
            self._folder_entry.delete(0, "end")
            self._folder_entry.insert(0, p)

    def _check_wsl(self):
        from ..shrink import check_wsl
        ok, _ = check_wsl()
        if not ok:
            self._step_vars[1].set(False)
            self._step_labels[1].configure(
                state="disabled",
                text="  2.  Shrink — WSL not detected (install WSL to enable)")

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
        self.after(0, dot.configure, {"text": sym, "text_color": c})
        self.after(0, lbl.configure, {"text_color": tc})

    # ── Pipeline ──────────────────────────────────────────────────────────────

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
            self._progress.error("Output folder / filename missing")
            return

        os.makedirs(folder, exist_ok=True)
        self._cancel_ev.clear()
        self._running = True
        self._run_btn.configure(state="disabled")

        for i in range(4):
            self._set_step_state(i, "waiting")

        self._progress.start("Pipeline starting…")
        opts = {
            "smart":    True,
            "shrink":   self._step_vars[1].get(),
            "compress": self._step_vars[2].get(),
            "cleanup":  self._step_vars[3].get(),
            "folder":   folder,
            "name":     name,
        }
        threading.Thread(target=self._worker, args=(drive, opts), daemon=True).start()

    def _worker(self, drive, opts):
        import time
        folder   = opts["folder"]
        name     = opts["name"]
        img_path = os.path.join(folder, f"{name}.img")
        gz_path  = os.path.join(folder, f"{name}.img.gz")

        try:
            # Step 1: Backup
            self._set_step_state(0, "running")
            t0 = time.time()
            from ..disk import backup_disk

            def cb1(done, total, speed):
                self.after(0, self._progress.update, done, total, speed,
                           "Step 1/3: Backing up…")

            self.after(0, self._progress.log,
                       f"Backing up {drive.name} ({drive.size_str})")
            backup_disk(drive, img_path, smart=opts["smart"],
                        progress_cb=cb1, cancel_event=self._cancel_ev)

            if self._cancel_ev.is_set():
                raise InterruptedError()

            dur1 = time.time() - t0
            self.after(0, self._step_status[0][2].configure,
                       {"text": f"{dur1/60:.1f}m"})
            self._set_step_state(0, "done")
            sz = os.path.getsize(img_path)
            self.after(0, self._progress.log,
                       f"Backup done — {sz/1_073_741_824:.2f} GB")

            # Step 2: Shrink
            if opts["shrink"]:
                self._set_step_state(1, "running")
                t1 = time.time()
                from ..shrink import shrink_image

                def log_cb(line):
                    self.after(0, self._progress.log, line)

                self.after(0, self._progress.update, 0, 1, 0, "Step 2/3: Shrinking…")
                ok = shrink_image(img_path, log_cb=log_cb, cancel_event=self._cancel_ev)
                if not ok:
                    raise RuntimeError("PiShrink failed")
                dur2 = time.time() - t1
                self.after(0, self._step_status[1][2].configure,
                           {"text": f"{dur2/60:.1f}m"})
                self._set_step_state(1, "done")
                sz2 = os.path.getsize(img_path)
                self.after(0, self._progress.log,
                           f"After shrink: {sz2/1_073_741_824:.2f} GB")
            else:
                self._set_step_state(1, "skipped")

            if self._cancel_ev.is_set():
                raise InterruptedError()

            # Step 3: Compress
            if opts["compress"]:
                self._set_step_state(2, "running")
                t2 = time.time()
                from ..compress import compress_image

                def cb3(done, total, speed):
                    self.after(0, self._progress.update, done, total, speed,
                               "Step 3/3: Compressing…")

                compress_image(img_path, gz_path,
                               level=self._settings.get("compression_level"),
                               progress_cb=cb3, cancel_event=self._cancel_ev)
                dur3 = time.time() - t2
                self.after(0, self._step_status[2][2].configure,
                           {"text": f"{dur3/60:.1f}m"})
                self._set_step_state(2, "done")
                sz3 = os.path.getsize(gz_path)
                self.after(0, self._progress.log,
                           f"Compressed: {sz3/1_073_741_824:.2f} GB → {gz_path}")
                self._settings.add_recent_image(gz_path)
            else:
                self._set_step_state(2, "skipped")
                self._settings.add_recent_image(img_path)

            # Step 4: Cleanup
            if opts["cleanup"] and opts["compress"] and os.path.exists(img_path):
                self._set_step_state(3, "running")
                os.remove(img_path)
                self.after(0, self._progress.log, "Removed uncompressed .img")
                self._set_step_state(3, "done")
            else:
                self._set_step_state(3, "skipped")

            self.after(0, self._progress.finish, "Pipeline complete")

        except InterruptedError:
            self.after(0, self._progress.error, "Cancelled")
        except Exception as e:
            self.after(0, self._progress.error, f"Error: {e}")
            for i in range(4):
                dot, _, _ = self._step_status[i]
                if dot.cget("text") == "↻":
                    self._set_step_state(i, "error")
        finally:
            self._running = False
            self.after(0, self._run_btn.configure, {"state": "normal"})

    def _cancel(self):
        self._cancel_ev.set()

    def on_activate(self):
        self._drives.refresh()
        self._check_wsl()
