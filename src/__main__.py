"""
__main__.py — Entry point.

Shows a splash screen immediately (raw tkinter, no CTk overhead),
checks for admin, elevates if needed, then loads the main app.
"""
import sys
import ctypes
import os
import subprocess


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def elevate():
    exe  = sys.executable
    args = " ".join([f'"{a}"' for a in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
    sys.exit(0)


def show_splash():
    """
    Raw tkinter splash — appears before customtkinter is imported,
    so the user sees something instantly while heavy modules load.
    """
    import tkinter as tk

    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.configure(bg="#0d0d0d")
    splash.attributes("-topmost", True)

    w, h = 320, 170
    sw   = splash.winfo_screenwidth()
    sh   = splash.winfo_screenheight()
    splash.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # Thin border frame
    border = tk.Frame(splash, bg="#22c55e", padx=1, pady=1)
    border.pack(fill="both", expand=True)
    inner  = tk.Frame(border, bg="#0d0d0d")
    inner.pack(fill="both", expand=True)

    tk.Label(inner, text="Pi", font=("Segoe UI", 38, "bold"),
             bg="#0d0d0d", fg="#22c55e").pack(side="left", padx=(32, 0), pady=40)
    tk.Label(inner, text="Kit", font=("Segoe UI", 38, "bold"),
             bg="#0d0d0d", fg="#f1f5f9").pack(side="left", pady=40)

    sub = tk.Frame(inner, bg="#0d0d0d")
    sub.pack(side="bottom", fill="x", pady=(0, 18))
    tk.Label(sub, text="Pi SD Card Manager", font=("Segoe UI", 10),
             bg="#0d0d0d", fg="#6b7280").pack()

    splash.update()
    return splash


def setup_logging():
    """Write unhandled exceptions to %APPDATA%\PiKit\crash.log."""
    import sys, threading, traceback, datetime
    log_dir  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PiKit")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "crash.log")

    def _write(header, exc_type, exc_value, exc_tb):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n{header}  {datetime.datetime.now()}\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)

    def _main_hook(exc_type, exc_value, exc_tb):
        _write("[MAIN THREAD]", exc_type, exc_value, exc_tb)

    def _thread_hook(args):
        _write(f"[THREAD {args.thread.name}]", args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook          = _main_hook
    threading.excepthook    = _thread_hook


def apply_pending_update():
    """
    Fallback: if a downloaded installer is still waiting from a previous session,
    run it now and exit before any UI loads.
    """
    from .updater import get_pending_update, clear_pending_update, spawn_installer_and_exit
    installer = get_pending_update()
    if not installer:
        return
    clear_pending_update()
    spawn_installer_and_exit(installer)


def main():
    if not is_admin():
        elevate()

    # Apply any downloaded update before anything else loads (no EXE lock yet)
    apply_pending_update()

    debug = "--debug" in sys.argv
    setup_logging()

    from .logger import setup as log_setup, log
    log_setup(debug=debug)
    log.info(f"Admin={is_admin()}  args={sys.argv}")

    splash = show_splash()

    log.info("Importing app…")
    from .app import PiKitApp

    log.info("Creating main window…")
    app = PiKitApp()
    # splash is tk.Tk() — destroying it nullifies tkinter's _default_root,
    # breaking font creation in any lazy-loaded CTk widget.
    # Re-establish app as the default root immediately after.
    import tkinter as _tk
    splash.destroy()
    _tk._default_root = app
    log.info("Entering mainloop")
    app.mainloop()
    log.info("Mainloop exited cleanly")


if __name__ == "__main__":
    main()
