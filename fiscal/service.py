"""Pondo's side of ZIMRA fiscalisation: turn a till sale or refund into a fiscal receipt, open and close the
fiscal day, and send receipts that were made while ZIMRA could not be reached.

The rule from the engine guide: a sale is never lost and never blocked because the internet is down.
The sale is saved in Pondo first; then the engine signs it, gives it the ZIMRA QR code and sends it to ZIMRA.
* submitted – ZIMRA accepted it.
* pending   – signed and stored by the engine; it goes to ZIMRA when "Send waiting receipts" runs.
* failed    – ZIMRA (or the engine) refused it. Nothing was sent; fix the problem and press "Try again".
"""
import json
import os
import time
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils import timezone

from . import engine as eng
from .models import FiscalCall, FiscalSetup

Z = Decimal("0")
C = Decimal("0.01")
CURRENCY = "USD"            # Pondo prices are in US$; ZiG cash is taken at the day's rate and counted in US$

SUBMITTED, PENDING, FAILED, PRACTICE = "submitted", "pending", "failed", "practice"
FLAGGED = "flagged"         # signed and stored by ZIMRA, but ZIMRA flagged it (red) – final, printed with its QR code
ISSUED = (SUBMITTED, PENDING, FLAGGED)   # a signed fiscal receipt exists for the slip
DAY_CHECK_EVERY = 600       # seconds between "is the fiscal day open?" checks while selling
_day = {"open": False, "checked": 0.0}

# ZIMRA servers per environment (engine guide §7). TEST is the default for anything new.
ENVIRONMENTS = {
    FiscalSetup.TEST: {"ZIMRASERVER": "https://fdmsapitest.zimra.co.zw", "POSENVIRONMENT": "TEST",
                       "TAXIDSTANDARDRATED": "517", "TAXIDZERORATED": "2", "TAXIDEXEMPTED": "3"},
    FiscalSetup.LIVE: {"ZIMRASERVER": "https://fdmsapi.zimra.co.zw", "POSENVIRONMENT": "PROD",
                       "TAXIDSTANDARDRATED": "515", "TAXIDZERORATED": "2", "TAXIDEXEMPTED": "1"},
}
QR_BASE = {FiscalSetup.TEST: "https://fdmstest.zimra.co.zw", FiscalSetup.LIVE: "https://fdms.zimra.co.zw"}


def demo():
    """The DEMO (practice copy) of Pondo must never fiscalise – it shares this computer's fiscal engine."""
    return os.environ.get("PONDO_DEMO") == "1"


def setup():
    return FiscalSetup.get()


def active():
    return not demo() and setup().active


def call(method, *args, sale=None, user=None, timeout=None):
    """Call the engine and write the call in the fiscal journal."""
    t0 = time.monotonic()
    env = eng.get_engine().call(method, *args, timeout=timeout)
    try:
        FiscalCall.objects.create(method=method, ok=eng.ok(env), message=(env.get("Message") or "")[:4000],
                                  data=(env.get("Data") or "")[:20000], sale=sale,
                                  user=user if getattr(user, "is_authenticated", False) else None,
                                  seconds=Decimal(str(round(time.monotonic() - t0, 2))))
    except Exception:  # noqa: BLE001 – the journal must never stop a sale
        pass
    return env


# ======================================================================== building the receipt
def _money(v):
    return str(Decimal(v).quantize(C))


def items_xml(sale, hs_code=""):
    """The engine's <ITEMS> list, in the receipt's currency (USD, or ZWG at the sale's rate – the same figures as the
    printed slip). Always positive numbers – for a credit note (02) the engine makes them negative."""
    rows = []
    for it, price, line in sale.lines():
        qty = abs(it.qty)
        amt = abs(line)
        rate = it.vat_rate or Z
        tax = (amt - amt / (1 + rate)).quantize(C)
        code = str(getattr(it.recipe, "number", "") or it.recipe_id)
        rows.append(
            "<ITEM>"
            f"<HH>{escape(hs_code or '')}</HH>"
            f"<ITEMCODE>{escape(code)}</ITEMCODE>"
            f"<ITEMNAME1>{escape(it.name[:200])}</ITEMNAME1>"
            f"<ITEMNAME2>{escape(it.name[:200])}</ITEMNAME2>"
            f"<QTY>{qty.normalize():f}</QTY>"
            f"<PRICE>{_money(abs(price))}</PRICE>"
            f"<AMT>{_money(amt)}</AMT>"
            f"<TAX>{_money(tax)}</TAX>"
            f"<TAXR>{rate.normalize():f}</TAXR>"
            "</ITEM>")
    return "<ITEMS>" + "".join(rows) + "</ITEMS>"


def currencies_xml(total, currency=CURRENCY):
    """One payment line equal to the receipt total, in the receipt's currency (ZIMRA checks payments = total)."""
    return (f"<CurrenciesReceived><Currency><Name>{currency}</Name><Amount>{_money(abs(total))}</Amount>"
            "<Rate>1</Rate></Currency></CurrenciesReceived>")


def _apply_receipt(sale, env):
    """Copy the engine's ReceiptData (QR code, day, number, sync state) onto the sale."""
    el = eng.payload(env)
    sale.fiscal_qr = eng.xml_text(el, "QRCode")[:300]
    sale.fiscal_day = eng.xml_text(el, "FiscalDayNo") or eng.xml_text(el, "FiscalDayNumber")
    sale.fiscal_global_no = eng.xml_text(el, "ReceiptGlobalNo") or eng.xml_text(el, "ReceiptGlobalNumber")
    sale.fiscal_device = eng.xml_text(el, "DeviceID")
    sync = eng.xml_text(el, "SyncState").lower()
    sale.fiscal_status = SUBMITTED if sync == "submitted" else PENDING
    warn = eng.xml_text(el, "ValidationWarnings")
    sale.fiscal_message = (env.get("Message") or "") + (f"\nWarnings: {warn}" if warn else "")


def zimra_qr(qr_base, device_id, receipt_date, global_no, signature_b64):
    """The ZIMRA verification link (engine guide §18): QRURL / deviceID(10) + date ddMMyyyy + global no(10) +
    the first 16 hex characters (upper case) of the MD5 of the RAW signature bytes (the base64-decoded signature)."""
    import base64
    import datetime as _dt
    import hashlib
    import re

    if not (qr_base and signature_b64 and str(global_no).strip()):
        return ""
    dev = int(re.sub(r"[^\d]", "", str(device_id)) or 0)
    try:
        when = _dt.datetime.fromisoformat(str(receipt_date)[:19])
    except ValueError:
        when = _dt.datetime.now()
    try:
        md5 = hashlib.md5(base64.b64decode(signature_b64)).hexdigest().upper()[:16]
    except (ValueError, TypeError):
        return ""
    return f"{qr_base.rstrip('/')}/{dev:010d}{when:%d%m%Y}{int(global_no):010d}{md5}"


def _signed_receipt(row):
    """The signed receipt JSON in a stored engine transaction, or None."""
    try:
        rec = json.loads((row or {}).get("JsonData") or "{}")
    except (ValueError, TypeError):
        return None
    rec = rec.get("receipt", rec) if isinstance(rec, dict) else None
    sig = ((rec or {}).get("receiptDeviceSignature") or {}).get("signature") if isinstance(rec, dict) else None
    return rec if sig else None


def _apply_row(sale, row):
    """Copy a stored engine transaction (GetTransaction) onto the sale. When the engine kept a signed receipt but no
    QR code (a receipt ZIMRA flagged red), the QR code is made from the receipt's own device signature."""
    if not isinstance(row, dict):
        return False
    qr = row.get("ReceiptQRCode") or ""
    rec = _signed_receipt(row)
    if not qr and rec:
        cfg = {}
        try:
            cfg = eng.read_config()
        except Exception:  # noqa: BLE001
            pass
        qr = zimra_qr(cfg.get("QRURL") or cfg.get("VERIFICATIONSERVER") or QR_BASE.get(setup().mode, ""),
                      row.get("DeviceID") or cfg.get("DEVICEID", ""), rec.get("receiptDate"),
                      rec.get("receiptGlobalNo") or row.get("GlobalReceiptNumber"),
                      rec["receiptDeviceSignature"]["signature"])
    if not qr:
        return False
    sale.fiscal_qr = qr[:300]
    sale.fiscal_day = str(row.get("FiscalDayNumber") or sale.fiscal_day or "")
    sale.fiscal_global_no = str(row.get("GlobalReceiptNumber") or sale.fiscal_global_no or "")
    sale.fiscal_device = str(row.get("DeviceID") or sale.fiscal_device or "")
    if rec and rec.get("receiptGlobalNo"):
        sale.fiscal_global_no = str(rec.get("receiptGlobalNo"))
    sync = str(row.get("FiscalSyncStatus") or "").lower()
    if sync == "synced":
        sale.fiscal_status = SUBMITTED
    elif sync == "pending" or row.get("ReceiptQRCode"):
        sale.fiscal_status = PENDING
    else:
        sale.fiscal_status = FLAGGED          # only a signed receipt, no sync state: ZIMRA flagged it red
    return True


def _is_red(msg):
    m = (msg or "").lower()
    return "stored by zimra" in m or ("red" in m and "validation" in m)


def _take_stored(sale, inv, msg, user, red=False):
    """Use the receipt the engine already signed for this slip (GetTransaction). A receipt ZIMRA stored but flagged
    red is signed and final (ZIMRA used up its number): it is printed with its QR code and the flag is kept on record.
    Returns True when a signed receipt was found."""
    row = eng.payload(call("GetTransaction", inv, sale=sale, user=user))
    if not _apply_row(sale, row):
        return False
    sale.fiscal_ref = inv
    if red:
        sale.fiscal_status = FLAGGED
    if sale.fiscal_status == FLAGGED:
        sale.fiscal_message = "ZIMRA validation: RED – " + (msg or "flagged by ZIMRA")
    else:
        sale.fiscal_message = "Recovered the receipt the engine had already signed for this slip."
    return True


SAVE_FIELDS = ["fiscal_status", "fiscal_ref", "fiscal_qr", "fiscal_day", "fiscal_global_no", "fiscal_device",
               "fiscal_message", "fiscal_mode", "fiscal_at"]


def _day_looks_closed(msg):
    m = (msg or "").lower()
    return "day" in m and ("closed" in m or "not open" in m or "fisc04" in m)


def ensure_day_open(user=None, force=False):
    """Open the fiscal day if it is closed (checked at most every 10 minutes while selling)."""
    if not force and _day["open"] and time.monotonic() - _day["checked"] < DAY_CHECK_EVERY:
        return True, ""
    env = call("GetStatus", user=user)
    st = eng.payload(env) if eng.ok(env) else None
    status = str((st or {}).get("FiscalDayStatus") or "") if isinstance(st, dict) else ""
    if eng.ok(env) and status == "FiscalDayOpened":
        _day.update(open=True, checked=time.monotonic())
        return True, ""
    if eng.ok(env) and status == "FiscalDayCloseInitiated":
        return False, "ZIMRA is still closing the last fiscal day – wait a minute and try again."
    env = call("OpenDay", user=user)
    if eng.ok(env):
        _day.update(open=True, checked=time.monotonic())
        return True, ""
    _day.update(open=False, checked=0.0)
    return False, env.get("Message") or "Could not open the fiscal day."


def fiscalise(sale, user=None):
    """Make the fiscal receipt for one till sale or refund. Never raises; the result is saved on the sale."""
    if not active():
        return sale
    if sale.fiscal_status in ISSUED:
        return sale
    s = setup()
    sale.fiscal_mode = s.mode
    sale.fiscal_at = timezone.now()
    refund = sale.kind == "refund"
    original = sale.refund_of if refund else None
    if refund and original is not None and original.fiscal_status not in ISSUED:
        if original.fiscal_status == PRACTICE:
            sale.fiscal_status, sale.fiscal_message = PRACTICE, "The original slip was a practice slip."
        else:
            sale.fiscal_status = FAILED
            sale.fiscal_message = (f"The original slip {original.number} is not fiscalised yet – "
                                   "fix that one first, then try this refund again.")
        sale.save(update_fields=SAVE_FIELDS)
        return sale
    if s.auto_open_day:
        ensure_day_open(user)

    inv = (sale.fiscal_ref or sale.number).split("-R")[0]
    if sale.fiscal_message and sale.fiscal_message != "Not fiscalised yet.":
        # a retry: if the engine already signed a receipt for this slip, use it – never send the same slip twice
        if _take_stored(sale, inv, sale.fiscal_message, user, red=_is_red(sale.fiscal_message)):
            sale.save(update_fields=SAVE_FIELDS)
            return sale
    env = _transact(sale, inv, refund, original, s, user)
    msg = env.get("Message") or ""
    if not eng.ok(env) and _day_looks_closed(msg) and s.auto_open_day:
        opened, why = ensure_day_open(user, force=True)
        if opened:
            env = _transact(sale, inv, refund, original, s, user)
            msg = env.get("Message") or ""
    if not eng.ok(env) and "already used on this device" in msg:
        # the engine already has this invoice (e.g. Pondo was stopped half-way): take the stored receipt
        if _take_stored(sale, inv, msg, user):
            sale.save(update_fields=SAVE_FIELDS)
            return sale
    if eng.ok(env):
        sale.fiscal_ref = inv
        _apply_receipt(sale, env)
    elif _is_red(msg) and _take_stored(sale, inv, msg, user, red=True):
        pass                      # signed, stored by ZIMRA, flagged red: printed with its QR code
    else:
        sale.fiscal_ref = inv
        sale.fiscal_status = FAILED
        sale.fiscal_message = msg or "The fiscal engine said no, without a reason."
    sale.save(update_fields=SAVE_FIELDS)
    return sale


def _transact(sale, inv, refund, original, s, user):
    zwg = sale.in_zwg
    cur = "ZWG" if zwg else CURRENCY
    total = abs(sale.total_fx if zwg else sale.total)
    vat = abs(sale.vat_fx if zwg else sale.vat)
    comment = ""
    if refund:
        comment = (f"Refund of slip {original.number}: {sale.reason}" if original else f"Refund: {sale.reason}")[:200]
    # the customer, when they asked for their details (ZIMRA keeps them only with a name AND a TIN – else "Walk In")
    return call("TransactM",
                cur, sale.customer_email, inv,
                sale.customer_name, sale.customer_vat, sale.customer_address, sale.customer_phone, sale.customer_tin,
                _money(total), _money(vat),
                "02" if refund else "01",
                comment,
                (original.fiscal_ref or original.number) if original else "",
                items_xml(sale, s.hs_code), currencies_xml(total, cur),
                sale=sale, user=user)


# ======================================================================== day, queue and look-ups
def summary(user=None):
    """Everything the Fiscal page shows. Each part fails on its own."""
    out = {"mode": setup().mode, "demo": demo(), "engine_installed": eng.get_engine().installed()
           if hasattr(eng.get_engine(), "installed") else True}
    lic = call("CheckLicense", user=user)
    out["license"] = eng.payload(lic) if eng.ok(lic) else {"allowed": False, "message": lic.get("Message")}
    st = call("GetStatus", user=user)
    out["status_ok"] = eng.ok(st)
    out["status"] = eng.payload(st) if eng.ok(st) else None
    out["status_message"] = st.get("Message", "")
    if isinstance(out["status"], dict) and out["status"].get("FiscalDayStatus") == "FiscalDayOpened":
        _day.update(open=True, checked=time.monotonic())
    dev = call("GetDeviceStatus", user=user)
    el = eng.payload(dev) if eng.ok(dev) else None
    out["device"] = {k: eng.xml_text(el, k) for k in ("Status", "DeviceID", "SerialNumber", "CompanyName",
                                                      "FiscalDay", "LastReceiptGlobalNo", "Note")} if el is not None else None
    out["device_message"] = dev.get("Message", "")
    return out


def open_day(user=None):
    env = call("OpenDay", user=user)
    if eng.ok(env):
        _day.update(open=True, checked=time.monotonic())
    return env


def sync_pending(user=None):
    """Send every receipt made while ZIMRA could not be reached, then update the slips in Pondo."""
    from till.models import Sale

    env = call("SubmitPendingQueue", 200, user=user)
    data = eng.payload(env) if eng.ok(env) else None
    updated = 0
    for item in (data or {}).get("items", []) if isinstance(data, dict) else []:
        inv = str(item.get("invoiceNumber") or "")
        sale = Sale.objects.filter(fiscal_ref=inv).first() if inv else None
        if not sale:
            continue
        st = str(item.get("status") or "").lower()
        if st == "synced":
            # the receipt was renumbered onto ZIMRA's sequence – fetch its final number and QR code
            row = eng.payload(call("GetTransaction", inv, sale=sale, user=user))
            if not _apply_row(sale, row):
                sale.fiscal_status = SUBMITTED
                sale.fiscal_global_no = str(item.get("globalReceiptNo") or sale.fiscal_global_no)
            sale.fiscal_status = SUBMITTED
            sale.fiscal_message = item.get("message") or "Sent to ZIMRA."
        elif st == "red":
            if not _take_stored(sale, inv, item.get("message") or "", user, red=True):
                sale.fiscal_status = FAILED
                sale.fiscal_message = item.get("message") or "ZIMRA flagged this receipt red."
        elif st == "rejected-data":
            sale.fiscal_status = FAILED
            sale.fiscal_message = item.get("message") or "ZIMRA refused this receipt."
        else:
            continue
        sale.save(update_fields=SAVE_FIELDS)
        updated += 1
    return env, data, updated


def close_day(user=None):
    """End of the day: send waiting receipts, then the Z report (which closes the fiscal day on ZIMRA)."""
    sync_env, _, _ = sync_pending(user)
    env = call("ZReport", user=user)
    if eng.ok(env):
        _day.update(open=False, checked=0.0)
    return sync_env, env


def retry_failed(user=None, limit=50):
    from till.models import Sale

    done = 0
    for sale in Sale.objects.filter(fiscal_status=FAILED).order_by("created_at")[:limit]:
        sale.fiscal_status = ""
        fiscalise(sale, user)
        done += sale.fiscal_status in ISSUED
    return done


def trader():
    """The registered taxpayer printed on fiscal slips – from the engine's config (filled in by ZIMRA registration)."""
    try:
        cfg = eng.read_config()
    except Exception:  # noqa: BLE001
        return {}
    return {"name": cfg.get("TAXPAYERNAME", ""), "tin": cfg.get("TAXPAYERTIN", ""), "vat": cfg.get("VATNUMBER", ""),
            "device": cfg.get("DEVICEID", ""), "serial": cfg.get("SERIALNUMBER", "")}


def counts():
    from till.models import Sale

    return {k: Sale.objects.filter(fiscal_status=k).count() for k in (SUBMITTED, PENDING, FAILED, FLAGGED)}


def pretty(env):
    """An envelope for the support view: Data made readable."""
    d = eng.payload(env)
    if isinstance(d, (dict, list)):
        data = json.dumps(d, indent=2, ensure_ascii=False)
    else:
        data = env.get("Data") or ""
    return {"Code": env.get("Code"), "Message": env.get("Message"), "Data": data}


# ======================================================================== ZIMRA's own view (read-only)
def zimra_status(user=None):
    """ZIMRA's own getStatus for this device, asked directly through the engine's ZIMRA gateway (read-only):
    fiscal day, day status, last receipt global number and the day's document quantities and counters."""
    env = call("__zimra", "GetStatus", user=user)
    if not eng.ok(env):
        return env
    try:
        rep = json.loads(env.get("Data") or "{}")
    except ValueError:
        return eng.envelope(0, "Pondo could not read ZIMRA's answer.", env.get("Data") or "")
    js = rep.get("Json") or rep.get("Raw") or ""
    ok = str(rep.get("Success")).lower() == "true"
    return eng.envelope(1 if ok else 0, rep.get("Message") or ("ZIMRA getStatus" if ok else "ZIMRA did not answer"),
                        js if isinstance(js, str) else json.dumps(js))
