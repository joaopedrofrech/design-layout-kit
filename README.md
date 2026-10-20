# pdf-layout-starter

A project template for PDFs where layout matters (menus, flyers, price lists, catalogs, one-pagers) and the content changes over time.

**What it is:** a small Python pipeline that builds the PDF from two separate things:
- `content.yaml` — all text, prices, photo names, colors and settings (size, bleed, targets, version).
- `build.py` — the layout only: fonts and `draw()`, which positions everything on the page.

**What you get:** one command generates every file you need, always editable (vector text, fonts embedded, opens in Affinity, Illustrator and Acrobat):
- print: CMYK (FOGRA39), 300 dpi, plus a PDF/X-1a for the printer;
- web: sRGB, a pure 300 dpi file plus a light 150 dpi optimized one.

Every output is checked automatically, and each delivery gets its own versioned folder (`dist/v1/`, `dist/v2/`, …).

## How to edit
Most changes only touch `content.yaml`; the layout stays untouched. Two ways, same result:
- **By hand:** open `content.yaml`, change a price, text, item or photo name, save, run `python3 build.py`.
- **With an AI agent:** ask in plain language ("raise the fish prices by 5%", "swap the cover photo", "add a new section"). The agent edits `content.yaml` (or `build.py` only if the layout changes), runs the build, reads the warnings and sends you the PDFs to review. `AGENTS.md` holds the rules it follows.

## Use
```
pip install -r requirements.txt
python3 build.py                 # every target in `targets` of content.yaml
python3 build.py --target web    # one run, only that target (print | web)
python3 build.py --bump          # version += 1 (new dist/v<N>/ folder), then build
python3 lib/check.py dist/v1/*.pdf   # re-check any generated PDF
python3 -m unittest              # test suite (~25 s)
```

## Outputs
Files go to `dist/v<version>/`, named `<slug>-v<version>-<color>-<dpi>dpi[-<variant>].pdf`.
A full run cleans only the current version folder; older versions stay. `--target` replaces only its own files.

| target | file | use |
|---|---|---|
| print | `…-cmyk-fogra39-300dpi.pdf` | pure, editable |
| print | `…-cmyk-fogra39-300dpi-pdfx1a.pdf` | send to the printer |
| web | `…-rgb-300dpi.pdf` | pure, editable |
| web | `…-rgb-150dpi-web.pdf` | site / WhatsApp / QR (light, linearized) |

Every output is checked right after the build (fonts embedded, vector text present, accents extractable, CMYK-only for print, image dpi). The build stops if a check fails.

## Versions
`version:` in `content.yaml` is the delivery version. Keep working on the same version while iterating (builds overwrite `dist/v<N>/`); bump it when you send a new version to the client. Commit `dist/` only when you want those PDFs in git (a CMYK menu is ~12 MB per version).

## Bleed
`bleed_mm: 3` makes the PDF page larger (trim + 3 mm each side) with the origin at the trim corner. `draw()` keeps using `ctx.page_size` (trim size); extend full-page backgrounds by `ctx.bleed`. X-1a gets `TrimBox`/`BleedBox` accordingly. Crop marks are not drawn (printers add them).

## Start a new project
1. Copy this folder and name it `kit-<client>-<project>-<size>` (e.g. `kit-acme-menu-a4`).
2. Set `slug` (same name without `kit-`), `title`, `author`, `client`, `lang`, `targets`, `page` (any size), `colors` in `content.yaml`.
3. Replace `draw()` in `build.py` with the real layout (keep `run(...)` at the bottom) and the example keys in `content.yaml` with the real content.
4. Put fonts in `assets/fonts/` (register them in `build.py`) and images in `assets/images/`.
5. Build, run the tests when you touch `lib/`, and check `dist/`.

`lib/` is the shared pipeline — do not fork it per project. `assets/images/placeholder.jpg` is a dummy; delete it.
The X-1a check is structural, not a certification: ask the printer to run preflight.

## Files in this repo
- `skill/SKILL.md` — reference copy of the `pdf-layout-kit` AI skill (the skill itself does not depend on this repo).
- `NOTICE` — third-party licenses (Poppins font, FOGRA39 profile). Code: MIT (`LICENSE`).
