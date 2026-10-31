# HeisenBench results

## Which bugs do the repositories' own tests catch?

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
| runledger | `runledger-deferred-transactions` | concurrency | caught | caught (47s) |
| runledger | `runledger-lease-expiry-not-fenced` | lease fencing | caught | caught (0s) |
| runledger | `runledger-extra-retry-after-failure` | retry accounting | caught | caught (1s) |
| runledger | `runledger-claim-skips-reaper` | recovery | caught | caught (1s) |
| runledger | `runledger-idempotency-ignores-attempt-limit` | idempotency | caught | caught (2s) |
| tickforge | `tickforge-publish-relaxed` | memory ordering | missed | caught (2s) |
| tickforge | `tickforge-consume-relaxed` | memory ordering | missed | caught (1s) |
| tickforge | `tickforge-full-ring-overwrites` | backpressure | caught | caught (1s) |
| tickforge | `tickforge-new-generation-keeps-trust` | feed integrity | caught | caught (1s) |
| matching-engine | `matching-level-total-int32` | book accounting | missed | caught (4s) |
| runledger | `runledger-short-busy-timeout` | concurrency | missed | caught (3s) |
| tickforge | `tickforge-producer-reads-tail-relaxed` | memory ordering | missed | caught (1s) |
| tickforge | `tickforge-consumer-frees-relaxed` | memory ordering | missed | caught (1s) |

caught by both: 16, escapes unit tests: 7

