"""Add another art to this kit: python3 new_art.py <name> [--slug SLUG]

Copies build.py + content.yaml into arts/<name>/ (own layout, size, version and dist/). lib/, assets/ and
brand.yaml (optional) stay shared at the kit root. Then edit arts/<name>/content.yaml and draw() in its build.py.
Same layout with different content or size? No new art needed: python3 build.py --content other.yaml
"""
import argparse
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description="Create arts/<name>/ from the root build.py + content.yaml")
    ap.add_argument("name", help="folder name, e.g. flyer-a5 (lowercase, hyphens)")
    ap.add_argument("--slug", help="output name base (default: the folder name); use <client>-<project>-<size>")
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.name):
        sys.exit("name: lowercase letters, digits and hyphens only")
    dest = os.path.join(BASE, "arts", args.name)
    if os.path.exists(dest):
        sys.exit(f"arts/{args.name} already exists")
    os.makedirs(dest)
    shutil.copy(os.path.join(BASE, "build.py"), os.path.join(dest, "build.py"))
    with open(os.path.join(BASE, "content.yaml"), encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r'(?m)^slug:[^\n]*', f'slug: "{args.slug or args.name}"', text, count=1)
    text = re.sub(r'(?m)^version:\s*\d+', "version: 1", text, count=1)
    with open(os.path.join(dest, "content.yaml"), "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Created arts/{args.name}/  (build.py, content.yaml)")
    print(f"Edit its content.yaml and draw(), then:  python3 arts/{args.name}/build.py   ->  arts/{args.name}/dist/v1/")


if __name__ == "__main__":
    main()
