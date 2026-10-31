#include "matching/command.hpp"
#include "matching/engine.hpp"
#include "reference.hpp"

#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>

namespace {

std::size_t assertions = 0;
std::size_t scenarios = 0;

void check(bool condition, const char* expression, int line) {
    ++assertions;
    if (!condition) throw std::runtime_error("line " + std::to_string(line) + ": " + expression);
}
#define CHECK(...) check((__VA_ARGS__), #__VA_ARGS__, __LINE__)

using namespace matching;

NewOrder limit(OrderId id, Side side, Price price, Quantity quantity) {
    return {id, side, OrderType::Limit, price, quantity};
}

NewOrder market(OrderId id, Side side, Quantity quantity) {
    return {id, side, OrderType::Market, 0, quantity};
}

template <typename E, typename F>
void scenario(std::string_view name, F&& function) {
    E engine;
    try {
        function(engine);
        engine.check_invariants();
        ++scenarios;
    } catch (const std::exception& error) {
        throw std::runtime_error(std::string(name) + ": " + error.what());
    }
}

template <typename E>
void unit_tests() {
    scenario<E>("empty book", [](auto& e) {
        CHECK(e.book().empty());
        CHECK(e.orders().empty());
        CHECK(e.cancel(1).reject == Reject::UnknownOrder);
        CHECK(e.amend(1, 100, 1).reject == Reject::UnknownOrder);
    });
    scenario<E>("best ask before older expensive ask", [](auto& e) {
        e.submit(limit(1, Side::Sell, 101, 5));
        e.submit(limit(2, Side::Sell, 100, 5));
        const auto result = e.submit(limit(3, Side::Buy, 101, 7));
        CHECK(result.trades == std::vector<Trade>{{2, 3, Side::Buy, 100, 5}, {1, 3, Side::Buy, 101, 2}});
        CHECK(e.orders() == std::vector<RestingOrder>{{1, Side::Sell, 101, 3, 1}});
    });
    scenario<E>("best bid and maker price", [](auto& e) {
        e.submit(limit(1, Side::Buy, 99, 3));
        e.submit(limit(2, Side::Buy, 100, 4));
        const auto result = e.submit(limit(3, Side::Sell, 98, 5));
        CHECK(result.trades == std::vector<Trade>{{2, 3, Side::Sell, 100, 4}, {1, 3, Side::Sell, 99, 1}});
    });
    scenario<E>("FIFO and partial maker", [](auto& e) {
        e.submit(limit(1, Side::Sell, 100, 2));
        e.submit(limit(2, Side::Sell, 100, 3));
        const auto result = e.submit(market(3, Side::Buy, 4));
        CHECK(result.trades == std::vector<Trade>{{1, 3, Side::Buy, 100, 2}, {2, 3, Side::Buy, 100, 2}});
        CHECK(e.book() == std::vector<LevelView>{{Side::Sell, 100, 1, 1}});
    });
    scenario<E>("unfilled limit rests", [](auto& e) {
        e.submit(limit(1, Side::Sell, 100, 2));
        const auto result = e.submit(limit(2, Side::Buy, 100, 5));
        CHECK(result.resting == 3);
        CHECK(result.unfilled == 0);
        CHECK(e.orders() == std::vector<RestingOrder>{{2, Side::Buy, 100, 3, 2}});
    });
    scenario<E>("market remainder canceled", [](auto& e) {
        CHECK(e.submit(market(1, Side::Buy, 5)).unfilled == 5);
        e.submit(limit(2, Side::Sell, 100, 2));
        const auto result = e.submit(market(3, Side::Buy, 7));
        CHECK(result.unfilled == 5);
        CHECK(result.resting == 0);
        CHECK(e.active_count() == 0);
    });
    scenario<E>("noncrossing limit", [](auto& e) {
        e.submit(limit(1, Side::Sell, 101, 2));
        CHECK(e.submit(limit(2, Side::Buy, 100, 2)).trades.empty());
        CHECK(e.book() == std::vector<LevelView>{{Side::Buy, 100, 2, 1}, {Side::Sell, 101, 2, 1}});
    });
    scenario<E>("cancel middle of FIFO", [](auto& e) {
        for (OrderId id = 1; id <= 3; ++id) e.submit(limit(id, Side::Buy, 100, 2));
        CHECK(e.cancel(2).accepted());
        const auto result = e.submit(market(4, Side::Sell, 4));
        CHECK(result.trades == std::vector<Trade>{{1, 4, Side::Sell, 100, 2}, {3, 4, Side::Sell, 100, 2}});
    });
    scenario<E>("reduction retains priority", [](auto& e) {
        e.submit(limit(1, Side::Sell, 100, 5));
        e.submit(limit(2, Side::Sell, 100, 3));
        CHECK(!e.amend(1, 100, 2).priority_lost);
        CHECK(e.orders()[0].priority == 1);
        const auto result = e.submit(market(3, Side::Buy, 3));
        CHECK(result.trades == std::vector<Trade>{{1, 3, Side::Buy, 100, 2}, {2, 3, Side::Buy, 100, 1}});
    });
    scenario<E>("increase loses priority", [](auto& e) {
        e.submit(limit(1, Side::Buy, 100, 2));
        e.submit(limit(2, Side::Buy, 100, 3));
        CHECK(e.amend(1, 100, 4).priority_lost);
        const auto result = e.submit(market(3, Side::Sell, 4));
        CHECK(result.trades == std::vector<Trade>{{2, 3, Side::Sell, 100, 3}, {1, 3, Side::Sell, 100, 1}});
    });
    scenario<E>("same size retains priority", [](auto& e) {
        e.submit(limit(1, Side::Buy, 100, 2));
        CHECK(!e.amend(1, 100, 2).priority_lost);
        CHECK(e.orders()[0].priority == 1);
    });
    scenario<E>("price amendment can immediately trade", [](auto& e) {
        e.submit(limit(1, Side::Buy, 100, 3));
        e.submit(limit(2, Side::Sell, 110, 5));
        const auto result = e.amend(2, 100, 4);
        CHECK(result.priority_lost);
        CHECK(result.trades == std::vector<Trade>{{1, 2, Side::Sell, 100, 3}});
        CHECK(result.resting == 1);
        CHECK(e.orders() == std::vector<RestingOrder>{{2, Side::Sell, 100, 1, 3}});
    });
    scenario<E>("rejects preserve orders", [](auto& e) {
        e.submit(limit(1, Side::Buy, 100, 2));
        const auto before = e.orders();
        CHECK(e.submit(limit(1, Side::Sell, 100, 10)).reject == Reject::DuplicateId);
        CHECK(e.submit(limit(0, Side::Buy, 100, 1)).reject == Reject::InvalidId);
        CHECK(e.submit(limit(2, Side::Buy, 0, 1)).reject == Reject::InvalidPrice);
        CHECK(e.submit(limit(2, Side::Buy, 100, 0)).reject == Reject::InvalidQuantity);
        CHECK(e.submit(limit(2, Side::Buy, 100, -1)).reject == Reject::InvalidQuantity);
        CHECK(e.submit(limit(2, Side::Buy, 100, max_order_quantity + 1)).reject == Reject::InvalidQuantity);
        CHECK(e.submit({2, Side::Buy, OrderType::Market, 100, 1}).reject == Reject::InvalidPrice);
        CHECK(e.submit({2, static_cast<Side>(2), OrderType::Limit, 100, 1}).reject == Reject::InvalidSide);
        CHECK(e.submit({2, Side::Buy, static_cast<OrderType>(2), 100, 1}).reject == Reject::InvalidType);
        CHECK(e.amend(1, 0, 1).reject == Reject::InvalidPrice);
        CHECK(e.amend(1, 100, 0).reject == Reject::InvalidQuantity);
        CHECK(e.orders() == before);
        CHECK(e.sequence() == 12);
    });
    scenario<E>("ID reusable after completion", [](auto& e) {
        e.submit(limit(1, Side::Sell, 100, 1));
        e.submit(market(2, Side::Buy, 1));
        CHECK(e.submit(limit(1, Side::Buy, 100, 1)).accepted());
    });
    scenario<E>("integer price and aggregate boundaries", [](auto& e) {
        const auto high = std::numeric_limits<Price>::max();
        e.submit(limit(1, Side::Sell, high, max_order_quantity));
        e.submit(limit(2, Side::Sell, high, max_order_quantity));
        CHECK(e.book()[0].quantity == 2 * max_order_quantity);
        CHECK(e.submit(limit(3, Side::Buy, high, 1)).trades[0].price == high);
    });
    scenario<E>("index stability under level relocation", [](auto& e) {
        for (OrderId id = 1; id <= 600; ++id) {
            e.submit(limit(id, Side::Buy, 8000 + static_cast<Price>(id), 5));
            e.submit(limit(id + 1000, Side::Sell, 10000 + static_cast<Price>(id), 5));
        }
        for (OrderId id = 1; id <= 600; id += 3) {
            CHECK(e.cancel(id).accepted());
            CHECK(e.amend(id + 1000, 11000 + static_cast<Price>(id), 7).accepted());
        }
        CHECK(e.active_count() == 1000);
    });
}

void differential(std::uint64_t seed, std::size_t command_count) {
    TreeEngine tree;
    FlatEngine flat;
    Reference reference;
    std::mt19937_64 random(seed);
    OrderId next_id = 1;

    for (std::size_t step = 0; step < command_count; ++step) {
        const auto existing = reference.orders();
        const auto choose_id = [&]() -> OrderId {
            if (!existing.empty() && random() % 5 != 0) return existing[random() % existing.size()].id;
            return next_id + 1000;
        };
        Command command;
        const auto choice = random() % 100;
        const auto side = random() % 2 == 0 ? Side::Buy : Side::Sell;
        const auto price = 10000 + static_cast<Price>(random() % 41) - 20;
        const auto quantity = static_cast<Quantity>(random() % 30 + 1);
        if (choice < 65) {
            auto id = next_id++;
            if (!existing.empty() && random() % 12 == 0) id = existing[random() % existing.size()].id;
            command.order = choice < 50 ? limit(id, side, price, quantity) : market(id, side, quantity);
            if (random() % 40 == 0) command.order.quantity = 0;
        } else if (choice < 85) {
            command.action = Action::Cancel;
            command.order.id = choose_id();
        } else {
            command.action = Action::Amend;
            command.order = limit(choose_id(), side, price, quantity);
            if (random() % 30 == 0) command.order.price = 0;
        }

        const auto expected = command.apply(reference);
        const auto actual_tree = command.apply(tree);
        const auto actual_flat = command.apply(flat);
        if (actual_tree != expected || actual_flat != expected ||
            tree.orders() != reference.orders() || flat.orders() != reference.orders()) {
            throw std::runtime_error("differential mismatch: seed=" + std::to_string(seed) +
                                     " step=" + std::to_string(step));
        }
        ++assertions;
        if (command.action == Action::Submit && expected.accepted()) {
            Quantity filled = 0;
            for (const auto& trade : expected.trades) filled += trade.quantity;
            CHECK(filled + expected.resting + expected.unfilled == command.order.quantity);
        }
        if (step % 64 == 0) {
            tree.check_invariants();
            flat.check_invariants();
            CHECK(tree.book() == flat.book());
            CHECK(tree.state_digest() == flat.state_digest());
        }
    }
    tree.check_invariants();
    flat.check_invariants();
    ++scenarios;
}

void parser_tests() {
    CHECK(!parse_command("  # comment"));
    CHECK(parse_command("LIMIT 42 BUY 100 3 # valid")->order.id == 42);
    CHECK(parse_command("MARKET 43 SELL 5")->order.type == OrderType::Market);
    CHECK(parse_command("AMEND 42 101 2")->action == Action::Amend);
    for (const auto* bad : {"LIMIT -1 BUY 1 1", "LIMIT 1 BUY 1 1 extra", "MARKET 1 buy 1",
                            "LIMIT 1 BUY 99999999999999999999999 1", "CANCEL 1x", "NOPE", "BOOK extra"}) {
        bool threw = false;
        try { (void)parse_command(bad); }
        catch (const std::invalid_argument&) { threw = true; }
        CHECK(threw);
    }
    ++scenarios;
}

} // namespace

int main() {
    try {
        unit_tests<TreeEngine>();
        unit_tests<FlatEngine>();
        parser_tests();
        for (const auto seed : {17ULL, 42ULL, 2027ULL}) differential(seed, 15000);
        std::cout << "PASS " << scenarios << " scenarios, " << assertions
                  << " assertions, 45000 randomized commands against independent reference\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
