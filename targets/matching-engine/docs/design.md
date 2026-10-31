# Design decisions

## Scope and processing model

One engine matches one instrument through one ordered command stream. The
state comprises buy and sell price levels, a FIFO at each level, and an active
order-ID index. Submitted orders consume the opposite side before any limit
remainder joins the same side.

A single writer makes arrival priority unambiguous and removes lock ownership
from the core algorithm. Multi-instrument concurrency belongs outside the
engine: shard commands by instrument, keeping each instrument ordered.

The prototype supports limit and market orders, cancellation, and amendments.
Market remainders are canceled. It does not model hidden orders, auctions,
self-trade prevention, participant accounts, risk limits, or exchange-specific
time-in-force rules. There is no network gateway or durable journal in this
version. Replay reads an explicit command file and recomputes events.

## Integer arithmetic

Prices are int64 ticks and quantities are positive int64 units. The engine
does not multiply price by quantity to calculate cash settlement. Price
comparisons never subtract potentially extreme integer values. Per-order and
live-order limits bound level totals below int64 overflow.

## Price-time priority

The best ask is the lowest sell price; the best bid is the highest buy price.
Within a level, the front of the FIFO list is always the next maker. A trade
uses that maker's price, and its quantity is the smaller of the incoming and
maker remaining quantities.

An accepted same-price size reduction edits the existing node. It preserves
the node's original priority number. A size increase or price change removes
the node and processes the amended remaining size as a fresh incoming limit
order. The ID remains the same, but priority becomes the current command
sequence. This convention is part of this simulator's documented rules.

Every business command advances the sequence, including rejected commands.
Read-only inspection and parser failures do not. IDs only need to be unique
among currently live orders.

## Index and storage lifetimes

The ID hash table holds side, price, and a list iterator. Cancellation avoids
scanning the FIFO, then locates the price level to maintain its aggregate.

Tree levels are values stored in `std::map`. Flat levels are separately owned
objects referenced by a sorted vector of `unique_ptr`s. Moving the flat vector
therefore moves pointers while the level and its list nodes stay in place.
An empty level is removed immediately. No locator outlives its order node.

Engine copying and moving are explicitly disabled because the index contains
iterators into the engine's own lists.

## Fair comparison

The matching algorithm is templated over price-level storage. Identical
matching code keeps the tree/flat comparison focused on storage costs.
Correctness tests also use an independent algorithm: the vector reference
chooses each maker by a full scan, with no dependency on either optimized
implementation.

Tree insertion and removal cost O(log P). Flat lookup also costs O(log P), but
inserting or deleting a price level moves O(P) pointers. Flat storage might
benefit a narrow book; wide books and frequent level changes can make pointer
movement expensive. The benchmark reports results rather than assuming the
winner.

## State and failure behavior

Business-rule validation occurs before matching begins, so a rejected business
command leaves the resting orders unchanged. Sequence numbers still advance.
Malformed console input stops replay with an explicit line-number error.

The engine assumes successful memory allocation. An allocation failure during
accepted matching is terminal for the process; there is no rollback/recovery
contract for `std::bad_alloc`. A production gateway would need capacity
reservation, admission control, and a durable recovery strategy.

## Validation strategy

Fixed examples test each matching rule independently. The randomized suite
compares complete outcomes and canonical order snapshots against the reference
after every command. Periodic invariant checks independently verify the ID
index, FIFO ordering, quantities, and uncrossed book. Sanitizers exercise node
and iterator lifetimes.

The replay fixture has manually specified expected trades. Its digests are
derived from those outcomes using explicit little-endian integer encoding.
Fingerprints make a deterministic run easy to compare, but full differential
tests remain the main correctness evidence.
