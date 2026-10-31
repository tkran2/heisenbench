"""Run agents over the bug library.

Examples:
  # Claude Code, headless
  python scripts/run_agents.py --agent claude-code \
      --cmd 'claude -p "$(cat {prompt_file})" --dangerously-skip-permissions --output-format json'

  # harness self-checks (no model): an agent that applies the true fix, and one that does nothing
  python scripts/run_agents.py --agent reference-fix --cmd 'python3 {repo}/scripts/reference_agent.py fix {workdir}'
  python scripts/run_agents.py --agent null --cmd 'true'

Results append to results/agents/<agent>.json (resumable).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from heisenbench.agent import run_agent  # noqa: E402
from heisenbench.bugspecs import BUGS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--cmd", required=True, help="shell template; {prompt_file}, {workdir} and {repo} are filled in")
    ap.add_argument("--hints", nargs="+", default=["none"], choices=["none", "oracle"])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--bugs", nargs="*", default=None)
    ap.add_argument("--target", default=None)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    out_dir = ROOT / "results" / "agents"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.agent}.json"
    results = json.loads(path.read_text()) if path.exists() else []
    done = {(r["bug"], r["hint"], r["run"]) for r in results}
    bugs = [b for b in BUGS if (not args.bugs or b.id in args.bugs) and (not args.target or b.target == args.target)]
    cmd = args.cmd.replace("{repo}", str(ROOT))
    with tempfile.TemporaryDirectory(prefix="hb-agent-") as tmp:
        for bug in bugs:
            for hint in args.hints:
                for k in range(args.runs):
                    if (bug.id, hint, k) in done:
                        continue
                    r = run_agent(bug, args.agent, cmd, hint, k, Path(tmp), args.timeout)
                    results.append(r.to_dict())
                    path.write_text(json.dumps(results, indent=2))
                    print(f"{bug.id:46s} hint={hint:6s} run={k} -> {r.outcome:16s} ({r.seconds:.0f}s)"
                          + (f" tampered={r.tampered}" if r.tampered else ""), flush=True)


if __name__ == "__main__":
    main()
