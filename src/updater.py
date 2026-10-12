"""
updater.py — Background GitHub release checker.

Calls the GitHub releases API on startup, compares against APP_VERSION,
and fires a callback if a newer version is available.
"""
import threading
import urllib.request
import urllib.error
import json

import tempfile

from .version import APP_VERSION, GITHUB_REPO

# ── Pending-update helpers ─────────────────────────────────────────────────────

def _pending_file():
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PiKit")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "pending_update.txt")

def get_pending_update():
    """Return installer path if one is waiting, else None."""
    p = _pending_file()
    try:
        if os.path.exists(p):
            path = open(p).read().strip()
            if path and os.path.exists(path):
                return path
    except Exception:
        pass
    return None

def set_pending_update(installer_path):
    with open(_pending_file(), "w") as f:
        f.write(installer_path)

def clear_pending_update():
    try:
        os.remove(_pending_file())
    except Exception:
        pass


def _parse_version(tag: str):
    """Convert 'v1.2.3' or '1.2.3' to (1, 2, 3) tuple."""
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def check_for_update(on_update_available, on_up_to_date=None, on_error=None):
    """
    Spawn a background thread that checks GitHub for a newer release.

    on_update_available(version: str, notes: str, download_url: str)
    on_up_to_date(latest_version: str)  — called when already on latest
    on_error(msg: str)
    """
    def _worker():
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PiKit-updater"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())

            latest_tag  = data.get("tag_name", "")
            notes       = data.get("body", "")
            assets      = data.get("assets", [])

            download_url = next(
                (a["browser_download_url"] for a in assets
                 if a["name"].endswith(".exe")),
                data.get("html_url", ""),
            )

            if not latest_tag:
                if on_error:
                    on_error("No releases found on GitHub")
                return

            if _parse_version(latest_tag) > _parse_version(APP_VERSION):
                on_update_available(latest_tag.lstrip("v"), notes, download_url)
            else:
                if on_up_to_date:
                    on_up_to_date(latest_tag.lstrip("v"))

        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_worker, daemon=True).start()


def download_installer(url: str, progress_cb=None):
    """
    Download the installer via PowerShell (handles GitHub CDN redirects
    reliably on Windows) then launch it silently.

    progress_cb(bytes_done, bytes_total)
    """
    import os, tempfile, subprocess, threading, time

    tmp = os.path.join(tempfile.gettempdir(), "PiKit_Update_Setup.exe")

    # Remove any previous partial download
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass

    # Get expected file size via HEAD so we can show progress
    total = 0
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "PiKit-updater"})
        with urllib.request.urlopen(req, timeout=10) as r:
            total = int(r.headers.get("Content-Length", 0))
    except Exception:
        pass

    # Download using PowerShell — proven reliable with GitHub CDN on Windows
    ps = (f'[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;'
          f'Invoke-WebRequest -Uri "{url}" -OutFile "{tmp}" -UseBasicParsing')
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    # Monitor file growth on a side thread for progress reporting
    if progress_cb:
        def _monitor():
            while proc.poll() is None:
                try:
                    done = os.path.getsize(tmp) if os.path.exists(tmp) else 0
                    progress_cb(done, total)
                except Exception:
                    pass
                time.sleep(0.4)
            # Final update
            try:
                progress_cb(os.path.getsize(tmp), total)
            except Exception:
                pass
        threading.Thread(target=_monitor, daemon=True).start()

    proc.wait(timeout=300)

    if proc.returncode != 0:
        raise RuntimeError("Download failed — PowerShell returned non-zero exit code")

    # Return the path — caller is responsible for launching after PiKit closes
    return tmp
