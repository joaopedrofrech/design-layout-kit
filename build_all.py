"""Build every design of this kit: python3 build_all.py [--only a,b] [--target print|web|image]

Runs designs/<name>/build.py for each design (alphabetical) with the same options and prints a summary.
Version bumps are deliberately not available here: bump each design on its own (build.py --bump).

--zip builds first, then packs everything the designs produced (current version) into
exports/<kit>-<date>.zip, one folder per design with the files loose inside. No zip if any build fails.
"""
import argparse
import datetime
import os
import subprocess
import sys
import zipfile

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
DESIGNS = os.path.join(BASE, "designs")


def pack(names):
    """Zip the current version's files in dist/ of each design into exports/<kit>-<date>.zip. Returns the zip path."""
    kit = os.path.basename(BASE)
    out = os.path.join(BASE, "exports", f"{kit}-{datetime.date.today().isoformat()}.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            with open(os.path.join(DESIGNS, n, "content.yaml"), encoding="utf-8") as f:
                D = yaml.safe_load(f) or {}
            folder = os.path.join(DESIGNS, n, "dist")
            prefix = f"{D['slug']}-v{D.get('version', 1)}-"
            for fn in sorted(os.listdir(folder)):
                if fn.startswith(prefix):
                    z.write(os.path.join(folder, fn), f"{kit}/{n}/{fn}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Build every design in designs/")
    ap.add_argument("--only", help="comma-separated design folder names (default: all)")
    ap.add_argument("--target", choices=["print", "web", "image"], help="one-off partial run of this target in every design")
    ap.add_argument("--zip", action="store_true", help="build, then pack the results into exports/<kit>-<date>.zip")
    args = ap.parse_args()
    if args.zip and args.target:
        sys.exit("--zip packs complete builds: it cannot be combined with --target")
    found = sorted(d for d in os.listdir(DESIGNS) if os.path.exists(os.path.join(DESIGNS, d, "build.py"))) \
        if os.path.isdir(DESIGNS) else []
    names = [n.strip() for n in args.only.split(",")] if args.only else found
    missing = [n for n in names if n not in found]
    if missing:
        sys.exit(f"unknown design(s): {', '.join(missing)}  (available: {', '.join(found) or 'none'})")
    if not names:
        sys.exit("no designs found in designs/")
    failed = []
    for n in names:
        print(f"\n=== {n} " + "=" * max(3, 60 - len(n)))
        cmd = [sys.executable, os.path.join(DESIGNS, n, "build.py")] + (["--target", args.target] if args.target else [])
        if subprocess.run(cmd, cwd=BASE).returncode != 0:
            failed.append(n)
    print("\nSummary:")
    for n in names:
        print(f"  {'FAILED' if n in failed else 'OK    '}  {n}   designs/{n}/dist/")
    if failed:
        sys.exit(1)
    if args.zip:
        print(f"\nZip: {os.path.relpath(pack(names), BASE)}")


if __name__ == "__main__":
    main()
