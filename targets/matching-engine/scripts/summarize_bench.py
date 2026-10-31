#!/usr/bin/env python3
"""Print medians across trials from the benchmark's CSV output."""

import csv
from collections import defaultdict
from pathlib import Path
import statistics
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 scripts/summarize_bench.py results/benchmark.csv")
    groups = defaultdict(list)
    comparisons = defaultdict(dict)
    with Path(sys.argv[1]).open(newline="") as source:
        for row in csv.DictReader(source):
            groups[(row["scenario"], row["implementation"])].append(row)
            comparisons[(row["scenario"], row["seed"], row["commands"], row["trial"])][row["implementation"]] = row
    if not groups:
        raise SystemExit("no benchmark rows")
    for key, pair in comparisons.items():
        if set(pair) != {"tree", "flat"}:
            raise SystemExit(f"missing implementation for {key}")
        for field in ("event_fingerprint", "state_digest", "trades", "rejected", "final_active"):
            if pair["tree"][field] != pair["flat"][field]:
                raise SystemExit(f"replay mismatch: {key}, {field}")
    print("| Scenario | Implementation | Trials | Median commands/s | Median p50 (ns) | Median p99 (ns) |")
    print("| --- | --- | ---: | ---: | ---: | ---: |")
    for (scenario, implementation), rows in sorted(groups.items()):
        median = lambda field: statistics.median(float(row[field]) for row in rows)
        print(f"| {scenario} | {implementation} | {len(rows)} | "
              f"{median('commands_per_second'):,.0f} | {median('p50_ns'):,.0f} | {median('p99_ns'):,.0f} |")
    print("\nAll tree/flat event fingerprints and final states agree.")


if __name__ == "__main__":
    main()
