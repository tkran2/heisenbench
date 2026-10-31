# Learn the engine by running it

## 1. Observe matching before reading the implementation

```bash
make demo
```

Read `examples/session.txt` beside its output. Track each order's remaining
size. Verify why maker 1 executes before maker 2, and why maker 6 executes
before maker 2 after the size increase.

## 2. Read the model and matching loop

```bash
cat include/matching/types.hpp
sed -n '190,280p' include/matching/engine.hpp
```

Follow an incoming buy order through `execute`: select best ask, check price,
fill the front maker, erase completed orders, erase empty levels, and finally
rest a limit remainder. Write down which iterators could become invalid at
each erase.

## 3. Verify amendment priority yourself

```bash
./build/matching-engine --check <<'SESSION'
LIMIT 1 BUY 10000 5
LIMIT 2 BUY 10000 5
AMEND 1 10000 3
ORDERS
AMEND 1 10000 8
ORDERS
MARKET 3 SELL 6
QUIT
SESSION
```

After the reduction, order 1 stays first. After the increase, order 2 moves
ahead of it. The market sell therefore fills order 2 before order 1.

## 4. Explore the tree/flat tradeoff

```bash
mkdir -p results
./build/matching-bench --scenario quiet --commands 1000000 --trials 5 > results/quiet.csv
./build/matching-bench --scenario wide --commands 1000000 --trials 5 > results/wide.csv
python3 scripts/summarize_bench.py results/quiet.csv
python3 scripts/summarize_bench.py results/wide.csv
```

Compare the effect of price-level count on each implementation. Read
`levels.hpp` to connect the measurements to pointer movement and tree lookup.

## 5. Make one change and measure it

Possible experiments include changing the ID-index reservation, using a pool
for order nodes, or adding a price level count to the benchmark output. Write a
hypothesis before changing the code, run the oracle and sanitizers, then repeat
the same workload and seed.

Keep the raw CSV and a short explanation of the result. If performance gets
worse, explaining the cause is useful engineering evidence.
