"""Run every bug through its target's unit tests and deep oracle.

For each target: the pristine snapshot must build and pass both. For each bug: the
buggy copy must still build (bugs are not compile errors), then we record whether
the repository's own tests notice it and whether deep verification does.

Usage: python scripts/validate_bugs.py [--target NAME] [--bug ID]
Writes results/oracle_matrix.json and results/oracle_matrix.md
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from heisenbench import oracle  # noqa: E402
from heisenbench.bugspecs import BUGS, REJECTED  # noqa: E402
from heisenbench.sandbox import materialize  # noqa: E402
from heisenbench.targets import TARGETS  # noqa: E402

OUT = ROOT / "results"


def check(target, bug, workroot: Path):
    work = materialize(target, workroot / (bug.id if bug else f"{target.name}-pristine"), bug)
    b = oracle.build(target, work)
    rec = {"target": target.name, "bug": bug.id if bug else None, "build": b.to_dict()}
    if not b.ok:
        return rec
    u = oracle.unit(target, work)
    d = oracle.deep(target, work)
    rec.update(unit=u.to_dict(), deep=d.to_dict())
    tag = "pristine" if bug is None else bug.id
    print(f"{tag:48s} unit={'pass' if u.ok else 'FAIL'} ({u.seconds:5.1f}s)  deep={'pass' if d.ok else 'FAIL'} ({d.seconds:6.1f}s)",
          flush=True)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target")
    ap.add_argument("--bug")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    path = OUT / "oracle_matrix.json"
    records = json.loads(path.read_text()) if path.exists() else []
    done = {(r["target"], r["bug"]) for r in records}
    with tempfile.TemporaryDirectory(prefix="heisenbench-") as tmp:
        for name, target in TARGETS.items():
            if args.target and name != args.target:
                continue
            todo = [None] + [b for b in BUGS if b.target == name]
            for bug in todo:
                if args.bug and (bug is None or bug.id != args.bug):
                    continue
                key = (name, bug.id if bug else None)
                if key in done:
                    continue
                rec = check(target, bug, Path(tmp))
                records = [r for r in records if (r["target"], r["bug"]) != key] + [rec]
                path.write_text(json.dumps(records, indent=2))
    write_table(records)


def write_table(records):
    rows = ["| Bug | Category | Unit tests | Deep oracle |", "| --- | --- | --- | --- |"]
    by_id = {b.id: b for b in BUGS}
    for r in sorted(records, key=lambda r: (r["target"], r["bug"] or "")):
        if r["bug"] is None or r["bug"] not in by_id:  # pristine runs and rejected candidates
            continue
        if not r["build"]["ok"]:
            rows.append(f"| `{r['bug']}` | {by_id[r['bug']].category} | build failed | build failed |")
            continue
        u = "pass (missed)" if r["unit"]["ok"] else "caught"
        d = "pass (missed)" if r["deep"]["ok"] else f"caught ({r['deep']['seconds']:.0f}s)"
        rows.append(f"| `{r['bug']}` | {by_id[r['bug']].category} | {u} | {d} |")
    (OUT / "oracle_matrix.md").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
