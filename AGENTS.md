# AGENTS.md

pdf-layout-starter. Content and layout are separate. Code, keys, folders: English. Content values: the client's language.

## Rules
- Content change → edit only `content.yaml`, then `python3 build.py`.
- Layout change → edit `draw(c, ctx)` in `build.py` (one `c.showPage()` per page). Never fork `lib/`.
- New project → copy the folder; set slug/title/author/lang/page/colors; rewrite `draw()`, `validate()` and the example keys in `content.yaml`; register fonts in `build.py`.
- Never edit `dist/` (generated). After any layout change run `python3 build.py` (all targets); `--target` is only for one partial run.
- Delivering a new version to the client → `python3 build.py --bump` (writes `dist/v<N>/`; older versions stay). Same version while iterating.
- Touching `lib/` → run `python3 -m unittest` (must stay green).
- Image changes → edit `prep.yaml`, run `python3 prep.py`, then build.
- After the build, send the PDFs from `dist/` to the user for preview.
- Naming: folder `kit-<client>-<project>-<size>`, `slug` = same without `kit-`.

## Image prep (`prep.py`, `prep.yaml`, `lib/prep.py`)
- Originals go in `assets/originals/` and are never modified. Recipes in `prep.yaml` turn them into `assets/images/` (what the layout uses): `python3 prep.py` (`--only NAME`, `--report` lists size, profile and max print size at 300 dpi).
- Local ops: `crop` (ratio + focus or box), `resize` (never upscales unless `upscale: true`), `tone`, `denoise`, `sharpen`, `flatten`. `normalize` always runs first (EXIF orientation, embedded ICC → sRGB, CMYK → RGB).
- AI ops (background removal, real upscaling, generation, mockups) are done by the agent with whatever image tools it has (connectors, its own image abilities). Save the raw result in `assets/originals/` with a suffix (`dish--nobg.png`, `dish--up4x.jpg`), log tool, date and parameters in `assets/originals/SOURCES.md`, then reference it in `prep.yaml`. Check usage rights of generated or third-party images.
- Before layout work run `python3 prep.py --report`: a photo below 300 dpi at its printed size needs a larger original or a real upscale, not a bigger `resize`.

## What `lib/core.py` does for you
- targets: `print` → `cmyk-fogra39-300dpi.pdf` + `-pdfx1a.pdf`; `web` → `rgb-300dpi.pdf` + `rgb-<dpi>dpi-web.pdf`. Files: `dist/v<version>/<slug>-v<version>-<suffix>.pdf`.
- checks every output after building (`lib/check.py`): fonts embedded, vector text present, Unicode map, CMYK-only (print), image dpi. A failure stops the build.
- `ctx.K.<name>` colors from `content.yaml → colors`, already in the output color space (CMYK FOGRA39 or sRGB); `ctx.white`.
- `ctx.make_image(pil_image, w_pt, h_pt, photo=True)` → JPEG path for `drawImage`: print/pure never downsample (upscale only below 300 dpi); web downsamples to `web.dpi`. Pass `photo=False` for flat logos.
- `ctx.warn(msg)`, `ctx.P(path)`, `ctx.page_size` (TRIM size), `ctx.bleed` (pt), `ctx.version`, `ctx.out` (mode, dpi, up, down), `ctx.D` (content).
- With `bleed_mm > 0` the page is larger and the origin is shifted to the trim corner: draw as usual, extend full-page backgrounds by `ctx.bleed` on every side.
- Canvas gets `initialFontName` and `enforceColorSpace` automatically (no unembedded Helvetica; wrong color space errors).

## content.yaml (top-level)
`slug` · `version` · `title` · `author` (who made the file) · `client` (PDF Subject) · `lang` · `targets` (list: print, web) · `bleed_mm` · `page {width_mm,height_mm}` · `web {dpi,quality}` · `colors` (sRGB hex) + whatever keys the layout reads. If `author` is empty, ask the user who signs the file (and set `client`). Quote every string; indent with spaces.

## Hard rules
- Use the images through `ctx.make_image` (never `drawImage` on the raw file).
- Don't delete "unused" fonts from page resources (shared across pages).
- X-1a is the direct pikepdf method; Ghostscript only for third-party RGB/transparency PDFs (`lib/export_x1a.py --force-gs`), since it recompresses photos and drops accents' Unicode map.
- Web optimized is built at the target dpi, never post-compressed.
- Verify: the build already checks every file; to re-check use `python3 lib/check.py dist/v<N>/*.pdf`. Never describe a PDF you did not check. The X-1a report is structural, not a certification.
- Ghostscript on PDFs with transparency can flatten whole pages into images (no text): the checklist fails that case, do not deliver it.
