"""Run a coding agent on one bug and score its patch.

The agent gets a fresh git checkout of the buggy target and the issue text. Its
command is a template (any CLI agent works), run with the checkout as the working
directory and a time limit. Afterwards the harness:

  1. records the agent's diff against the buggy starting point,
  2. restores the target's oracle files from the pristine snapshot (and notes any
     tampering),
  3. builds, runs the unit tests, and runs the held-out deep oracle.

Outcomes:
  fixed            unit tests and deep verification both pass
  plausible_wrong  unit tests pass, deep verification fails: the fix looks done but is not
  unit_fail        the repository's own tests still fail
  build_fail       the patch does not compile
  no_change        the agent changed nothing outside the oracle files
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import oracle
from .bugspecs import Bug
from .sandbox import materialize, restore_protected
from .targets import TARGETS

PROMPT = """You are working in a git repository ({summary}). A user filed this issue:

{issue}

Find the root cause and fix it in the source code. Keep the change minimal. Do not
edit tests or verification code; changes to them are discarded before your fix is
evaluated. You may build the project and run any of its tools.{hint}
When you are done, reply with a short summary of the root cause and your fix."""

HINTS = {
    "none": "",
    "oracle": "\n\nThe repository includes heavier verification than its unit tests: {deep_hint}",
}

DEEP_HINTS = {
    "quorumlog": "`make build/quorum-sim && ./build/quorum-sim --seeds 2000` runs seeded fault-injected clusters "
                 "and checks safety and linearizability.",
    "matching-engine": "tests/reference.hpp is an independent reference model; fuzzing the engine against it "
                       "with many random commands is the strongest check.",
    "runledger": "concurrency problems show up when many threads submit, claim and complete jobs against one "
                 "database file at once.",
    "tickforge": "`make tsan` builds the tests with ThreadSanitizer.",
}


@dataclass
class AgentResult:
    bug: str
    agent: str
    hint: str
    run: int
    outcome: str
    seconds: float
    diff: str
    tampered: list[str] = field(default_factory=list)
    unit: dict | None = None
    deep: dict | None = None
    agent_tail: str = ""
    reverted_injection: bool = False

    def to_dict(self):
        return asdict(self)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def prompt_for(bug: Bug, hint: str) -> str:
    target = TARGETS[bug.target]
    h = HINTS[hint].format(deep_hint=DEEP_HINTS[bug.target])
    return PROMPT.format(summary=target.summary, issue=bug.issue, hint=h)


def run_agent(bug: Bug, agent_name: str, agent_cmd: str, hint: str, run_index: int, workroot: Path,
              timeout: int = 1800) -> AgentResult:
    target = TARGETS[bug.target]
    work = materialize(target, workroot / f"{bug.id}-{agent_name}-{hint}-{run_index}", bug)
    git(work, "init", "-q")
    git(work, "-c", "user.email=bench@localhost", "-c", "user.name=bench", "add", "-A")
    git(work, "-c", "user.email=bench@localhost", "-c", "user.name=bench", "commit", "-q", "-m", "start")
    prompt_file = work.parent / f"{work.name}.prompt.txt"
    prompt_file.write_text(prompt_for(bug, hint))

    cmd = agent_cmd.format(prompt_file=shlex.quote(str(prompt_file)), workdir=shlex.quote(str(work)))
    t0 = time.time()
    try:
        p = subprocess.run(cmd, shell=True, cwd=work, capture_output=True, text=True, timeout=timeout)
        tail = (p.stdout + p.stderr)[-4000:]
    except subprocess.TimeoutExpired as e:
        tail = "AGENT TIMEOUT\n" + ((e.stdout or b"").decode(errors="replace"))[-3000:]
    seconds = time.time() - t0

    subprocess.run(["rm", "-rf", "build"], cwd=work)
    tampered = restore_protected(target, work)
    git(work, "add", "-A")
    diff = git(work, "diff", "--cached", "HEAD")
    reverted = all(e.old in (work / e.file).read_text() for e in bug.edits)

    res = AgentResult(bug=bug.id, agent=agent_name, hint=hint, run=run_index, outcome="", seconds=seconds,
                      diff=diff, tampered=tampered, agent_tail=tail, reverted_injection=reverted)
    if not diff.strip():
        res.outcome = "no_change"
        return res
    b = oracle.build(target, work)
    if not b.ok:
        res.outcome = "build_fail"
        res.unit = b.to_dict()
        return res
    u = oracle.unit(target, work)
    res.unit = u.to_dict()
    if not u.ok:
        res.outcome = "unit_fail"
        return res
    d = oracle.deep(target, work)
    res.deep = d.to_dict()
    res.outcome = "fixed" if d.ok else "plausible_wrong"
    return res


def save(results: list[AgentResult], path: Path) -> None:
    path.write_text(json.dumps([r.to_dict() for r in results], indent=2))
