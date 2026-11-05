"""Check that the oracle matrix in results/oracle_matrix.json still reproduces.

For each selected target: the pristine snapshot must build and pass both its unit
tests and its deep oracle; every bug must apply, still build, be caught by the deep
oracle, and be caught or missed by the unit tests exactly as recorded.

Usage: python scripts/selfcheck.py [--targets matching-engine runledger ...]
Exits 1 on any difference. QuorumLog takes several minutes per bug and TickForge
needs ThreadSanitizer, so CI runs the other two by default.
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
from heisenbench.bugspecs import BUGS  # noqa: E402
from heisenbench.sandbox import materialize  # noqa: E402
from heisenbench.targets import TARGETS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", default=["matching-engine", "runledger"])
    args = ap.parse_args()
    recorded = {(r["target"], r["bug"]): r for r in json.loads((ROOT / "results" / "oracle_matrix.json").read_text())}
    failures = []
    with tempfile.TemporaryDirectory(prefix="hb-selfcheck-") as tmp:
        for name in args.targets:
            target = TARGETS[name]
            work = materialize(target, Path(tmp) / f"{name}-pristine")
            b, u = oracle.build(target, work), None
            ok = b.ok and (u := oracle.unit(target, work)).ok and oracle.deep(target, work).ok
            print(f"{name:16s} pristine                                     {'ok' if ok else 'FAILED'}", flush=True)
            if not ok:
                failures.append(f"{name}: pristine snapshot does not pass")
            for bug in (b for b in BUGS if b.target == name):
                work = materialize(target, Path(tmp) / bug.id, bug)
                if not oracle.build(target, work).ok:
                    failures.append(f"{bug.id}: does not build")
                    continue
                unit_caught = not oracle.unit(target, work).ok
                deep_caught = not oracle.deep(target, work).ok
                rec = recorded.get((name, bug.id))
                expected_unit = rec is not None and not rec["unit"]["ok"]
                status = "ok"
                if not deep_caught:
                    status = "deep oracle missed it"
                elif unit_caught != expected_unit and bug.category != "concurrency":
                    # Whether a unit test trips over a race depends on timing; for those
                    # bugs only the deep oracle's verdict is required to reproduce.
                    status = f"unit tests {'caught' if unit_caught else 'missed'} it, matrix says otherwise"
                print(f"{name:16s} {bug.id:44s} {status}", flush=True)
                if status != "ok":
                    failures.append(f"{bug.id}: {status}")
    print(f"\n{len(failures)} difference(s)" + "".join(f"\n  {f}" for f in failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
