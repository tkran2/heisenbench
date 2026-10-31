# C++20 Matching Engine

A single-instrument exchange matching engine with price-time priority, two
price-level storage implementations, deterministic replay, and reproducible
benchmarks. The core has no third-party dependencies.

## Run from your Mac's Terminal

Install Apple's compiler tools if `c++ --version` does not work:

```bash
xcode-select --install
```

From this project's directory:

```bash
make -j2
make test
make demo
```

The compiler must support C++20. Python 3 is used for CLI integration tests and
benchmark summaries; the engine itself is entirely C++.

## Try an order book

```bash
./build/matching-engine
```

Enter these commands one at a time:

```text
LIMIT 1 SELL 10010 5
LIMIT 2 SELL 10010 7
LIMIT 3 BUY 10010 8
BOOK
ORDERS
CHECK
QUIT
```

Order 3 buys all 5 units from order 1, then 3 units from order 2. The remaining
book has order 2 selling 4 units at 10010 ticks. Every fill occurs at the maker's
price. A tick size of one cent would make 10010 ticks equal $100.10.

## Matching rules

| Rule | Behavior |
| --- | --- |
| Price priority | Buy orders consume the lowest asks; sells consume the highest bids. |
| Time priority | Orders at the same price execute in FIFO order. |
| Limit order | Execute at the limit or better; rest any remaining quantity. |
| Market order | Consume available liquidity; cancel any unfilled quantity. |
| Trade price | Use the resting maker's price. |
| Cancel | Remove the live order and update its level aggregate. |
| Amend | Specify a new price and **new remaining quantity**. |
| Same-price reduction | Preserve the original FIFO position. An unchanged size also preserves it. |
| Price change or size increase | Lose priority, re-enter the book, and execute if marketable. |
| Order IDs | Nonzero and unique among live orders; reusable after completion or cancellation. |
| Validation | Positive integer prices and quantities; quantities at most 1,000,000,000. Market prices are zero in the API. |
| Capacity | Reject new submissions at 1,000,000 live orders, including market submissions. Existing orders can still be canceled or amended. |
| Command sequence | Increment for each submitted, canceled, or amended order, including business rejections. |

This is one serialized command stream. Engine instances have a single writer;
independent instruments can use independent instances.

## Replay the same session with both implementations

```bash
./build/matching-engine --impl tree --check --file examples/session.txt > /tmp/tree-replay.txt
./build/matching-engine --impl flat --check --file examples/session.txt > /tmp/flat-replay.txt
diff -u /tmp/tree-replay.txt /tmp/flat-replay.txt
```

The outputs should be identical. `--check` scans the book after every mutation
to verify FIFO order, quantities, index consistency, and an uncrossed book.
`--quiet` emits only the final summary. An invariant check also runs when any
normal session finishes.

Input grammar:

```text
LIMIT id BUY|SELL price_ticks quantity
MARKET id BUY|SELL quantity
CANCEL id
AMEND id price_ticks new_remaining_quantity
BOOK
ORDERS
CHECK
HELP
QUIT
```

Blank lines and `#` comments are allowed. A business-rule rejection is an output
event and processing continues. Malformed input reports its line number and
exits with status 2.

The summary includes an event fingerprint and a final-state fingerprint. Their
explicit byte encoding makes them stable across architectures. They are useful
regression checks; they are not cryptographic hashes.

## Two storage implementations

Both implementations use identical matching rules and a FIFO list at each
price. An ID hash table stores a stable iterator to each resting order.

| Operation, P = active price levels | Tree (`std::map`) | Flat (sorted vector of stable level pointers) |
| --- | --- | --- |
| Find price level | O(log P) | O(log P) |
| Insert or remove price level | O(log P) | O(P) pointer movement |
| Best price | O(1) | O(1) |
| Remove order from FIFO after ID lookup | O(1) | O(1) |
| Complete cancel | Expected O(1) ID lookup + O(log P) level lookup/deletion | Expected O(1) ID lookup + O(log P) level lookup + O(P) if a level disappears |

The flat version packs level pointers into contiguous storage. It still
allocates each price level and FIFO node separately; it is not an entirely
contiguous order book. The comparison measures whether cheaper navigation
outweighs pointer movement for a particular workload.

## Correctness checks

```bash
make test
make sanitize
```

The C++ suite contains 32 fixed scenarios across both implementations and
45,000 randomized commands over three seeds. Every randomized outcome and full
order snapshot is checked against a separate vector-based reference model that
scans all orders to choose each maker. Tests cover partial fills, price/time
priority, cancellation, amendment semantics, invalid inputs, integer boundaries,
and index stability as flat levels move.

Seven Python integration tests check the console program, error handling,
replay fixtures, and agreement between implementations. AddressSanitizer and
UndefinedBehaviorSanitizer run through `make sanitize`.

GitHub Actions runs tests on Linux and macOS, plus a CMake/CTest job on Linux.

## Benchmark on your hardware

```bash
mkdir -p results
./build/matching-bench --commands 100000 --trials 3 > results/benchmark.csv
python3 scripts/summarize_bench.py results/benchmark.csv
```

For a longer experiment:

```bash
./build/matching-bench --commands 1000000 --trials 5 --seed 2027 > results/long-run.csv
python3 scripts/summarize_bench.py results/long-run.csv
```

Four synthetic workloads exercise different book behavior:

| Scenario | Workload |
| --- | --- |
| quiet | Narrow price range, mostly resting limit orders, with cancellations, market orders, and amendments. |
| cancel | Roughly balanced live-order cancellation and replenishment, plus amendments. |
| burst | More market sweeps and a shifting midpoint that makes existing quotes tradeable. |
| wide | Thousands of initial price levels with insertion, removal, and repricing. |

Workloads are generated before timing. Tree and flat receive exactly the same
preload and command sequence, and their resulting event fingerprints and final
states must agree. Trials alternate which implementation runs first.
Depleted books receive additional limit orders to keep the test from becoming
an empty-book benchmark. CSV rows include the actual command mix and preload
size; the scenario labels do not imply exact fixed percentages.

Throughput uses a batch pass and includes matching, result allocation, and a
small output-consumption fingerprint. Latency uses a separate replay with
per-command timestamps. CSV output reports p50, p99, maximum, and measured
clock-pair overhead. The latency samples include clock overhead; it is not
subtracted. File parsing, workload generation, CSV printing, and invariant
scans are outside the timed regions.

These are in-process command measurements. See
[benchmarks/README.md](benchmarks/README.md) for the recorded environment and raw
baseline. Repeat on your Mac to establish your own results.

## Project map

| File | Purpose |
| --- | --- |
| `include/matching/types.hpp` | Orders, trades, outcomes, and portable digest encoding. |
| `include/matching/levels.hpp` | Tree and flat price-level storage. |
| `include/matching/engine.hpp` | Matching, cancellation, amendment, ID index, invariants. |
| `include/matching/command.hpp` | Terminal grammar and command dispatch. |
| `src/main.cpp` | Interactive terminal and file replay. |
| `src/benchmark.cpp` | Deterministic workloads and performance measurements. |
| `tests/reference.hpp` | Independent slow correctness oracle. |
| `tests/test_engine.cpp` | Fixed scenarios and randomized differential tests. |
| `docs/design.md` | Design choices, scope, and tradeoffs. |
| `docs/walkthrough.md` | A code-reading and experiment sequence. |
| `docs/mac-and-github.md` | Download, build, and GitHub publishing commands. |

## CMake alternative

```bash
cmake -S . -B build-cmake -DCMAKE_BUILD_TYPE=Release
cmake --build build-cmake --parallel 2
ctest --test-dir build-cmake --output-on-failure
```

## Next experiments

1. Profile price-level lookup, list allocation, and ID lookup on your Mac.
2. Try an order-node pool or a bounded tick-array implementation, preserving
   the same oracle tests and workload traces.
3. Add a binary command journal and crash-recovery experiments around the
   deterministic core.

MIT licensed.
