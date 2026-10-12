"""
__main__.py — Entry point.

Shows a splash screen immediately (raw tkinter, no CTk overhead),
checks for admin, elevates if needed, then loads the main app.
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


def main():
    if not is_admin():
        elevate()

    splash = show_splash()

    # Heavy imports happen here — splash is already visible
    from .app import PiKitApp

    app = PiKitApp()
    splash.destroy()
    app.mainloop()


if __name__ == "__main__":
    main()
