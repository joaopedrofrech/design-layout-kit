"""
Shared pipeline for the PDF kits: targets, color, images, naming, X-1a, web optimization.

A project's build.py only registers fonts, validates its own content and defines
draw(c, ctx) — the layout. Everything else lives here:

    from lib.core import run
    run(draw, base_dir=BASE, font="Body", validate=validate)

ctx (passed to draw):
    ctx.D            content (the design's content.yaml merged over ../../brand.yaml)
    ctx.out          current output: mode (cmyk|rgb), dpi, quality, up, down, optimize, suffix, x1a
    ctx.K            colors by name from content "colors" (reportlab colors, already in the output space)
    ctx.white        white in the output space
    ctx.P(*parts)    path relative to the design folder, falling back to the kit root (shared assets)
    ctx.make_image(PIL image, w_pt, h_pt, photo=True) -> temp JPEG path ready for drawImage
    ctx.warn(msg)    collected and printed after each output
    ctx.page_size    (width, height) of the TRIM size in points (draw as if there were no bleed)
                     `page` in content.yaml: {width_mm,height_mm}, a preset (a4, a5-landscape, letter), "210x297mm" or "1080x1350px"
    ctx.bleed        bleed in points (0 by default); with bleed_mm > 0 the PDF page is larger and the origin
                     is already shifted, so extend full-page backgrounds by ctx.bleed on every side
    ctx.version      project version (content.yaml `version`), outputs go to dist/v<version>/
"""
import argparse
import glob
import os
import re
import sys
import tempfile
from types import SimpleNamespace

from PIL import Image, ImageCms, ImageFilter
from reportlab.lib.colors import CMYKColor, Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

MM = 72 / 25.4


def kit_root(here):
    """Folder that holds lib/core.py: `here` itself, or the nearest parent (a design in designs/<name>/)."""
    p = os.path.abspath(here)
    while not os.path.exists(os.path.join(p, "lib", "core.py")):
        if p == os.path.dirname(p):
            sys.exit("lib/core.py not found in any parent folder.")
        p = os.path.dirname(p)
    return p


def resolver(here, kit):
    """P(*parts): path inside the design folder if it exists there, else inside the kit root (shared assets)."""
    def P(*parts):
        own = os.path.join(here, *parts)
        if os.path.exists(own):
            return own
        shared = os.path.join(kit, *parts)
        return shared if os.path.exists(shared) else own
    return P


def load_content(path, kit=None):
    """Reads the YAML. If brand.yaml exists in the kit root it is merged underneath (the design's keys win;
    `colors` and `web` are merged key by key)."""
    try:
        import yaml
    except ImportError:
        sys.exit("Missing PyYAML:  pip install -r requirements.txt")

    def read(p):
        with open(p, encoding="utf-8") as f:
            try:
                return yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                sys.exit(f"Invalid YAML in {p} (check indentation with spaces, quotes, colons):\n{e}")

    D = read(path)
    brand = os.path.join(kit, "brand.yaml") if kit else None
    if brand and os.path.exists(brand) and os.path.abspath(path) != os.path.abspath(brand):
        merged = read(brand)
        for k, v in D.items():
            if k in ("colors", "web") and isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return merged
    return D


PAGE_PRESETS_MM = {"a3": (297, 420), "a4": (210, 297), "a5": (148, 210), "a6": (105, 148),
                   "letter": (215.9, 279.4), "legal": (215.9, 355.6)}


def parse_page(pg):
    """`page` -> (width_pt, height_pt, in_pixels).
    Accepts {width_mm, height_mm}, a preset ("a4", "a5-landscape", "letter"), "210x297mm" or "1080x1350px"
    (a pixel page is 1 px = 1 pt, so it renders 1:1 at 72 dpi)."""
    if pg is None:
        return A4[0], A4[1], False
    if isinstance(pg, dict):
        return pg["width_mm"] * MM, pg["height_mm"] * MM, False
    s = str(pg).strip().lower()
    m = re.fullmatch(r"([\d.]+)\s*x\s*([\d.]+)\s*(mm|px)", s)
    if m:
        w, h = float(m.group(1)), float(m.group(2))
        return (w * MM, h * MM, False) if m.group(3) == "mm" else (w, h, True)
    name, land = (s[:-10], True) if s.endswith("-landscape") else (s, False)
    if name in PAGE_PRESETS_MM:
        w, h = PAGE_PRESETS_MM[name]
        return ((h, w) if land else (w, h))[0] * MM, ((h, w) if land else (w, h))[1] * MM, False
    raise ValueError(f"page: unknown value {pg!r} (use {sorted(PAGE_PRESETS_MM)}, optional -landscape, "
                     f"\"210x297mm\", \"1080x1350px\" or {{width_mm, height_mm}})")


def base_errors(D):
    err = [f"missing key: {k}" for k in ("slug", "title") if k not in D]
    if not set(D.get("targets", ["print", "web"])) <= {"print", "web", "image"}:
        err.append("targets must be a list with print, web and/or image")
    try:
        parse_page(D.get("page"))
    except (ValueError, KeyError, TypeError) as e:
        err.append(str(e) if isinstance(e, ValueError) else "page: expected {width_mm, height_mm}")
    im = D.get("image") or {}
    if not set(im.get("formats", ["png"])) <= {"png", "jpg"}:
        err.append("image.formats must be a list with png and/or jpg")
    return err


def outputs(target, D, ctx):
    """print -> pure CMYK (+ X-1a).  web -> pure sRGB + optimized sRGB.  image -> PNG/JPG of every page."""
    if target == "print":
        return [SimpleNamespace(mode="cmyk", dpi=300, quality=100, up=True, down=False,
                                optimize=False, suffix="cmyk-fogra39-300dpi", x1a=True, image=False)]
    if target == "image":
        return [SimpleNamespace(mode="rgb", dpi=ctx.image_dpi, quality=100, up=False, down=True,
                                optimize=False, suffix=None, x1a=False, image=True)]
    web = D.get("web")
    wd, wq = int((web or {}).get("dpi", 150)), int((web or {}).get("quality", 80))
    return [SimpleNamespace(mode="rgb", dpi=300, quality=100, up=True, down=False,
                            optimize=False, suffix="rgb-300dpi", x1a=False, image=False),
            SimpleNamespace(mode="rgb", dpi=wd, quality=wq, up=False, down=True,
                            optimize=True, suffix=f"rgb-{wd}dpi-web", x1a=False, image=False)]


class Ctx:
    def __init__(self, D, base, kit=None):
        self.kit = kit or base
        self.D, self.base = D, base
        self.P = resolver(base, self.kit)
        self.out = None
        self.K = SimpleNamespace()
        self.white = None
        self.warnings = []
        self._n = 0
        self.tmp = tempfile.mkdtemp(prefix="pdfkit_")
        w, h, self.page_in_px = parse_page(D.get("page"))
        self.page_size = (w, h)
        self.bleed_cfg = float(D.get("bleed_mm", 0)) * MM
        self.bleed, self.full_size = self.bleed_cfg, self.page_size
        self._set_bleed(self.bleed_cfg)
        im = D.get("image") or {}
        self.image_formats = list(im.get("formats", ["png"]))
        self.image_quality = int(im.get("quality", 92))
        self.image_transparent = bool(im.get("transparent", False))
        if im.get("width_px"):
            self.image_width_px = int(im["width_px"])
        elif not im.get("dpi") and self.page_in_px:
            self.image_width_px = round(w)
        else:
            self.image_width_px = None
        self.image_dpi = (self.image_width_px / (w / 72)) if self.image_width_px else float(im.get("dpi", 150))
        self.version = int(D.get("version", 1))
        icc = os.path.join(self.kit, "assets", "profiles", "FOGRA39L_coated.icc")
        srgb = ImageCms.createProfile("sRGB")
        fogra = ImageCms.getOpenProfile(icc)
        self._flat = ImageCms.buildTransform(srgb, fogra, "RGB", "CMYK",
                                             renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
        self._photo = ImageCms.buildTransform(srgb, fogra, "RGB", "CMYK",
                                              renderingIntent=ImageCms.Intent.PERCEPTUAL)

    def _set_bleed(self, b):
        self.bleed = b
        self.full_size = (self.page_size[0] + 2 * b, self.page_size[1] + 2 * b)

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
        self._set_bleed(0.0 if out.image else self.bleed_cfg)     # images are the trim area only
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
            im = im.resize((mw, mh), Image.LANCZOS)      # flat design (logos): always exact size
        if o.mode == "cmyk":
            im = ImageCms.applyTransform(im, self._photo if photo else self._flat)
        self._n += 1
        path = os.path.join(self.tmp, f"img_{self._n:03d}.jpg")
        q = o.quality if photo else max(o.quality, 92)
        im.save(path, "JPEG", quality=q, subsampling=0 if q >= 95 else 2,
                optimize=o.optimize, dpi=(o.dpi, o.dpi))
        return path


class BleedCanvas(canvas.Canvas):
    """Canvas whose origin sits at the trim corner: the page is larger by `bleed` on every side."""

    def __init__(self, *a, bleed=0.0, **k):
        super().__init__(*a, **k)
        self._shift = f"1 0 0 1 {bleed:.4f} {bleed:.4f} cm"
        self._code.append(self._shift)

    def showPage(self):
        super().showPage()
        self._code.append(self._shift)

    def save(self):
        if self._code == [self._shift]:      # no content after the last showPage: avoid a blank page
            self._code = []
        super().save()


def bump_version(content_path):
    """Increase `version:` in the content file (inserting it after `slug:` if missing)."""
    with open(content_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"(?m)^version:\s*(\d+)", text)
    if m:
        new = int(m.group(1)) + 1
        text = text[:m.start()] + f"version: {new}" + text[m.end():]
    else:
        new = 2
        text = re.sub(r"(?m)^(slug:[^\n]*\n)", r"\1version: 2\n", text, count=1)
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(text)
    return new


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


def rasterize(pdf_path, dist, base_name, ctx):
    """PDF pages -> PNG/JPG files in dist. Returns the list of written paths."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        sys.exit("Missing pypdfium2:  pip install -r requirements.txt")
    pdf = pdfium.PdfDocument(pdf_path)
    n, written = len(pdf), []
    fill = (0, 0, 0, 0) if ctx.image_transparent else (255, 255, 255, 255)
    for i in range(n):
        page = pdf[i]
        im = page.render(scale=ctx.image_dpi / 72, fill_color=fill).to_pil()
        if ctx.image_width_px:                              # exact width; height from the page ratio
            pw, ph = page.get_size()
            target = (ctx.image_width_px, round(ctx.image_width_px * ph / pw))
            if im.size != target:
                im = im.resize(target, Image.LANCZOS)
        name = f"{base_name}-{im.width}x{im.height}px" + (f"-p{i + 1}" if n > 1 else "")
        for fmt in ctx.image_formats:
            path = os.path.join(dist, f"{name}.{fmt}")
            if fmt == "png":
                (im if ctx.image_transparent else im.convert("RGB")).save(path, "PNG", optimize=True)
            else:
                flat = im
                if im.mode == "RGBA":
                    flat = Image.new("RGB", im.size, (255, 255, 255))
                    flat.paste(im, mask=im.getchannel("A"))
                flat.convert("RGB").save(path, "JPEG", quality=ctx.image_quality, subsampling=0,
                                         dpi=(round(ctx.image_dpi), round(ctx.image_dpi)))
            written.append(path)
    pdf.close()
    return written


def run(draw, base_dir, font, validate=None):
    ap = argparse.ArgumentParser(description="Build PDFs into dist/")
    ap.add_argument("--target", choices=["print", "web", "image"],
                    help="build only this target (default: every target in 'targets' of the content file)")
    ap.add_argument("--content", default=os.path.join(base_dir, "content.yaml"),
                    help="content file (default content.yaml); another file = a variation with the same layout")
    ap.add_argument("--bump", action="store_true",
                    help="increase `version` in the content file first (new dist/v<N>/ folder)")
    args = ap.parse_args()
    kit = kit_root(base_dir)

    if args.bump:
        print(f"Version bumped to v{bump_version(args.content)}")
    D = load_content(args.content, kit)
    errors = base_errors(D) + (validate(D) if validate else [])
    if errors:
        sys.exit("content.yaml has problems:\n  - " + "\n  - ".join(errors))
    targets = [args.target] if args.target else list(D.get("targets", ["print", "web"]))

    ctx = Ctx(D, base_dir, kit)
    if not D.get("author"):
        print("  • 'author' is empty (brand.yaml or content.yaml): ask who signs the file.")
    dist = os.path.join(base_dir, "dist", f"v{ctx.version}")
    os.makedirs(dist, exist_ok=True)
    stem = f"{glob.escape(D['slug'])}-v{ctx.version}-"
    img_files = lambda: [f for ext in ("png", "jpg") for f in glob.glob(os.path.join(dist, f"{stem}rgb-*px*.{ext}"))]
    if not args.target:                       # full run: only this slug's files of this version are cleaned
        for old in glob.glob(os.path.join(dist, f"{stem}*.pdf")) + img_files():
            os.remove(old)
    elif args.target == "image":
        for old in img_files():
            os.remove(old)

    made = []
    todo = [o for t in targets for o in outputs(t, D, ctx)]
    for out in todo:
        ctx.use(out)
        path = (os.path.join(ctx.tmp, "image-source.pdf") if out.image
                else os.path.join(dist, f"{D['slug']}-v{ctx.version}-{out.suffix}.pdf"))
        for old in (path, path[:-4] + "-pdfx1a.pdf"):     # replace only what is rebuilt
            if os.path.exists(old):
                os.remove(old)
        kw = dict(pagesize=ctx.full_size, initialFontName=font, initialFontSize=10,
                  enforceColorSpace=out.mode)           # errors if a wrong color space slips in
        c = BleedCanvas(path, bleed=ctx.bleed, **kw) if ctx.bleed else canvas.Canvas(path, **kw)
        c.setTitle(D["title"])
        c.setAuthor(D.get("author", ""))
        c.setSubject(D.get("client", ""))
        draw(c, ctx)
        c.save()
        if out.optimize:
            optimize_web(path, D)
        if not out.image:
            made.append(path)
            print(f"OK  {os.path.basename(path)}")
        for w in ctx.warnings:
            print("  •", w)
        sys.path.insert(0, kit)
        from lib.check import check, failed
        results = check(path, out.mode, min_dpi=299 if out.up else None,
                        max_dpi=out.dpi + 1 if out.down else None)
        for name, status, detail in results:
            if status == "FAIL":
                print(f"  [FAIL]  {name} {detail}")
        if failed(results):
            sys.exit("Output check failed — see above.")
        if out.image:
            for img in rasterize(path, dist, f"{D['slug']}-v{ctx.version}-rgb", ctx):
                made.append(img)
                print(f"OK  {os.path.basename(img)}")
        if out.x1a and D.get("x1a", True):
            sys.path.insert(0, kit)
            from lib.export_x1a import export
            x1a = path[:-4] + "-pdfx1a.pdf"
            ok = export(path, x1a, D["title"], D.get("author", ""), D.get("bleed_mm", 0))
            made.append(x1a)
            if not ok:
                sys.exit("PDF/X-1a check failed — see report above.")

    print(f"\nFiles in dist/v{ctx.version}/:")
    for p in made:
        print(f"  {os.path.getsize(p) / 1e6:6.2f} MB   {os.path.basename(p)}")
