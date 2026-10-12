"""Flash view — write a .img or .img.gz to an SD card."""
import os
import threading
import customtkinter as ctk

from .. import theme as T
from ..widgets import DriveSelector, FilePickRow, ConfirmEntry, ProgressPanel
from ..settings_mgr import Settings


class FlashView(ctk.CTkFrame):
    def __init__(self, master, settings: Settings, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._settings  = settings
        self._cancel_ev = threading.Event()
        self._running   = False

        # ── Title ──────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Flash Image to SD Card", font=T.FONT_H1,
                     text_color=T.TEXT).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(self, text="Write a .img or .img.gz image directly to a removable drive.",
                     font=T.FONT_SMALL, text_color=T.TEXT_DIM).pack(anchor="w", pady=(0, 16))

        # ── Image file ────────────────────────────────────────────────────────
        self._img_pick = FilePickRow(
            self, label="Image File",
            mode="open",
            filetypes=[("Pi Image", "*.img *.img.gz *.gz"), ("All files", "*.*")],
            default_dir=settings.get("default_image_folder"),
            recents=settings.get("recent_images"),
        )
        self._img_pick.pack(fill="x", pady=(0, 12))

        # ── Drive selector ────────────────────────────────────────────────────
        self._drives = DriveSelector(self, on_select=self._on_drive_selected)
        self._drives.pack(fill="x", pady=(0, 12))
        self._drives.refresh()

        # ── Options ───────────────────────────────────────────────────────────
        opt_frame = ctk.CTkFrame(self, fg_color=T.BG_CARD, corner_radius=8,
                                 border_width=1, border_color=T.BORDER)
        opt_frame.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(opt_frame, fg_color="transparent")
        inner.pack(padx=14, pady=10)
        self._verify_var = ctk.BooleanVar(value=settings.get("verify_after_flash"))
        ctk.CTkCheckBox(inner, text="Verify after flash (re-read and checksum)",
                        variable=self._verify_var,
                        font=T.FONT_BODY, text_color=T.TEXT,
                        fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                        checkmark_color="#000").pack(anchor="w")

        # ── Confirm + Flash ───────────────────────────────────────────────────
        self._confirm = ConfirmEntry(
            self,
            confirm_text="FLASH",
            button_text="⚡  Flash Image",
            on_confirm=self._start_flash,
            warn_msg="This will permanently erase all data on the selected drive.  Type FLASH to confirm.",
        )
        self._confirm.pack(fill="x", pady=(0, 12))

        # ── Progress ──────────────────────────────────────────────────────────
        self._progress = ProgressPanel(self, on_cancel=self._cancel)
        self._progress.pack(fill="x")

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_drive_selected(self, drive):
        pass  # Could auto-populate confirm text with drive letter

    def _start_flash(self):
        if self._running:
            return
        img_path = self._img_pick.get()
        drive    = self._drives.selected_drive()

        if not img_path or not os.path.exists(img_path):
            self._progress.error("Image file not found")
            return
        if not drive:
            self._progress.error("No drive selected")
            return

        self._settings.add_recent_image(img_path)
        self._settings.set("verify_after_flash", self._verify_var.get())

        self._cancel_ev.clear()
        self._running = True
        self._progress.start(f"Flashing to {drive.device}…")

        threading.Thread(target=self._flash_worker,
                         args=(img_path, drive), daemon=True).start()

    def _flash_worker(self, img_path, drive):
        from ..disk import flash_disk
        import hashlib

        def cb(done, total, speed):
            self.after(0, self._progress.update, done, total, speed, "Writing…")

        try:
            flash_disk(img_path, drive, progress_cb=cb,
                       cancel_event=self._cancel_ev)

            if self._verify_var.get() and not self._cancel_ev.is_set():
                self.after(0, self._progress.log, "Verifying…")
                self._verify(img_path, drive)
            else:
                self.after(0, self._progress.finish, "Flash complete")
        except InterruptedError:
            self.after(0, self._progress.error, "Cancelled")
        except Exception as e:
            self.after(0, self._progress.error, f"Error: {e}")
        finally:
            self._running = False

    def _verify(self, img_path, drive):
        """Read back written data and compare MD5 against source."""
        import hashlib, gzip, win32file

        is_gz = img_path.lower().endswith(".gz")
        open_fn = gzip.open if is_gz else open

        src_md5 = hashlib.md5()
        with open_fn(img_path, "rb") as f:
            while chunk := f.read(4 * 1024 * 1024):
                src_md5.update(chunk)
        src_digest = src_md5.hexdigest()

        disk_md5 = hashlib.md5()
        handle = win32file.CreateFile(
            drive.device, win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
            None, win32file.OPEN_EXISTING,
            win32file.FILE_FLAG_NO_BUFFERING | win32file.FILE_FLAG_SEQUENTIAL_SCAN,
            None)
        try:
            to_read = os.path.getsize(img_path)  # same amount we wrote
            done = 0
            while done < to_read:
                chunk_sz = min(4 * 1024 * 1024, to_read - done)
                _, data = win32file.ReadFile(handle, chunk_sz)
                if not data:
                    break
                disk_md5.update(data)
                done += len(data)
                self.after(0, self._progress.update, done, to_read, 0, "Verifying…")
        finally:
            win32file.CloseHandle(handle)

        if src_digest == disk_md5.hexdigest():
            self.after(0, self._progress.finish, "Flash complete — verified ✓")
        else:
            self.after(0, self._progress.error, "Verification FAILED — checksums differ")

    def _cancel(self):
        self._cancel_ev.set()

    def on_activate(self):
        """Called when this view is shown."""
        self._drives.refresh()
