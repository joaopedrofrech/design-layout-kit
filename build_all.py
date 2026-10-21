"""Build every design of this kit: python3 build_all.py [--only a,b] [--target print|web|image]

Runs designs/<name>/build.py for each design (alphabetical) with the same options and prints a summary.
Version bumps are deliberately not available here: bump each design on its own (build.py --bump).
"""
import argparse
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DESIGNS = os.path.join(BASE, "designs")


def main():
    ap = argparse.ArgumentParser(description="Build every design in designs/")
    ap.add_argument("--only", help="comma-separated design folder names (default: all)")
    ap.add_argument("--target", choices=["print", "web", "image"], help="one-off partial run of this target in every design")
    args = ap.parse_args()
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
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
