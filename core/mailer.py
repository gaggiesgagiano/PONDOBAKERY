"""Sending e-mail from Pondo: invoices, quotations, orders and reports, as PDF attachments.

* The SMTP password is kept scrambled with this laptop's secret key (data/secret.key), never in plain text.
* PDFs are made by Google Chrome on the laptop (headless, invisible) from the same pages you print.
"""
import base64
import hashlib
import hmac
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import escape


# ------------------------------------------------------------------ password scrambling (stdlib only)
def _key():
    return hashlib.sha256(("pondo-mail:" + settings.SECRET_KEY).encode()).digest()


def _stream(nonce, n):
    out, i = b"", 0
    while len(out) < n:
        out += hmac.new(_key(), nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
        i += 1
    return out[:n]


def encrypt(text):
    if not text:
        return ""
    raw = text.encode()
    nonce = os.urandom(16)
    ct = bytes(a ^ b for a, b in zip(raw, _stream(nonce, len(raw))))
    tag = hmac.new(_key(), nonce + ct, hashlib.sha256).digest()[:16]
    return base64.b64encode(nonce + tag + ct).decode()


def decrypt(blob):
    if not blob:
        return ""
    data = base64.b64decode(blob)
    nonce, tag, ct = data[:16], data[16:32], data[32:]
    if not hmac.compare_digest(tag, hmac.new(_key(), nonce + ct, hashlib.sha256).digest()[:16]):
        raise ValueError("The saved e-mail password can't be read on this laptop – type it again in E-mail settings.")
    return bytes(a ^ b for a, b in zip(ct, _stream(nonce, len(ct)))).decode()


# ------------------------------------------------------------------ PDF with Chrome
def find_chrome():
    if os.environ.get("PONDO_CHROME"):
        return os.environ["PONDO_CHROME"]
    roots = [os.environ.get(v, "") for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    for root in roots:
        p = os.path.join(root, "Google", "Chrome", "Application", "chrome.exe") if root else ""
        if p and os.path.exists(p):
            return p
    for name in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    # last resort: Microsoft Edge in the background (invisible) – it makes the same PDF
    for root in roots:
        p = os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe") if root else ""
        if p and os.path.exists(p):
            return p
    return None


def _local_html(html):
    """Point /static/ and /media/ at the files on this laptop, so Chrome can open the page without logging in."""
    static = Path(settings.STATICFILES_DIRS[0]).resolve().as_uri() + "/"
    media = (Path(settings.MEDIA_ROOT).resolve().as_uri() + "/") if getattr(settings, "MEDIA_ROOT", "") else None
    html = re.sub(r'(["\'(])/static/', lambda m: m.group(1) + static, html)
    if media:
        html = re.sub(r'(["\'(])/media/', lambda m: m.group(1) + media, html)
    return html


def html_to_pdf(html, timeout=90):
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("Google Chrome was not found on this laptop – it is needed to make the PDF.")
    tmp = Path(tempfile.mkdtemp(prefix="pondo-pdf-"))
    try:
        src, out = tmp / "page.html", tmp / "page.pdf"
        src.write_text(_local_html(html), encoding="utf-8")
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--disable-extensions", f"--user-data-dir={tmp / 'profile'}", "--no-pdf-header-footer",
               "--print-to-pdf-no-header", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
               "--allow-file-access-from-files", f"--print-to-pdf={out}", src.as_uri()]
        if sys.platform != "win32" and hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, creationflags=flags)
        if not out.exists() or out.stat().st_size < 500:
            raise RuntimeError("Chrome could not make the PDF.")
        return out.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ sending
def split_addresses(text):
    return [a.strip() for a in re.split(r"[,;\s]+", text or "") if a.strip()]


def valid_address(a):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", a))


def connection(es, password=None):
    pw = password if password is not None else decrypt(es.password_enc)
    return get_connection(host=es.host, port=es.port, username=es.username, password=pw,
                          use_ssl=es.security == es.SSL, use_tls=es.security == es.TLS, timeout=40)


def body_html(text, signature):
    paras = "".join(f"<p style=\"margin:0 0 12px\">{escape(p).replace(chr(10), '<br>')}</p>"
                    for p in text.strip().split("\n\n") if p.strip())
    sig = escape(signature.strip()).replace("\n", "<br>")
    return (f"<div style=\"font-family:Arial,sans-serif;font-size:14px;color:#3b1d14;line-height:1.5\">{paras}"
            f"<div style=\"margin-top:18px;padding-top:10px;border-top:3px solid #e56026;color:#7a1315;font-size:13px\">{sig}</div>"
            f"</div>")


def send(es, to, subject, text, attachments=(), cc=(), user=None, what=""):
    """Send one e-mail. attachments: [(filename, bytes, mimetype)]. Returns (ok, error)."""
    from .models import EmailLog

    full_text = text.rstrip() + ("\n\n" + es.signature.strip() if es.signature.strip() else "")
    msg = EmailMultiAlternatives(subject=subject, body=full_text, from_email=f"{es.from_name} <{es.from_email}>",
                                 to=list(to), cc=list(cc), bcc=[es.from_email] if es.copy_me else [],
                                 reply_to=[es.from_email], connection=connection(es))
    msg.attach_alternative(body_html(text, es.signature), "text/html")
    for name, data, mime in attachments:
        msg.attach(name, data, mime)
    ok, err = True, ""
    try:
        msg.send(fail_silently=False)
    except Exception as e:  # noqa: BLE001 – show the person what went wrong
        ok, err = False, friendly_error(e)
    EmailLog.objects.create(user=user if user is not None and user.is_authenticated else None, what=what[:120],
                            to=", ".join(list(to) + list(cc))[:300], subject=subject[:200],
                            attachments=", ".join(a[0] for a in attachments)[:300], ok=ok, error=err[:300])
    return ok, err


def friendly_error(e):
    s = str(e)
    low = s.lower()
    if "authentication" in low or "535" in s or "credentials" in low:
        return "The mail server refused the username or password. Check them in E-mail settings."
    if "timed out" in low or "timeout" in low:
        return "The mail server did not answer – check the internet connection and the server name / port."
    if "getaddrinfo" in low or "name or service" in low or "nodename" in low:
        return "The mail server name was not found – check the server name and the internet connection."
    if "ssl" in low or "wrong version" in low:
        return "Secure connection failed – try SSL with port 465, or STARTTLS with port 587."
    if "refused" in low:
        return "The mail server refused the connection – check the port."
    return f"Could not send: {s[:200]}"
