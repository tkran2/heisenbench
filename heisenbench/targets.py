"""The systems under test and how each one is built, unit-tested and deeply verified.

`unit` is the repository's own test suite: what a developer (or a coding agent) runs
before calling a change done. `deep` is held-out verification that is much more
thorough: seeded fault-injection simulation with linearizability checking,
differential fuzzing against an independent reference model, concurrency stress
with property checks, and ThreadSanitizer. A bug "escapes" when unit passes and deep
fails.

`protected` files belong to the oracles. Before an agent's patch is scored they are
restored from the pristine snapshot, so a patch cannot pass by weakening a check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLES = ROOT / "oracles"


@dataclass(frozen=True)
class Target:
    name: str
    language: str
    summary: str
    build: str | None
    unit: str
    deep: tuple[str, ...]
    protected: tuple[str, ...] = ()
    unit_timeout: int = 900
    deep_timeout: int = 2400
    env: dict = field(default_factory=dict)

    @property
    def snapshot(self) -> Path:
        return ROOT / "targets" / self.name

    def render(self, cmd: str, workdir: Path) -> str:
        return cmd.format(oracles=ORACLES, target=workdir, pristine=self.snapshot)


TARGETS = {
    t.name: t
    for t in [
        Target(
            name="quorumlog",
            language="C++20",
            summary="Raft replicated log with client sessions, snapshots and a deterministic simulator",
            build="make -j4 build/quorum-sim build/core-tests build/storage-tests",
            unit="./build/core-tests examples/session.txt && ./build/storage-tests",
            deep=("./build/quorum-sim --seeds 10000",),
            protected=("tests/", "include/quorum/sim.hpp", "include/quorum/linearizability.hpp",
                       "src/sim_main.cpp", "scripts/", "Makefile"),
        ),
        Target(
            name="matching-engine",
            language="C++20",
            summary="price-time priority limit order book with an independent reference model",
            build="make -j4 build/matching-engine build/matching-tests",
            unit="make test",
            deep=("c++ -std=c++20 -O2 -I{target}/include -I{pristine}/tests {oracles}/matching_deep.cpp "
                  "-o build/matching-deep && ./build/matching-deep",),
            protected=("tests/", "Makefile"),
        ),
        Target(
            name="runledger",
            language="Python",
            summary="durable job queue on SQLite with idempotency keys and fenced leases",
            build=None,
            unit="python3 -m unittest discover -s tests",
            deep=("python3 {oracles}/runledger_deep.py {target}",),
            protected=("tests/",),
        ),
        Target(
            name="tickforge",
            language="C++20",
            summary="lock-free SPSC ring and CRC-checked market-data feed state machine",
            build="make build/tests",
            unit="make test",
            deep=("c++ -std=c++20 -O1 -g -pthread -fsanitize=thread -I{target}/include {oracles}/tickforge_deep.cpp "
                  "-o build/tickforge-deep-tsan && TSAN_OPTIONS=halt_on_error=1 ./build/tickforge-deep-tsan",
                  "c++ -std=c++20 -O2 -pthread -I{target}/include {oracles}/tickforge_deep.cpp "
                  "-o build/tickforge-deep && ./build/tickforge-deep --long"),
            protected=("tests/", "Makefile"),
        ),
    ]
}
