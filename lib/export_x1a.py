#!/usr/bin/env python3
"""
CMYK PDF -> PDF/X-1a:2001 (Coated FOGRA39).

    python3 lib/export_x1a.py in.pdf out.pdf [--title "Name"] [--author "Client"] [--bleed-mm 3] [--force-gs]

DEFAULT ("direct", pikepdf only): when the input is clean (CMYK/Gray only, fonts embedded,
no transparency) nothing is reprocessed — photos, fonts and text (with accents) stay
byte-identical. It only adds what X-1a requires: OutputIntent FOGRA39 + ICC, GTS_PDFX keys,
Trapped=False, TrimBox/BleedBox, PDF 1.3, /ID.

FALLBACK (Ghostscript): only for third-party PDFs with RGB/transparency (or --force-gs).
It rewrites fonts and images (recompresses JPEGs, loses the Unicode map of accents).
Keep the original as the editable version.

Bleed: --bleed-mm only sets Trim/BleedBox; the INPUT page must already include the bleed.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


def _ps_escape(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _gs_def(title):
    return f"""%!
[ /GTS_PDFXVersion (PDF/X-1:2001) /GTS_PDFXConformance (PDF/X-1a:2001)
  /Title ({_ps_escape(title)}) /Trapped /False /DOCINFO pdfmark
/ICCProfile (profile.icc) def
[/_objdef {{icc_PDFX}} /type /stream /OBJ pdfmark
[{{icc_PDFX}} << /N 4 >> /PUT pdfmark
[{{icc_PDFX}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFX}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFX}} << /Type /OutputIntent /S /GTS_PDFX
  /OutputCondition (Coated FOGRA39 (ISO 12647-2:2004))
  /Info (Coated FOGRA39 (ISO 12647-2:2004))
  /OutputConditionIdentifier (FOGRA39) /RegistryName (http://www.color.org)
  /DestOutputProfile {{icc_PDFX}} >> /PUT pdfmark
[{{Catalog}} <</OutputIntents [ {{OutputIntent_PDFX}} ]>> /PUT pdfmark
"""


def ghostscript(src, dst, title, author, bleed_mm):
    gs = shutil.which("gs") or shutil.which("gswin64c")
    if not gs:
        sys.exit("This PDF needs the Ghostscript method (RGB/transparency) but gs was not found.")
    tmp = tempfile.mkdtemp(prefix="x1a_")
    try:
        shutil.copy(ICC, os.path.join(tmp, "profile.icc"))
        defps = os.path.join(tmp, "x1a_def.ps")      # never name it PDFX_def.ps (gs loads its own sample)
        with open(defps, "w", encoding="latin-1", errors="replace") as f:
            f.write(_gs_def(title))
        raw = os.path.join(tmp, "raw.pdf")
        cmd = [gs, "-q", "-dBATCH", "-dNOPAUSE", "-dNOSAFER", "-sDEVICE=pdfwrite",
               "-dCompatibilityLevel=1.3", "-sColorConversionStrategy=CMYK",
               "-sProcessColorModel=DeviceCMYK", "-dEmbedAllFonts=true", "-dSubsetFonts=true",
               "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false",
               "-dDownsampleMonoImages=false", f"-sOutputFile={raw}", defps, os.path.abspath(src)]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp)
        if r.returncode != 0 or not os.path.exists(raw):
            sys.exit("Ghostscript failed:\n" + (r.stdout + r.stderr)[-1500:])
        pdf = pikepdf.open(raw)
        sg = bleed_mm * MM
        for pg in pdf.pages:
            mb = [float(x) for x in pg.MediaBox]
            pg.TrimBox = pikepdf.Array([mb[0] + sg, mb[1] + sg, mb[2] - sg, mb[3] - sg])
            pg.BleedBox = pikepdf.Array(mb)
        pdf.docinfo["/Title"] = pikepdf.String(title)
        pdf.docinfo["/Author"] = pikepdf.String(author)
        pdf.save(dst, min_version="1.3", force_version="1.3")
        pdf.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
        for pg in p.pages:
            trim_ok &= "/TrimBox" in pg
            for _, f in (pg.Resources.get("/Font") or {}).items():
                d = f.get("/FontDescriptor")
                if d is None and "/DescendantFonts" in f:
                    d = f.DescendantFonts[0].FontDescriptor
                fonts_ok &= d is not None and any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))
        checks += [("TrimBox on every page", trim_ok), ("All fonts embedded", fonts_ok)]
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


def export(src, dst, title=None, author="", bleed_mm=0.0, force_gs=False):
    """Convert src to PDF/X-1a at dst. Prints the report; returns True if every check passed."""
    if not os.path.exists(ICC):
        sys.exit(f"ICC profile not found: {ICC}")
    with pikepdf.open(src) as s:
        title = title or str(s.docinfo.get("/Title", os.path.splitext(os.path.basename(src))[0]))
        issues = analyze(s)
    if issues or force_gs:
        print("Method: Ghostscript fallback (X-1a-blocking items):", *issues, sep="\n   - ")
        print("   WARNING: Ghostscript recompresses photos and may lose accents' Unicode map. "
              "Keep the original as the editable version.")
        ghostscript(src, dst, title, author, bleed_mm)
    else:
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
    ap.add_argument("--force-gs", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if export(a.src, a.dst, a.title, a.author, a.bleed_mm, a.force_gs) else 1)
