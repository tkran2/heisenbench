"""Deep oracle for RunLedger: deterministic lease/retry properties and concurrency stress.

Usage: python runledger_deep.py <runledger checkout>

Part 1 drives the database with a fake clock through the lease, retry, reaper and
idempotency rules, checking each documented guarantee.
Part 2 runs real threads against one SQLite file: submitters racing on shared
idempotency keys while workers claim, complete, fail and abandon jobs with short
leases. Afterwards every job must be terminal, have at most one committed result,
respect its attempt budget, and no call may have raised.
Exit status 1 on the first violated property.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from runledger.db import Conflict, Database  # noqa: E402

PAYLOAD = json.loads((ROOT / "examples" / "baseline.json").read_text())
RESULT = {"ok": True}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def check(cond, message):
    if not cond:
        print("FAIL", message)
        sys.exit(1)


def fresh(clock=None):
    tmp = tempfile.mkdtemp(prefix="rl-deep-")
    return Database(Path(tmp) / "jobs.sqlite", clock or time.time, base_backoff=0.01)


def deterministic_properties():
    # Lease fencing: once the lease has expired, the holder can no longer act, reaped or not.
    for lease in (0.5, 5.0, 60.0):
        c = Clock()
        db = fresh(c)
        job = db.submit("k", PAYLOAD, 3)[0]["id"]
        claim = db.claim("w1", lease)
        c.now += lease * 1.01
        check(not db.complete(job, claim["lease_token"], RESULT), f"complete accepted after lease expiry (lease={lease})")
        check(not db.heartbeat(job, claim["lease_token"], lease), "heartbeat revived an expired lease")
        check(not db.fail(job, claim["lease_token"], "late"), "fail accepted after lease expiry")
        check(db.get(job)["result"] is None, "a result was stored by an expired lease holder")

    # Retry budget through explicit failures: exactly max_attempts runs, then dead.
    for budget in (1, 2, 3, 5):
        c = Clock()
        db = fresh(c)
        job = db.submit("k", PAYLOAD, budget)[0]["id"]
        runs = 0
        while True:
            c.now += 1000
            claim = db.claim("w", 10)
            if claim is None:
                break
            runs += 1
            check(runs <= budget, f"job ran {runs} times with max_attempts={budget}")
            db.fail(job, claim["lease_token"], "boom")
        check(runs == budget, f"job ran {runs} times, expected {budget}")
        check(db.get(job)["state"] == "dead", "exhausted job is not dead")

    # Retry budget through lease expiry, with the reaper reclaiming work.
    for budget in (1, 2, 4):
        c = Clock()
        db = fresh(c)
        job = db.submit("k", PAYLOAD, budget)[0]["id"]
        owners, misses = [], 0
        while misses < 2:  # a claim that reaps an expired lease returns nothing; retry once
            c.now += 1000
            claim = db.claim(f"w{len(owners)}", 5)
            if claim is None:
                misses += 1
                continue
            misses = 0
            owners.append(claim["lease_owner"])
            check(len(owners) <= budget, f"expired job was reclaimed {len(owners)} times, budget {budget}")
        check(len(owners) == budget, f"expired job reclaimed {len(owners)} times, expected {budget}")
        check(db.get(job)["state"] == "dead", "job whose leases all expired is not dead")

    # Idempotency: same key and same request returns the same job; any difference conflicts.
    db = fresh(Clock())
    first, created = db.submit("key", PAYLOAD, 3)
    again, created2 = db.submit("key", PAYLOAD, 3)
    check(created and not created2 and first["id"] == again["id"], "idempotent resubmission created a new job")
    for variant, attempts in ((PAYLOAD, 4), ({**PAYLOAD, "name": PAYLOAD["name"] + "-x"}, 3)):
        try:
            db.submit("key", variant, attempts)
            check(False, "conflicting resubmission under an existing idempotency key was accepted")
        except Conflict:
            pass

    # At most one committed result per job.
    c = Clock()
    db = fresh(c)
    job = db.submit("k", PAYLOAD, 3)[0]["id"]
    claim = db.claim("w", 10)
    check(db.complete(job, claim["lease_token"], RESULT), "valid completion rejected")
    check(not db.complete(job, claim["lease_token"], RESULT), "second completion accepted")
    check(db.metrics()["committed_results"] == 1, "more than one result committed")


def stress(seed: int):
    rng = random.Random(seed)
    db = fresh()
    keys = [f"key-{i}" for i in range(30)]
    budgets = {k: rng.randint(1, 4) for k in keys}
    errors, ids = [], {}
    lock = threading.Lock()
    start = threading.Barrier(16)

    def submitter(i):
        r = random.Random(seed * 100 + i)
        start.wait()
        for k in r.sample(keys, len(keys)):
            try:
                job, _ = db.submit(k, PAYLOAD, budgets[k])
                with lock:
                    if ids.setdefault(k, job["id"]) != job["id"]:
                        errors.append(f"two jobs for idempotency key {k}")
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(f"submit raised {type(e).__name__}: {e}")

    stop = threading.Event()

    def worker(i):
        r = random.Random(seed * 1000 + i)
        start.wait()
        while not stop.is_set():
            try:
                claim = db.claim(f"worker-{i}", 0.25)
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(f"claim raised {type(e).__name__}: {e}")
                continue
            if claim is None:
                time.sleep(0.005)
                continue
            roll = r.random()
            try:
                if roll < 0.15:
                    continue  # abandon: simulate a crash after claiming
                if roll < 0.40:
                    db.fail(claim["id"], claim["lease_token"], "simulated failure")
                else:
                    db.complete(claim["id"], claim["lease_token"], {"by": i})
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(f"worker call raised {type(e).__name__}: {e}")

    threads = [threading.Thread(target=submitter, args=(i,)) for i in range(10)]
    threads += [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads[:10]:
        t.join()
    deadline = time.time() + 45
    while time.time() < deadline:
        states = db.metrics()["states"]
        if set(states) <= {"succeeded", "dead"} and sum(states.values()) == len(keys):
            break
        time.sleep(0.05)
    stop.set()
    for t in threads[10:]:
        t.join()

    check(not errors, f"stress seed {seed}: {errors[0] if errors else ''} ({len(errors)} errors)")
    jobs = db.list()
    check(len(jobs) == len(keys), f"stress seed {seed}: {len(jobs)} jobs for {len(keys)} idempotency keys")
    for row in jobs:
        full = db.get(row["id"])
        attempts = len(full["attempts"])
        check(full["state"] in ("succeeded", "dead"), f"stress seed {seed}: job left in state {full['state']}")
        check(attempts <= full["max_attempts"], f"stress seed {seed}: {attempts} attempts > max {full['max_attempts']}")
        if full["state"] == "succeeded":
            check(full["result"] is not None, f"stress seed {seed}: succeeded job has no result")
        if full["state"] == "dead":
            check(full["result"] is None and attempts == full["max_attempts"],
                  f"stress seed {seed}: dead job with {attempts}/{full['max_attempts']} attempts")
    check(db.metrics()["committed_results"] == sum(1 for j in jobs if j["state"] == "succeeded"),
          f"stress seed {seed}: committed results do not match succeeded jobs")


if __name__ == "__main__":
    deterministic_properties()
    for seed in range(4):
        stress(seed)
    print("OK deterministic properties and 4 stress runs")
