"""
Image prep: assets/originals/  --(prep.yaml recipes)-->  assets/images/

Optional and minimal: nothing is edited unless a recipe asks for it. Originals are never modified.
Each recipe in prep.yaml names a source file and, only if needed, a list of operations; the result is
written to assets/images/ and is what the layout uses. A recipe without `ops` just normalizes the file
(orientation + sRGB). A file that needs nothing can simply be placed in assets/images/ directly.

    python3 prep.py                 # run every recipe
    python3 prep.py --only dish.jpg # run only recipes whose output name matches
    python3 prep.py --report        # size / profile / max print size of every image

Operations (applied in order, after the implicit `normalize`):
    crop:    {ratio: "4:3", focus_x: 0.5, focus_y: 0.5}   or   {box: [left, top, right, bottom]} in pixels
    resize:  {max: 3000}  longest side in px   or   {width: px}   (never upscales unless upscale: true)
    tone:    {brightness: 1, contrast: 1, saturation: 1, gamma: 1, warmth: 0 (-1..1), auto: false}
    denoise: {size: 3}                                          (median filter, odd size)
    sharpen: {radius: 1.4, percent: 55, threshold: 2}           (the build sharpens photos again: use sparingly)
    flatten: {color: "#ffffff"}                                 (alpha -> solid color)

`normalize` (always first): EXIF orientation, embedded ICC profile -> sRGB, CMYK -> RGB.
Output: .jpg (quality 100, 4:4:4; alpha is flattened on white) or .png (keeps alpha).
AI steps (background removal, real upscaling, generation) run outside this script: see AGENTS.md.
"""
import argparse
import io
import os
import sys

from PIL import Image, ImageCms, ImageEnhance, ImageFilter, ImageOps

OPS = {"crop", "resize", "tone", "denoise", "sharpen", "flatten"}
EXTS = (".jpg", ".jpeg", ".png")


# ------------------------------------------------------------ operations
def normalize(im):
    """EXIF orientation, embedded ICC -> sRGB, any mode -> RGB/RGBA."""
    im = ImageOps.exif_transpose(im)
    icc = im.info.get("icc_profile")
    if im.mode in ("P", "PA", "LA", "L", "1", "I;16"):
        im = im.convert("RGBA" if (im.mode in ("PA", "LA") or "transparency" in im.info) else "RGB")
    if icc and im.mode in ("RGB", "RGBA", "CMYK"):
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            out = "RGBA" if im.mode == "RGBA" else "RGB"
            return ImageCms.profileToProfile(im, src, ImageCms.createProfile("sRGB"), outputMode=out,
                                             renderingIntent=ImageCms.Intent.PERCEPTUAL)
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    return im if im.mode in ("RGB", "RGBA") else im.convert("RGB")


def op_crop(im, a):
    if "box" in a:
        l, t, r, b = (int(v) for v in a["box"])
        return im.crop((l, t, r, b))
    rw, rh = (float(v) for v in str(a["ratio"]).split(":"))
    target = rw / rh
    w, h = im.size
    if w / h > target:                      # too wide: cut the sides
        nw, nh = round(h * target), h
    else:                                   # too tall: cut top/bottom
        nw, nh = w, round(w / target)
    left = round((w - nw) * a.get("focus_x", 0.5))
    top = round((h - nh) * a.get("focus_y", 0.5))
    return im.crop((left, top, left + nw, top + nh))


def op_resize(im, a):
    w, h = im.size
    if "max" in a:
        s = a["max"] / max(w, h)
    else:
        s = a["width"] / w
    if s > 1 and not a.get("upscale"):
        return im
    return im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)


def op_tone(im, a):
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB")
    if a.get("auto"):
        rgb = ImageOps.autocontrast(rgb, cutoff=0.5)
    g = a.get("gamma", 1)
    if g != 1:
        lut = [round(255 * ((i / 255) ** (1 / g))) for i in range(256)]
        rgb = rgb.point(lut * 3)
    for key, cls in (("brightness", ImageEnhance.Brightness), ("contrast", ImageEnhance.Contrast),
                     ("saturation", ImageEnhance.Color)):
        if a.get(key, 1) != 1:
            rgb = cls(rgb).enhance(a[key])
    wm = a.get("warmth", 0)
    if wm:
        r, gg, b = rgb.split()
        r = r.point(lambda v: min(255, round(v * (1 + 0.12 * wm))))
        b = b.point(lambda v: min(255, round(v * (1 - 0.12 * wm))))
        rgb = Image.merge("RGB", (r, gg, b))
    if alpha is not None:
        rgb.putalpha(alpha)
    return rgb


def op_denoise(im, a):
    return im.filter(ImageFilter.MedianFilter(size=int(a.get("size", 3))))


def op_sharpen(im, a):
    return im.filter(ImageFilter.UnsharpMask(radius=a.get("radius", 1.4), percent=a.get("percent", 55),
                                             threshold=a.get("threshold", 2)))


def op_flatten(im, a):
    h = str(a.get("color", "#ffffff")).lstrip("#")
    bg = Image.new("RGB", im.size, tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
    if im.mode == "RGBA":
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


FUNCS = {"crop": op_crop, "resize": op_resize, "tone": op_tone, "denoise": op_denoise,
         "sharpen": op_sharpen, "flatten": op_flatten}


# ------------------------------------------------------------ recipes
def load_recipes(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            sys.exit(f"Invalid YAML in {path}:\n{e}")
    return data.get("images") or []


def recipe_errors(recipes, originals):
    err = []
    for i, r in enumerate(recipes):
        w = f"images[{i}]"
        if "src" not in r:
            err.append(f"{w}: missing `src`")
            continue
        if not os.path.exists(os.path.join(originals, r["src"])):
            err.append(f"{w}: original not found: assets/originals/{r['src']}")
        out = r.get("out", r["src"])
        if not out.lower().endswith(EXTS):
            err.append(f"{w}: `out` must end in .jpg or .png")
        for j, op in enumerate(r.get("ops") or []):
            if not isinstance(op, dict) or len(op) != 1 or next(iter(op)) not in OPS:
                got = list(op) if isinstance(op, dict) else op
                err.append(f"{w}.ops[{j}]: got {got}, expected exactly one of {sorted(OPS)}")
            elif next(iter(op)) == "crop":
                a = op["crop"] or {}
                if "ratio" not in a and "box" not in a:
                    err.append(f"{w}.ops[{j}]: crop needs `ratio` or `box`")
    return err


def run_recipe(r, originals, images):
    src = os.path.join(originals, r["src"])
    out = os.path.join(images, r.get("out", r["src"]))
    with Image.open(src) as f:
        im = normalize(f)
        im.load()
    for op in r.get("ops") or []:
        (name, args), = op.items()
        im = FUNCS[name](im, args or {})
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if out.lower().endswith(".png"):
        im.save(out, "PNG", optimize=True)
    else:
        if im.mode == "RGBA":                       # JPEG has no alpha: flatten on white instead of dropping it
            im = op_flatten(im, {})
        im.save(out, "JPEG", quality=100, subsampling=0)
    return out, im.size


# ------------------------------------------------------------ report
def report(folder, label):
    rows = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.lower().endswith(EXTS):
            continue
        with Image.open(os.path.join(folder, name)) as im:
            w, h = im.size
            prof = "ICC" if im.info.get("icc_profile") else "no profile"
            alpha = "alpha" if im.mode in ("RGBA", "LA", "PA") else ""
            cm = lambda px: px / 300 * 2.54
            rows.append(f"  {name:36} {w}x{h}px  {w * h / 1e6:5.1f} MP  "
                        f"{im.mode:5} {prof:10} {alpha:5} max at 300 dpi: {cm(w):.1f} x {cm(h):.1f} cm")
    print(f"{label}:" + ("" if rows else " (empty)"))
    print("\n".join(rows))


def main(base):
    ap = argparse.ArgumentParser(description="Prepare images: assets/originals -> assets/images")
    ap.add_argument("--recipes", default=os.path.join(base, "prep.yaml"))
    ap.add_argument("--only", help="run only recipes whose output file name equals this")
    ap.add_argument("--report", action="store_true", help="list every image with size, profile and max print size")
    args = ap.parse_args()
    originals = os.path.join(base, "assets", "originals")
    images = os.path.join(base, "assets", "images")
    if args.report:
        report(originals, "assets/originals")
        report(images, "assets/images")
        return
    recipes = load_recipes(args.recipes) if os.path.exists(args.recipes) else []
    errors = recipe_errors(recipes, originals)
    if errors:
        sys.exit("prep.yaml has problems:\n  - " + "\n  - ".join(errors))
    todo = [r for r in recipes if not args.only or r.get("out", r["src"]) == args.only]
    if not todo:
        print("Nothing to do (no recipes in prep.yaml)." if not args.only else f"No recipe outputs {args.only}.")
        return
    for r in todo:
        out, size = run_recipe(r, originals, images)
        print(f"OK  {os.path.relpath(out, base)}  {size[0]}x{size[1]}px")
