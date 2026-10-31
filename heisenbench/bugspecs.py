"""The bug library.

Each bug is a small edit to a pristine target, written the way such bugs are really
introduced: a dropped condition, a boundary flipped, a field forgotten. Agents see
only the buggy repository and `issue`, a symptom-level report with no pointer to the
code. `explanation` is for maintainers and scoring, never shown to agents.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Edit:
    file: str
    old: str
    new: str


@dataclass(frozen=True)
class Bug:
    id: str
    target: str
    category: str
    issue: str
    explanation: str
    edits: tuple[Edit, ...]


BUGS: list[Bug] = [
    # ---------------------------------------------------------------- quorumlog
    Bug(
        id="quorumlog-commit-unverified-suffix",
        target="quorumlog",
        category="consensus safety",
        issue=(
            "In long soaks with partitions, one replica occasionally ends up with a different state "
            "fingerprint than the others at the same applied index. It looks like it applied a command "
            "that was never committed cluster-wide."
        ),
        explanation=(
            "A follower advances its commit index to min(leaderCommit, last log index) instead of the last "
            "index it just verified against the leader, so stale entries past the compared prefix can be "
            "committed and applied (Raft paper, AppendEntries step 5)."
        ),
        edits=(Edit("include/quorum/raft.hpp",
                    "            ? log_.last_index() : m.prev_index + m.entries.size();\n"
                    "        advance_commit(std::min(m.leader_commit, reply.match_index));",
                    "            ? log_.last_index() : m.prev_index + m.entries.size();\n"
                    "        advance_commit(std::min(m.leader_commit, log_.last_index()));"),),
    ),
    Bug(
        id="quorumlog-stale-snapshot-rolls-back",
        target="quorumlog",
        category="consensus safety",
        issue=(
            "Occasionally a follower's commit index goes backwards right after it receives a snapshot from "
            "the leader, and its state machine is reloaded from an older state."
        ),
        explanation=(
            "A delayed InstallSnapshot older than the follower's commit index (but newer than its own "
            "snapshot) is installed, moving commit backwards and restoring older state."
        ),
        edits=(Edit("include/quorum/raft.hpp",
                    "        if (m.snap_index <= commit_) {",
                    "        if (m.snap_index <= log_.base_index()) {"),),
    ),
    Bug(
        id="quorumlog-vote-not-persisted",
        target="quorumlog",
        category="consensus safety",
        issue="We have seen two leaders elected in the same term after nodes crash and restart during an election.",
        explanation="Granting a vote does not persist it, so a restarted node can vote again in the same term.",
        edits=(Edit("include/quorum/raft.hpp",
                    "                vote_ = m.from;\n"
                    "                persist_hard_state();\n"
                    "                election_elapsed_ = 0;",
                    "                vote_ = m.from;\n"
                    "                election_elapsed_ = 0;"),),
    ),
    Bug(
        id="quorumlog-follower-skips-term-check",
        target="quorumlog",
        category="consensus safety",
        issue=(
            "After a leader change, a follower that had stale entries from an old term sometimes keeps some "
            "of them instead of replacing them with the new leader's entries."
        ),
        explanation=(
            "When appending, a follower treats any index it already holds as matching, without comparing "
            "terms, so conflicting entries are never truncated."
        ),
        edits=(Edit("include/quorum/raft.hpp",
                    "                if (log_.term_at(index) == entry.term) continue; // Already have it.",
                    "                continue; // Already have it."),),
    ),
    Bug(
        id="quorumlog-restore-merges-sessions",
        target="quorumlog",
        category="exactly-once",
        issue=(
            "After a follower installs a snapshot from the leader and later becomes leader itself, a "
            "client's retried command is occasionally applied twice."
        ),
        explanation=(
            "Restoring a snapshot merges its session table into the existing one; std::map::merge keeps the "
            "stale local entries, so dedupe state from the snapshot is lost for those clients."
        ),
        edits=(Edit("include/quorum/replica.hpp",
                    "        sessions_ = std::move(sessions);",
                    "        sessions_.merge(sessions);"),),
    ),
    Bug(
        id="quorumlog-compact-mislabels-snapshot",
        target="quorumlog",
        category="snapshotting",
        issue=(
            "Followers that fall far behind and catch up from a snapshot sometimes end up missing a few "
            "commands: their state differs from the leader's at the same applied index."
        ),
        explanation=(
            "Compaction labels the staged snapshot with the current applied index instead of the index at "
            "which its state was captured, so the entries in between are lost to anyone installing it."
        ),
        edits=(Edit("include/quorum/replica.hpp",
                    "            raft_.compact(staged_->index, std::move(staged_->data));",
                    "            raft_.compact(applied_, std::move(staged_->data));"),),
    ),
    # ---------------------------------------------------------- matching-engine
    Bug(
        id="matching-equal-amend-loses-priority",
        target="matching-engine",
        category="priority rules",
        issue=(
            "Re-sending an amend with the same price and the same remaining quantity (some clients do this "
            "as a no-op) moves the order to the back of the queue at its price level."
        ),
        explanation="The in-place amend condition uses quantity < remaining instead of <=.",
        edits=(Edit("include/matching/engine.hpp",
                    "        if (price == resting.price && quantity <= resting.quantity) {",
                    "        if (price == resting.price && quantity < resting.quantity) {"),),
    ),
    Bug(
        id="matching-amend-increase-keeps-priority",
        target="matching-engine",
        category="priority rules",
        issue=(
            "Increasing a resting order's quantity with an amend at the same price keeps its place in the "
            "queue. The documented rule is that an increase loses time priority."
        ),
        explanation="The in-place amend path ignores the quantity condition, so increases keep FIFO position.",
        edits=(Edit("include/matching/engine.hpp",
                    "        if (price == resting.price && quantity <= resting.quantity) {",
                    "        if (price == resting.price) {"),),
    ),
    Bug(
        id="matching-trade-at-aggressor-price",
        target="matching-engine",
        category="pricing",
        issue=(
            "When an aggressive limit order crosses the spread, trades print at the aggressor's limit price "
            "instead of the resting order's price."
        ),
        explanation="Fills use the incoming limit price instead of the maker's level price.",
        edits=(Edit("include/matching/engine.hpp",
                    "            result.trades.push_back({maker.id, incoming.id, incoming.side, level.price, fill});",
                    "            result.trades.push_back({maker.id, incoming.id, incoming.side,\n"
                    "                                     incoming.type == OrderType::Limit ? incoming.price : level.price, fill});"),),
    ),
    Bug(
        id="matching-amend-down-stale-level-total",
        target="matching-engine",
        category="book accounting",
        issue=(
            "After orders are amended down in size, the aggregate quantity shown for a price level is larger "
            "than the sum of the orders resting there."
        ),
        explanation="The in-place amend updates the order but not its level's aggregate quantity.",
        edits=(Edit("include/matching/engine.hpp",
                    "            auto* level = side_levels(resting.side).find(price);\n"
                    "            level->quantity -= resting.quantity - quantity;\n",
                    ""),),
    ),
    # ---------------------------------------------------------------- runledger
    Bug(
        id="runledger-deferred-transactions",
        target="runledger",
        category="concurrency",
        issue=(
            "Under load with several workers and API clients we occasionally see 'database is locked' "
            "errors, and rarely a duplicate-key error when two clients submit the same idempotency key at "
            "the same moment."
        ),
        explanation=(
            "Write transactions start with a deferred BEGIN, so the read-then-write in submit/claim can race "
            "and fail on lock upgrade or on the unique constraint instead of serializing."
        ),
        edits=(Edit("runledger/db.py", '            con.execute("BEGIN IMMEDIATE")', '            con.execute("BEGIN")'),),
    ),
    Bug(
        id="runledger-lease-expiry-not-fenced",
        target="runledger",
        category="lease fencing",
        issue=(
            "A worker that stalled past its lease, but before any other worker picked the job up, was still "
            "able to commit its result."
        ),
        explanation="The authorization query checks the lease token but not lease expiry.",
        edits=(Edit("runledger/db.py",
                    "        return con.execute(\"SELECT * FROM jobs WHERE id=? AND state='running' AND lease_token=? AND lease_until>?\",\n"
                    "                           (job, token, now)).fetchone()",
                    "        return con.execute(\"SELECT * FROM jobs WHERE id=? AND state='running' AND lease_token=?\",\n"
                    "                           (job, token)).fetchone()"),),
    ),
    Bug(
        id="runledger-extra-retry-after-failure",
        target="runledger",
        category="retry accounting",
        issue="Jobs configured with max_attempts=3 are run a fourth time after three explicit failures.",
        explanation="fail() moves a job to dead only when attempt > max_attempts.",
        edits=(Edit("runledger/db.py",
                    '            state = "dead" if row["attempt"] >= row["max_attempts"] else "retry_wait"\n'
                    '            con.execute("UPDATE jobs SET state=?,updated=?,next_run=?,last_error=?',
                    '            state = "dead" if row["attempt"] > row["max_attempts"] else "retry_wait"\n'
                    '            con.execute("UPDATE jobs SET state=?,updated=?,next_run=?,last_error=?'),),
    ),
    Bug(
        id="runledger-claim-skips-reaper",
        target="runledger",
        category="recovery",
        issue="After a worker process is killed mid-job, the job stays in 'running' forever and no other worker picks it up.",
        explanation="claim() no longer reaps expired leases before selecting work.",
        edits=(Edit("runledger/db.py", "            now = self.clock(); self.reap(con, now)", "            now = self.clock()"),),
    ),
    Bug(
        id="runledger-idempotency-ignores-attempt-limit",
        target="runledger",
        category="idempotency",
        issue=(
            "Submitting the same idempotency key again with a different max_attempts silently returns the "
            "original job instead of reporting a conflict."
        ),
        explanation="The idempotency fingerprint covers the payload but not max_attempts.",
        edits=(Edit("runledger/db.py",
                    '        payload_hash = digest({"payload": payload, "max_attempts": max_attempts})',
                    '        payload_hash = digest({"payload": payload})'),),
    ),
    # ---------------------------------------------------------------- tickforge
    Bug(
        id="tickforge-publish-relaxed",
        target="tickforge",
        category="memory ordering",
        issue="ThreadSanitizer flags a race in the ring buffer when a producer and a consumer run concurrently.",
        explanation="push() publishes the new head with a relaxed store, so the slot write is not released.",
        edits=(Edit("include/tickforge.hpp",
                    "        head_.value.store(head + 1, std::memory_order_release);",
                    "        head_.value.store(head + 1, std::memory_order_relaxed);"),),
    ),
    Bug(
        id="tickforge-consume-relaxed",
        target="tickforge",
        category="memory ordering",
        issue=(
            "On an ARM test machine the consumer occasionally reads stale contents from a slot it just "
            "popped. Runs on x86 never show it."
        ),
        explanation="pop() reads the producer's head with a relaxed load, so it does not acquire the slot contents.",
        edits=(Edit("include/tickforge.hpp",
                    "        if (tail == head_.value.load(std::memory_order_acquire)) return false;",
                    "        if (tail == head_.value.load(std::memory_order_relaxed)) return false;"),),
    ),
    Bug(
        id="tickforge-full-ring-overwrites",
        target="tickforge",
        category="backpressure",
        issue=(
            "When the consumer falls behind and the ring fills up, some messages are lost or replaced "
            "instead of the producer being told the ring is full."
        ),
        explanation="The full check uses > capacity, so one push past full overwrites an unread slot.",
        edits=(Edit("include/tickforge.hpp",
                    "        if (head - tail_.value.load(std::memory_order_acquire) == slots_.size()) return false;",
                    "        if (head - tail_.value.load(std::memory_order_acquire) > slots_.size()) return false;"),),
    ),
    Bug(
        id="tickforge-new-generation-keeps-trust",
        target="tickforge",
        category="feed integrity",
        issue=(
            "After the feed restarts with a new generation, quote() keeps returning data before a fresh "
            "snapshot has arrived, even though the trust gate should be closed."
        ),
        explanation="Moving to a new generation resets the sequence but not the trust flag.",
        edits=(Edit("include/tickforge.hpp",
                    "            generation_ = message.generation; have_sequence_ = false; trusted_ = false;",
                    "            generation_ = message.generation; have_sequence_ = false;"),),
    ),
    Bug(
        id="matching-level-total-int32",
        target="matching-engine",
        category="book accounting",
        issue=(
            "With very large orders, the aggregate size reported for a price level sometimes wraps around "
            "to a negative number."
        ),
        explanation=(
            "PriceLevel's aggregate quantity was narrowed to 32 bits; several near-maximum orders at one "
            "price overflow it."
        ),
        edits=(Edit("include/matching/levels.hpp",
                    "    Quantity quantity{};\n    std::list<RestingOrder> orders;",
                    "    std::int32_t quantity{}; // 32 bits keeps the level header compact\n    std::list<RestingOrder> orders;"),),
    ),
    Bug(
        id="runledger-short-busy-timeout",
        target="runledger",
        category="concurrency",
        issue=(
            "Under a burst of submissions with several workers running, a few API calls fail with "
            "\"database is locked\". It never happens on a quiet system."
        ),
        explanation="The SQLite busy timeout was cut from 10 s to 50 ms, so contended writers give up instead of waiting.",
        edits=(Edit("runledger/db.py",
                    "        con = sqlite3.connect(self.path, timeout=10)",
                    "        con = sqlite3.connect(self.path, timeout=0.05)  # local file: no need to wait long"),),
    ),
    Bug(
        id="tickforge-producer-reads-tail-relaxed",
        target="tickforge",
        category="memory ordering",
        issue=(
            "ThreadSanitizer reports a race between the consumer reading a slot and the producer writing the "
            "same slot on the next lap around the ring."
        ),
        explanation="push() reads the consumer's tail with a relaxed load, so slot reuse is not ordered after the consumer's read.",
        edits=(Edit("include/tickforge.hpp",
                    "        if (head - tail_.value.load(std::memory_order_acquire) == slots_.size()) return false;",
                    "        if (head - tail_.value.load(std::memory_order_relaxed) == slots_.size()) return false;"),),
    ),
    Bug(
        id="tickforge-consumer-frees-relaxed",
        target="tickforge",
        category="memory ordering",
        issue=(
            "Under heavy load on a weakly ordered machine, a popped item is occasionally overwritten while "
            "the consumer is still copying it."
        ),
        explanation="pop() frees the slot with a relaxed store, so the consumer's read is not released before reuse.",
        edits=(Edit("include/tickforge.hpp",
                    "        tail_.value.store(tail + 1, std::memory_order_release);",
                    "        tail_.value.store(tail + 1, std::memory_order_relaxed);"),),
    ),
]

# Candidate bugs that turned out to be harmless (equivalent mutants), kept for the record.
REJECTED: list[Bug] = [
    Bug(
        id="quorumlog-snapshot-keeps-conflicting-suffix",
        target="quorumlog",
        category="consensus safety (equivalent mutant)",
        issue=(
            "A follower that was offline for a long time and caught up through a snapshot sometimes keeps "
            "log entries after the snapshot point that the leader never had. Later it can apply commands "
            "the rest of the cluster did not."
        ),
        explanation=(
            "InstallSnapshot keeps the log suffix whenever the index exists, without checking its term. "
            "Harmless here: kept entries from another term are repaired by the next AppendEntries consistency "
            "check before they can commit, because a follower only commits through the prefix it has just "
            "verified against the leader. 10,000 simulated clusters and the unit tests agree: no violation."
        ),
        edits=(Edit("include/quorum/raft.hpp",
                    "        const bool keep_suffix =\n"
                    "            log_.has(m.snap_index) && log_.term_at(m.snap_index) == m.snap_term;",
                    "        const bool keep_suffix = log_.has(m.snap_index);"),),
    ),

    Bug(
        id="quorumlog-compact-after-install",
        target="quorumlog",
        category="snapshotting (not exercised by any oracle)",
        issue=(
            "A follower occasionally aborts with \"can only compact committed, uncompacted entries\" a little "
            "while after it caught up from the leader's snapshot."
        ),
        explanation=(
            "A snapshot staged for local compaction is no longer discarded when an installed snapshot has "
            "already moved the log base past it, so compaction later targets an index inside the snapshot. "
            "A real bug, but neither the unit tests nor 10,000 simulated clusters reach that interleaving, "
            "so it cannot be scored and is excluded."
        ),
        edits=(Edit("include/quorum/replica.hpp",
                    "        if (staged_ && staged_->index <= base) staged_.reset(); // Superseded by an install.\n",
                    ""),),
    ),
]

BY_ID = {b.id: b for b in BUGS}
