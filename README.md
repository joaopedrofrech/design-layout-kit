# pdf-layout-starter

A project template for PDFs where layout matters (menus, flyers, price lists, catalogs, one-pagers) and the content changes over time.

**What it is:** a small Python pipeline that builds the PDF from two separate things:
- `content.yaml` (one per art) — all text, prices, photo names and the art's settings (size, bleed, targets, version).
- `build.py` (one per art) — the layout only: fonts and `draw()`, which positions everything on the page.
- `brand.yaml` (shared) — author, client, language and brand colors.

**What you get:** one command generates every file you need, always editable (vector text, fonts embedded, opens in Affinity, Illustrator and Acrobat):
- print: CMYK (FOGRA39), 300 dpi, plus a PDF/X-1a for the printer;
- web: sRGB, a pure 300 dpi file plus a light 150 dpi optimized one.

Every output is checked automatically, and each delivery gets its own versioned folder (`dist/v1/`, `dist/v2/`, …).

## How to edit
Most changes only touch an art's `content.yaml`; the layout stays untouched. Two ways, same result:
- **By hand:** open `arts/<art>/content.yaml`, change a price, text, item or photo name, save, run `python3 arts/<art>/build.py`.
- **With an AI agent:** ask in plain language ("raise the fish prices by 5%", "swap the cover photo", "add a new section"). The agent edits `content.yaml` (or `build.py` only if the layout changes), runs the build, reads the warnings and sends you the PDFs to review. `AGENTS.md` holds the rules it follows.

## Structure
Everything lives in an art folder from day one, so adding more arts later changes nothing:
```
kit-<client>[-<project>]/
  arts/
    <art>/                    e.g. menu-a4, flyer-a5 (one folder per piece)
      content.yaml            texts, prices, photos, size, targets, version
      build.py                the layout (draw)
      dist/v1/                generated PDFs of this art
  brand.yaml                  shared: author, client, lang, colors, web settings
  assets/{originals,images,fonts,profiles}/    shared files
  lib/                        the pipeline (do not edit per project)
  prep.py  prep.yaml          optional image prep
  new_art.py                  adds another art
```
The starter ships with one art, `arts/main/`: rename the folder to the piece (e.g. `menu-a4`).

## Use
```
pip install -r requirements.txt
python3 arts/main/build.py                 # every target of the art
python3 arts/main/build.py --target web    # one run, only that target (print | web)
python3 arts/main/build.py --bump          # version += 1 (new dist/v<N>/ folder), then build
python3 prep.py                            # prepare images (assets/originals -> assets/images)
python3 lib/check.py arts/main/dist/v1/*.pdf   # re-check any generated PDF
python3 -m unittest                        # test suite (~50 s)
```

## More than one art
- **Another piece** (flyer next to the menu): `python3 new_art.py flyer-a5` copies an art into `arts/flyer-a5/` with its own `build.py`, `content.yaml`, version and `dist/`. Fonts, images, color profile and `brand.yaml` stay shared. Run it with `python3 arts/flyer-a5/build.py`.
- **Same layout, different content or size** (a variation): copy the art's `content.yaml` to e.g. `content-b.yaml`, give it its own `slug`, and run `python3 arts/<art>/build.py --content arts/<art>/content-b.yaml`.
- An art can override any `brand.yaml` key in its own `content.yaml`, and can have its own `assets/` (its files win over the shared ones).

## Image prep
Optional and minimal: nothing is edited unless you ask. Put original photos and logos in `assets/originals/` (never modified). Only for an image that needs something, add a recipe in `prep.yaml` (crop to a ratio, resize, tone, denoise, flatten transparency) and run `python3 prep.py`: the result lands in `assets/images/`, which is what the layout uses. An image that needs nothing can go straight into `assets/images/`. Recipe images get their embedded color profile converted to sRGB and EXIF rotation applied.
`python3 prep.py --report` lists every image with its size, profile and the largest size it can print at 300 dpi.
Background removal, real upscaling and image generation are done by the AI agent with its own tools; the raw result is saved in `assets/originals/` and logged in `assets/originals/SOURCES.md`.

## Outputs
Files go to `arts/<art>/dist/v<version>/`, named `<slug>-v<version>-<color>-<dpi>dpi[-<variant>].pdf`.
A full run cleans only that slug's files of the current version; older versions stay. `--target` replaces only its own files.

| target | file | use |
|---|---|---|
| print | `…-cmyk-fogra39-300dpi.pdf` | pure, editable |
| print | `…-cmyk-fogra39-300dpi-pdfx1a.pdf` | send to the printer |
| web | `…-rgb-300dpi.pdf` | pure, editable |
| web | `…-rgb-150dpi-web.pdf` | site / WhatsApp / QR (light, linearized) |

Every output is checked right after the build (fonts embedded, vector text present, accents extractable, CMYK-only for print, image dpi). The build stops if a check fails.

## Versions
`version:` in the art's `content.yaml` is the delivery version. Keep working on the same version while iterating (builds overwrite `dist/v<N>/`); bump it when you send a new version to the client. Commit `dist/` only when you want those PDFs in git (a CMYK menu is ~12 MB per version).

## Bleed
`bleed_mm: 3` makes the PDF page larger (trim + 3 mm each side) with the origin at the trim corner. `draw()` keeps using `ctx.page_size` (trim size); extend full-page backgrounds by `ctx.bleed`. X-1a gets `TrimBox`/`BleedBox` accordingly. Crop marks are not drawn (printers add them).

## Start a new project
1. Copy this folder and name it `kit-<client>[-<project>]` (e.g. `kit-acme`).
2. Rename `arts/main/` to the piece (e.g. `menu-a4`) and set its `slug` to `<kit name without kit->-<art folder>` (e.g. `acme-menu-a4`), plus `title`, `targets`, `page` (any size) in its `content.yaml`.
3. Fill `brand.yaml` (`author`, `client`, `lang`, `colors`).
4. Replace `draw()` in the art's `build.py` with the real layout (keep `run(...)` at the bottom) and the example keys in its `content.yaml` with the real content.
5. Put fonts in `assets/fonts/` (register them in `build.py`) and original images in `assets/originals/`, then prepare them with `prep.yaml` + `python3 prep.py`.
6. Build, run the tests when you touch `lib/`, and check the PDFs.

`lib/` is the shared pipeline — do not fork it per project. `assets/images/placeholder.jpg` is a dummy; delete it.
The X-1a check is structural, not a certification: ask the printer to run preflight.

## Files in this repo
- `skill/SKILL.md` — reference copy of the `pdf-layout-kit` AI skill (the skill itself does not depend on this repo).
- `NOTICE` — third-party licenses (Poppins font, FOGRA39 profile). Code: MIT (`LICENSE`).
