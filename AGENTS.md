# AGENTS.md

pdf-layout-starter. Content and layout are separate. Code, keys, folders: English. Content values: the client's language.

## Rules
- Content change → edit only the design's `content.yaml` (or `brand.yaml` for shared keys), then `python3 designs/<design>/build.py`.
- Layout change → edit `draw(c, ctx)` in `designs/<design>/build.py` (one `c.showPage()` per page). Never fork `lib/`.
- New project → copy the folder; rename `designs/main/`; set slug/title/page in its `content.yaml` and author/client/lang/colors in `brand.yaml`; rewrite `draw()`, `validate()` and the example keys; register fonts in `build.py`.
- Never edit `dist/` (generated). After any layout change run `python3 designs/<design>/build.py` (all targets); `--target` is only for one partial run.
- Delivering a new version to the client → `python3 designs/<design>/build.py --bump` (writes `designs/<design>/dist/v<N>/`; older versions stay). Same version while iterating.
- Touching `lib/` → run `python3 -m unittest` (must stay green).
- Image changes → edit `prep.yaml`, run `python3 prep.py`, then build.
- After the build, send the PDFs from `dist/` to the user for preview.

## Structure
`designs/<design>/{build.py,content.yaml,dist/}` per piece; shared at the kit root: `brand.yaml`, `assets/`, `lib/`, `prep.py`, `prep.yaml`, `new_design.py`, `build_all.py`. The starter ships `designs/main/`: rename it to the piece. Kit folder `kit-<client>[-<project>]`, design folder `<piece>-<size>` (e.g. `menu-a4`), `slug` = `<kit name without kit->-<design folder>`.
- Another design → `python3 new_design.py <name>` (copies a design into `designs/<name>/`), run with `python3 designs/<name>/build.py`; `dist/` and `version` are per design.
- Everything at once → `python3 build_all.py [--only a,b] [--target web]` (no bump there; bump each design with its own `build.py --bump`).
- Same layout, other content or size → another content file in the design folder + `python3 designs/<design>/build.py --content <file>` (own `slug`).
- `lib/`, fonts, images and the ICC profile are shared (`P(...)` looks in the design folder first, then the kit root). Never copy `lib/` into a design.
- `brand.yaml` holds `author`, `client`, `lang`, `colors`, `web`; a design's `content.yaml` overrides any of them. For a new design of the same client, reuse its brand, fonts and images before asking for them again.

## Image prep (`prep.py`, `prep.yaml`, `lib/prep.py`)
- Optional and minimal: edit an image only when it has a visible problem or the layout needs a crop. No default denoise, sharpening or tone. An image that needs nothing goes straight into `assets/images/`.
- Originals go in `assets/originals/` and are never modified. Recipes in `prep.yaml` turn them into `assets/images/` (what the layout uses): `python3 prep.py` (`--only NAME`, `--report` lists size, profile and max print size at 300 dpi).
- Local ops: `crop` (ratio + focus or box), `resize` (never upscales unless `upscale: true`), `tone`, `denoise`, `sharpen`, `flatten`. `normalize` always runs first (EXIF orientation, embedded ICC → sRGB, CMYK → RGB).
- AI ops (background removal, real upscaling, generation, mockups) are done by the agent with whatever image tools it has (connectors, its own image abilities). Save the raw result in `assets/originals/` with a suffix (`dish--nobg.png`, `dish--up4x.jpg`), log tool, date and parameters in `assets/originals/SOURCES.md`, then reference it in `prep.yaml`. Check usage rights of generated or third-party images.
- Before layout work run `python3 prep.py --report`: a photo below 300 dpi at its printed size needs a larger original or a real upscale, not a bigger `resize`.

## What `lib/core.py` does for you
- `page:` accepts a preset (`a3 a4 a5 a6 letter legal`, `-landscape`), `"210x297mm"`, `"1080x1350px"` (1 px = 1 pt, renders 1:1) or `{width_mm,height_mm}`.
- targets: `image` → PNG/JPG of every page (`rgb-<w>x<h>px[-p<n>].png|jpg`) from `image: {formats, width_px | dpi, quality, transparent}`; trim area only (bleed ignored), sRGB. `print` → `cmyk-fogra39-300dpi.pdf` + `-pdfx1a.pdf`; `web` → `rgb-300dpi.pdf` + `rgb-<dpi>dpi-web.pdf`. Files: `designs/<design>/dist/v<version>/<slug>-v<version>-<suffix>.pdf`.
- checks every output after building (`lib/check.py`): fonts embedded, vector text present, Unicode map, CMYK-only (print), image dpi. A failure stops the build.
- `ctx.K.<name>` colors from `brand.yaml → colors`, already in the output color space (CMYK FOGRA39 or sRGB); `ctx.white`.
- `ctx.make_image(pil_image, w_pt, h_pt, photo=True)` → JPEG path for `drawImage`: print/pure never downsample (upscale only below 300 dpi); web downsamples to `web.dpi`. Pass `photo=False` for flat logos.
- `ctx.warn(msg)`, `ctx.P(path)`, `ctx.page_size` (TRIM size), `ctx.bleed` (pt), `ctx.version`, `ctx.out` (mode, dpi, up, down), `ctx.D` (content).
- With `bleed_mm > 0` the page is larger and the origin is shifted to the trim corner: draw as usual, extend full-page backgrounds by `ctx.bleed` on every side.
- Canvas gets `initialFontName` and `enforceColorSpace` automatically (no unembedded Helvetica; wrong color space errors).

## content.yaml (per design) and brand.yaml (shared)
Design: `slug` · `version` · `title` · `targets` (list: print, web) · `bleed_mm` · `page {width_mm,height_mm}` + whatever keys the layout reads. Brand: `author` (who made the file) · `client` (PDF Subject) · `lang` · `web {dpi,quality}` · `colors` (sRGB hex). If `author` is empty, ask the user who signs the file (and set `client`). Quote every string; indent with spaces.

## Hard rules
- Use the images through `ctx.make_image` (never `drawImage` on the raw file).
- Don't delete "unused" fonts from page resources (shared across pages).
- X-1a is the direct pikepdf method; Ghostscript only for third-party RGB/transparency PDFs (`lib/export_x1a.py --force-gs`), since it recompresses photos and drops accents' Unicode map.
- Web optimized is built at the target dpi, never post-compressed.
- Verify: the build already checks every file; to re-check use `python3 lib/check.py designs/<design>/dist/v<N>/*.pdf`. Never describe a PDF you did not check. The X-1a report is structural, not a certification.
- Ghostscript on PDFs with transparency can flatten whole pages into images (no text): the checklist fails that case, do not deliver it.
