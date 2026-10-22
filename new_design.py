"""Add another design to this kit: python3 new_design.py <name> [--from DESIGN] [--slug SLUG]

Copies build.py + content.yaml of an existing design (default: the first one in designs/) into designs/<name>/:
own layout, size, version and dist/. lib/, assets/ and brand.yaml stay shared at the kit root.
Then edit designs/<name>/content.yaml and draw() in its build.py.
Same layout with different content or size? No new design needed: python3 designs/<design>/build.py --content other.yaml
"""
import argparse
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DESIGNS = os.path.join(BASE, "designs")


def main():
    ap = argparse.ArgumentParser(description="Create designs/<name>/ from an existing design")
    ap.add_argument("name", help="design folder name, e.g. flyer-a5 (lowercase, hyphens)")
    ap.add_argument("--from", dest="src", help="design to copy (default: the first one in designs/)")
    ap.add_argument("--slug", help="output name base (default: <kit name without 'kit-'>-<name>)")
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.name):
        sys.exit("name: lowercase letters, digits and hyphens only")
    existing = sorted(d for d in os.listdir(DESIGNS) if os.path.isdir(os.path.join(DESIGNS, d))) if os.path.isdir(DESIGNS) else []
    src = args.src or (existing[0] if existing else None)
    if not src or not os.path.isdir(os.path.join(DESIGNS, src)):
        sys.exit("no design to copy from: designs/ is empty or --from points to a missing folder")
    dest = os.path.join(DESIGNS, args.name)
    if os.path.exists(dest):
        sys.exit(f"designs/{args.name} already exists")
    os.makedirs(dest)
    shutil.copy(os.path.join(DESIGNS, src, "build.py"), os.path.join(dest, "build.py"))
    with open(os.path.join(DESIGNS, src, "content.yaml"), encoding="utf-8") as f:
        text = f.read()
    kit = re.sub(r"^kit-", "", os.path.basename(BASE))
    slug = args.slug or f"{kit}-{args.name}"
    text = re.sub(r'(?m)^slug:[^\n]*', f'slug: "{slug}"', text, count=1)
    text = re.sub(r'(?m)^version:\s*\d+', "version: 1", text, count=1)
    with open(os.path.join(dest, "content.yaml"), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Created designs/{args.name}/ from designs/{src}/  (slug: {slug})")
    print(f"Edit its content.yaml and draw(), then:  python3 designs/{args.name}/build.py   ->  designs/{args.name}/dist/")


if __name__ == "__main__":
    main()
