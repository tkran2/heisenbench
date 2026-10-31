#pragma once

#include "matching/types.hpp"

#include <algorithm>
#include <limits>
#include <vector>

// Deliberately slow, structurally independent oracle: an unsorted vector and a
// full scan to select every maker. It does not use Engine or its level storage.
class Reference {
public:
    matching::Outcome submit(const matching::NewOrder& input) {
        using namespace matching;
        Outcome result;
        result.sequence = ++sequence_;
        result.id = input.id;
        if (!input.id) result.reject = Reject::InvalidId;
        else if (input.side != Side::Buy && input.side != Side::Sell) result.reject = Reject::InvalidSide;
        else if (input.type != OrderType::Limit && input.type != OrderType::Market) result.reject = Reject::InvalidType;
        else if ((input.type == OrderType::Limit && input.price <= 0) ||
                 (input.type == OrderType::Market && input.price != 0)) result.reject = Reject::InvalidPrice;
        else if (input.quantity <= 0 || input.quantity > max_order_quantity) result.reject = Reject::InvalidQuantity;
        else if (find(input.id) != orders_.end()) result.reject = Reject::DuplicateId;
        else if (orders_.size() >= max_live_orders) result.reject = Reject::Capacity;
        if (result.accepted()) match(input, result);
        return result;
    }

    matching::Outcome cancel(matching::OrderId id) {
        matching::Outcome result;
        result.sequence = ++sequence_;
        result.id = id;
        const auto it = find(id);
        if (it == orders_.end()) result.reject = matching::Reject::UnknownOrder;
        else orders_.erase(it);
        return result;
    }

    matching::Outcome amend(matching::OrderId id, matching::Price price, matching::Quantity quantity) {
        using namespace matching;
        Outcome result;
        result.sequence = ++sequence_;
        result.id = id;
        const auto it = find(id);
        if (it == orders_.end()) result.reject = Reject::UnknownOrder;
        else if (price <= 0) result.reject = Reject::InvalidPrice;
        else if (quantity <= 0 || quantity > max_order_quantity) result.reject = Reject::InvalidQuantity;
        else if (price == it->price && quantity <= it->quantity) {
            it->quantity = quantity;
            result.resting = quantity;
        } else {
            const auto side = it->side;
            orders_.erase(it);
            result.priority_lost = true;
            match({id, side, OrderType::Limit, price, quantity}, result);
        }
        return result;
    }

    [[nodiscard]] std::vector<matching::RestingOrder> orders() const {
        auto result = orders_;
        std::sort(result.begin(), result.end(), [](const auto& left, const auto& right) {
            if (left.side != right.side) return left.side == matching::Side::Buy;
            if (left.price != right.price)
                return left.side == matching::Side::Buy ? left.price > right.price : left.price < right.price;
            return left.priority < right.priority;
        });
        return result;
    }

private:
    std::vector<matching::RestingOrder>::iterator find(matching::OrderId id) {
        return std::find_if(orders_.begin(), orders_.end(),
            [id](const auto& order) { return order.id == id; });
    }

    void match(const matching::NewOrder& input, matching::Outcome& result) {
        using namespace matching;
        auto remaining = input.quantity;
        while (remaining > 0) {
            auto selected = orders_.size();
            for (std::size_t i = 0; i < orders_.size(); ++i) {
                const auto& order = orders_[i];
                if (order.side == input.side) continue;
                if (input.type == OrderType::Limit &&
                    ((input.side == Side::Buy && order.price > input.price) ||
                     (input.side == Side::Sell && order.price < input.price))) continue;
                if (selected == orders_.size() ||
                    (input.side == Side::Buy && order.price < orders_[selected].price) ||
                    (input.side == Side::Sell && order.price > orders_[selected].price) ||
                    (order.price == orders_[selected].price && order.priority < orders_[selected].priority))
                    selected = i;
            }
            if (selected == orders_.size()) break;
            auto& maker = orders_[selected];
            const auto size = std::min(maker.quantity, remaining);
            result.trades.push_back({maker.id, input.id, input.side, maker.price, size});
            maker.quantity -= size;
            remaining -= size;
            if (maker.quantity == 0) orders_.erase(orders_.begin() + static_cast<std::ptrdiff_t>(selected));
        }
        if (remaining > 0 && input.type == OrderType::Limit) {
            orders_.push_back({input.id, input.side, input.price, remaining, result.sequence});
            result.resting = remaining;
        } else if (input.type == OrderType::Market) result.unfilled = remaining;
    }

    std::vector<matching::RestingOrder> orders_;
    std::uint64_t sequence_{};
};
