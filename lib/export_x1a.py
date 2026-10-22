#!/usr/bin/env python3
"""
CMYK PDF -> PDF/X-1a:2001 (Coated FOGRA39).

    python3 lib/export_x1a.py in.pdf out.pdf [--title "Name"] [--author "Client"] [--bleed-mm 3]

Direct method (pikepdf only): the input must be clean (CMYK/Gray only, fonts embedded, no
transparency), which is what the kit builds. Nothing is reprocessed — photos, fonts and text
(with accents) stay byte-identical. It only adds what X-1a requires: OutputIntent FOGRA39 + ICC,
GTS_PDFX keys, Trapped=False, TrimBox/BleedBox, PDF 1.3, /ID.

A PDF that is not clean (RGB, transparency, named color spaces) is refused with the reason:
rebuild it in CMYK with the kit instead of converting it.

Bleed: --bleed-mm only sets Trim/BleedBox; the INPUT page must already include the bleed.
"""
import argparse
import os
import re
import sys
from datetime import datetime

try:
    import pikepdf
except ImportError:
    sys.exit("Missing pikepdf:  pip install -r requirements.txt")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICC = os.path.join(BASE, "assets", "profiles", "FOGRA39L_coated.icc")
MM = 72 / 25.4


def page_bytes(pg):
    c = pg.Contents
    return b"".join(s.read_bytes() for s in c) if isinstance(c, pikepdf.Array) else c.read_bytes()


def analyze(pdf):
    """Things that block the direct method (non-CMYK, transparency, named color spaces)."""
    issues = []
    for n, pg in enumerate(pdf.pages, 1):
        res = pg.Resources
        if re.search(rb"\s(rg|RG)\s", page_bytes(pg)):
            issues.append(f"page {n}: RGB color in content")
        for name, x in (res.get("/XObject") or {}).items():
            if str(x.get("/Subtype")) == "/Image":
                cs = str(x.get("/ColorSpace"))
                if cs not in ("/DeviceCMYK", "/DeviceGray"):
                    issues.append(f"page {n}: image {name} in {cs}")
                if "/SMask" in x:
                    issues.append(f"page {n}: image {name} has transparency (SMask)")
        for name, g in (res.get("/ExtGState") or {}).items():
            if ("/SMask" in g and str(g.SMask) != "/None") or \
               any(k in g and float(g[k]) < 1 for k in ("/ca", "/CA")):
                issues.append(f"page {n}: transparency in {name}")
        for name, cs in (res.get("/ColorSpace") or {}).items():
            issues.append(f"page {n}: color space {name}")
    return issues


def direct(src, dst, title, author, bleed_mm):
    pdf = pikepdf.open(src)
    sg = bleed_mm * MM
    for pg in pdf.pages:
        mb = [float(x) for x in pg.MediaBox]
        pg.TrimBox = pikepdf.Array([mb[0] + sg, mb[1] + sg, mb[2] - sg, mb[3] - sg])
        pg.BleedBox = pikepdf.Array(mb)
    with open(ICC, "rb") as f:
        icc = pikepdf.Stream(pdf, f.read())
    icc.N = 4
    icc.Alternate = pikepdf.Name.DeviceCMYK
    cond = pikepdf.String("Coated FOGRA39 (ISO 12647-2:2004)")
    oi = pikepdf.Dictionary(
        Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFX,
        OutputCondition=cond, Info=cond,
        OutputConditionIdentifier=pikepdf.String("FOGRA39"),
        RegistryName=pikepdf.String("http://www.color.org"),
        DestOutputProfile=pdf.make_indirect(icc))
    pdf.Root.OutputIntents = pikepdf.Array([pdf.make_indirect(oi)])
    di = pdf.docinfo
    di["/GTS_PDFXVersion"] = pikepdf.String("PDF/X-1:2001")
    di["/GTS_PDFXConformance"] = pikepdf.String("PDF/X-1a:2001")
    di["/Trapped"] = pikepdf.Name("/False")          # not Name.False_
    di["/Title"] = pikepdf.String(title)
    di["/Author"] = pikepdf.String(author)
    if "/Subject" not in di:
        di["/Subject"] = pikepdf.String("")
    for k in ("/CreationDate", "/ModDate"):
        if k not in di:
            di[k] = pikepdf.String(datetime.now().strftime("D:%Y%m%d%H%M%S"))
    pdf.save(dst, min_version="1.3", force_version="1.3",
             object_stream_mode=pikepdf.ObjectStreamMode.disable,
             compress_streams=True, deterministic_id=True)
    pdf.close()


def report(dst):
    with pikepdf.open(dst) as p:
        info, oi = p.docinfo, p.Root.OutputIntents[0]
        checks = [
            ("PDF version 1.3", str(p.pdf_version) == "1.3"),
            ("GTS_PDFXVersion = PDF/X-1:2001", str(info.get("/GTS_PDFXVersion")) == "PDF/X-1:2001"),
            ("GTS_PDFXConformance = PDF/X-1a:2001", str(info.get("/GTS_PDFXConformance")) == "PDF/X-1a:2001"),
            ("Trapped = False", str(info.get("/Trapped")) == "/False"),
            ("OutputIntent GTS_PDFX / FOGRA39 with embedded ICC (N=4)",
             str(oi.S) == "/GTS_PDFX" and str(oi.OutputConditionIdentifier) == "FOGRA39"
             and "/DestOutputProfile" in oi and int(oi.DestOutputProfile.N) == 4),
            ("File identifier (/ID) present", "/ID" in p.trailer),
            ("Not encrypted", not p.is_encrypted),
        ]
        fonts_ok = trim_ok = True
        n_fonts = 0
        for pg in p.pages:
            trim_ok &= "/TrimBox" in pg
            for _, f in (pg.Resources.get("/Font") or {}).items():
                n_fonts += 1
                d = f.get("/FontDescriptor")
                if d is None and "/DescendantFonts" in f:
                    d = f.DescendantFonts[0].FontDescriptor
                fonts_ok &= d is not None and any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))
        checks += [("TrimBox on every page", trim_ok), ("All fonts embedded", fonts_ok),
                   ("Vector text present (page not rasterized)", n_fonts > 0)]
        if not fonts_ok:
            print("      · unembedded font (reportlab: Canvas(initialFontName='YourRegisteredFont')).")
        issues = analyze(p)
        checks.append(("CMYK/Gray only, no RGB, no transparency", not issues))
        for i in issues:
            print("      ·", i)
    ok = True
    for name, v in checks:
        print(("  [ok]    " if v else "  [FAIL]  ") + name)
        ok &= v
    print("  Note: own structural check, not a certification. Validate with the printer's preflight "
          "(Acrobat Pro / callas pdfToolbox / PitStop) using the PDF/X-1a profile.")
    return ok


def export(src, dst, title=None, author="", bleed_mm=0.0):
    """Convert a clean CMYK PDF to PDF/X-1a at dst. Prints the report; returns True if every check passed."""
    if not os.path.exists(ICC):
        sys.exit(f"ICC profile not found: {ICC}")
    with pikepdf.open(src) as s:
        title = title or str(s.docinfo.get("/Title", os.path.splitext(os.path.basename(src))[0]))
        issues = analyze(s)
    if issues:
        sys.exit("PDF/X-1a needs a clean CMYK PDF; this one has:\n   - " + "\n   - ".join(issues)
                 + "\nBuild it in CMYK with the kit (--target print) instead of converting it.")
    direct(src, dst, title, author, bleed_mm)
    print("X-1a method: direct (photos, fonts and text preserved byte for byte)")
    print(f"OK  {os.path.basename(dst)}")
    return report(dst)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="CMYK PDF -> PDF/X-1a:2001 (FOGRA39)")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--title")
    ap.add_argument("--author", default="")
    ap.add_argument("--bleed-mm", type=float, default=0.0)
    a = ap.parse_args()
    sys.exit(0 if export(a.src, a.dst, a.title, a.author, a.bleed_mm) else 1)
