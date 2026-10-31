CXX ?= c++
CPPFLAGS += -Iinclude
CXXFLAGS ?= -O3 -DNDEBUG
CXXFLAGS += -std=c++20 -Wall -Wextra -Wpedantic -Wconversion -Wshadow
BUILD ?= build
HEADERS := $(wildcard include/matching/*.hpp)

.PHONY: all test demo bench sanitize clean

all: $(BUILD)/matching-engine $(BUILD)/matching-tests $(BUILD)/matching-bench

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/matching-engine: src/main.cpp $(HEADERS) | $(BUILD)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $< -o $@ $(LDFLAGS)

$(BUILD)/matching-tests: tests/test_engine.cpp tests/reference.hpp $(HEADERS) | $(BUILD)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $< -o $@ $(LDFLAGS)

$(BUILD)/matching-bench: src/benchmark.cpp $(HEADERS) | $(BUILD)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $< -o $@ $(LDFLAGS)

test: all
	$(BUILD)/matching-tests
	python3 tests/test_cli.py $(BUILD)/matching-engine

demo: $(BUILD)/matching-engine
	$(BUILD)/matching-engine --check --file examples/session.txt

bench: $(BUILD)/matching-bench
	$(BUILD)/matching-bench --commands 100000 --trials 3

sanitize:
	$(MAKE) BUILD=build-sanitize CXXFLAGS='-std=c++20 -O1 -g -Wall -Wextra -Wpedantic -Wconversion -Wshadow -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined' test

clean:
	rm -rf build build-sanitize
