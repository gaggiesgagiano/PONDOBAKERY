"""The Fiscal (ZIMRA) pages: day status and buttons for supervisors, setup and support tools for the Manager."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.access import DEFAULT_ROLE, EDIT, need, rights
from core.models import Shop, log_change

from . import engine as eng
from . import service
from .models import FiscalCall, FiscalSetup


def _supervisor(request):
    u = request.user
    if u.is_superuser:
        return True
    acc = getattr(u, "access", None)
    return (acc.role if acc and acc.role else DEFAULT_ROLE) in ("supervisor", "assistant_manager", "manager")


def _say(request, env, done):
    if eng.ok(env):
        messages.success(request, f"{done} {env.get('Message') or ''}".strip())
    else:
        messages.error(request, env.get("Message") or "The fiscal engine said no.")


# ======================================================================= the fiscal page
@need("sales", EDIT)
def home(request):
    from till.models import Sale

    s = service.setup()
    e = eng.get_engine()
    if getattr(e, "blocked", lambda: False)():
        messages.error(request, eng.BLOCKED.format(folder=e.folder))
    info = service.summary(request.user) if s.active and not service.demo() else None
    problems = Sale.objects.filter(fiscal_status__in=(service.FAILED, service.PENDING, service.FLAGGED)).select_related("shift__till")
    return render(request, "fiscal/home.html", {
        "s": s, "info": info, "counts": service.counts(), "problems": problems[:100],
        "boss": _supervisor(request), "owner": rights(request).owner, "demo": service.demo(),
        "recent": FiscalCall.objects.select_related("sale")[:15] if rights(request).owner else []})


@need("sales", EDIT)
@require_POST
def act(request):
    if not _supervisor(request):
        messages.error(request, "Only a Supervisor or manager can do that.")
        return redirect("fiscal:home")
    if not service.active():
        messages.error(request, "Fiscalisation is off.")
        return redirect("fiscal:home")
    what = request.POST.get("do")
    if what == "open":
        _say(request, service.open_day(request.user), "Fiscal day opened.")
    elif what == "sync":
        env, data, n = service.sync_pending(request.user)
        if eng.ok(env) and isinstance(data, dict):
            messages.success(request, f"Sent {data.get('submitted', 0)} of {data.get('total', 0)} waiting receipts to ZIMRA "
                                      f"({data.get('stillPending', 0)} still waiting, {data.get('failed', 0)} refused).")
        else:
            _say(request, env, "Done.")
    elif what == "close":
        sync_env, env = service.close_day(request.user)
        _say(request, env, "Fiscal day closed (Z report).")
        if eng.ok(env):
            log_change(request.user, "Fiscal", "Z report", "closed", env.get("Message", "")[:200])
    elif what == "retry":
        n = service.retry_failed(request.user)
        left = service.counts()[service.FAILED]
        (messages.success if not left else messages.warning)(
            request, f"{n} slip(s) fiscalised now." + (f" {left} still refused – open them to see why." if left else ""))
    return redirect("fiscal:home")


@need("sales", EDIT)
@require_POST
def retry_one(request, pk):
    from till.models import Sale

    sale = get_object_or_404(Sale, pk=pk)
    if sale.fiscal_status == service.FAILED:
        sale.fiscal_status = ""
        service.fiscalise(sale, request.user)
    if sale.fiscal_status in service.ISSUED:
        messages.success(request, f"{sale.number} has its signed fiscal receipt now"
                         + (" (ZIMRA flagged it red)." if sale.fiscal_status == service.FLAGGED else "."))
    else:
        messages.error(request, f"{sale.number}: {sale.fiscal_message}")
    back = request.POST.get("back") or ""
    return redirect(back if back.startswith("/") and not back.startswith("//") else "fiscal:home")


# ======================================================================= setup (Manager)
CONFIG_FIELDS = [("DEVICEBRANCHNAME", "Shop name on the receipt"), ("DEVICESTREET", "Street"),
                 ("DEVICEHOUSENO", "House / stand no."), ("DEVICECITY", "City"), ("DEVICEPROVINCE", "Province")]
TOOLS = ["GetCardDetails", "GetConfig", "GetStatus", "GetDeviceStatus", "GetCertificateDetails", "CheckLicense",
         "GetLicense", "CheckEnvironmentTransition", "GetUnProcessedTransactionsSummary"]


ZIMRA_STATUS = "ZIMRA getStatus (direct)"


def _config_defaults():
    shop = Shop.objects.filter(active=True).first()
    street = (shop.address_line1 if shop else "") or ""
    house, _, rest = street.partition(" ")
    return {"DEVICEBRANCHNAME": shop.name if shop else "Pondo Bakery",
            "DEVICEHOUSENO": house if house.isdigit() else "", "DEVICESTREET": rest if house.isdigit() else street,
            "DEVICECITY": "Harare", "DEVICEPROVINCE": "Harare"}


@need(owner=True)
def setup(request):
    s = service.setup()
    installed = eng.get_engine().installed() if hasattr(eng.get_engine(), "installed") else True
    if getattr(eng.get_engine(), "blocked", lambda: False)():
        messages.error(request, eng.BLOCKED.format(folder=eng.get_engine().folder))
    try:
        cfg = eng.read_config() if installed else {}
    except Exception as e:  # noqa: BLE001
        cfg = {}
        messages.error(request, f"Could not read the engine's config.ini: {e}")
    raw = None
    if request.method == "POST":
        what = request.POST.get("do")
        if what == "save":
            mode = request.POST.get("mode")
            if mode not in dict(FiscalSetup.MODES):
                mode = s.mode
            if mode == FiscalSetup.LIVE and s.mode != FiscalSetup.LIVE and request.POST.get("sure") != "LIVE":
                messages.error(request, "To switch to LIVE, type LIVE in the box – from then on every till slip is a real tax invoice.")
                return redirect("fiscal:setup")
            if mode != FiscalSetup.OFF and not installed:
                messages.error(request, "The fiscal engine is not installed in the fiscal_engine folder yet.")
                return redirect("fiscal:setup")
            hs = "".join(ch for ch in (request.POST.get("hs_code") or "") if ch.isdigit())[:8]
            old = s.mode
            s.mode, s.hs_code, s.auto_open_day, s.updated_by = mode, hs, bool(request.POST.get("auto_open_day")), request.user
            s.save()
            if mode != FiscalSetup.OFF:
                values = dict(service.ENVIRONMENTS[mode])
                qr = (request.POST.get("qr_base") or "").strip().rstrip("/") or service.QR_BASE[mode]
                values.update({"QRURL": qr, "VERIFICATIONSERVER": qr, "VATFLAG": "1", "TIMEOUT": "20",
                               "DEVICEOPERATINGMODE": "ONLINE"})
                for key, _label in CONFIG_FIELDS:
                    values[key] = (request.POST.get(key) or "").strip()[:100]
                try:
                    eng.write_config(values)
                except OSError as e:
                    messages.error(request, f"Could not write the engine's config.ini: {e}")
                    return redirect("fiscal:setup")
                eng.get_engine().restart()
            log_change(request.user, "Fiscal", "setup", "changed", f"{old} → {mode}")
            messages.success(request, f"Saved. Fiscalisation: {s.get_mode_display()}.")
            if old != mode and FiscalSetup.OFF not in (old, mode):
                messages.warning(request, "You changed ZIMRA server: the device must be registered again on the new "
                                          "server (step 2 and 3 below) before slips are accepted.")
            return redirect("fiscal:setup")
        if what == "license":
            key = (request.POST.get("license") or "").strip()
            serial = (request.POST.get("serial") or "").strip()
            dev = "".join(ch for ch in (request.POST.get("device") or "") if ch.isdigit())
            if not key:
                messages.error(request, "Paste the licence key.")
                return redirect("fiscal:setup")
            # The licence belongs to one device serial number. Pondo writes serial, device ID and key into config.ini
            # and the engine activates it when it starts. (Not SetLicense: after SetLicense the engine encrypts
            # config.ini and locks its folder to SYSTEM and Administrators – that locks Pondo out of its own engine.)
            values = {"LICENSEKEY": key}
            if serial:
                values["SERIALNUMBER"] = serial
            if dev:
                values["DEVICEID"] = dev
            try:
                eng.write_config(values)
            except OSError as e:
                messages.error(request, f"Could not write the engine's config.ini: {e}")
                return redirect("fiscal:setup")
            eng.get_engine().restart()
            env = service.call("CheckLicense", user=request.user)
            lic = eng.payload(env) if eng.ok(env) else None
            if isinstance(lic, dict) and lic.get("allowed"):
                messages.success(request, f"Licence active – {lic.get('message', '')}")
                log_change(request.user, "Fiscal", "licence", "applied", f"serial {lic.get('serial', serial)}")
            else:
                messages.error(request, "The licence is not active: " + ((lic or {}).get("message") if isinstance(lic, dict)
                                                                          else env.get("Message", "")))
            raw = service.pretty(env)
        elif what in ("generate", "verify", "register", "apply"):
            serial = (request.POST.get("serial") or "").strip()
            key = (request.POST.get("activation") or "").strip()
            dev = "".join(ch for ch in (request.POST.get("device") or "") if ch.isdigit())
            folder = (request.POST.get("folder") or "").strip()
            if what != "apply" and not (serial and key and dev):
                messages.error(request, "Type the serial number, the activation key and the device ID from ZIMRA.")
            else:
                if what == "generate":
                    env = service.call("GenerateDeviceCertificates", serial, key, dev, user=request.user)
                elif what == "verify":
                    env = service.call("VerifyCertificateDetails", serial, key, dev, folder, user=request.user)
                elif what == "register":   # NB the engine's order: activation key, serial, device ID
                    env = service.call("RegisterDeviceWithZimra", key, serial, dev, user=request.user)
                else:
                    folder = folder or (cfg.get("CERTIFICATEFOLDER", "").rstrip("\\/") + ("\\" + dev if dev else ""))
                    env = service.call("ApplyDeviceSettings", folder, dev, serial, key, user=request.user)
                _say(request, env, {"generate": "Certificates made.", "verify": "Checked.", "register": "Registered with ZIMRA.",
                                    "apply": "Device settings applied."}[what])
                log_change(request.user, "Fiscal", "device", what, env.get("Message", "")[:200])
                raw = service.pretty(env)
        elif what == "tool":
            tool = request.POST.get("tool")
            if tool in TOOLS:
                args = []
                if tool == "GetUnProcessedTransactionsSummary":
                    st = eng.payload(service.call("GetStatus", user=request.user)) or {}
                    args = [str(st.get("LastFiscalDayNo", "") if isinstance(st, dict) else ""), ""]
                raw = service.pretty(service.call(tool, *args, user=request.user))
                raw["tool"] = tool
            elif tool == ZIMRA_STATUS:
                raw = service.pretty(service.zimra_status(user=request.user))
                raw["tool"] = tool
        elif what == "lookup":
            inv = (request.POST.get("invoice") or "").strip()
            if inv:
                raw = service.pretty(service.call("GetTransaction", inv, user=request.user))
                raw["tool"] = f"GetTransaction {inv}"
        elif what == "restart":
            eng.get_engine().restart()
            messages.success(request, "The fiscal engine starts fresh on the next call.")
            return redirect("fiscal:setup")
        try:
            cfg = eng.read_config() if installed else {}
        except Exception:  # noqa: BLE001
            pass
    defaults = _config_defaults()
    fields = [(k, label, cfg.get(k) or defaults.get(k, "")) for k, label in CONFIG_FIELDS]
    qr_now = cfg.get("QRURL") or service.QR_BASE.get(s.mode, "")
    return render(request, "fiscal/setup.html", {
        "s": s, "cfg": cfg, "fields": fields, "installed": installed, "folder": eng.engine_dir(), "raw": raw,
        "tools": TOOLS + [ZIMRA_STATUS], "modes": FiscalSetup.MODES, "qr_now": qr_now, "demo": service.demo(),
        "dev_id": request.POST.get("device") or cfg.get("DEVICEID", ""),
        "dev_serial": request.POST.get("serial") or cfg.get("SERIALNUMBER", ""),
        "cert_folder": cfg.get("CERTIFICATEFOLDER", r"C:\FiscalStackZW certificates"),
        "engine_info": getattr(eng.get_engine(), "info", {}), "post": request.POST if request.method == "POST" else {}})


@need(owner=True)
def journal(request):
    calls = FiscalCall.objects.select_related("sale", "user")
    q = (request.GET.get("q") or "").strip()
    if q:
        calls = calls.filter(method__icontains=q) | calls.filter(message__icontains=q) | calls.filter(sale__number__icontains=q)
    if request.GET.get("bad"):
        calls = calls.filter(ok=False)
    page = Paginator(calls, 50).get_page(request.GET.get("page"))
    return render(request, "fiscal/journal.html", {"page": page, "q": q, "bad": request.GET.get("bad")})


@need(owner=True)
def call_detail(request, pk):
    c = get_object_or_404(FiscalCall.objects.select_related("sale", "user"), pk=pk)
    return render(request, "fiscal/call.html", {"c": c, "pretty": service.pretty({"Code": "1" if c.ok else "0",
                                                                                 "Message": c.message, "Data": c.data})})
