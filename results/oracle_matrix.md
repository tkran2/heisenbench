| Bug | Category | Unit tests | Deep oracle |
| --- | --- | --- | --- |
| `matching-amend-down-stale-level-total` | book accounting | caught | caught (3s) |
| `matching-amend-increase-keeps-priority` | priority rules | caught | caught (3s) |
| `matching-equal-amend-loses-priority` | priority rules | caught | caught (3s) |
| `matching-level-total-int32` | book accounting | pass (missed) | caught (4s) |
| `matching-trade-at-aggressor-price` | pricing | caught | caught (3s) |
| `quorumlog-commit-unverified-suffix` | consensus safety | pass (missed) | caught (92s) |
| `quorumlog-compact-after-install` | snapshotting | pass (missed) | pass (missed) |
| `quorumlog-compact-mislabels-snapshot` | snapshotting | caught | caught (13s) |
| `quorumlog-follower-skips-term-check` | consensus safety | caught | caught (145s) |
| `quorumlog-restore-merges-sessions` | exactly-once | caught | caught (27s) |
| `quorumlog-stale-snapshot-rolls-back` | consensus safety | caught | caught (85s) |
| `quorumlog-vote-not-persisted` | consensus safety | caught | caught (91s) |
| `runledger-claim-skips-reaper` | recovery | caught | caught (1s) |
| `runledger-deferred-transactions` | concurrency | caught | caught (47s) |
| `runledger-extra-retry-after-failure` | retry accounting | caught | caught (1s) |
| `runledger-idempotency-ignores-attempt-limit` | idempotency | caught | caught (2s) |
| `runledger-lease-expiry-not-fenced` | lease fencing | caught | caught (0s) |
| `runledger-short-busy-timeout` | concurrency | pass (missed) | caught (3s) |
| `tickforge-consume-relaxed` | memory ordering | pass (missed) | caught (1s) |
| `tickforge-consumer-frees-relaxed` | memory ordering | pass (missed) | caught (1s) |
| `tickforge-full-ring-overwrites` | backpressure | caught | caught (1s) |
| `tickforge-new-generation-keeps-trust` | feed integrity | caught | caught (1s) |
| `tickforge-producer-reads-tail-relaxed` | memory ordering | pass (missed) | caught (1s) |
| `tickforge-publish-relaxed` | memory ordering | pass (missed) | caught (2s) |
