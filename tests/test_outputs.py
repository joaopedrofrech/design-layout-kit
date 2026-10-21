"""Tests: page presets, the image target (PNG/JPG), build_all."""
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

from PIL import Image
from reportlab.pdfgen import canvas

from tests.test_pipeline import ROOT, build, copy_project, edit, pdfs  # noqa: F401

sys.path.insert(0, ROOT)
from lib.core import MM, base_errors, parse_page, rasterize  # noqa: E402


def dist(proj, design="main", version=1):
    return os.path.join(proj, "designs", design, "dist", f"v{version}")


def names(proj, design="main"):
    d = dist(proj, design)
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


class PagePresets(unittest.TestCase):
    def test_presets_and_units(self):
        w, h, px = parse_page("a4")
        self.assertAlmostEqual(w, 210 * MM, places=3)
        self.assertAlmostEqual(h, 297 * MM, places=3)
        self.assertFalse(px)
        w, h, _ = parse_page("A5-Landscape")
        self.assertAlmostEqual(w, 210 * MM, places=3)
        self.assertAlmostEqual(h, 148 * MM, places=3)
        self.assertEqual(parse_page("1080x1350px"), (1080.0, 1350.0, True))
        w, h, px = parse_page("100x50mm")
        self.assertAlmostEqual(w, 100 * MM, places=3)
        self.assertFalse(px)
        self.assertAlmostEqual(parse_page({"width_mm": 10, "height_mm": 20})[1], 20 * MM, places=3)
        self.assertAlmostEqual(parse_page(None)[0], 210 * MM, delta=0.5)

    def test_unknown_value_is_reported(self):
        for bad in ("a9", "1080x1350", "big"):
            self.assertTrue(base_errors({"slug": "x", "title": "t", "page": bad}), bad)

    def test_bad_target_and_formats_are_reported(self):
        self.assertTrue(base_errors({"slug": "x", "title": "t", "targets": ["tv"]}))
        self.assertTrue(base_errors({"slug": "x", "title": "t", "image": {"formats": ["gif"]}}))
        self.assertFalse(base_errors({"slug": "x", "title": "t", "targets": ["print", "web", "image"]}))


class ImageTarget(unittest.TestCase):
    def setUp(self):
        self.proj = copy_project()
        edit(self.proj, r"^targets:.*$", "targets: [web, image]")
        edit(self.proj, r"^# image:.*$", "image: {formats: [png, jpg], width_px: 800, quality: 90}")

    def test_png_and_jpg_have_the_requested_width(self):
        r = build(self.proj)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = names(self.proj)
        png = [n for n in got if n.endswith(".png")]
        jpg = [n for n in got if n.endswith(".jpg")]
        self.assertEqual((len(png), len(jpg)), (1, 1))
        self.assertIn("-rgb-800x1131px", png[0])
        for n in (png[0], jpg[0]):
            with Image.open(os.path.join(dist(self.proj), n)) as im:
                self.assertEqual(im.size, (800, 1131))
                self.assertEqual(im.mode, "RGB")

    def test_image_ignores_bleed(self):
        edit(self.proj, r"^bleed_mm:\s*0", "bleed_mm: 3")
        self.assertEqual(build(self.proj, "--target", "image").returncode, 0)
        with Image.open(os.path.join(dist(self.proj), next(n for n in names(self.proj) if n.endswith(".png")))) as im:
            self.assertEqual(im.size, (800, 1131))        # trim only, no bleed

    def test_partial_image_run_keeps_pdfs_and_replaces_images(self):
        self.assertEqual(build(self.proj).returncode, 0)
        before_pdfs = [n for n in names(self.proj) if n.endswith(".pdf")]
        edit(self.proj, r"width_px: 800", "width_px: 500")
        self.assertEqual(build(self.proj, "--target", "image").returncode, 0)
        after = names(self.proj)
        self.assertEqual([n for n in after if n.endswith(".pdf")], before_pdfs)
        self.assertFalse(any("800x" in n for n in after))
        self.assertTrue(any("-rgb-500x" in n for n in after))

    def test_full_run_cleans_old_images(self):
        self.assertEqual(build(self.proj).returncode, 0)
        edit(self.proj, r"width_px: 800", "width_px: 500")
        self.assertEqual(build(self.proj).returncode, 0)
        self.assertFalse(any("800x" in n for n in names(self.proj)))

    def test_pixel_page_renders_one_to_one(self):
        edit(self.proj, r"^page:.*$", 'page: "1080x1350px"')
        edit(self.proj, r"^image:.*$", "image: {formats: [png]}")
        self.assertEqual(build(self.proj, "--target", "image").returncode, 0)
        self.assertEqual([n for n in names(self.proj) if n.endswith(".png")],
                         ["client-project-a4-v1-rgb-1080x1350px.png"])

    def test_multi_page_files_get_a_page_suffix_and_transparent_png_keeps_alpha(self):
        path = os.path.join(tempfile.mkdtemp(prefix="rast_"), "two.pdf")
        c = canvas.Canvas(path, pagesize=(200, 100))
        c.setFillColorRGB(1, 0, 0)
        c.rect(0, 0, 50, 50, fill=1)
        c.showPage()
        c.rect(0, 0, 50, 50, fill=1)
        c.showPage()
        c.save()
        ctx = SimpleNamespace(image_dpi=144, image_width_px=None, image_formats=["png", "jpg"],
                              image_quality=90, image_transparent=True)
        out = tempfile.mkdtemp(prefix="rast_out_")
        files = [os.path.basename(f) for f in rasterize(path, out, "x-v1-rgb", ctx)]
        self.assertEqual(files, ["x-v1-rgb-400x200px-p1.png", "x-v1-rgb-400x200px-p1.jpg",
                                 "x-v1-rgb-400x200px-p2.png", "x-v1-rgb-400x200px-p2.jpg"])
        with Image.open(os.path.join(out, files[0])) as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.getpixel((300, 20))[3], 0)       # untouched area is transparent
        with Image.open(os.path.join(out, files[1])) as im:
            self.assertEqual(im.mode, "RGB")
            self.assertEqual(im.getpixel((300, 20)), (255, 255, 255))


class BuildAll(unittest.TestCase):
    def setUp(self):
        self.proj = copy_project()
        subprocess.run([sys.executable, "new_design.py", "flyer-a5"], cwd=self.proj, check=True, capture_output=True)

    def run_all(self, *args):
        return subprocess.run([sys.executable, "build_all.py", *args], cwd=self.proj, capture_output=True, text=True)

    def test_builds_every_design(self):
        r = self.run_all("--target", "web")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for d in ("main", "flyer-a5"):
            self.assertEqual(len(names(self.proj, d)), 2, d)
        self.assertIn("OK      flyer-a5", r.stdout)

    def test_only_builds_the_chosen_design(self):
        r = self.run_all("--only", "flyer-a5", "--target", "web")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(names(self.proj, "flyer-a5")), 2)
        self.assertEqual(names(self.proj, "main"), [])

    def test_unknown_design_is_an_error(self):
        r = self.run_all("--only", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nope", r.stdout + r.stderr)

    def test_one_failure_does_not_stop_the_others_and_exit_code_reports_it(self):
        edit(self.proj, r"^title:.*$", "", design="flyer-a5")        # missing title -> validation error
        r = self.run_all("--target", "web")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(names(self.proj, "main")), 2)
        self.assertIn("FAILED  flyer-a5", r.stdout)

    def zip_names(self):
        import zipfile
        import glob
        z = glob.glob(os.path.join(self.proj, "exports", "*.zip"))
        self.assertEqual(len(z), 1)
        return sorted(zipfile.ZipFile(z[0]).namelist())

    def test_zip_builds_then_packs_one_folder_per_design(self):
        r = self.run_all("--zip")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        zn = self.zip_names()
        for d in ("main", "flyer-a5"):
            self.assertEqual(len([n for n in zn if f"/{d}/" in n]), len(names(self.proj, d)), d)
        self.assertTrue(all(n.count("/") == 2 for n in zn))     # kit/design/file

    def test_zip_only_includes_chosen_designs(self):
        r = self.run_all("--zip", "--only", "flyer-a5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(all("/flyer-a5/" in n for n in self.zip_names()))

    def test_zip_not_created_when_a_build_fails(self):
        edit(self.proj, r"^title:.*$", "", design="flyer-a5")
        r = self.run_all("--zip")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "exports")))

    def test_zip_rejects_target(self):
        r = self.run_all("--zip", "--target", "web")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.proj, "exports")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
