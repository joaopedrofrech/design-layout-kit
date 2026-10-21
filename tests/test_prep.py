"""Tests for the image prep stage (lib/prep.py + prep.py)."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageCms

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import prep  # noqa: E402

FOGRA = os.path.join(ROOT, "assets", "profiles", "FOGRA39L_coated.icc")


def project():
    """Minimal temp project: prep.py + lib/ + empty assets."""
    base = tempfile.mkdtemp(prefix="prep_test_")
    shutil.copy(os.path.join(ROOT, "prep.py"), base)
    shutil.copytree(os.path.join(ROOT, "lib"), os.path.join(base, "lib"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    os.makedirs(os.path.join(base, "assets", "originals"))
    os.makedirs(os.path.join(base, "assets", "images"))
    return base


def write_recipes(base, text):
    with open(os.path.join(base, "prep.yaml"), "w", encoding="utf-8") as f:
        f.write(text)


def run(base, *args):
    return subprocess.run([sys.executable, "prep.py", *args], cwd=base, capture_output=True, text=True)


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


class Operations(unittest.TestCase):
    def test_crop_ratio_and_focus(self):
        im = Image.new("RGB", (400, 200))
        for x in range(400):                       # left half red, right half blue
            for y in range(200):
                im.putpixel((x, y), (255, 0, 0) if x < 200 else (0, 0, 255))
        left = prep.op_crop(im, {"ratio": "1:1", "focus_x": 0})
        right = prep.op_crop(im, {"ratio": "1:1", "focus_x": 1})
        self.assertEqual(left.size, (200, 200))
        self.assertEqual(left.getpixel((100, 100)), (255, 0, 0))
        self.assertEqual(right.getpixel((100, 100)), (0, 0, 255))

    def test_crop_box(self):
        self.assertEqual(prep.op_crop(Image.new("RGB", (100, 100)), {"box": [10, 20, 60, 80]}).size, (50, 60))

    def test_resize_never_upscales_unless_asked(self):
        im = Image.new("RGB", (1000, 500))
        self.assertEqual(prep.op_resize(im, {"max": 400}).size, (400, 200))
        self.assertEqual(prep.op_resize(im, {"max": 4000}).size, (1000, 500))
        self.assertEqual(prep.op_resize(im, {"max": 2000, "upscale": True}).size, (2000, 1000))

    def test_tone_warmth_and_gamma(self):
        im = Image.new("RGB", (4, 4), (100, 100, 100))
        warm = prep.op_tone(im, {"warmth": 1}).getpixel((0, 0))
        self.assertGreater(warm[0], warm[2])
        bright = prep.op_tone(im, {"gamma": 2}).getpixel((0, 0))
        self.assertGreater(bright[1], 100)

    def test_flatten_alpha(self):
        im = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
        out = prep.op_flatten(im, {"color": "#00ff00"})
        self.assertEqual(out.mode, "RGB")
        self.assertEqual(out.getpixel((0, 0)), (0, 255, 0))

    def test_normalize_exif_orientation(self):
        im = Image.new("RGB", (40, 20), "white")
        exif = Image.Exif()
        exif[0x0112] = 6                            # rotate 90
        buf = io.BytesIO()
        im.save(buf, "JPEG", exif=exif)
        buf.seek(0)
        self.assertEqual(prep.normalize(Image.open(buf)).size, (20, 40))

    def test_normalize_cmyk_with_profile_to_rgb(self):
        cmyk = Image.new("CMYK", (8, 8), (0, 0, 0, 0))     # paper white
        icc = open(FOGRA, "rb").read()
        buf = io.BytesIO()
        cmyk.save(buf, "JPEG", icc_profile=icc)
        buf.seek(0)
        out = prep.normalize(Image.open(buf))
        self.assertEqual(out.mode, "RGB")
        self.assertTrue(all(v > 235 for v in out.getpixel((0, 0))))


class Cli(unittest.TestCase):
    def setUp(self):
        self.base = project()
        self.orig = os.path.join(self.base, "assets", "originals", "pic.jpg")
        Image.new("RGB", (800, 600), (200, 120, 60)).save(self.orig, quality=95)

    def test_recipe_runs_and_original_is_untouched(self):
        before = md5(self.orig)
        write_recipes(self.base, 'images:\n  - src: "pic.jpg"\n    out: "pic-sq.jpg"\n    ops:\n'
                                 '      - crop: {ratio: "1:1"}\n      - resize: {max: 300}\n')
        r = run(self.base)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = os.path.join(self.base, "assets", "images", "pic-sq.jpg")
        self.assertEqual(Image.open(out).size, (300, 300))
        self.assertEqual(md5(self.orig), before)

    def test_png_keeps_alpha(self):
        Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(os.path.join(self.base, "assets", "originals", "logo.png"))
        write_recipes(self.base, 'images:\n  - src: "logo.png"\n')
        self.assertEqual(run(self.base).returncode, 0)
        self.assertEqual(Image.open(os.path.join(self.base, "assets", "images", "logo.png")).mode, "RGBA")

    def test_only_runs_one_recipe(self):
        write_recipes(self.base, 'images:\n  - src: "pic.jpg"\n    out: "a.jpg"\n  - src: "pic.jpg"\n    out: "b.jpg"\n')
        self.assertEqual(run(self.base, "--only", "b.jpg").returncode, 0)
        names = os.listdir(os.path.join(self.base, "assets", "images"))
        self.assertEqual(names, ["b.jpg"])

    def test_errors_are_reported(self):
        write_recipes(self.base, 'images:\n  - src: "nope.jpg"\n  - src: "pic.jpg"\n    ops:\n'
                                 '      - blur: {}\n      - crop: {}\n')
        r = run(self.base)
        self.assertNotEqual(r.returncode, 0)
        msg = r.stdout + r.stderr
        for needle in ("nope.jpg", "blur", "crop needs"):
            self.assertIn(needle, msg)

    def test_no_recipes_is_not_an_error(self):
        write_recipes(self.base, "images: []\n")
        self.assertEqual(run(self.base).returncode, 0)

    def test_report_lists_sizes(self):
        write_recipes(self.base, "images: []\n")
        r = run(self.base, "--report")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pic.jpg", r.stdout)
        self.assertIn("800x600px", r.stdout)
        self.assertIn("cm", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
