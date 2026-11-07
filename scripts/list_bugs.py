"""Print the bug library: target, id, category, whether unit tests catch it, and the issue.

Usage: python scripts/list_bugs.py [--target NAME] [--issues]
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from heisenbench.bugspecs import BUGS, REJECTED  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--target")
ap.add_argument("--issues", action="store_true", help="also print each issue report")
args = ap.parse_args()

matrix_path = ROOT / "results" / "oracle_matrix.json"
matrix = {r["bug"]: r for r in json.loads(matrix_path.read_text())} if matrix_path.exists() else {}
bugs = [b for b in BUGS if not args.target or b.target == args.target]
for b in bugs:
    r = matrix.get(b.id)
    unit = "?" if r is None or not r["build"]["ok"] else ("caught" if not r["unit"]["ok"] else "ESCAPES")
    print(f"{b.target:16s} {b.id:46s} {b.category:18s} unit tests: {unit}")
    if args.issues:
        print(textwrap.indent(textwrap.fill(b.issue, 88), "    "), end="\n\n")
escapes = sum(1 for b in bugs if b.id in matrix and matrix[b.id]["build"]["ok"] and matrix[b.id]["unit"]["ok"])
print(f"\n{len(bugs)} bugs, {escapes} invisible to the repositories' own unit tests; {len(REJECTED)} rejected candidates")
