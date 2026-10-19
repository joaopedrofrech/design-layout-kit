# pdf-layout-starter

Starter kit for PDFs where you want layout control and cheap future edits: content in `content.yaml`, layout in `build.py`, one command to generate print and web files.

## Use
```
pip install -r requirements.txt
python3 build.py                 # every target in `targets` of content.yaml
python3 build.py --target web    # one run, only that target (print | web)
```
Files go to `dist/` (a full run cleans it), named `<slug>-<color>-<dpi>dpi[-<variant>].pdf`:

| target | file | use |
|---|---|---|
| print | `…-cmyk-fogra39-300dpi.pdf` | pure, editable |
| print | `…-cmyk-fogra39-300dpi-pdfx1a.pdf` | send to the printer |
| web | `…-rgb-300dpi.pdf` | pure, editable |
| web | `…-rgb-150dpi-web.pdf` | site / WhatsApp / QR (light, linearized) |

## Start a new project
1. Copy this folder and name it `kit-<client>-<project>-<size>` (e.g. `kit-recanto-do-tambaqui-cardapio-a4`).
2. Set `slug` (same name without `kit-`), `title`, `author`, `lang`, `targets`, `page` (any size), `colors` in `content.yaml`.
3. Replace `draw()` in `build.py` with the real layout (keep `run(...)` at the bottom) and the example keys in `content.yaml` with the real content.
4. Put fonts in `assets/fonts/` (register them in `build.py`) and images in `assets/images/`.
5. Build both targets and check `dist/`.

`lib/` is the shared pipeline — do not fork it per project. `assets/images/placeholder.jpg` is a dummy; delete it.
The X-1a check is structural, not a certification: ask the printer to run preflight.

## Files in this repo
- `skill/SKILL.md` — reference copy of the `pdf-layout-kit` AI skill (the skill itself does not depend on this repo).
- `NOTICE` — third-party licenses (Poppins font, FOGRA39 profile). Code: MIT (`LICENSE`).
- Use it as a GitHub template ("Use this template") or clone and copy. Folder naming for projects: `kit-<client>-<project>-<size>`.
