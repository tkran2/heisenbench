# HeisenBench

[![CI](https://github.com/tkran2/heisenbench/actions/workflows/ci.yml/badge.svg)](https://github.com/tkran2/heisenbench/actions/workflows/ci.yml)

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

23 bugs across the four targets. **7 of the 23 are invisible to the repositories' own test suites**, although those suites are strong (QuorumLog's runs 240 simulated clusters, the matching engine's fuzzes 45,000 commands against its reference model); every bug is caught by a deep oracle.

| Target | Bug | Category | Unit tests | Deep oracle |
| --- | --- | --- | --- | --- |
| quorumlog | `quorumlog-commit-unverified-suffix` | consensus safety | missed | caught (92s) |
| quorumlog | `quorumlog-stale-snapshot-rolls-back` | consensus safety | caught | caught (85s) |
| quorumlog | `quorumlog-vote-not-persisted` | consensus safety | caught | caught (91s) |
| quorumlog | `quorumlog-follower-skips-term-check` | consensus safety | caught | caught (145s) |
| quorumlog | `quorumlog-restore-merges-sessions` | exactly-once | caught | caught (27s) |
| quorumlog | `quorumlog-compact-mislabels-snapshot` | snapshotting | caught | caught (13s) |
| matching-engine | `matching-equal-amend-loses-priority` | priority rules | caught | caught (3s) |
| matching-engine | `matching-amend-increase-keeps-priority` | priority rules | caught | caught (3s) |
| matching-engine | `matching-trade-at-aggressor-price` | pricing | caught | caught (3s) |
| matching-engine | `matching-amend-down-stale-level-total` | book accounting | caught | caught (3s) |
| matching-engine | `matching-level-total-int32` | book accounting | missed | caught (4s) |
| runledger | `runledger-deferred-transactions` | concurrency | caught | caught (47s) |
| runledger | `runledger-lease-expiry-not-fenced` | lease fencing | caught | caught (0s) |
| runledger | `runledger-extra-retry-after-failure` | retry accounting | caught | caught (1s) |
| runledger | `runledger-claim-skips-reaper` | recovery | caught | caught (1s) |
| runledger | `runledger-idempotency-ignores-attempt-limit` | idempotency | caught | caught (2s) |
| runledger | `runledger-short-busy-timeout` | concurrency | missed | caught (3s) |
| tickforge | `tickforge-publish-relaxed` | memory ordering | missed | caught (2s) |
| tickforge | `tickforge-consume-relaxed` | memory ordering | missed | caught (1s) |
| tickforge | `tickforge-full-ring-overwrites` | backpressure | caught | caught (1s) |
| tickforge | `tickforge-new-generation-keeps-trust` | feed integrity | caught | caught (1s) |
| tickforge | `tickforge-producer-reads-tail-relaxed` | memory ordering | missed | caught (1s) |
| tickforge | `tickforge-consumer-frees-relaxed` | memory ordering | missed | caught (1s) |

Each bug is a one- to three-line edit of the kind people really make: a dropped
condition, a flipped boundary, a relaxed memory order, a narrowed integer, a guard
removed from a rare path. Agents see the issue text only; the edit and its
explanation stay in `heisenbench/bugspecs.py`.

Two candidates were rejected after validation and are kept in `REJECTED`:

- Letting `InstallSnapshot` keep a log suffix without checking its term looks like a
  safety bug, but no check fires in 10,000 simulated clusters, and for a good reason:
  a follower only commits through the prefix it has just verified against the
  leader, so stale entries are always repaired before they can be applied. Defense in
  depth turns it into an equivalent mutant.
- Dropping the guard that discards a staged local snapshot after a newer one was
  installed is a real race, but neither the unit tests nor the simulator ever reach
  that interleaving, so it cannot be scored.

## How an agent run is scored

1. A fresh git checkout of the buggy target is created, and the agent command runs in
   it with the issue text as its prompt (any CLI agent works). The included Claude
   Code agent (`scripts/agents/claude_code.sh`) runs headless with file edits allowed
   and shell access limited to building, testing and inspecting the repository.
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

## Agent results (pilot)

Claude Code (headless, `claude-opus-5-5`, file edits plus build/test/inspect commands
only), issue text only (`none` condition), one run per bug, on six bugs chosen to mix
four that escape the unit tests with two that do not:

| Bug | Escapes unit tests? | Outcome | Agent time | Turns | Patch |
| --- | :---: | --- | ---: | ---: | --- |
| `quorumlog-commit-unverified-suffix` | yes | fixed | 91 s | 10 | commit through `prev_index + entries.size()`, the verified prefix |
| `quorumlog-vote-not-persisted` | no | fixed | 119 s | 8 | persist the vote before replying |
| `matching-equal-amend-loses-priority` | no | fixed | 45 s | 6 | restore `<=` in the in-place amend condition |
| `matching-level-total-int32` | yes | fixed | 54 s | 8 | widen the level aggregate back to 64 bits |
| `runledger-short-busy-timeout` | yes | fixed | 13 s | 6 | raise the busy timeout to 30 s (the original was 10 s) |
| `tickforge-publish-relaxed` | yes | fixed | 34 s | 6 | publish the head with release ordering |

Six of six fixed, every patch survives the deep oracle, no plausible-but-wrong
fixes, no test tampering; about $0.81 of API-equivalent usage in total. With a
symptom-level issue report, a frontier agent localizes these bugs quickly: each
report names a subsystem, and each bug sits within a few lines of where that
subsystem's invariant is enforced. The informative next experiments are harder
conditions and weaker models, where unit-test-passing but wrong fixes become
possible.


## Run it

Requirements: a C++20 compiler with ThreadSanitizer, make, Python 3.10+.

```bash
python scripts/validate_bugs.py            # every bug through unit tests and deep oracle
python scripts/run_agents.py --agent reference-fix --cmd 'python3 {repo}/scripts/reference_agent.py fix {workdir}'
python scripts/run_agents.py --agent claude-code --hints none oracle \
    --cmd 'sh {repo}/scripts/agents/claude_code.sh {prompt_file}'
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
