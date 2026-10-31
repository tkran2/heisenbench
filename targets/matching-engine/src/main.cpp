#include "matching/command.hpp"
#include "matching/engine.hpp"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void print_help() {
    std::cout <<
        "LIMIT id BUY|SELL price_ticks quantity\n"
        "MARKET id BUY|SELL quantity\n"
        "CANCEL id\n"
        "AMEND id price_ticks new_remaining_quantity\n"
        "BOOK    # Aggregate levels, best price first on each side\n"
        "ORDERS  # Individual orders in matching priority\n"
        "CHECK   # Verify book and ID-index invariants\n"
        "HELP\n"
        "QUIT\n";
}

struct Options {
    std::string implementation{"tree"};
    std::string file;
    bool check{};
    bool quiet{};
};

template <typename EngineType>
int run(std::istream& input, const Options& options) {
    EngineType engine;
    matching::Digest events;
    std::uint64_t trade_count = 0;
    std::uint64_t rejected_count = 0;
    std::size_t line_number = 0;
    bool stopped = false;

    for (std::string line; !stopped && std::getline(input, line);) {
        ++line_number;
        try {
            const auto parsed = matching::parse_command(std::move(line));
            if (!parsed) continue;
            const auto& command = *parsed;
            switch (command.action) {
            case matching::Action::Book: {
                if (options.quiet) break;
                const auto levels = engine.book();
                if (levels.empty()) std::cout << "BOOK EMPTY\n";
                for (const auto& level : levels)
                    std::cout << "LEVEL " << matching::side_name(level.side) << ' '
                        << level.price << ' ' << level.quantity << ' ' << level.order_count << '\n';
                break;
            }
            case matching::Action::Orders:
                if (!options.quiet) {
                    if (engine.active_count() == 0) std::cout << "ORDERS EMPTY\n";
                    for (const auto& order : engine.orders())
                        std::cout << "ORDER " << order.id << ' ' << matching::side_name(order.side)
                            << ' ' << order.price << ' ' << order.quantity << ' ' << order.priority << '\n';
                }
                break;
            case matching::Action::Check:
                engine.check_invariants();
                if (!options.quiet) std::cout << "CHECK OK\n";
                break;
            case matching::Action::Help:
                if (!options.quiet) print_help();
                break;
            case matching::Action::Quit:
                stopped = true;
                break;
            default: {
                const auto result = command.apply(engine);
                events.add(result);
                trade_count += result.trades.size();
                rejected_count += result.accepted() ? 0U : 1U;
                if (!options.quiet) {
                    if (result.accepted())
                        std::cout << "ACCEPT " << result.sequence << ' ' << result.id
                            << " resting=" << result.resting << " unfilled=" << result.unfilled
                            << " priority_lost=" << result.priority_lost << '\n';
                    else
                        std::cout << "REJECT " << result.sequence << ' ' << result.id << ' '
                            << matching::reject_name(result.reject) << '\n';
                    for (const auto& trade : result.trades)
                        std::cout << "TRADE " << result.sequence << ' ' << trade.maker_id << ' '
                            << trade.taker_id << ' ' << matching::side_name(trade.taker_side)
                            << ' ' << trade.price << ' ' << trade.quantity << '\n';
                }
                if (options.check) engine.check_invariants();
                break;
            }
            }
        } catch (const std::exception& error) {
            std::cerr << "line " << line_number << ": " << error.what() << '\n';
            return 2;
        }
    }

    engine.check_invariants();
    std::cout << "SUMMARY commands=" << engine.sequence() << " active=" << engine.active_count()
        << " trades=" << trade_count << " rejected=" << rejected_count
        << " events=" << std::hex << events.value() << " state=" << engine.state_digest()
        << std::dec << '\n';
    return 0;
}

} // namespace

int main(int argc, char** argv) {
    try {
        Options options;
        for (int i = 1; i < argc; ++i) {
            const std::string argument = argv[i];
            if (argument == "--impl" && i + 1 < argc) options.implementation = argv[++i];
            else if (argument == "--file" && i + 1 < argc) options.file = argv[++i];
            else if (argument == "--check") options.check = true;
            else if (argument == "--quiet") options.quiet = true;
            else if (argument == "--help") {
                std::cout << "Usage: matching-engine [--impl tree|flat] [--file PATH] [--check] [--quiet]\n";
                print_help();
                return 0;
            } else throw std::invalid_argument("unknown or incomplete option: " + argument);
        }
        if (options.implementation != "tree" && options.implementation != "flat")
            throw std::invalid_argument("--impl must be tree or flat");

        std::ifstream file;
        std::istream* input = &std::cin;
        if (!options.file.empty() && options.file != "-") {
            file.open(options.file);
            if (!file) throw std::runtime_error("cannot open: " + options.file);
            input = &file;
        }
        return options.implementation == "tree" ? run<matching::TreeEngine>(*input, options)
                                                : run<matching::FlatEngine>(*input, options);
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 2;
    }
}
