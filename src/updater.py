"""
updater.py — Background GitHub release checker.

Calls the GitHub releases API on startup, compares against APP_VERSION,
and fires a callback if a newer version is available.
"""
import os
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

def _file_version(path):
    """(major, minor, patch) from an exe's ProductVersion, or None if it has none / cannot be read.

    Inno Setup installers carry the version as the ProductVersion string; their numeric file version is
    0.0.0, so that is not used. An unreadable or all-zero version means "unknown", never "old".
    """
    import ctypes
    import re
    from ctypes import wintypes
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr, n = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(n)) or n.value < 4:
            return None
        lang, cp = (wintypes.WORD * 2).from_address(ptr.value)
        sub = "\\StringFileInfo\\%04x%04x\\ProductVersion" % (lang, cp)
        if not ver.VerQueryValueW(buf, sub, ctypes.byref(ptr), ctypes.byref(n)) or not n.value:
            return None
        text = ctypes.wstring_at(ptr.value, n.value).rstrip("\0")
        m = re.match(r"(\d+)\.(\d+)\.(\d+)", text)
        v = tuple(int(x) for x in m.groups()) if m else None
        return v if v and any(v) else None
    except Exception:
        return None


def get_pending_update():
    """Return installer path if one is waiting and is newer than this app, else None.

    A leftover installer that is not newer than the running version is stale (the update it carried is
    already installed): it is deleted and forgotten. Without this, an old marker made every launch re-run
    the installer and exit, so the app never opened.
    """
    p = _pending_file()
    try:
        if os.path.exists(p):
            path = open(p).read().strip()
            if path and os.path.exists(path):
                v = _file_version(path)
                if v is not None and v <= _parse_version(APP_VERSION):
                    clear_pending_update()
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                    return None
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


def spawn_installer_and_exit(installer_path):
    """
    Start the installer silently and exit immediately so the EXE lock is released.

    The installer closes/replaces files itself (Restart Manager) and relaunches
    PiKit when it finishes (see the [Run] section in installer.iss).
    Calls os._exit(0) so this process stops holding its files.
    Returns False (without exiting) if the installer could not be started,
    e.g. antivirus quarantined or locked the downloaded file.
    """
    import subprocess

    log_dir = os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()), "PiKit")
    os.makedirs(log_dir, exist_ok=True)
    log = os.path.join(log_dir, "update_log.txt")

    try:
        subprocess.Popen(
            [installer_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             "/CLOSEAPPLICATIONS", "/PIKITRELAUNCH", f"/LOG={log}"],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except Exception:
        try:
            os.remove(installer_path)
        except Exception:
            pass
        clear_pending_update()
        return False
    # os._exit() below never returns, so the pending marker must be cleared HERE. If it is left behind, the
    # installer relaunches PiKit, PiKit finds the marker, runs the installer again and exits: a loop.
    clear_pending_update()
    os._exit(0)

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
    Download the installer to a temp file and return its path.

    progress_cb(bytes_done, bytes_total)
    """
    tmp = os.path.join(tempfile.gettempdir(), "PiKit_Update_Setup.exe")

    # Remove any previous partial download
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass

    req = urllib.request.Request(url, headers={"User-Agent": "PiKit-updater"})
    done = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
        if total and done != total:
            raise RuntimeError(f"Download incomplete ({done} of {total} bytes)")
        if not total:
            # No Content-Length: can't compare sizes, so sanity-check it looks like an exe
            with open(tmp, "rb") as f:
                if done < 1_000_000 or f.read(2) != b"MZ":
                    raise RuntimeError("Download incomplete or not an installer")
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise

    # Return the path — caller is responsible for launching after PiKit closes
    return tmp