"""Start the Pondo Bakery program.

Normal way: "Pondo Bakery.exe" (or its icon) – it runs this file quietly with "--server".
Trouble-shooting way: double-click "Start Pondo.bat" (runs this file and shows a black window
with any error messages). Close the black window to stop the program.
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "vendor"))
sys.path.insert(0, BASE)
os.chdir(BASE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pondo_site.settings")

HOST, PORT = "127.0.0.1", int(os.environ.get("PONDO_PORT", "8765"))
URL = f"http://{HOST}:{PORT}/"
BIND = os.environ.get("PONDO_BIND", "0.0.0.0")  # 0.0.0.0 = other computers on the network may connect


def network_addresses():
    """The addresses other computers type in Chrome: this computer's name first, then its network number(s)."""
    out = []
    try:
        name = socket.gethostname()
        if name:
            out.append(f"http://{name.lower()}:{PORT}/")
    except OSError:
        pass
    ips = set()
    try:  # the address this computer uses on the shop network
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    for ip in sorted(ips):
        if not ip.startswith("127."):
            out.append(f"http://{ip}:{PORT}/")
    return out


def open_browser(url=None):
    """Open Pondo in Google Chrome. Only if Chrome is not installed, use the Windows default browser."""
    import subprocess

    url = url or URL
    places = [os.environ.get(v, "") for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    for root in places:
        chrome = os.path.join(root, "Google", "Chrome", "Application", "chrome.exe") if root else ""
        if chrome and os.path.exists(chrome):
            try:
                subprocess.Popen([chrome, url])
                return
            except OSError:
                break
    webbrowser.open(url)


def port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def prepare(say=print):
    """Back up the data, then bring the database up to date with the program."""
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    from core.backup import make_local_backup

    if Path(settings.DATABASES["default"]["NAME"]).exists():
        try:
            make_local_backup("start")  # before any update, so an update can always be undone
        except Exception as e:  # never stop the program because of a backup problem
            say(f"(could not make the start-up backup: {e})")
    say("Getting ready ...")
    call_command("migrate", verbosity=0, interactive=False)


def _hang_up_on_https():
    """Phones (Chrome) often try https:// first, even when http:// is typed. Pondo has no https inside the shop, so
    hang up on such a try at once – Chrome then uses http:// straight away instead of waiting until it times out."""
    from waitress.channel import HTTPChannel

    if getattr(HTTPChannel, "_pondo_patched", False):
        return
    original = HTTPChannel.received

    def received(self, data):
        if not getattr(self, "_pondo_first_seen", False):
            self._pondo_first_seen = True
            if data[:2] == b"\x16\x03":      # the start of a secure (TLS) hello, not a normal web request
                self.will_close = True
                return False
        return original(self, data)

    HTTPChannel.received = received
    HTTPChannel._pondo_patched = True


def serve():
    from waitress import serve as waitress_serve

    _hang_up_on_https()

    from pondo_site.wsgi import application as django_app

    log_path = Path(__file__).resolve().parent / "data" / "visits_log.txt"

    def application(environ, start_response):
        """Visits from OTHER computers and phones are written to data/visits_log.txt (to find connection problems)."""
        ip = environ.get("REMOTE_ADDR", "")
        if ip.startswith("127.") or ip == "::1":
            return django_app(environ, start_response)
        import time
        t0, seen = time.time(), {}

        def sr(status, headers, exc_info=None):
            seen["s"] = status.split(" ", 1)[0]
            return start_response(status, headers, exc_info)
        try:
            return django_app(environ, sr)
        finally:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {ip:15}  {seen.get('s', '?'):>3}  "
                            f"{(time.time() - t0) * 1000:5.0f} ms  {environ.get('REQUEST_METHOD')} {environ.get('PATH_INFO')}  "
                            f"{environ.get('HTTP_USER_AGENT', '')[:60]}\n")
            except Exception:
                pass

    waitress_serve(application, host=BIND, port=PORT, threads=12, _quiet=True)  # up to ~10 people at once


def main():
    print("=" * 60)
    print("  PONDO BAKERY")
    print("=" * 60)
    if port_in_use():
        print("The program is already running - opening it in your browser.")
        open_browser(URL)
        time.sleep(2)
        return
    prepare(lambda m: print("  " + m))
    threading.Timer(1.5, lambda: open_browser(URL)).start()
    print()
    print("  Pondo Bakery is running.")
    print(f"  Your browser opens by itself. If not, go to:  {URL}")
    for a in network_addresses():
        print(f"  Other computers in the shop:  {a}")
    print()
    print("  KEEP THIS WINDOW OPEN while you work.")
    print("  To stop the program: close this window.")
    print()
    serve()


def server_mode():
    """Used by Pondo Bakery.exe: no messages to the screen – everything goes to data\\pondo_log.txt."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} starting Pondo (Python {sys.version.split()[0]})")
    prepare(lambda m: print("  " + m))
    print(f"  running at {URL}")
    print("  other computers: " + "  ".join(network_addresses()))
    serve()


if __name__ == "__main__":
    if "--server" in sys.argv:
        try:
            server_mode()
        except Exception:
            import traceback

            traceback.print_exc()
            sys.exit(1)
        sys.exit(0)
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        print("\nSomething went wrong (see above). Take a photo of this window and send it to Claude.")
        input("Press Enter to close ...")
