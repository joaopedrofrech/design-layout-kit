#!/usr/bin/env python3
"""
Starter — one-page example layout. Replace draw() with the real layout for each project.

    python3 designs/<design>/build.py                  # every target in `targets` of the design's content.yaml
    python3 designs/<design>/build.py --target web     # one run, only this target: print | web

Outputs in designs/<design>/dist/v<N>/  (<slug>-v<N>-<color>-<dpi>dpi[-<variant>].pdf):
  print  cmyk-fogra39-300dpi.pdf (pure, editable) + cmyk-fogra39-300dpi-pdfx1a.pdf (printer)
  web    rgb-300dpi.pdf (pure, editable)          + rgb-150dpi-web.pdf (light, linearized)

Pipeline (targets, color, images, naming, X-1a, web optimization): lib/core.py — do not fork it per project.
"""
import os
import sys

from PIL import Image
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = HERE                                     # kit root = nearest folder with lib/core.py (this one, or a parent when
while not os.path.exists(os.path.join(KIT, "lib", "core.py")) and KIT != os.path.dirname(KIT):   # this is a design in designs/<name>/)
    KIT = os.path.dirname(KIT)
sys.path.insert(0, KIT)
from lib.core import resolver, run  # noqa: E402

P = resolver(HERE, KIT)                        # design folder first, then shared kit assets

# ---- fonts: register every font used (and set the default in run(font=...))
for name, file in [("Body", "Poppins-Regular.ttf"), ("BodyMd", "Poppins-Medium.ttf"),
                   ("BodyBd", "Poppins-Bold.ttf")]:
    pdfmetrics.registerFont(TTFont(name, P("assets", "fonts", file)))


def validate(D):
    """Project-specific content checks; return a list of error strings."""
    err = [f"colors.{k} missing" for k in ("primary", "accent", "text", "muted") if k not in D.get("colors", {})]
    if "photo" in D and not os.path.exists(P(D["photo"]["file"])):
        err.append(f"photo not found: {D['photo']['file']}")
    return err


def draw(c, ctx):
    """The layout. c = reportlab canvas, ctx = see lib/core.py. One c.showPage() per page."""
    D, K = ctx.D, ctx.K
    W, H = ctx.page_size
    M = 40

    # header bar
    bl = ctx.bleed                       # 0 unless bleed_mm > 0: extend backgrounds past the trim edge
    c.setFillColor(K.primary)
    c.rect(-bl, H - 60, W + 2 * bl, 60 + bl, stroke=0, fill=1)
    c.setFillColor(ctx.white)
    c.setFont("BodyBd", 12)
    c.drawString(M, H - 36, D["header"])

    # heading + intro
    y = H - 110
    c.setFillColor(K.text)
    c.setFont("BodyBd", 26)
    c.drawString(M, y, D["heading"])
    c.setFillColor(K.muted)
    c.setFont("Body", 10.5)
    for ln in simpleSplit(D["intro"], "Body", 10.5, W - 2 * M):
        y -= 16
        c.drawString(M, y, ln)

    # price-list rows with dotted leader
    y -= 34
    for name, value in D["items"]:
        c.setFillColor(K.text)
        c.setFont("BodyMd", 10.5)
        c.drawString(M, y, name)
        c.setFont("BodyBd", 10.5)
        c.drawRightString(W - M, y, value)
        nw = pdfmetrics.stringWidth(name, "BodyMd", 10.5)
        vw = pdfmetrics.stringWidth(value, "BodyBd", 10.5)
        c.setStrokeColor(K.accent)
        c.setDash(0.6, 2.6)
        c.line(M + nw + 6, y + 1.5, W - M - vw - 6, y + 1.5)
        c.setDash()
        y -= 22

    # photo filling the rest of the page (crop to the box; never stretch)
    ph = D["photo"]
    box_w, box_h = W - 2 * M, y - M - 10
    if box_h > 60:
        src = Image.open(ctx.P(ph["file"]))
        s = max(box_w / src.width, box_h / src.height)
        cw, ch = box_w / s, box_h / s
        left = (src.width - cw) * ph.get("focus_x", 0.5)
        top = (src.height - ch) * ph.get("focus_y", 0.5)
        crop = src.crop((round(left), round(top), round(left + cw), round(top + ch)))
        real = crop.width / (box_w / 72)
        if real < ctx.out.dpi and ctx.out.up:
            ctx.warn(f"{ph['file']}: only {real:.0f} dpi at this size (upscaled to {ctx.out.dpi}).")
        c.drawImage(ctx.make_image(crop, box_w, box_h), M, M, box_w, box_h)
    c.showPage()


if __name__ == "__main__":
    run(draw, HERE, font="Body", validate=validate)
