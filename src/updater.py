"""
updater.py — Background GitHub release checker.

Calls the GitHub releases API on startup, compares against APP_VERSION,
and fires a callback if a newer version is available.
"""
import threading
import urllib.request
import urllib.error
import json

from .version import APP_VERSION, GITHUB_REPO


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


def download_and_run_installer(url: str, progress_cb=None):
    """
    Download the installer to %TEMP% and launch it.

    progress_cb(bytes_done, bytes_total)
    Runs the installer — it will ask for UAC and replace the app.
    """
    import os, tempfile, subprocess

    tmp = os.path.join(tempfile.gettempdir(), "PiKit_Update_Setup.exe")

    req = urllib.request.Request(url, headers={"User-Agent": "PiKit-updater"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done  = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)

    # /VERYSILENT — no wizard, no prompts, no progress window
    # /NORESTART  — suppress any reboot prompt
    subprocess.Popen(
        [tmp, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
