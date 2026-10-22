"""
Local test suite (stdlib unittest, no extra dependency):   python3 -m unittest -v

Builds a temporary copy of the project and checks the behaviours the kit promises.
Tests that need poppler (pdftotext / pdfimages) are skipped if it is not installed.
"""
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import pikepdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib.check import check, failed  # noqa: E402
from lib.export_x1a import analyze  # noqa: E402

HAS_POPPLER = bool(shutil.which("pdftotext") and shutil.which("pdfimages"))
MM = 72 / 25.4


def copy_project():
    dst = tempfile.mkdtemp(prefix="kit_test_")
    proj = os.path.join(dst, "kit-acme-test")
    shutil.copytree(ROOT, proj, ignore=shutil.ignore_patterns(".git", "dist", "tests", "__pycache__", "skill"))
    return proj


def edit(proj, pattern, repl, brand=False, design="main"):
    p = os.path.join(proj, "brand.yaml") if brand else os.path.join(proj, "designs", design, "content.yaml")
    with open(p, encoding="utf-8") as f:
        t = f.read()
    t2 = re.sub(pattern, repl, t, count=1, flags=re.M)
    assert t != t2, f"pattern not found: {pattern}"
    with open(p, "w", encoding="utf-8") as f:
        f.write(t2)


def build(proj, *args, design="main"):
    return subprocess.run([sys.executable, f"designs/{design}/build.py", *args], cwd=proj, capture_output=True, text=True)


def pdfs(proj, version=1, design="main"):
    return sorted(glob.glob(os.path.join(proj, "designs", design, "dist", f"*-v{version}-*.pdf")))


def pick(files, tail):
    return next(f for f in files if f.endswith(tail))


def image_hashes(path):
    out = []
    with pikepdf.open(path) as pdf:
        for pg in pdf.pages:
            for _, x in (pg.Resources.get("/XObject") or {}).items():
                if str(x.get("/Subtype")) == "/Image":
                    out.append(hashlib.md5(x.read_raw_bytes()).hexdigest())
    return out


def text(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout


class FullBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proj = copy_project()
        edit(cls.proj, r'^author:.*$', 'author: "Test Author"', brand=True)
        cls.res = build(cls.proj)
        cls.files = pdfs(cls.proj)
        cls.slug = "client-project-a4-v1"

    def test_build_succeeds(self):
        self.assertEqual(self.res.returncode, 0, self.res.stdout + self.res.stderr)

    def test_names_and_folder(self):
        names = sorted(os.path.basename(f) for f in self.files)
        self.assertEqual(names, sorted(f"{self.slug}-{s}.pdf" for s in (
            "cmyk-fogra39-300dpi", "cmyk-fogra39-300dpi-pdfx1a", "rgb-300dpi", "rgb-150dpi-web")))

    def test_generic_checks_pass_everywhere(self):
        for f in self.files:
            mode = "cmyk" if "cmyk" in f else "rgb"
            self.assertFalse(failed(check(f, mode)), f)

    def test_x1a_keys(self):
        with pikepdf.open(pick(self.files, "-pdfx1a.pdf")) as p:
            self.assertEqual(str(p.pdf_version), "1.3")
            self.assertEqual(str(p.docinfo["/GTS_PDFXVersion"]), "PDF/X-1:2001")
            self.assertEqual(str(p.docinfo["/GTS_PDFXConformance"]), "PDF/X-1a:2001")
            self.assertEqual(str(p.docinfo["/Trapped"]), "/False")
            oi = p.Root.OutputIntents[0]
            self.assertEqual(str(oi.OutputConditionIdentifier), "FOGRA39")
            self.assertEqual(int(oi.DestOutputProfile.N), 4)
            self.assertTrue(all("/TrimBox" in pg for pg in p.pages))

    def test_print_is_pure_cmyk(self):
        for tail in ("cmyk-fogra39-300dpi.pdf", "-pdfx1a.pdf"):
            with pikepdf.open(pick(self.files, tail)) as p:
                self.assertEqual(analyze(p), [])

    def test_web_is_light_and_linearized(self):
        web, pure = pick(self.files, "-web.pdf"), pick(self.files, "rgb-300dpi.pdf")
        self.assertLess(os.path.getsize(web), os.path.getsize(pure) / 3)
        with pikepdf.open(web) as p:
            self.assertTrue(p.is_linearized)

    def test_metadata(self):
        for f in self.files:
            with pikepdf.open(f) as p:
                self.assertEqual(str(p.docinfo["/Author"]), "Test Author")
                self.assertIn("/Title", p.docinfo)

    @unittest.skipUnless(HAS_POPPLER, "needs poppler")
    def test_accents_survive_in_every_file(self):
        for f in self.files:
            t = text(f)
            self.assertIn("Pão de queijo", t, f)
            self.assertIn("Açaí com granola", t, f)

    @unittest.skipUnless(HAS_POPPLER, "needs poppler")
    def test_x1a_is_identical_to_pure(self):
        pure, x1a = pick(self.files, "cmyk-fogra39-300dpi.pdf"), pick(self.files, "-pdfx1a.pdf")
        self.assertEqual(text(pure), text(x1a))
        self.assertEqual(image_hashes(pure), image_hashes(x1a))

    @unittest.skipUnless(HAS_POPPLER, "needs poppler")
    def test_dpi_rules(self):
        self.assertFalse(failed(check(pick(self.files, "cmyk-fogra39-300dpi.pdf"), "cmyk", min_dpi=299)))
        self.assertFalse(failed(check(pick(self.files, "-web.pdf"), "rgb", max_dpi=151)))


class PartialAndVersions(unittest.TestCase):
    def setUp(self):
        self.proj = copy_project()
        self.assertEqual(build(self.proj).returncode, 0)

    def test_partial_run_keeps_other_files(self):
        before = {os.path.basename(f) for f in pdfs(self.proj)}
        self.assertEqual(build(self.proj, "--target", "web").returncode, 0)
        self.assertEqual({os.path.basename(f) for f in pdfs(self.proj)}, before)

    def test_bump_creates_new_version_and_keeps_old(self):
        v1 = {os.path.basename(f) for f in pdfs(self.proj, 1)}
        r = build(self.proj, "--bump")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.proj, "designs", "main", "content.yaml"), encoding="utf-8") as f:
            self.assertIn("version: 2", f.read())
        self.assertEqual({os.path.basename(f) for f in pdfs(self.proj, 1)}, v1)
        v2 = pdfs(self.proj, 2)
        self.assertEqual(len(v2), 4)
        self.assertTrue(all("-v2-" in os.path.basename(f) for f in v2))

    def test_rebuild_same_version_does_not_pile_up(self):
        build(self.proj)
        self.assertEqual(len(pdfs(self.proj)), 4)

    def test_empty_author_warns(self):
        self.assertIn("'author' is empty", build(self.proj).stdout)


class Bleed(unittest.TestCase):
    def test_real_bleed(self):
        proj = copy_project()
        edit(proj, r"^bleed_mm:\s*0", "bleed_mm: 3")
        r = build(proj, "--target", "print")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for f in pdfs(proj):
            with pikepdf.open(f) as p:
                self.assertEqual(len(p.pages), 1)
                mb = [float(x) for x in p.pages[0].MediaBox]
                self.assertAlmostEqual(mb[2] - mb[0], 216 * MM, delta=0.5)
                self.assertAlmostEqual(mb[3] - mb[1], 303 * MM, delta=0.5)
                if f.endswith("-pdfx1a.pdf"):          # X-1a carries Trim/BleedBox
                    tb = [float(x) for x in p.pages[0].TrimBox]
                    self.assertAlmostEqual(tb[2] - tb[0], 210 * MM, delta=0.5)
                    self.assertAlmostEqual(tb[3] - tb[1], 297 * MM, delta=0.5)


class MultiDesign(unittest.TestCase):
    def setUp(self):
        self.proj = copy_project()

    def new_design(self, *args):
        return subprocess.run([sys.executable, "new_design.py", *args], cwd=self.proj, capture_output=True, text=True)

    def test_starter_has_one_art_in_arts_main_and_nothing_buildable_at_root(self):
        self.assertTrue(os.path.exists(os.path.join(self.proj, "designs", "main", "build.py")))
        self.assertTrue(os.path.exists(os.path.join(self.proj, "brand.yaml")))
        self.assertFalse(os.path.exists(os.path.join(self.proj, "build.py")))

    def test_new_design_builds_in_its_own_folder_with_shared_assets(self):
        r = self.new_design("flyer", "--slug", "acme-flyer-a5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = build(self.proj, "--target", "web", design="flyer")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = sorted(os.listdir(os.path.join(self.proj, "designs", "flyer", "dist")))
        self.assertEqual(got, ["acme-flyer-a5-v1-rgb-150dpi-web.pdf", "acme-flyer-a5-v1-rgb-300dpi.pdf"])
        self.assertFalse(os.path.exists(os.path.join(self.proj, "designs", "main", "dist")))   # other design untouched

    def test_new_design_default_slug_comes_from_kit_and_art_names(self):
        self.assertEqual(self.new_design("flyer-a5").returncode, 0)
        with open(os.path.join(self.proj, "designs", "flyer-a5", "content.yaml"), encoding="utf-8") as f:
            self.assertIn('slug: "acme-test-flyer-a5"', f.read())

    def test_new_design_refuses_existing_and_bad_names(self):
        self.assertEqual(self.new_design("a").returncode, 0)
        for name in ("a", "Bad Name", "main"):
            self.assertNotEqual(self.new_design(name).returncode, 0)

    def test_second_content_file_does_not_delete_the_first(self):
        self.assertEqual(build(self.proj).returncode, 0)
        before = {os.path.basename(f) for f in pdfs(self.proj)}
        design = os.path.join(self.proj, "designs", "main")
        shutil.copy(os.path.join(design, "content.yaml"), os.path.join(design, "content-b.yaml"))
        with open(os.path.join(design, "content-b.yaml"), encoding="utf-8") as f:
            text = f.read().replace('slug: "client-project-a4"', 'slug: "variation-a4"')
        with open(os.path.join(design, "content-b.yaml"), "w", encoding="utf-8") as f:
            f.write(text)
        r = build(self.proj, "--content", os.path.join(design, "content-b.yaml"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = {os.path.basename(f) for f in pdfs(self.proj)}
        self.assertTrue(before <= after)
        self.assertEqual(len(after), 8)

    def test_brand_values_reach_the_pdf_and_the_art_can_override(self):
        edit(self.proj, r'^author:.*$', 'author: "Brand Author"', brand=True)
        edit(self.proj, r'^client:.*$', 'client: "Brand Client"', brand=True)
        self.assertEqual(build(self.proj, "--target", "web").returncode, 0)
        for f in pdfs(self.proj):
            with pikepdf.open(f) as p:
                self.assertEqual(str(p.docinfo["/Author"]), "Brand Author")
                self.assertEqual(str(p.docinfo["/Subject"]), "Brand Client")
        edit(self.proj, r'^title:', 'author: "Design Author"\ntitle:')
        self.assertEqual(build(self.proj, "--target", "web").returncode, 0)
        with pikepdf.open(pdfs(self.proj)[0]) as p:
            self.assertEqual(str(p.docinfo["/Author"]), "Design Author")

    def test_two_arts_share_brand_colors(self):
        self.assertEqual(self.new_design("flyer").returncode, 0)
        edit(self.proj, r'primary: "#1F6FEB"', 'primary: "#FF0000"', brand=True)
        from lib.core import load_content
        for design in ("main", "flyer"):
            D = load_content(os.path.join(self.proj, "designs", design, "content.yaml"), self.proj)
            self.assertEqual(D["colors"]["primary"], "#FF0000")
            self.assertEqual(D["colors"]["accent"], "#F5A524")          # untouched brand keys still merge in
            self.assertEqual(build(self.proj, "--target", "web", design=design).returncode, 0)


class Validation(unittest.TestCase):
    def test_missing_image_is_reported(self):
        proj = copy_project()
        edit(proj, r"^photo:.*$", 'photo: {file: "assets/images/nope.jpg"}')
        r = build(proj)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nope.jpg", r.stdout + r.stderr)

    def test_bad_target_is_reported(self):
        proj = copy_project()
        edit(proj, r"^targets:.*$", "targets: [print, tv]")
        r = build(proj)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("targets", r.stdout + r.stderr)


class NegativeCases(unittest.TestCase):
    def make(self, draw):
        from reportlab.pdfgen import canvas
        path = os.path.join(tempfile.mkdtemp(prefix="neg_"), "x.pdf")
        c = canvas.Canvas(path, pagesize=(200, 200))
        draw(c)
        c.showPage()
        c.save()
        return path

    def test_rgb_pdf_is_rejected_by_direct_method(self):
        def draw(c):
            c.setFillColorRGB(1, 0, 0)
            c.rect(10, 10, 50, 50, fill=1)
        with pikepdf.open(self.make(draw)) as p:
            self.assertTrue(analyze(p))

    def test_pdf_without_text_fails_vector_text_check(self):
        path = self.make(lambda c: c.drawString(10, 100, "Hello"))
        with pikepdf.open(path, allow_overwriting_input=True) as p:     # simulate a rasterized/flattened page
            del p.pages[0].Resources["/Font"]
            p.save(path)
        res = check(path, "rgb")
        self.assertTrue(failed(res))
        self.assertTrue(any("Vector text" in n and s == "FAIL" for n, s, _ in res))

    def test_unembedded_helvetica_fails(self):
        res = check(self.make(lambda c: c.drawString(10, 100, "Hello")), "rgb")
        self.assertTrue(any("embedded" in n and s == "FAIL" for n, s, _ in res))


if __name__ == "__main__":
    unittest.main(verbosity=2)
