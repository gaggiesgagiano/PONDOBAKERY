"""Look & feel: the brand colour themes, heading fonts and text sizes people can pick.

Colours and pairings follow the Pondo Bakery Brand Guidelines (pages 17 & 19):
  Pondo Orange background  -> Bakery Cream
  Warm Orange background   -> Bakery Cream or Pondo Burgundy
  Bakery Cream background  -> Pondo Burgundy, Pondo Teal, Pondo Orange or Warm Orange
  Pondo Burgundy background-> Bakery Cream or Warm Orange
  Pondo Teal background    -> Bakery Cream
"""
from pathlib import Path

from django.conf import settings

BRAND = {
    "orange": {"name": "Pondo Orange", "role": "Primary colour", "hex": "#e56026", "rgb": "229 · 96 · 38",
               "cmyk": "5 · 77 · 99 · 0", "pantone": "7579 C", "ink": "#fff3d7",
               "pairs": "Bakery Cream", "use": "The main colour – about 60% of a design."},
    "burgundy": {"name": "Pondo Burgundy", "role": "Secondary colour", "hex": "#7a1315", "rgb": "122 · 19 · 21",
                 "cmyk": "29 · 100 · 100 · 40", "pantone": "1815 C", "ink": "#fff3d7",
                 "pairs": "Bakery Cream or Warm Orange", "use": "Secondary – about 30%. Great for text and buttons."},
    "teal": {"name": "Pondo Teal", "role": "Secondary colour", "hex": "#218d80", "rgb": "33 · 141 · 128",
             "cmyk": "81 · 24 · 55 · 5", "pantone": "7473 C", "ink": "#fff3d7",
             "pairs": "Bakery Cream", "use": "Secondary – for stickers like “Today’s special”."},
    "warm": {"name": "Warm Orange", "role": "Supporting colour", "hex": "#f89b47", "rgb": "248 · 155 · 71",
             "cmyk": "0 · 46 · 81 · 0", "pantone": "6253 C", "ink": "#7a1315",
             "pairs": "Bakery Cream or Pondo Burgundy", "use": "Supporting colour for backgrounds and highlights."},
    "cream": {"name": "Bakery Cream", "role": "Accent / neutral colour", "hex": "#fff3d7", "rgb": "255 · 243 · 215",
              "cmyk": "0 · 3 · 17 · 0", "pantone": "6232 C", "ink": "#7a1315",
              "pairs": "Burgundy, Teal, Orange or Warm Orange", "use": "The calm background – about 10% accent."},
}

THEMES = {
    "classic": {"label": "Pondo Classic", "say": "Burgundy menu, cream pages, orange highlights.",
                "menu": "#7a1315", "menu_ink": "#fff3d7", "page": "#fff6e2", "accent": "#e56026",
                "logo": "primary_reverse_cream", "pattern": "cream", "pattern_op": ".07"},
    "orange": {"label": "Pondo Orange", "say": "The main brand colour – bright and happy.",
               "menu": "#e56026", "menu_ink": "#fff3d7", "page": "#fff6e2", "accent": "#7a1315",
               "logo": "primary_reverse_cream", "pattern": "cream", "pattern_op": ".12"},
    "teal": {"label": "Pondo Teal", "say": "Calm teal menu with cream.",
             "menu": "#218d80", "menu_ink": "#fff3d7", "page": "#fff6e2", "accent": "#e56026",
             "logo": "primary_reverse_cream", "pattern": "cream", "pattern_op": ".1"},
    "warm": {"label": "Warm Orange", "say": "Soft warm orange with burgundy.",
             "menu": "#f89b47", "menu_ink": "#7a1315", "page": "#fff6e2", "accent": "#7a1315",
             "logo": "primary_burgundy", "pattern": "burgundy", "pattern_op": ".08"},
    "cream": {"label": "Bakery Cream", "say": "Light and airy – a cream menu.",
              "menu": "#fff3d7", "menu_ink": "#7a1315", "page": "#fffaf0", "accent": "#e56026",
              "logo": "primary_orange", "pattern": "orange", "pattern_op": ".09"},
    "night": {"label": "Late Shift (dark)", "say": "Deep burgundy – easy on the eyes for night shifts.",
              "menu": "#7a1315", "menu_ink": "#fff3d7", "page": "#2b0708", "accent": "#f89b47",
              "logo": "primary_reverse_warm", "pattern": "warm", "pattern_op": ".06"},
}

FONTS = {
    "retro": {"label": "Pondo (brand font)", "say": "The brand font Pondo (Retro Star), in capitals – exactly like the brand guide."},
    "pondo": {"label": "Pondo font file", "say": "The Pondo font file from your designer, added under Look & feel."},
    "round": {"label": "Round", "say": "Friendly and rounded (the first Pondo look)."},
    "clean": {"label": "Clean", "say": "Plain Nunito – the easiest to read."},
}

SIZES = {"normal": "Normal", "large": "Large", "xl": "Extra large"}

FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf"}
FONT_MAGIC = {".woff2": (b"wOF2",), ".woff": (b"wOFF",), ".ttf": (b"\x00\x01\x00\x00", b"true"), ".otf": (b"OTTO",)}


def brand_font_path(cs):
    if not cs.brand_font:
        return None
    p = Path(settings.MEDIA_ROOT) / "brand" / cs.brand_font
    return p if p.exists() else None


def resolve(cs, user=None):
    """The look for this person: their own choices, else the business default."""
    own = None
    if user is not None and getattr(user, "is_authenticated", False):
        from .models import UserLook
        try:
            own = user.look
        except UserLook.DoesNotExist:
            own = None
    theme = (own and own.theme) or cs.theme or "classic"
    font = (own and own.heading_font) or cs.heading_font or "retro"
    size = (own and own.text_size) or cs.text_size or "normal"
    pattern = cs.pattern if not (own and own.pattern) else own.pattern == "on"
    hello = cs.greeting if not (own and own.greeting) else own.greeting == "on"
    if theme not in THEMES:
        theme = "classic"
    has_font = brand_font_path(cs) is not None
    if font not in FONTS or (font == "pondo" and not has_font):
        font = "retro"
    t = THEMES[theme]
    biz_font = cs.heading_font if cs.heading_font in FONTS else "retro"
    if biz_font == "pondo" and not has_font:
        biz_font = "retro"
    return {
        "theme": theme, "font": font, "size": size if size in SIZES else "normal",
        "pattern": "on" if pattern else "off", "hello": "on" if hello else "off",
        "logo": t["logo"], "pattern_file": t["pattern"], "pattern_op": t["pattern_op"],
        "has_brand_font": has_font, "font_version": cs.brand_font,
        "biz_font": biz_font,  # printouts always use the business font
    }
