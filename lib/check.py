#!/usr/bin/env python3
"""
Structural checks for a generated PDF.

    python3 lib/check.py dist/v1/*.pdf [--mode cmyk|rgb] [--min-dpi 299] [--max-dpi 151]

Checks: pages, encryption, fonts embedded, vector text present (page not rasterized),
Unicode map on every font (accents stay extractable), color (cmyk: no RGB operators or
RGB/transparent images), effective image dpi (needs `pdfimages` from poppler; skipped if absent).
Own structural checks, not a certification.
"""
import argparse
import re
import shutil
import subprocess
import sys

try:
    import pikepdf
except ImportError:
    sys.exit("Missing pikepdf:  pip install -r requirements.txt")


def _fonts(pdf):
    seen = {}
    for pg in pdf.pages:
        for name, f in (pg.Resources.get("/Font") or {}).items():
            d = f.get("/FontDescriptor")
            if d is None and "/DescendantFonts" in f:
                d = f.DescendantFonts[0].FontDescriptor
            embedded = d is not None and any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))
            seen[(str(name), f.objgen)] = (embedded, "/ToUnicode" in f)
    return list(seen.values())


def _page_bytes(pg):
    c = pg.Contents
    return b"".join(s.read_bytes() for s in c) if isinstance(c, pikepdf.Array) else c.read_bytes()


def _color_issues(pdf):
    issues = []
    for n, pg in enumerate(pdf.pages, 1):
        res = pg.Resources
        if re.search(rb"\s(rg|RG)\s", _page_bytes(pg)):
            issues.append(f"page {n}: RGB color in content")
        for name, x in (res.get("/XObject") or {}).items():
            if str(x.get("/Subtype")) == "/Image":
                if str(x.get("/ColorSpace")) not in ("/DeviceCMYK", "/DeviceGray"):
                    issues.append(f"page {n}: image {name} is not DeviceCMYK/Gray")
                if "/SMask" in x:
                    issues.append(f"page {n}: image {name} has transparency (SMask)")
        for name, g in (res.get("/ExtGState") or {}).items():
            if ("/SMask" in g and str(g.SMask) != "/None") or \
               any(k in g and float(g[k]) < 1 for k in ("/ca", "/CA")):
                issues.append(f"page {n}: transparency in {name}")
    return issues


def image_ppi(path):
    """Effective ppi of every placed image (needs poppler's pdfimages); None if unavailable."""
    if not shutil.which("pdfimages"):
        return None
    out = subprocess.run(["pdfimages", "-list", path], capture_output=True, text=True).stdout
    ppis = []
    for line in out.splitlines()[2:]:
        f = line.split()
        if len(f) > 13 and f[2] == "image":
            ppis.append(min(int(f[12]), int(f[13])))
    return ppis


def check(path, mode=None, min_dpi=None, max_dpi=None):
    """Return [(name, 'ok'|'FAIL'|'skip', detail)]."""
    r = []
    with pikepdf.open(path) as pdf:
        r.append(("Has pages", "ok" if len(pdf.pages) else "FAIL", ""))
        r.append(("Not encrypted", "ok" if not pdf.is_encrypted else "FAIL", ""))
        fonts = _fonts(pdf)
        r.append(("Vector text present (page not rasterized)", "ok" if fonts else "FAIL",
                  "" if fonts else "no fonts found: text was flattened into an image"))
        r.append(("All fonts embedded", "ok" if all(e for e, _ in fonts) else "FAIL", ""))
        r.append(("Unicode map on every font (accents extractable)",
                  "ok" if all(u for _, u in fonts) else "FAIL", ""))
        if mode == "cmyk":
            issues = _color_issues(pdf)
            r.append(("CMYK/Gray only, no RGB, no transparency", "ok" if not issues else "FAIL",
                      "; ".join(issues[:3])))
    if min_dpi or max_dpi:
        ppis = image_ppi(path)
        if ppis is None:
            r.append(("Image dpi", "skip", "pdfimages (poppler) not installed"))
        elif ppis:
            lo, hi = min(ppis), max(ppis)
            if min_dpi:
                r.append((f"Images >= {min_dpi} dpi", "ok" if lo >= min_dpi else "FAIL", f"lowest {lo}"))
            if max_dpi:
                r.append((f"Images <= {max_dpi} dpi", "ok" if hi <= max_dpi else "FAIL", f"highest {hi}"))
    return r


def failed(results):
    return any(s == "FAIL" for _, s, _ in results)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--mode", choices=["cmyk", "rgb"])
    ap.add_argument("--min-dpi", type=int)
    ap.add_argument("--max-dpi", type=int)
    a = ap.parse_args()
    bad = False
    for f in a.pdf:
        print(f)
        res = check(f, a.mode, a.min_dpi, a.max_dpi)
        for name, status, detail in res:
            print(f"  [{status:<4}] {name} {detail}".rstrip())
        bad |= failed(res)
    sys.exit(1 if bad else 0)
