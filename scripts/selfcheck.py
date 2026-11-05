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
            stages = [("build", oracle.build)]
            stages += [("unit tests", oracle.unit), ("deep oracle", oracle.deep)]
            failed = None
            for stage, fn in stages:
                r = fn(target, work)
                attempts = 1
                while not r.ok and stage != "build" and attempts < 3:
                    # RunLedger's suite has a known race: its oversized-request test can see a
                    # broken pipe instead of a 413 when the server rejects before draining the
                    # body (about 1 run in 20 for that test, 1 in 6 for the suite). A pristine
                    # stage therefore has to fail three times to count.
                    print(f"{name:16s} pristine {stage} failed, retrying (timing-dependent)", flush=True)
                    r = fn(target, work)
                    attempts += 1
                if not r.ok:
                    failed = (stage, r)
                    break
            print(f"{name:16s} pristine                                     "
                  f"{'ok' if failed is None else 'FAILED at ' + failed[0]}", flush=True)
            if failed is not None:
                print("    " + failed[1].tail[-1200:].replace("\n", "\n    "), flush=True)
                failures.append(f"{name}: pristine snapshot fails its {failed[0]}")
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
