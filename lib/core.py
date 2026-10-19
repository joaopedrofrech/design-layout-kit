"""
Shared pipeline for the PDF kits: targets, color, images, naming, X-1a, web optimization.

A project's build.py only registers fonts, validates its own content and defines
draw(c, ctx) — the layout. Everything else lives here:

    from lib.core import run
    run(draw, base_dir=BASE, font="Body", validate=validate)

ctx (passed to draw):
    ctx.D            content (dict from content.yaml)
    ctx.out          current output: mode (cmyk|rgb), dpi, quality, up, down, optimize, suffix, x1a
    ctx.K            colors by name from content "colors" (reportlab colors, already in the output space)
    ctx.white        white in the output space
    ctx.P(*parts)    path relative to the project folder
    ctx.make_image(PIL image, w_pt, h_pt, photo=True) -> temp JPEG path ready for drawImage
    ctx.warn(msg)    collected and printed after each output
    ctx.page_size    (width, height) in points
"""
import argparse
import glob
import os
import sys
import tempfile
from types import SimpleNamespace

from PIL import Image, ImageCms, ImageFilter
from reportlab.lib.colors import CMYKColor, Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

MM = 72 / 25.4


def load_content(path):
    try:
        import yaml
    except ImportError:
        sys.exit("Missing PyYAML:  pip install -r requirements.txt")
    with open(path, encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            sys.exit(f"Invalid YAML (check indentation with spaces, quotes, colons):\n{e}")


def base_errors(D):
    err = [f"missing key: {k}" for k in ("slug", "title") if k not in D]
    if not set(D.get("targets", ["print", "web"])) <= {"print", "web"}:
        err.append("targets must be a list with print and/or web")
    return err


def outputs(target, web):
    """print -> pure CMYK (+ X-1a).  web -> pure sRGB + optimized sRGB."""
    if target == "print":
        return [SimpleNamespace(mode="cmyk", dpi=300, quality=100, up=True, down=False,
                                optimize=False, suffix="cmyk-fogra39-300dpi", x1a=True)]
    wd, wq = int((web or {}).get("dpi", 150)), int((web or {}).get("quality", 80))
    return [SimpleNamespace(mode="rgb", dpi=300, quality=100, up=True, down=False,
                            optimize=False, suffix="rgb-300dpi", x1a=False),
            SimpleNamespace(mode="rgb", dpi=wd, quality=wq, up=False, down=True,
                            optimize=True, suffix=f"rgb-{wd}dpi-web", x1a=False)]


class Ctx:
    def __init__(self, D, base):
        self.D, self.base = D, base
        self.out = None
        self.K = SimpleNamespace()
        self.white = None
        self.warnings = []
        self._n = 0
        self.tmp = tempfile.mkdtemp(prefix="pdfkit_")
        self.page_size = A4
        pg = D.get("page")
        if pg:
            self.page_size = (pg["width_mm"] * MM, pg["height_mm"] * MM)
        icc = os.path.join(base, "assets", "profiles", "FOGRA39L_coated.icc")
        srgb = ImageCms.createProfile("sRGB")
        fogra = ImageCms.getOpenProfile(icc)
        self._flat = ImageCms.buildTransform(srgb, fogra, "RGB", "CMYK",
                                             renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
        self._photo = ImageCms.buildTransform(srgb, fogra, "RGB", "CMYK",
                                              renderingIntent=ImageCms.Intent.PERCEPTUAL)

    def P(self, *a):
        return os.path.join(self.base, *a)

    def warn(self, msg):
        self.warnings.append(msg)

    def color(self, hexstr):
        h = hexstr.lstrip("#")
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if self.out.mode == "rgb":
            return Color(*[v / 255 for v in rgb])
        v = ImageCms.applyTransform(Image.new("RGB", (1, 1), rgb), self._flat).getpixel((0, 0))
        return CMYKColor(*[round(x / 255, 3) for x in v])

    def use(self, out):
        self.out = out
        self.warnings.clear()
        for k, v in (self.D.get("colors") or {}).items():
            setattr(self.K, k, self.color(v))
        self.white = Color(1, 1, 1) if out.mode == "rgb" else CMYKColor(0, 0, 0, 0)

    def make_image(self, im, w_pt, h_pt, photo=True):
        """CMYK/pure: never downsample, upscale only below target dpi. Web: downsample to target dpi."""
        o = self.out
        im = im.convert("RGB")
        mw, mh = round(w_pt / 72 * o.dpi), round(h_pt / 72 * o.dpi)
        if photo:
            if im.width < mw and o.up:
                im = im.resize((mw, mh), Image.LANCZOS)
            elif im.width > mw and o.down:
                im = im.resize((mw, mh), Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=55, threshold=2))
        else:
            im = im.resize((mw, mh), Image.LANCZOS)      # flat art (logos): always exact size
        if o.mode == "cmyk":
            im = ImageCms.applyTransform(im, self._photo if photo else self._flat)
        self._n += 1
        path = os.path.join(self.tmp, f"img_{self._n:03d}.jpg")
        q = o.quality if photo else max(o.quality, 92)
        im.save(path, "JPEG", quality=q, subsampling=0 if q >= 95 else 2,
                optimize=o.optimize, dpi=(o.dpi, o.dpi))
        return path


def optimize_web(path, D):
    """Lossless structure compression + linearization ('fast web view'). Images/fonts untouched."""
    import pikepdf
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        pdf.docinfo["/Title"] = pikepdf.String(D["title"])
        pdf.docinfo["/Author"] = pikepdf.String(D.get("author", ""))
        if D.get("lang"):
            pdf.Root.Lang = pikepdf.String(D["lang"])
        pdf.save(path, linearize=True, compress_streams=True,
                 object_stream_mode=pikepdf.ObjectStreamMode.generate)


def run(draw, base_dir, font, validate=None):
    ap = argparse.ArgumentParser(description="Build PDFs into dist/")
    ap.add_argument("--target", choices=["print", "web"],
                    help="build only this target (default: every target in 'targets' of the content file)")
    ap.add_argument("--content", default=os.path.join(base_dir, "content.yaml"))
    args = ap.parse_args()

    D = load_content(args.content)
    errors = base_errors(D) + (validate(D) if validate else [])
    if errors:
        sys.exit("content.yaml has problems:\n  - " + "\n  - ".join(errors))
    targets = [args.target] if args.target else list(D.get("targets", ["print", "web"]))

    ctx = Ctx(D, base_dir)
    if not D.get("author"):
        print("  • 'author' is empty in content.yaml (PDF metadata): ask who signs the file.")
    dist = os.path.join(base_dir, "dist")
    os.makedirs(dist, exist_ok=True)
    if not args.target:                       # full run: dist/ is cleaned
        for old in glob.glob(os.path.join(dist, "*.pdf")):
            os.remove(old)

    made = []
    todo = [o for t in targets for o in outputs(t, D.get("web"))]
    for out in todo:
        ctx.use(out)
        path = os.path.join(dist, f"{D['slug']}-{out.suffix}.pdf")
        for old in (path, path[:-4] + "-pdfx1a.pdf"):     # replace only what is rebuilt
            if os.path.exists(old):
                os.remove(old)
        c = canvas.Canvas(path, pagesize=ctx.page_size, initialFontName=font, initialFontSize=10,
                          enforceColorSpace=out.mode)   # errors if a wrong color space slips in
        c.setTitle(D["title"])
        c.setAuthor(D.get("author", ""))
        c.setSubject(D.get("client", ""))
        draw(c, ctx)
        c.save()
        if out.optimize:
            optimize_web(path, D)
        made.append(path)
        print(f"OK  {os.path.basename(path)}")
        for w in ctx.warnings:
            print("  •", w)
        if out.x1a and D.get("x1a", True):
            sys.path.insert(0, base_dir)
            from lib.export_x1a import export
            x1a = path[:-4] + "-pdfx1a.pdf"
            ok = export(path, x1a, D["title"], D.get("author", ""), D.get("bleed_mm", 0))
            made.append(x1a)
            if not ok:
                sys.exit("PDF/X-1a check failed — see report above.")

    print("\nFiles in dist/:")
    for p in made:
        print(f"  {os.path.getsize(p) / 1e6:6.2f} MB   {os.path.basename(p)}")
