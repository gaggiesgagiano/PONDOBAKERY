"""Talks to the ZIMRA fiscal engine (FiscalStackZW.dll) through the small bridge program in fiscal_engine\\.

* One bridge process for the whole of Pondo – the engine wants exactly one instance, with calls one after the other.
* Every call waits its turn (at most GATE_WAIT seconds), and every call has a time limit. If the engine hangs,
  the bridge is stopped and started again on the next call – the till never freezes for long.
* Every answer is the engine's envelope: {"Code": "1" | "0", "Message": "...", "Data": "<a JSON or XML string>"}.
  Data is a STRING – use payload() to read it (the engine guide's "read Data twice" rule).
"""
import configparser
import itertools
import json
import os
import queue
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from django.conf import settings

GATE_WAIT = 15          # seconds a call waits for the one before it (engine guide §5)
DEFAULT_TIMEOUT = 45    # seconds for a normal call (the engine's own HTTP timeout is set lower in config.ini)
LONG_TIMEOUT = 200      # close day / Z report / registration / sync: ZIMRA closes a day asynchronously (~90 s)
LONG_CALLS = {"CloseDay", "ZReport", "RegisterDeviceWithZimra", "SubmitPendingQueue", "SubmitFile",
              "OpenDay", "GenerateDeviceCertificates", "ApplyDeviceSettings", "RecoverFiscalDay"}
START_WAIT = 60
BRIDGE_EXE = "PondoFiscalBridge.exe"
SECTION = "FISCALSTACKZW"


def engine_dir():
    return Path(getattr(settings, "FISCAL_ENGINE_DIR", settings.BASE_DIR / "fiscal_engine"))


def log_path():
    return Path(settings.DATA_DIR) / "fiscal_engine_log.txt"


def envelope(code, message, data=""):
    return {"Code": str(code), "Message": message, "Data": data}


def ok(env):
    return bool(env) and str(env.get("Code")) == "1"


def payload(env):
    """The Data of an envelope: a dict (JSON), an XML element, or None. Never index env["Data"] directly."""
    if not env:
        return None
    d = env.get("Data")
    if isinstance(d, dict):
        return d
    s = (d or "").strip()
    if not s:
        return None
    if s[0] in "{[":
        try:
            return json.loads(s)
        except ValueError:
            return None
    if s[0] == "<":
        try:
            return ET.fromstring(s)
        except ET.ParseError:
            return None
    return None


def xml_text(el, tag, default=""):
    """First <tag> anywhere below el (the engine nests FDMSData inside ReceiptData)."""
    if el is None:
        return default
    if el.tag == tag:
        return (el.text or "").strip()
    found = el.find(f".//{tag}")
    return (found.text or "").strip() if found is not None and found.text else default


# ----------------------------------------------------------------------------------------------- config.ini
def config_paths():
    """Where the engine reads config.ini: %ProgramData%\\FiscalStackZW first, else next to the bridge."""
    out = []
    pd = os.environ.get("PROGRAMDATA")
    if pd:
        p = Path(pd) / "FiscalStackZW" / "config.ini"
        if p.exists():
            out.append(p)
    out.append(engine_dir() / "config.ini")
    return out


def _read_ini(path):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str          # keep the engine's UPPERCASE keys
    if path.exists():
        cp.read(path, encoding="utf-8-sig")
    if not cp.has_section(SECTION):
        cp.add_section(SECTION)
    return cp


def _unprotect(value):
    """The engine encrypts some values in config.ini ("ENC:…", Windows DPAPI, machine scope) once a licence is set
    through SetLicense. Pondo reads them back the same way; anything it can't read comes back empty."""
    if not value.startswith("ENC:"):
        return value
    if not sys.platform.startswith("win"):
        return ""
    try:
        import base64
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        def blob(b):
            buf = ctypes.create_string_buffer(b, len(b))
            return Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

        data, keep1 = blob(base64.b64decode(value[4:]))
        entropy, keep2 = blob(b"FiscalStackZW_Data_v1")
        out = Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(data), None, ctypes.byref(entropy), None, None, 0,
                                                        ctypes.byref(out)):
            return ""
        try:
            return ctypes.string_at(out.pbData, out.cbData).decode("utf-8", "replace")
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
    except Exception:  # noqa: BLE001
        return ""


def read_config():
    """The engine's effective settings (the first config.ini it would read), encrypted values decrypted."""
    return {k: _unprotect(v) for k, v in _read_ini(config_paths()[0]).items(SECTION)}


def write_config(values):
    """Set keys in every config.ini the engine might read, keeping all other keys. Restart the engine afterwards."""
    for path in config_paths():
        cp = _read_ini(path)
        for k, v in values.items():
            cp.set(SECTION, k, "" if v is None else str(v))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".ini.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            cp.write(f, space_around_delimiters=False)
        os.replace(tmp, path)


# ----------------------------------------------------------------------------------------------- the bridge
class Engine:
    """The one connection to the bridge process. Use get_engine(), not this class directly."""

    def __init__(self, folder=None):
        self.folder = Path(folder) if folder else engine_dir()
        self.gate = threading.Lock()
        self.proc = None
        self.replies = queue.Queue()
        self.ids = itertools.count(1)
        self.info = {}
        self.last_error = ""

    # -- availability
    def command(self):
        exe = self.folder / BRIDGE_EXE
        if sys.platform.startswith("win"):
            return [str(exe)]
        mono = getattr(settings, "FISCAL_MONO", "") or "mono"     # tests / development on Linux
        return [mono, str(exe)]

    def installed(self):
        try:
            return (self.folder / "FiscalStackZW.dll").exists()
        except OSError:      # Windows refuses the folder (antivirus / Controlled folder access)
            return False

    def blocked(self):
        """True when Windows refuses access to the engine folder (antivirus, Controlled folder access)."""
        try:
            os.listdir(self.folder)
            return False
        except PermissionError:
            return True
        except OSError:
            return False

    def build_bridge(self):
        """Compile the bridge with the C# compiler that comes with Windows (only if the .exe is missing)."""
        exe = self.folder / BRIDGE_EXE
        if exe.exists() or not sys.platform.startswith("win"):
            return exe.exists()
        windir = os.environ.get("WINDIR", r"C:\Windows")
        for fw in ("Framework64", "Framework"):
            csc = Path(windir) / "Microsoft.NET" / fw / "v4.0.30319" / "csc.exe"
            if csc.exists():
                r = subprocess.run([str(csc), "/nologo", "/target:exe", "/platform:anycpu", "/optimize+",
                                    f"/out:{BRIDGE_EXE}", "/reference:FiscalStackZW.dll",
                                    "/reference:Newtonsoft.Json.dll", "PondoFiscalBridge.cs"],
                                   cwd=self.folder, capture_output=True, text=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if r.returncode != 0:
                    self.last_error = "Could not build the bridge: " + (r.stdout or r.stderr)[-500:]
                return exe.exists()
        self.last_error = ".NET Framework 4 is not installed on this computer."
        return False

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    # -- start / stop
    def _start(self):
        if self.blocked():
            raise EngineDown(BLOCKED.format(folder=self.folder))
        if not self.installed():
            raise EngineDown(f"The fiscal engine is not installed (no FiscalStackZW.dll in {self.folder}).")
        if not self.build_bridge():
            raise EngineDown(self.last_error or f"{BRIDGE_EXE} is missing in {self.folder}.")
        log_path().parent.mkdir(parents=True, exist_ok=True)
        if log_path().exists() and log_path().stat().st_size > 5_000_000:
            os.replace(log_path(), str(log_path()) + ".old")
        log = open(log_path(), "a", encoding="utf-8", errors="replace")
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} fiscal engine start =====\n")
        log.flush()
        self.replies = queue.Queue()
        self.proc = subprocess.Popen(self.command(), cwd=self.folder, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=log, bufsize=0,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.close()   # the child keeps its own handle
        threading.Thread(target=self._read, args=(self.proc, self.replies), daemon=True).start()
        try:
            hello = self.replies.get(timeout=START_WAIT)
        except queue.Empty:
            self.stop()
            raise EngineDown("The fiscal engine did not start within a minute.")
        if hello is None:
            self.stop()
            raise EngineDown("The fiscal engine stopped while starting – see data\\fiscal_engine_log.txt.")
        self.info = hello
        if not hello.get("ok"):
            err = hello.get("startError") or "unknown error"
            self.stop()
            raise EngineDown(f"The fiscal engine could not start: {err}")

    @staticmethod
    def _read(proc, replies):
        """Each bridge process gets its own reply queue, so a stopped process can't confuse the next one."""
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                replies.put(json.loads(line))
            except ValueError:
                pass
        replies.put(None)   # the process ended

    def stop(self):
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            if p.poll() is None:
                try:
                    p.stdin.write(b'{"id":-1,"method":"__exit"}\n')
                    p.stdin.flush()
                    p.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired, ValueError):
                    pass
            if p.poll() is None:
                p.kill()
        except OSError:
            pass

    def restart(self):
        """After config.ini changed: a fresh engine instance reads it (engine guide §7)."""
        with self.gate:
            self.stop()

    # -- calls
    def call(self, method, *args, timeout=None):
        """Call one engine method. Always returns an envelope dict – never raises."""
        if not self.gate.acquire(timeout=GATE_WAIT):
            return envelope(0, "The fiscal engine is busy with another till. Try again in a moment.")
        try:
            return self._call(method, list(args), timeout or (LONG_TIMEOUT if method in LONG_CALLS else DEFAULT_TIMEOUT))
        except PermissionError:
            self.stop()
            self.last_error = BLOCKED.format(folder=self.folder)
            return envelope(0, self.last_error)
        except OSError as e:
            self.stop()
            self.last_error = f"The fiscal engine could not be started: {e}"
            return envelope(0, self.last_error)
        except EngineDown as e:
            self.last_error = str(e)
            return envelope(0, str(e))
        finally:
            self.gate.release()

    def _call(self, method, args, timeout):
        if not self.running():
            self._start()
        rid = next(self.ids)
        line = json.dumps({"id": rid, "method": method, "args": ["" if a is None else a for a in args]}) + "\n"
        try:
            self.proc.stdin.write(line.encode("utf-8"))
            self.proc.stdin.flush()
        except (OSError, ValueError):
            self.stop()
            raise EngineDown("The fiscal engine stopped – it starts again on the next try.")
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                self.stop()   # a hung engine is restarted on the next call
                raise EngineDown(f"The fiscal engine did not answer {method} within {timeout} seconds.")
            try:
                rep = self.replies.get(timeout=left)
            except queue.Empty:
                continue
            if rep is None:
                self.stop()
                raise EngineDown("The fiscal engine stopped unexpectedly – see data\\fiscal_engine_log.txt.")
            if rep.get("id") != rid:
                continue      # a late answer to a call that already timed out
            if not rep.get("ok"):
                return envelope(0, "Fiscal engine error: " + (rep.get("error") or "unknown"))
            if method.startswith("__"):
                return envelope(1, "ok", json.dumps(rep))
            try:
                env = json.loads(rep.get("result") or "")
            except ValueError:
                return envelope(0, "The fiscal engine gave an answer Pondo can't read.", rep.get("result") or "")
            if not isinstance(env, dict):
                return envelope(0, "The fiscal engine gave an answer Pondo can't read.", rep.get("result") or "")
            env.setdefault("Code", "0")
            env.setdefault("Message", "")
            env.setdefault("Data", "")
            env["Code"], env["Data"] = str(env["Code"]), env["Data"] if isinstance(env["Data"], str) else json.dumps(env["Data"])
            return env


class EngineDown(Exception):
    pass


BLOCKED = ("Windows is blocking the fiscal engine folder ({folder}). Open Windows Security → Virus & threat protection → "
           "Protection history, and allow PondoFiscalBridge.exe / the fiscal_engine folder (or add it under "
           "Ransomware protection → Allow an app through Controlled folder access).")


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = Engine()
        return _engine


def set_engine(e):
    """Tests put a fake engine in here."""
    global _engine
    with _engine_lock:
        if _engine is not None and _engine is not e and hasattr(_engine, "stop"):
            _engine.stop()
        _engine = e
