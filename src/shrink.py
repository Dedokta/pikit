"""
shrink.py — Run PiShrink on a .img file via WSL.

PiShrink is a bash script that:
  1. Shrinks the ext4 root partition to the minimum size needed
  2. Resizes the partition entry in the MBR to match
  3. Adds a first-boot resize service so the Pi expands back to fill the card

We call it via WSL, which must be installed.  The pishrink.sh script is
bundled in the assets/ folder next to the executable.
"""
import os
import subprocess
import sys
import threading


def get_asset_path(filename):
    """Resolve path to a bundled asset (works both dev and PyInstaller 6+)."""
    if getattr(sys, "frozen", False):
        # PyInstaller 6: data files land in sys._MEIPASS (_internal/)
        base = sys._MEIPASS
        return os.path.normpath(os.path.join(base, "assets", filename))
    else:
        base = os.path.join(os.path.dirname(__file__), "..", "assets")
        return os.path.normpath(os.path.join(base, filename))


def win_to_wsl(win_path):
    """Convert a Windows path to a WSL /mnt/ path."""
    path = win_path.replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        path  = f"/mnt/{drive}" + path[2:]
    return path


def check_wsl():
    """Return (available: bool, distros: list[str])."""
    try:
        r = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-16-le",    # wsl --list outputs UTF-16 LE
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        distros = [l.strip().rstrip("\x00") for l in r.stdout.splitlines() if l.strip().rstrip("\x00")]
        return len(distros) > 0, distros
    except Exception:
        return False, []


def shrink_image(img_path: str, log_cb=None, cancel_event: threading.Event = None) -> bool:
    """
    Shrink img_path in-place using PiShrink via WSL.

    log_cb(line: str)  — called for each line of PiShrink output.
    cancel_event       — set to abort (process will be killed).

    Returns True on success, False on failure.
    """
    pishrink = get_asset_path("pishrink.sh")
    if not os.path.exists(pishrink):
        if log_cb:
            log_cb(f"[ERROR] pishrink.sh not found at {pishrink}")
        return False

    wsl_script = win_to_wsl(pishrink)
    wsl_img    = win_to_wsl(img_path)

    cmd = ["wsl", "bash", wsl_script, wsl_img]

    if log_cb:
        log_cb(f"Running: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        for line in proc.stdout:
            line = line.rstrip()
            if log_cb:
                log_cb(line)
            if cancel_event and cancel_event.is_set():
                proc.kill()
                if log_cb:
                    log_cb("[CANCELLED]")
                return False

        proc.wait()
        if proc.returncode != 0:
            if log_cb:
                log_cb(f"[ERROR] PiShrink exited with code {proc.returncode}")
            return False

        if log_cb:
            log_cb("[OK] PiShrink complete")
        return True

    except Exception as e:
        if log_cb:
            log_cb(f"[ERROR] {e}")
        return False
