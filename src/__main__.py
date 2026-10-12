"""
__main__.py — Entry point.

Checks for admin rights (required for raw disk access) and re-launches
with UAC elevation if needed.  Then starts the PiKit GUI.
"""
import sys
import ctypes
import os


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def elevate():
    """Re-launch the current process with admin rights via ShellExecute runas."""
    exe  = sys.executable
    args = " ".join([f'"{a}"' for a in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
    sys.exit(0)


def main():
    if not is_admin():
        elevate()

    from .app import PiKitApp
    app = PiKitApp()
    app.mainloop()


if __name__ == "__main__":
    main()
