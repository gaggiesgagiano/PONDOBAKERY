"""My look / business look & feel, the Pondo font file, and the 'Our Brand' page."""
import os
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .access import need
from .look import BRAND, FONT_MAGIC, FONT_TYPES, FONTS, SIZES, THEMES, brand_font_path, resolve
from .models import CompanySettings, UserLook, log_change

MAX_FONT = 8 * 1024 * 1024


def _choices(cs):
    import json
    pmap = {k: [t["pattern"], t["pattern_op"], t["logo"]] for k, t in THEMES.items()}
    return {"themes": THEMES, "fonts": FONTS, "sizes": SIZES, "has_brand_font": brand_font_path(cs) is not None,
            "pattern_map": json.dumps(pmap)}


@login_required
def my_look(request):
    cs = CompanySettings.get()
    own, _ = UserLook.objects.get_or_create(user=request.user)
    if request.method == "POST":
        if request.POST.get("reset"):
            own.theme = own.heading_font = own.text_size = own.pattern = own.greeting = ""
        else:
            t = request.POST.get("theme", "")
            f = request.POST.get("font", "")
            z = request.POST.get("size", "")
            own.theme = t if t in THEMES else ""
            own.heading_font = f if f in FONTS else ""
            own.text_size = z if z in SIZES else ""
            own.pattern = request.POST.get("pattern", "") if request.POST.get("pattern") in ("on", "off") else ""
            own.greeting = request.POST.get("greeting", "") if request.POST.get("greeting") in ("on", "off") else ""
        own.save()
        messages.success(request, "Your look is saved. Only you see it – everybody else keeps theirs.")
        return redirect("core:look")
    business = resolve(cs)
    return render(request, "core/look.html", {
        **_choices(cs), "mine": True, "sel": {"theme": own.theme, "font": own.heading_font, "size": own.text_size,
                                              "pattern": own.pattern, "greeting": own.greeting},
        "business": business, "cs": cs,
    })


@need(owner=True)
def business_look(request):
    cs = CompanySettings.get()
    if request.method == "POST":
        t, f, z = request.POST.get("theme"), request.POST.get("font"), request.POST.get("size")
        if t in THEMES:
            cs.theme = t
        if f in FONTS:
            cs.heading_font = f
        if z in SIZES:
            cs.text_size = z
        cs.pattern = request.POST.get("pattern") == "on"
        cs.greeting = request.POST.get("greeting") == "on"
        cs.tagline = (request.POST.get("tagline") or "").strip()[:60]
        cs.save()
        log_change(request.user, "Settings", "Look & feel", f"{THEMES[cs.theme]['label']} · {FONTS[cs.heading_font]['label']}")
        messages.success(request, "Look & feel saved for the whole business.")
        return redirect("core:look_business")
    sel = {"theme": cs.theme, "font": cs.heading_font, "size": cs.text_size,
           "pattern": "on" if cs.pattern else "off", "greeting": "on" if cs.greeting else "off"}
    return render(request, "core/look.html", {**_choices(cs), "mine": False, "sel": sel, "cs": cs,
                                              "font_file": cs.brand_font})


@need(owner=True)
@require_POST
def brand_font_upload(request):
    cs = CompanySettings.get()
    folder = Path(settings.MEDIA_ROOT) / "brand"
    if request.POST.get("remove"):
        p = brand_font_path(cs)
        if p:
            p.unlink(missing_ok=True)
        cs.brand_font = ""
        if cs.heading_font == "pondo":
            cs.heading_font = "retro"
        cs.save()
        UserLook.objects.filter(heading_font="pondo").update(heading_font="")
        messages.success(request, "The Pondo font file is removed. Headings use the Retro font again.")
        return redirect("core:look_business")
    f = request.FILES.get("font")
    if not f:
        messages.error(request, "Pick the font file first.")
        return redirect("core:look_business")
    ext = os.path.splitext(f.name)[1].lower()
    head = f.read(4)
    f.seek(0)
    if ext not in FONT_TYPES or not head.startswith(FONT_MAGIC[ext]):
        messages.error(request, "That is not a font file. Use the .otf, .ttf, .woff or .woff2 file from your designer.")
        return redirect("core:look_business")
    if f.size > MAX_FONT:
        messages.error(request, "That font file is too big (more than 8 MB).")
        return redirect("core:look_business")
    folder.mkdir(parents=True, exist_ok=True)
    old = brand_font_path(cs)
    name = f"pondo-font{ext}"
    with open(folder / name, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)
    if old and old.name != name:
        old.unlink(missing_ok=True)
    cs.brand_font = name
    cs.heading_font = "pondo"
    cs.save()
    log_change(request.user, "Settings", "Pondo font", f.name)
    messages.success(request, "Pondo font added – all headings now use it. (People who picked their own font keep theirs.)")
    return redirect("core:look_business")


def brand_font(request):
    """Serves the uploaded Pondo font (also used on the login page)."""
    p = brand_font_path(CompanySettings.get())
    if not p:
        raise Http404
    r = FileResponse(open(p, "rb"), content_type=FONT_TYPES.get(p.suffix.lower(), "application/octet-stream"))
    r["Cache-Control"] = "max-age=86400"
    return r


@login_required
def brand_view(request):
    """The brand guidelines, inside the program: values, colours, fonts, logos to download."""
    logos = [
        ("Primary logo", "Use whenever there is enough space – the character with the Pondo wordmark.",
         [("primary_burgundy", "#fff3d7"), ("primary_orange", "#fff3d7"), ("primary_teal", "#fff3d7"), ("primary_warm", "#fff3d7"),
          ("primary_reverse_cream", "#e56026"), ("primary_reverse_cream", "#7a1315"), ("primary_reverse_cream", "#218d80"),
          ("primary_reverse_warm", "#7a1315"), ("primary_burgundy", "#f89b47")]),
        ("Secondary logo", "Stacked version for spaces where the main logo doesn’t fit – packaging, signs, social media.",
         [("secondary_orange", "#fff3d7"), ("secondary_burgundy", "#fff3d7"), ("secondary_cream", "#e56026"), ("secondary_cream", "#7a1315")]),
        ("Submark", "Round “Fresh since ’26” badge for small spaces – stickers, stamps, boxes.",
         [("submark_orange", "#fff3d7"), ("submark_burgundy", "#fff3d7"), ("badge_burgundy_on_cream", "#e56026"),
          ("badge_cream_on_orange", "#fff3d7"), ("submark_cream", "#7a1315"), ("badge_cream_on_teal", "#fff3d7")]),
        ("Logo mark", "The Pondo character on its own – profile pictures, stamps and stickers.",
         [("mark_orange", "#fff3d7"), ("mark_burgundy", "#fff3d7"), ("mark_teal", "#fff3d7"), ("mark_cream", "#e56026")]),
    ]
    colour = {"burgundy": "Burgundy", "orange": "Orange", "teal": "Teal", "warm": "Warm orange", "cream": "Cream"}
    on = {"#fff3d7": "cream", "#e56026": "orange", "#7a1315": "burgundy", "#218d80": "teal", "#f89b47": "warm orange"}

    def label(name, bg):
        parts = name.split("_")
        if parts[0] == "badge":  # badge_<art>_on_<disc>
            disc = colour[parts[3]].lower()
            return f"{colour[parts[1]]} badge on {'an' if disc[0] in 'aeiou' else 'a'} {disc} circle"
        return f"{colour[parts[-1]]}{' (reverse)' if 'reverse' in parts else ''} – on {on.get(bg, bg)}"

    logos = [(t, say, [(n, bg, label(n, bg)) for n, bg in items]) for t, say, items in logos]
    art = ["samoosa", "cookie", "bun", "glazed_bun", "pie", "bread", "cupcake", "donut", "starburst"]
    return render(request, "core/brand.html", {"brand": BRAND, "logos": logos, "art": art, "look_now": resolve(CompanySettings.get(), request.user)})
