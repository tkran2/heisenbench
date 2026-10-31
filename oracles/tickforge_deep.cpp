// Deep oracle for TickForge: ring-buffer semantics, a concurrent stress test that is
// run both under ThreadSanitizer and natively for longer, and feed trust-gate rules.
//
//   tickforge_deep          short run (use under -fsanitize=thread)
//   tickforge_deep --long   many more items, natively compiled
// Exit status 1 on the first violated property.

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>

#include "tickforge.hpp"

using namespace tickforge;

namespace {

void require(bool cond, const char* what) {
    if (!cond) {
        std::printf("FAIL %s\n", what);
        std::exit(1);
    }
}

// A cache-line-sized item whose fields must stay consistent with each other, so a
// torn or stale slot read is detectable without a sanitizer.
struct Item {
    std::uint64_t seq;
    std::uint64_t words[7];
};
static_assert(sizeof(Item) == 64);

Item make(std::uint64_t seq) {
    Item it{seq, {}};
    std::uint64_t z = seq * 0x9E3779B97F4A7C15ULL + 1;
    for (auto& w : it.words) {
        z ^= z >> 31;
        z *= 0xBF58476D1CE4E5B9ULL;
        w = z;
    }
    return it;
}

void ring_semantics() {
    for (std::size_t cap : {2u, 4u, 16u}) {
        SpscRing<Item> ring(cap);
        for (std::size_t i = 0; i < cap; ++i) require(ring.push(make(i)), "push into a non-full ring failed");
        require(!ring.push(make(999)), "push into a full ring succeeded");
        Item out{};
        for (std::size_t i = 0; i < cap; ++i) {
            require(ring.pop(out), "pop from a non-empty ring failed");
            const Item want = make(i);
            require(std::memcmp(&out, &want, sizeof(Item)) == 0, "ring returned the wrong item or out of order");
        }
        require(!ring.pop(out), "pop from an empty ring succeeded");
    }
}

void stress(std::size_t cap, std::uint64_t count) {
    SpscRing<Item> ring(cap);
    std::atomic<bool> ok{true};
    std::thread producer([&] {
        for (std::uint64_t i = 0; i < count; ++i) {
            const Item it = make(i);
            while (!ring.push(it)) std::this_thread::yield();
        }
    });
    std::thread consumer([&] {
        Item out{};
        for (std::uint64_t i = 0; i < count; ++i) {
            while (!ring.pop(out)) std::this_thread::yield();
            const Item want = make(i);
            if (std::memcmp(&out, &want, sizeof(Item)) != 0) ok.store(false);
        }
    });
    producer.join();
    consumer.join();
    require(ok.load(), "concurrent stress: consumer saw a lost, duplicated, stale or torn item");
}

std::array<std::uint8_t, 64> frame(Kind kind, std::uint64_t gen, std::uint64_t seq) {
    if (kind == Kind::heartbeat) return encode({kind, gen, seq, 0, 0, 0, 0});
    return encode({kind, gen, seq, 100, 102, 5, 7});
}

void trust_gate() {
    FeedState s;
    require(s.ingest(frame(Kind::snapshot, 1, 0)) == Action::published && s.trusted(), "snapshot did not open the gate");
    require(s.ingest(frame(Kind::update, 1, 1)) == Action::published, "in-order update not published");
    // A new generation must close the gate until its own snapshot arrives.
    require(s.ingest(frame(Kind::update, 2, 5)) == Action::fenced, "update from a new generation was not fenced");
    require(!s.trusted(), "gate stayed open after a generation change without a snapshot");
    bool threw = false;
    try {
        (void)s.quote();
    } catch (const std::logic_error&) {
        threw = true;
    }
    require(threw, "quote() served data behind a closed gate");
    // Recovery is a snapshot from a newer generation.
    require(s.ingest(frame(Kind::snapshot, 3, 0)) == Action::published && s.trusted(), "new snapshot did not reopen");
    // A gap closes the gate.
    require(s.ingest(frame(Kind::update, 3, 2)) == Action::fenced && !s.trusted(), "sequence gap did not close the gate");
    // Malformed input closes the gate.
    FeedState m;
    m.ingest(frame(Kind::snapshot, 1, 0));
    auto bad = frame(Kind::update, 1, 1);
    bad[30] ^= 1;
    require(m.ingest(bad) == Action::fenced && !m.trusted(), "corrupt frame did not close the gate");
    // Old generations are ignored.
    FeedState o;
    o.ingest(frame(Kind::snapshot, 3, 0));
    require(o.ingest(frame(Kind::update, 2, 1)) == Action::old_generation && o.trusted(), "old generation mishandled");
}

}  // namespace

int main(int argc, char** argv) {
    const bool longer = argc > 1 && std::string(argv[1]) == "--long";
    ring_semantics();
    trust_gate();
    const std::uint64_t n = longer ? 3'000'000 : 150'000;
    for (std::size_t cap : {2u, 8u, 64u}) stress(cap, n);
    std::printf("OK ring semantics, trust gate, stress %llu items x 3 capacities\n", static_cast<unsigned long long>(n));
    return 0;
}
