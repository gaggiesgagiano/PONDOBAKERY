"""Pondo Bakery – starts the program without the black window.

The desktop / taskbar icon runs this file with pythonw.exe. It shows a small Pondo window while the
program runs; close that window (or press "Close Pondo") to stop the program.
If something goes wrong, the message is shown on screen and written to data\\pondo_log.txt.
"""
import os
import queue
import sys
import threading
import time
import traceback
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "data", "pondo_log.txt")

# pythonw has no console: send anything printed to a small log file instead
try:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if os.path.exists(LOG) and os.path.getsize(LOG) > 1_000_000:
        os.replace(LOG, LOG + ".old")
    _log = open(LOG, "a", encoding="utf-8", buffering=1)
    _log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start =====\n")
    sys.stdout = sys.stderr = _log
except OSError:
    pass

sys.path.insert(0, HERE)
import run  # noqa: E402  (sets up paths and settings)

CREAM, MAROON, ORANGE, INK, MUTED, RED = "#FFF3D7", "#7A1315", "#E56026", "#2A1412", "#7C5A4A", "#B3261E"
events = queue.Queue()


def start_program():
    """Runs in the background: back up, update the database, then serve until the program closes."""
    try:
        run.prepare(lambda m: events.put(("status", m)))
        events.put(("ready", None))
        run.serve()
    except Exception as e:
        traceback.print_exc()
        if run.port_in_use():  # another Pondo window got there first
            events.put(("already", None))
        else:
            events.put(("error", f"{type(e).__name__}: {e}"))


def without_window():
    """Fallback if Python was installed without its window toolkit: run quietly in the background."""
    threading.Timer(4, lambda: run.open_browser(run.URL)).start()
    run.prepare()
    run.serve()


def main():
    if run.port_in_use():  # already open – just show it
        run.open_browser(run.URL)
        return
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        without_window()
        return

    root = tk.Tk()
    root.title("Pondo Bakery")
    root.configure(bg=CREAM)
    root.resizable(False, False)
    try:
        root.iconbitmap(default=os.path.join(HERE, "static", "img", "pondo.ico"))
    except tk.TclError:
        pass
    font = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"

    try:
        logo = tk.PhotoImage(file=os.path.join(HERE, "static", "img", "pondo_logo_orange.png")).subsample(5, 5)
        tk.Label(root, image=logo, bg=CREAM).pack(padx=28, pady=(22, 6))
        root._logo = logo
    except tk.TclError:
        tk.Label(root, text="Pondo Bakery", font=(font, 20, "bold"), fg=MAROON, bg=CREAM).pack(padx=28, pady=(22, 6))

    status = tk.Label(root, text="Getting ready …", font=(font, 12, "bold"), fg=MAROON, bg=CREAM)
    status.pack(padx=28)
    note = tk.Label(root, text="Please wait a moment.", font=(font, 9), fg=MUTED, bg=CREAM, wraplength=320,
                    justify="center")
    note.pack(padx=28, pady=(4, 14))
    net = tk.Label(root, text="", font=(font, 10, "bold"), fg=MAROON, bg="#FFE3C4", justify="center", padx=12, pady=8)

    row = tk.Frame(root, bg=CREAM)
    row.pack(padx=28, pady=(0, 22))
    btn = dict(font=(font, 10, "bold"), relief="flat", bd=0, padx=16, pady=8, cursor="hand2")
    open_btn = tk.Button(row, text="Open Pondo", bg=ORANGE, fg="#5C0E10", activebackground="#F89B47",
                         state="disabled", command=lambda: run.open_browser(run.URL), **btn)
    open_btn.pack(side="left", padx=6)

    def close():
        if messagebox.askyesno("Close Pondo Bakery?",
                               "Close the program now?\n\nSave what you are busy with in the browser first.",
                               parent=root):
            root.destroy()
            os._exit(0)

    tk.Button(row, text="Close Pondo", bg="#FFFFFF", fg=MAROON, activebackground="#FFF3D7", command=close,
              **btn).pack(side="left", padx=6)
    root.protocol("WM_DELETE_WINDOW", close)

    def poll():
        try:
            while True:
                kind, msg = events.get_nowait()
                if kind == "status":
                    status.config(text=msg)
                elif kind == "ready":
                    status.config(text="Pondo is running")
                    note.config(text="It opens in your browser. Keep this little window open while you work "
                                     "(you can minimise it). Close it when you finish for the day.")
                    adds = run.network_addresses()
                    if adds:
                        net.config(text="Other computers – type in Chrome:\n" + "\n".join(adds[:3]))
                        net.pack(padx=28, pady=(0, 14))
                    open_btn.config(state="normal")
                    root.after(800, lambda: run.open_browser(run.URL))
                elif kind == "already":
                    run.open_browser(run.URL)
                    root.destroy()
                    os._exit(0)
                elif kind == "error":
                    status.config(text="Pondo could not start", fg=RED)
                    note.config(text=msg)
                    messagebox.showerror("Pondo Bakery",
                                         f"Something went wrong while starting:\n\n{msg}\n\n"
                                         "Take a photo of this message and send it to Claude.\n"
                                         f"More detail is in {LOG}", parent=root)
        except queue.Empty:
            pass
        root.after(200, poll)

    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
    threading.Thread(target=start_program, daemon=True).start()
    root.after(200, poll)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, "Pondo could not start. Take a photo of this message and send it to "
                                                f"Claude.\n\nDetails are in {LOG}", "Pondo Bakery", 0x10)
        except Exception:
            pass
        os._exit(1)
