"""The ZIMRA verification QR code as a small inline SVG (crisp on the 80 mm slip printer, no image files)."""
from django.utils.html import escape
from django.utils.safestring import mark_safe


def qr_svg(text, size_mm=34):
    if not text:
        return ""
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError:
        return ""
    q = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=2)
    q.add_data(text)
    q.make(fit=True)
    m = q.get_matrix()
    n = len(m)
    path = "".join(f"M{x},{y}h1v1h-1z" for y, row in enumerate(m) for x, on in enumerate(row) if on)
    return mark_safe(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{size_mm}mm" height="{size_mm}mm" '
        f'shape-rendering="crispEdges" role="img" aria-label="ZIMRA QR code {escape(text)}">'
        f'<rect width="{n}" height="{n}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
