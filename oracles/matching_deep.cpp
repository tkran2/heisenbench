// Deep oracle for the matching engine: differential fuzzing against the pristine
// reference model across several command regimes, with every invariant checked after
// every command and both level-storage variants compared to each other.
//
// Regimes go beyond the repository's own randomized test: amend-heavy flow with
// same-price amends at, below and above the resting size; wide price ranges; large
// quantities; and market-order sweeps. Exit status 1 on the first mismatch.

#include <cstdio>
#include <map>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

#include "matching/engine.hpp"
#include "reference.hpp"

using namespace matching;

namespace {

struct Regime {
    const char* name;
    int submit_pct, cancel_pct;  // remainder amends
    int market_pct;              // share of submits that are market orders
    Price width;                 // prices drawn from 10000 +/- width
    Quantity max_qty;
    int same_price_amend_pct;    // share of amends that keep the resting price
};

const Regime kRegimes[] = {
    {"baseline", 65, 20, 23, 20, 30, 10},
    {"amend-heavy", 40, 10, 10, 10, 50, 70},
    {"wide-book", 70, 15, 10, 500, 1000, 20},
    {"large-quantities", 60, 20, 15, 30, max_order_quantity, 30},
    {"sweeps", 55, 10, 45, 15, 200, 20},
};

std::string describe(const Outcome& o) {
    std::string s = "seq=" + std::to_string(o.sequence) + " id=" + std::to_string(o.id) +
                    " reject=" + std::string(reject_name(o.reject)) + " resting=" + std::to_string(o.resting) +
                    " unfilled=" + std::to_string(o.unfilled) + " priority_lost=" + std::to_string(o.priority_lost) +
                    " trades=[";
    for (const auto& t : o.trades)
        s += "(" + std::to_string(t.maker_id) + "@" + std::to_string(t.price) + "x" + std::to_string(t.quantity) + ")";
    return s + "]";
}

void run(const Regime& r, std::uint64_t seed, int commands) {
    TreeEngine tree;
    FlatEngine flat;
    Reference ref;
    std::mt19937_64 rng(seed);
    auto pick = [&](std::uint64_t n) { return rng() % n; };
    OrderId next_id = 1;
    for (int step = 0; step < commands; ++step) {
        const auto resting = ref.orders();
        const int choice = static_cast<int>(pick(100));
        const Side side = pick(2) ? Side::Buy : Side::Sell;
        const Price price = 10000 + static_cast<Price>(pick(2 * r.width + 1)) - r.width;
        const Quantity qty = 1 + static_cast<Quantity>(pick(static_cast<std::uint64_t>(r.max_qty)));
        Outcome want, a, b;
        std::string what;
        if (choice < r.submit_pct || resting.empty()) {
            NewOrder o{next_id++, side, OrderType::Limit, price, qty};
            if (static_cast<int>(pick(100)) < r.market_pct) {
                o.type = OrderType::Market;
                o.price = 0;
            }
            what = "submit";
            want = ref.submit(o);
            a = tree.submit(o);
            b = flat.submit(o);
        } else if (choice < r.submit_pct + r.cancel_pct) {
            const OrderId id = resting[pick(resting.size())].id;
            what = "cancel";
            want = ref.cancel(id);
            a = tree.cancel(id);
            b = flat.cancel(id);
        } else {
            const auto& target = resting[pick(resting.size())];
            Price p = price;
            Quantity q = qty;
            if (static_cast<int>(pick(100)) < r.same_price_amend_pct) {
                p = target.price;
                const int k = static_cast<int>(pick(3));  // below, equal to, above the resting size
                q = k == 0 ? std::max<Quantity>(1, target.quantity - 1) : k == 1 ? target.quantity
                                                                                  : std::min(max_order_quantity, target.quantity + 1);
            }
            what = "amend";
            want = ref.amend(target.id, p, q);
            a = tree.amend(target.id, p, q);
            b = flat.amend(target.id, p, q);
        }
        const auto ro = ref.orders();
        if (!(a == want) || !(b == want) || tree.orders() != ro || flat.orders() != ro) {
            std::printf("MISMATCH regime=%s seed=%llu step=%d %s\n  reference: %s\n  tree:      %s\n  flat:      %s\n",
                        r.name, static_cast<unsigned long long>(seed), step, what.c_str(), describe(want).c_str(),
                        describe(a).c_str(), describe(b).c_str());
            throw std::runtime_error("differential mismatch");
        }
        tree.check_invariants();
        flat.check_invariants();
        if (tree.book() != flat.book()) throw std::runtime_error("tree and flat books differ");
        // Level aggregates must equal the sum of the resting orders the reference holds.
        std::map<std::pair<int, Price>, Quantity> sums;
        for (const auto& o : ro) sums[{static_cast<int>(o.side), o.price}] += o.quantity;
        for (const auto& level : tree.book())
            if (sums[{static_cast<int>(level.side), level.price}] != level.quantity)
                throw std::runtime_error("level aggregate differs from resting orders");
    }
}

}  // namespace

int main() {
    long long commands = 0;
    for (const auto& r : kRegimes) {
        for (std::uint64_t seed = 1; seed <= 40; ++seed) {
            try {
                run(r, seed * 7919 + 13, 3000);
            } catch (const std::exception& e) {
                std::printf("FAIL %s (regime %s, seed %llu)\n", e.what(), r.name, static_cast<unsigned long long>(seed));
                return 1;
            }
            commands += 3000;
        }
    }
    std::printf("OK %lld commands across %zu regimes\n", commands, sizeof(kRegimes) / sizeof(kRegimes[0]));
    return 0;
}
