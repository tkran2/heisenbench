"""Summarize oracle validation and agent runs into results/SUMMARY.md."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from heisenbench.bugspecs import BUGS  # noqa: E402

RES = ROOT / "results"


def oracle_section(lines):
    path = RES / "oracle_matrix.json"
    if not path.exists():
        return
    recs = {(r["target"], r["bug"]): r for r in json.loads(path.read_text())}
    lines += ["## Which bugs do the repositories' own tests catch?", "",
              "| Target | Bug | Category | Unit tests | Deep oracle |", "| --- | --- | --- | --- | --- |"]
    tally = Counter()
    for b in BUGS:
        r = recs.get((b.target, b.id))
        if r is None or not r["build"]["ok"]:
            continue
        u, d = r["unit"]["ok"], r["deep"]["ok"]
        cls = ("escapes unit tests" if u and not d else "caught by both" if not u and not d
               else "missed by both" if u and d else "unit only")
        tally[cls] += 1
        lines.append(f"| {b.target} | `{b.id}` | {b.category} | {'missed' if u else 'caught'} | "
                     f"{'missed' if d else 'caught (%.0fs)' % r['deep']['seconds']} |")
    lines += ["", ", ".join(f"{k}: {v}" for k, v in sorted(tally.items())), ""]


def agent_section(lines):
    files = sorted((RES / "agents").glob("*.json")) if (RES / "agents").exists() else []
    files = [f for f in files if f.stem not in ("reference-fix", "tamper", "null")]
    if not files:
        return
    lines += ["## Agent results", "",
              "| Agent | Hint | Runs | Fixed | Plausible but wrong | Unit tests fail | Build fails | No change |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    detail = defaultdict(list)
    for f in files:
        rows = json.loads(f.read_text())
        by_hint = defaultdict(list)
        for r in rows:
            by_hint[r["hint"]].append(r)
            detail[(f.stem, r["bug"])].append(r["outcome"])
        for hint, rs in sorted(by_hint.items()):
            c = Counter(r["outcome"] for r in rs)
            lines.append(f"| {f.stem} | {hint} | {len(rs)} | {c['fixed']} | {c['plausible_wrong']} | {c['unit_fail']} | "
                         f"{c['build_fail']} | {c['no_change']} |")
    lines += ["", "| Agent | Bug | Outcomes |", "| --- | --- | --- |"]
    for (agent, bug), outs in sorted(detail.items()):
        lines.append(f"| {agent} | `{bug}` | {', '.join(outs)} |")
    lines.append("")


if __name__ == "__main__":
    out = ["# HeisenBench results", ""]
    oracle_section(out)
    agent_section(out)
    (RES / "SUMMARY.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))
