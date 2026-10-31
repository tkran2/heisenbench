# HeisenBench

Can a coding agent find and fix a bug that a project's own unit tests do not catch,
and does its fix survive verification that the tests cannot do?

HeisenBench injects realistic bugs into four systems that come with unusually strong
verification: a Raft replicated log with a deterministic fault-injecting simulator
and linearizability checker, a matching engine with an independent reference model, a
SQLite job queue with fenced leases, and a lock-free market-data ring. An agent gets
the buggy repository and a symptom-level issue report, nothing else. Its patch is
then scored twice: by the repository's own test suite, which the agent can run, and
by a held-out **deep oracle** (10,000 simulated clusters, differential fuzzing, a
concurrency stress test, ThreadSanitizer). A patch that passes the tests and fails
the deep oracle is a **plausible-but-wrong fix**: exactly what a reward based on unit
tests would accept.

Scoring is deterministic and needs no model judge: every outcome is decided by a
build, a test suite or an oracle.

## The bug library

<!-- ORACLE_TABLE -->

Each bug is a one- to three-line edit of the kind people really make: a dropped
condition, a flipped boundary, a relaxed memory order, a narrowed integer, a guard
removed from a rare path. Agents see the issue text only; the edit and its
explanation stay in `heisenbench/bugspecs.py`.

One candidate was rejected after validation. Letting `InstallSnapshot` keep a log
suffix without checking its term looks like a safety bug, but no check fires in
10,000 simulated clusters, and for a good reason: a follower only commits through
the prefix it has just verified against the leader, so stale entries are always
repaired before they can be applied. It is kept in `REJECTED` as an example of
defense in depth turning a bug into an equivalent mutant.

## How an agent run is scored

1. A fresh git checkout of the buggy target is created, and the agent command runs in
   it with the issue text as its prompt (any CLI agent works; see below).
2. The harness records the agent's diff, then restores every oracle file (tests,
   simulator, checker, build files) from the pristine snapshot. Edits to them are
   reported as tampering and discarded, so a patch cannot pass by weakening a check.
3. Build, unit tests, deep oracle. Outcomes: `fixed`, `plausible_wrong`, `unit_fail`,
   `build_fail`, `no_change`.

Two prompt conditions: `none` (issue only) and `oracle` (the prompt also says how to
run the project's heavier verification), which measures how much agents gain from
being pointed at the right tool.

The harness is checked with scripted agents: one that applies the true fix scores
`fixed` on every bug, and one that deletes the tests instead of fixing anything has
its tampering detected and reverted.

<!-- AGENT_RESULTS -->

## Run it

Requirements: a C++20 compiler with ThreadSanitizer, make, Python 3.10+.

```bash
python scripts/validate_bugs.py            # every bug through unit tests and deep oracle
python scripts/run_agents.py --agent reference-fix --cmd 'python3 {repo}/scripts/reference_agent.py fix {workdir}'
python scripts/run_agents.py --agent claude-code --hints none oracle \
    --cmd 'claude -p "$(cat {prompt_file})" --dangerously-skip-permissions'
python scripts/report.py                   # results/SUMMARY.md
```

## Layout

```text
targets/          pinned snapshots of the four systems (see each ORIGIN file)
heisenbench/      bug library, target definitions, sandboxing, oracle runner, agent harness
oracles/          deep oracles: matching_deep.cpp, runledger_deep.py, tickforge_deep.cpp
scripts/          vendoring, validation, agent runs, report
results/          oracle matrix, agent results, SUMMARY.md
```

The targets are my own earlier projects
([QuorumLog](https://github.com/tkran2/QuorumLog),
[matching-engine](https://github.com/tkran2/matching-engine),
[RunLedger](https://github.com/tkran2/RunLedger),
[TickForge](https://github.com/tkran2/TickForge)); their verification tooling is what
makes ground truth possible here.

MIT license.
