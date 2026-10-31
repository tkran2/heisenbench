#include "matching/command.hpp"
#include "matching/engine.hpp"

#include <algorithm>
#include <bit>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

using namespace matching;
using Clock = std::chrono::steady_clock;

struct Workload {
    std::vector<Command> preload;
    std::vector<Command> commands;
    std::size_t limits{};
    std::size_t markets{};
    std::size_t cancels{};
    std::size_t amendments{};
};

// This set permits random live-order selection without scanning the book.
class LiveIds {
public:
    void insert(OrderId id) {
        if (positions_.contains(id)) return;
        positions_[id] = ids_.size();
        ids_.push_back(id);
    }
    void erase(OrderId id) {
        const auto it = positions_.find(id);
        if (it == positions_.end()) return;
        const auto position = it->second;
        ids_[position] = ids_.back();
        positions_[ids_[position]] = position;
        ids_.pop_back();
        positions_.erase(id);
    }
    [[nodiscard]] bool empty() const { return ids_.empty(); }
    [[nodiscard]] std::size_t size() const { return ids_.size(); }
    [[nodiscard]] OrderId pick(std::uint64_t random) const { return ids_[random % ids_.size()]; }
private:
    std::vector<OrderId> ids_;
    std::unordered_map<OrderId, std::size_t> positions_;
};

Workload generate(std::string_view scenario, std::size_t count, std::uint64_t seed) {
    TreeEngine model;
    LiveIds live;
    std::mt19937_64 random(seed);
    OrderId next_id = 1;
    Workload workload;
    workload.commands.reserve(count);
    const Price span = scenario == "wide" ? 2048 : (scenario == "burst" ? 64 : 16);
    const std::size_t preload_count = scenario == "wide" ? 4096U : 256U;

    const auto record = [&](const Command& command, std::vector<Command>& destination) {
        const auto outcome = command.apply(model);
        if (!outcome.accepted()) throw std::logic_error("workload generator produced a rejected command");
        for (const auto& trade : outcome.trades)
            if (!model.contains(trade.maker_id)) live.erase(trade.maker_id);
        if (model.contains(command.order.id)) live.insert(command.order.id);
        else live.erase(command.order.id);
        destination.push_back(command);
    };

    for (std::size_t i = 0; i < preload_count; ++i) {
        const auto side = i % 2 == 0 ? Side::Buy : Side::Sell;
        const auto distance = 1 + static_cast<Price>((i / 2) % static_cast<std::size_t>(span));
        const auto price = 10000 + (side == Side::Buy ? -distance : distance);
        record({Action::Submit, {next_id++, side, OrderType::Limit, price, 20}}, workload.preload);
    }

    Price midpoint = 10000;
    for (std::size_t i = 0; i < count; ++i) {
        if (scenario == "burst" && i % 64 == 0)
            midpoint += static_cast<Price>(random() % 11) - 5;
        // Keep prices positive even for unusually large user-selected traces.
        midpoint = std::clamp(midpoint, Price{4000}, Price{16000});
        const auto roll = random() % 100;
        const auto cancel_percent = scenario == "cancel" ? 45U : (scenario == "burst" ? 15U : 30U);
        const auto market_percent = scenario == "cancel" ? 0U : (scenario == "burst" ? 35U : 10U);
        // Replenish depleted books before timing their next command. Otherwise
        // a market-heavy trace degenerates into measuring empty-book no-ops.
        const auto minimum_live = scenario == "wide" ? 2048U : 128U;
        const bool force_limit = live.size() < minimum_live;
        Command command;
        if (!force_limit && !live.empty() && (roll < cancel_percent || live.size() > 8192)) {
            command.action = Action::Cancel;
            command.order.id = live.pick(random());
        } else if (!force_limit && roll < cancel_percent + market_percent) {
            command.order = {next_id++, random() % 2 == 0 ? Side::Buy : Side::Sell,
                OrderType::Market, 0, static_cast<Quantity>(random() % 80 + 1)};
        } else if (!force_limit && !live.empty() && roll < cancel_percent + market_percent + 10U) {
            command.action = Action::Amend;
            command.order.id = live.pick(random());
            // Find the chosen order's side only while generating, never during
            // a timed engine pass. All generation is excluded from timing.
            const auto orders = model.orders();
            const auto chosen = std::find_if(orders.begin(), orders.end(), [&](const auto& order) {
                return order.id == command.order.id;
            });
            const auto distance = 1 + static_cast<Price>(random() % static_cast<std::uint64_t>(span));
            command.order.price = midpoint + (chosen->side == Side::Buy ? -distance : distance);
            command.order.quantity = static_cast<Quantity>(random() % 40 + 1);
        } else {
            const auto side = random() % 2 == 0 ? Side::Buy : Side::Sell;
            const auto distance = 1 + static_cast<Price>(random() % static_cast<std::uint64_t>(span));
            const auto price = midpoint + (side == Side::Buy ? -distance : distance);
            command.order = {next_id++, side, OrderType::Limit, price,
                             static_cast<Quantity>(random() % 40 + 1)};
        }
        record(command, workload.commands);
        if (command.action == Action::Cancel) ++workload.cancels;
        else if (command.action == Action::Amend) ++workload.amendments;
        else if (command.order.type == OrderType::Market) ++workload.markets;
        else ++workload.limits;
    }
    model.check_invariants();
    return workload;
}

// Consume results using a small, deterministic fingerprint. Its cost is part
// of the batch-throughput measurement and outside individual latency samples.
struct Observed {
    std::uint64_t fingerprint{0x9e3779b97f4a7c15ULL};
    std::uint64_t trades{};
    std::uint64_t rejected{};

    void add(const Outcome& result) {
        const auto mix = [&](std::uint64_t value) {
            fingerprint = std::rotl(fingerprint, 7) ^ (value + 0x9e3779b97f4a7c15ULL);
        };
        mix(result.sequence);
        mix(result.id);
        mix(static_cast<std::uint64_t>(result.reject));
        mix(static_cast<std::uint64_t>(result.resting));
        mix(static_cast<std::uint64_t>(result.unfilled));
        mix(result.priority_lost ? 1U : 0U);
        mix(result.trades.size());
        trades += result.trades.size();
        rejected += result.accepted() ? 0U : 1U;
        for (const auto& trade : result.trades) {
            mix(trade.maker_id);
            mix(trade.taker_id);
            mix(static_cast<std::uint64_t>(trade.taker_side));
            mix(static_cast<std::uint64_t>(trade.price));
            mix(static_cast<std::uint64_t>(trade.quantity));
        }
    }
    bool operator==(const Observed&) const = default;
};

struct Measurement {
    double commands_per_second{};
    std::int64_t p50_ns{};
    std::int64_t p99_ns{};
    std::int64_t max_ns{};
    std::uint64_t state{};
    std::size_t active{};
    Observed observed;
};

template <typename E>
Measurement measure(const Workload& workload) {
    E throughput_engine;
    for (const auto& command : workload.preload) (void)command.apply(throughput_engine);
    Observed batch_results;
    const auto start = Clock::now();
    for (const auto& command : workload.commands) batch_results.add(command.apply(throughput_engine));
    const auto finish = Clock::now();
    const auto elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(finish - start).count();
    throughput_engine.check_invariants();

    // Separate pass: per-command timestamps must not distort batch throughput.
    E latency_engine;
    for (const auto& command : workload.preload) (void)command.apply(latency_engine);
    std::vector<std::int64_t> latencies;
    latencies.reserve(workload.commands.size());
    Observed latency_results;
    for (const auto& command : workload.commands) {
        const auto before = Clock::now();
        const auto result = command.apply(latency_engine);
        const auto after = Clock::now();
        latencies.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(after - before).count());
        latency_results.add(result);
    }
    latency_engine.check_invariants();
    if (batch_results != latency_results || throughput_engine.state_digest() != latency_engine.state_digest())
        throw std::logic_error("throughput/latency replay mismatch");

    std::sort(latencies.begin(), latencies.end());
    Measurement result;
    result.commands_per_second = static_cast<double>(workload.commands.size()) * 1e9 /
                                 static_cast<double>(elapsed_ns);
    result.p50_ns = latencies[(latencies.size() - 1) * 50 / 100];
    result.p99_ns = latencies[(latencies.size() - 1) * 99 / 100];
    result.max_ns = latencies.back();
    result.state = throughput_engine.state_digest();
    result.active = throughput_engine.active_count();
    result.observed = batch_results;
    return result;
}

std::int64_t clock_overhead() {
    std::vector<std::int64_t> samples;
    samples.reserve(10000);
    for (int i = 0; i < 10000; ++i) {
        const auto before = Clock::now();
        const auto after = Clock::now();
        samples.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(after - before).count());
    }
    std::sort(samples.begin(), samples.end());
    return samples[samples.size() / 2];
}

void print(std::string_view scenario, std::string_view implementation, const Workload& workload,
           std::uint64_t seed, std::size_t trial, std::int64_t clock_ns, const Measurement& result) {
    std::cout << scenario << ',' << implementation << ',' << workload.commands.size() << ',' << seed << ',' << trial
        << ',' << std::fixed << std::setprecision(0) << result.commands_per_second
        << ',' << result.p50_ns << ',' << result.p99_ns << ',' << result.max_ns
        << ',' << clock_ns << ',' << result.observed.trades << ',' << result.observed.rejected
        << ',' << result.active << ',' << std::hex << result.observed.fingerprint << ',' << result.state
        << std::dec << ',' << workload.preload.size() << ',' << workload.limits << ',' << workload.markets
        << ',' << workload.cancels << ',' << workload.amendments << '\n';
}

} // namespace

int main(int argc, char** argv) {
    try {
        std::size_t count = 100000;
        std::size_t trials = 3;
        std::uint64_t seed = 2027;
        std::string selected = "all";
        for (int i = 1; i < argc; ++i) {
            const std::string argument = argv[i];
            if (argument == "--commands" && i + 1 < argc) count = parse_number<std::size_t>(argv[++i]);
            else if (argument == "--trials" && i + 1 < argc) trials = parse_number<std::size_t>(argv[++i]);
            else if (argument == "--seed" && i + 1 < argc) seed = parse_number<std::uint64_t>(argv[++i]);
            else if (argument == "--scenario" && i + 1 < argc) selected = argv[++i];
            else if (argument == "--help") {
                std::cout << "Usage: matching-bench [--commands N] [--trials N] [--seed N] "
                             "[--scenario all|quiet|cancel|burst|wide]\n";
                return 0;
            } else throw std::invalid_argument("unknown or incomplete option: " + argument);
        }
        if (count == 0 || count > 5000000 || trials == 0 || trials > 20)
            throw std::invalid_argument("commands must be 1..5000000; trials must be 1..20");
        if (selected != "all" && selected != "quiet" && selected != "cancel" &&
            selected != "burst" && selected != "wide")
            throw std::invalid_argument("unknown scenario");

        const auto overhead = clock_overhead();
        std::cout << "scenario,implementation,commands,seed,trial,commands_per_second,p50_ns,p99_ns,max_ns,"
                     "clock_pair_p50_ns,trades,rejected,final_active,event_fingerprint,state_digest,"
                     "preload,limit_commands,market_commands,cancel_commands,amend_commands\n";
        for (const auto* scenario : {"quiet", "cancel", "burst", "wide"}) {
            if (selected != "all" && selected != scenario) continue;
            const auto workload = generate(scenario, count, seed);
            for (std::size_t trial = 1; trial <= trials; ++trial) {
                Measurement tree;
                Measurement flat;
                if (trial % 2 != 0) {
                    tree = measure<TreeEngine>(workload);
                    flat = measure<FlatEngine>(workload);
                } else {
                    flat = measure<FlatEngine>(workload);
                    tree = measure<TreeEngine>(workload);
                }
                if (tree.observed != flat.observed || tree.state != flat.state)
                    throw std::logic_error("tree/flat replay mismatch");
                print(scenario, "tree", workload, seed, trial, overhead, tree);
                print(scenario, "flat", workload, seed, trial, overhead, flat);
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 2;
    }
}
