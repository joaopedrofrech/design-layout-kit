"""Image prep: assets/originals/ -> assets/images/ following prep.yaml. Run: python3 prep.py  (--report, --only NAME)"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from lib.prep import main  # noqa: E402

if __name__ == "__main__":
    main(BASE)
