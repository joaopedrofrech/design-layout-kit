---
name: "pdf-layout-kit"
description: "Cria kits de PDF com layout controlado: conteúdo em YAML separado do layout, saídas para impressão (CMYK/FOGRA39, 300 dpi, PDF/X-1a) e web (sRGB, otimizado), sempre editáveis. Tamanho e layout livres."
---

# PDF layout kit (editable print + web)

Layout is NEVER fixed: each project has its own size, pages and layout, taken from the user's references. What repeats is the method and the technical rules below. Answer in the user's language (Portuguese if he writes Portuguese). Code, keys, folders and file names are always English; only content values use the content's language.

This skill only builds the kit. Combine it freely with any other skill or tool available (a general PDF skill for merge/split/extract/OCR, image, font or document skills, etc.) whenever that helps the task.

## 1. Brief (one round, ask only what is missing)
Look at the attachments first. Need: size/orientation/pages (any size, mm), targets (`print`, `web` or both), bleed (default 0), brand colors (sample pixels from brand files, don't guess), fonts, logo, references (copy structure, not identity), complete content. PDF metadata: `author` = who made the file (the person or studio; ask once if you don't know it, never assume), `client` = client name (goes to PDF Subject). List content gaps instead of inventing. If the request is clear, start and ask along with the first results.

## 2. Project structure (always deliver this)
```
kit-<client>-<project>-<size>/        e.g. kit-recanto-do-tambaqui-cardapio-a4
  README.md  AGENTS.md  requirements.txt  .gitignore
  content.yaml            ALL text, prices, photo names, colors (YAML keys in English)
  build.py                layout only: fonts, validate(), draw(c, ctx), run(...)
  lib/core.py             pipeline: targets, color, images, naming, web optimize
  lib/export_x1a.py       CMYK PDF -> PDF/X-1a:2001
  assets/{images,fonts,profiles}/   (profiles/FOGRA39L_coated.icc)
  dist/                   generated PDFs
```
- `README.md` is for humans (install, build, edit, ~15 lines). `AGENTS.md` is for AIs (rules, block types, hard rules, what not to touch, "after the build send the PDFs from dist/ to the user for preview").
- `lib/core.py` holds everything that is not layout, so each project only rewrites `draw(c, ctx)`: `ctx.D` content, `ctx.K` colors already in the output color space, `ctx.make_image(img, w_pt, h_pt, photo=True)` returns a JPEG path ready for drawImage, `ctx.warn()`, `ctx.out` (mode, dpi), `ctx.page_size`. It also sets PDF Title/Author/Subject/Lang from the content.
- `content.yaml` top level: `slug` (= folder name without `kit-`, i.e. `<client>-<project>-<size>`), `title`, `author`, `client`, `lang`, `targets: [print, web]` (deliverables of the project, set once), `bleed_mm`, `page {width_mm,height_mm}`, `web {dpi: 150, quality: 80}`, `colors` (sRGB hex) + content keys. Quote every string, indent with spaces. Content is never hardcoded in `build.py`. `pip install -r requirements.txt` (reportlab, pillow, pikepdf, pyyaml).
- `build.py` validates content (missing keys, missing image files, unknown blocks) and prints WARNINGS: column overflow, photo below target dpi. CLI: `python3 build.py` builds every target in `targets`; `--target print|web` is only a one-off partial run; `--content file.yaml`.
- Photos fill leftover space: compute the free height and adapt the crop (`focus_x`, `focus_y` 0..1), never touch the rest of the layout.

## 3. Targets and output names (`dist/<slug>-<color>-<dpi>dpi[-<variant>].pdf`)
| target | file | purpose |
|---|---|---|
| print | `<slug>-cmyk-fogra39-300dpi.pdf` | pure, editable (CMYK) |
| print | `<slug>-cmyk-fogra39-300dpi-pdfx1a.pdf` | PDF/X-1a, goes to the printer |
| web | `<slug>-rgb-300dpi.pdf` | pure, editable (sRGB) |
| web | `<slug>-rgb-150dpi-web.pdf` | optimized: images at `web.dpi`, JPEG `web.quality`, linearized |
A full run cleans `dist/`; `--target` replaces only its own files. Hyphens only, lowercase, no accents in names. All four files build in seconds.

## 4. Technical rules
- Text stays VECTOR with embedded fonts, one line = one text object (editable in Affinity/Illustrator/Acrobat). Ship the fonts. Find fonts in /usr/share/fonts, else raw.githubusercontent.com/google/fonts/main/ofl/<FONT>/. FOGRA39 profile: /usr/share/texlive/texmf-dist/tex/generic/colorprofiles/FOGRA39L_coated.icc (copy into assets/profiles).
- reportlab Canvas: `initialFontName='<registered font>'` (else unembedded Helvetica fails X-1a) and `enforceColorSpace='cmyk'|'rgb'` matching the output (errors if a wrong color slips in). Do not delete "unused" fonts from page resources (shared across pages).
- Color: print converts every color and image sRGB→CMYK with ICC FOGRA39L_coated via Pillow ImageCms (flat colors/logo RELATIVE_COLORIMETRIC, photos PERCEPTUAL); web keeps sRGB. No transparency, no alpha shadows (X-1a forbids). Flatten PNG logos over the real background first.
- Images, pure outputs (300 dpi at printed size): NEVER downsample; upscale with LANCZOS only if below 300 dpi (warn with the real dpi); UnsharpMask(radius 1.4, percent 55, threshold 2); JPEG quality 100, subsampling 0, dpi tag. Crop the visible area first, then convert.
- Images, web optimized: build directly at the target dpi (downsample LANCZOS, no upscale), JPEG ~80, then pikepdf `save(linearize=True, compress_streams=True, object_stream_mode=generate)`, set Title/Author/`/Lang`. Never post-compress with Ghostscript (loses accents' Unicode map, recompresses). Expect ~1–2 MB vs ~12 MB for a full A4 photo menu.

## 5. PDF/X-1a:2001 — direct pikepdf method (tested)
When the reportlab PDF is clean (DeviceCMYK/Gray only, fonts embedded, no transparency), reprocess nothing; only ADD: TrimBox/BleedBox per page (Trim = Media when bleed 0), ICC stream (`N=4`, `Alternate=DeviceCMYK`), `OutputIntents[0]` = {Type OutputIntent, S GTS_PDFX, OutputCondition and Info "Coated FOGRA39 (ISO 12647-2:2004)", OutputConditionIdentifier "FOGRA39", RegistryName http://www.color.org, DestOutputProfile}, docinfo `GTS_PDFXVersion` "PDF/X-1:2001", `GTS_PDFXConformance` "PDF/X-1a:2001", `Trapped` = `pikepdf.Name('/False')` (NOT `Name.False_`), Title, Author, then `pdf.save(min_version='1.3', force_version='1.3', object_stream_mode=disable, compress_streams=True, deterministic_id=True)`. Measured on a real menu: identical text with accents, 5/5 images byte-identical, 0 pixels different at 300 dpi, 0.2 s.
- Reject the direct method if you find: `rg/RG` operators, non-DeviceCMYK/Gray images, SMask or ExtGState alpha, named ColorSpace. Then Ghostscript fallback (only for third-party PDFs; tell the user it rewrites fonts and recompresses JPEGs; keep the original as the editable one): `.ps` with GTS keys + OutputIntent + embedded ICC N=4, NOT named PDFX_def.ps; run with `-dNOSAFER -dCompatibilityLevel=1.3 -sColorConversionStrategy=CMYK -sProcessColorModel=DeviceCMYK -dDownsampleColorImages=false` (never `-dColorImageDownsampleType=/None`); then add TrimBox with pikepdf.
- Final report to the user: version 1.3; GTS keys; Trapped False; OutputIntent FOGRA39 with N=4 profile; /ID; TrimBox on all pages; fonts embedded; only CMYK/Gray; zero rg/RG; no transparency; not encrypted. Compare with the pure PDF: `pdftotext` identical, `pdfimages -all` md5 equal, `pdftoppm -r 300` zero different pixels.
- Honesty: this is a structural self-check, NOT a certification; recommend the printer's preflight (Acrobat Pro, callas pdfToolbox, PitStop). `bleed_mm` only sets Trim/BleedBox; a real bleed needs a larger page with extended background. X-4 / PDF/A were not tested.

## 6. Workflow
1. Inventory attachments (`pdftoppm -r 100`, `pdfimages -j`, `pdffonts`). 2. Gather content BEFORE drawing; write `content.yaml`. 3. Write `draw()` for the reference layout. 4. Preview (`pdftoppm -r 90`) and check: cut text, overlaps, unbalanced columns, contrast (dark text on mid orange fails: lighten the background), orphan words. 5. Send the first draft early; iterate only on what the user points out. 6. Build all targets, run the checks of sections 4–5, send the PDFs from `dist/` and the kit zip (with `dist/` filled), and say in one line what was not possible (low-res photo, missing price).
Never say "print-ready" without running the checks.

## 7. Content review (before final delivery; if asked, only report and wait for approval before editing)
Spelling, accents, agreement, hyphens, capitalization and `c/` vs `com` consistency; compare with the original text item by item (nothing lost, nothing invented); suspicious or missing prices and consistent `R$ 00,00`; notes whose scope shrank in the new layout; quotes, song lyrics and third-party text in commercial material (copyright); commonly missing items (service fee, contact, payment methods): suggest, don't add.

## 8. Menus
Typical sections: petiscos, pratos, peixes/carnes, sobremesas, cervejas, bebidas, doses. Portion notes ("1/2 porção = 60%", "para 2 pessoas") must appear in EVERY section they apply to. Prices right-aligned with a dotted leader for short lists; price chip for dishes with description; table for variations. Front/back menus need balanced columns; fill leftovers with photos and a quote. "Imagens meramente ilustrativas" only if the client wants it.

## 9. Token economy
Content edit = change only `content.yaml`, run `build.py`, read the warnings; skip the preview for simple price changes. Batch all change requests in one round. Use targeted edits instead of rewriting files. Look at previews only when the layout changed.