"""Add another art to this kit: python3 new_art.py <name> [--from ART] [--slug SLUG]

Copies build.py + content.yaml of an existing art (default: the first one in arts/) into arts/<name>/:
own layout, size, version and dist/. lib/, assets/ and brand.yaml stay shared at the kit root.
Then edit arts/<name>/content.yaml and draw() in its build.py.
Same layout with different content or size? No new art needed: python3 arts/<art>/build.py --content other.yaml
"""
import argparse
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ARTS = os.path.join(BASE, "arts")


def main():
    ap = argparse.ArgumentParser(description="Create arts/<name>/ from an existing art")
    ap.add_argument("name", help="art folder name, e.g. flyer-a5 (lowercase, hyphens)")
    ap.add_argument("--from", dest="src", help="art to copy (default: the first one in arts/)")
    ap.add_argument("--slug", help="output name base (default: <kit name without 'kit-'>-<name>)")
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.name):
        sys.exit("name: lowercase letters, digits and hyphens only")
    existing = sorted(d for d in os.listdir(ARTS) if os.path.isdir(os.path.join(ARTS, d))) if os.path.isdir(ARTS) else []
    src = args.src or (existing[0] if existing else None)
    if not src or not os.path.isdir(os.path.join(ARTS, src)):
        sys.exit("no art to copy from: arts/ is empty or --from points to a missing folder")
    dest = os.path.join(ARTS, args.name)
    if os.path.exists(dest):
        sys.exit(f"arts/{args.name} already exists")
    os.makedirs(dest)
    shutil.copy(os.path.join(ARTS, src, "build.py"), os.path.join(dest, "build.py"))
    with open(os.path.join(ARTS, src, "content.yaml"), encoding="utf-8") as f:
        text = f.read()
    kit = re.sub(r"^kit-", "", os.path.basename(BASE))
    slug = args.slug or f"{kit}-{args.name}"
    text = re.sub(r'(?m)^slug:[^\n]*', f'slug: "{slug}"', text, count=1)
    text = re.sub(r'(?m)^version:\s*\d+', "version: 1", text, count=1)
    with open(os.path.join(dest, "content.yaml"), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Created arts/{args.name}/ from arts/{src}/  (slug: {slug})")
    print(f"Edit its content.yaml and draw(), then:  python3 arts/{args.name}/build.py   ->  arts/{args.name}/dist/v1/")


if __name__ == "__main__":
    main()
