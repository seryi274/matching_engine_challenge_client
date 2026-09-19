# Matching Engine Challenge

Build a high-performance C++ matching engine. Correctness first, then speed.

A matching engine is the core of every financial exchange. It receives buy and sell orders, keeps an order book per symbol, and decides when trades happen. You implement one, test it locally, and submit it to the challenge server. The server compiles your code in a sandbox, runs 29 correctness tests, benchmarks it, and updates the live leaderboard.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Rules](#rules)
- [Submitting](#submitting)
- [Interface Overview](#interface-overview)
- [Matching Rules](#matching-rules)
- [Scoring](#scoring)
- [Local Development](#local-development)
- [Project Structure](#project-structure)
- [Tips](#tips)

---

## Quick Start

```bash
git clone https://github.com/seryi274/matching_engine_challenge_client.git
cd matching_engine_challenge_client

# Build in Release mode with g++ and Ninja
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++
cmake --build build

./build/test_correctness     # must end with "29/29 tests passed."
./build/benchmark            # local latency and throughput numbers

# Edit config.py (TEAM_NAME, PASSWORD, SERVER), then try it out:
python check.py             # practice server: builds and tests, not scored
python submit.py            # the real thing: scored, ranked, rate limited
```

No compiler on your machine? Skip the two `cmake` lines and use `python check.py`:
the practice server builds and tests your code for you, as often as you like.

`check.py`, `submit.py` and `test.py` need Python 3.8 or newer and nothing else: standard library only, nothing to install.

## Rules

- Teams of up to 5 people.
- Implement the `MatchingEngine` class in `src/matching_engine.cpp`. You may add more `.cpp` and `.h` files directly inside `src/` (no sub-directories); the build picks them up automatically.
- You may add **private members**, helper types and `#include` directives to `include/exchange/matching_engine.h`. Do **not** change the public interface (constructor, method signatures).
- `include/exchange/types.h`, `test/`, `bench/` and `CMakeLists.txt` are the harness. The server uses its own copies, so local edits to them have no effect on your score.
- **Single-threaded only.** No threads, no async, no coroutines, no multi-process tricks.
- The server compiles with `g++ -std=c++20 -O2 -march=native -DNDEBUG -Wall -Werror`. Warnings are errors.
- Remove debug printing before you submit. A test or benchmark run that prints more than 32 MiB is stopped and the submission fails, and printing slows your benchmark anyway.
- You must pass **all 29 correctness tests** to be ranked.
- One submission per team every 5 minutes, and only after your previous submission has finished.

## Submitting

1. Open `config.py` and fill in:

   | Field | Meaning |
   |---|---|
   | `TEAM_NAME` | Letters, digits, `-` or `_`, up to 32 characters. This is the name on the leaderboard. |
   | `PASSWORD` | Chosen by you on your **first** submission. Every later submission for that team name must use the same password. Do not forget it. |
   | `SERVER` | `host:port` given to you by the organisers, for example `3.10.192.154:8000`. |

2. Run `python submit.py`. The script:
   - builds and runs the correctness tests locally first (skip with `--no-test`; upload despite a local failure with `--force`),
   - uploads every `.cpp .cc .h .hpp .hh .inl .ipp` file directly inside `src/` plus `include/exchange/matching_engine.h`, and nothing else,
   - waits and prints the server's build log, test count and benchmark table as they arrive (`--no-wait` returns right after the upload).

3. Watch the leaderboard. The URL is in `leaderboard.txt`. Your latest submission is also at `http://SERVER/api/status/TEAM_NAME`.

You can resubmit as often as the rate limit allows. Your **best** passing submission is the one that counts.

Common rejections:

| Message | What to do |
|---|---|
| `Incorrect password for this team` | That team name is already registered with a different password. Use the right one or pick another name. |
| `Rate limited` | Wait for the number of seconds shown in the message. |
| `Your submission #N is still ...` | Your previous submission is still waiting or running. Wait for its result, then submit again. |
| `Not allowed: ...` | Only files directly inside `src/` and `include/exchange/matching_engine.h` are accepted. Remove the file. |
| `Client credentials rejected` | Your copy of `submit.py` is out of date. Run `git pull`. |

## Interface Overview

Your engine must conform to the interface defined in two header files.

### `include/exchange/types.h` (do not modify)

| Type | Purpose |
|------|---------|
| `Side` | Enum: `Buy` or `Sell` (uint8_t). |
| `OrderStatus` | Enum: `Accepted`, `Filled`, `Cancelled`, `Rejected`. |
| `OrderRequest` | Input to `addOrder()`. Fields: `symbol` (string), `side`, `price` (int64_t ticks), `quantity` (uint32_t lots). |
| `OrderAck` | Returned by `addOrder()`. Fields: `order_id` (uint64_t), `status`. |
| `Trade` | Emitted via `onTrade()` callback. Fields: `buy_order_id`, `sell_order_id`, `symbol`, `price`, `quantity`. |
| `OrderUpdate` | Emitted via `onOrderUpdate()` callback. Fields: `order_id`, `status`, `remaining_quantity`. |
| `PriceLevel` | Used by `getBookSnapshot()`. Fields: `price`, `total_quantity`, `order_count`. |
| `Listener` | Abstract class with virtual `onTrade(const Trade&)` and `onOrderUpdate(const OrderUpdate&)`. The tests and the benchmark implement this. |

### `include/exchange/matching_engine.h` (public interface fixed)

| Method | Signature | Description |
|--------|-----------|-------------|
| Constructor | `MatchingEngine(Listener* listener)` | Initialize with a callback listener. |
| `addOrder` | `OrderAck addOrder(const OrderRequest&)` | Submit a new limit order. Assign ID, match, rest remainder. |
| `cancelOrder` | `bool cancelOrder(uint64_t order_id)` | Cancel a resting order. Returns false if not found. |
| `amendOrder` | `bool amendOrder(uint64_t order_id, int64_t new_price, uint32_t new_quantity)` | Modify a resting order. May trigger matching. |
| `getBookSnapshot` | `vector<PriceLevel> getBookSnapshot(const string& symbol, Side side) const` | Snapshot of one side of the book. Not performance-critical. |
| `getOrderCount` | `uint64_t getOrderCount() const` | Total resting orders. Not performance-critical. |

Order IDs are monotonically increasing, starting at 1. Rejected orders get `order_id = 0`.

The class provides two private members you can use: `listener_` (the callback pointer) and `next_order_id_` (initialized to 1). Add any additional data structures you need as private members below the `// TODO` comment.

## Matching Rules

Your engine must implement **price-time priority (FIFO)** matching:

1. **Price priority.** A buy order matches against the lowest-priced resting sell whose price is at or below the buy's price. A sell order matches against the highest-priced resting buy whose price is at or above the sell's price.
2. **Time priority.** At the same price level, the order that arrived earliest is matched first (FIFO).
3. **Execution price.** The trade price is always the **resting** (passive) order's price, not the incoming (aggressive) order's price.
4. **Greedy matching.** Fill as much as possible immediately. If the incoming order's quantity exceeds the resting order's quantity, fill the resting order completely and continue to the next resting order (or next price level).
5. **Partial fills.** If an incoming order is only partially filled, the remainder rests on the book with status `Accepted`.
6. **Rejection.** Reject orders with `price <= 0`, `quantity == 0`, or empty `symbol`. Rejected orders return `OrderAck{0, Rejected}`.
7. **Cancellation.** `cancelOrder(id)` removes the order from the book and emits an `OrderUpdate` with status `Cancelled`. Returns false if the order does not exist or is already filled/cancelled.
8. **Amendment.** `amendOrder(id, new_price, new_quantity)` modifies a resting order:
   - If the **price changes**: the order **loses** time priority.
   - If the **quantity increases** (price unchanged): the order **loses** time priority.
   - If **only the quantity decreases** (price unchanged): the order **keeps** time priority.
   - After amendment, the order may match if prices now cross.
   - Returns false if the order is not found, or if `new_price <= 0` or `new_quantity == 0`.
9. **Callback ordering.** During a single `addOrder` call that matches N resting orders, call `onTrade()` and `onOrderUpdate()` for each fill in price-time priority order, then `onOrderUpdate()` for the aggressor order.
10. **Symbol isolation.** Orders for different symbols never interact.

The 29 tests in `test/test_correctness.cpp` are the specification. If you are unsure about an edge case, the test tells you.

## Scoring

### Correctness (pass/fail)

All 29 tests must pass. A submission that fails any test is recorded but never ranked.

### Performance (ranking)

The server runs the benchmark binary three times and keeps the best run. Each run executes, per scenario, a 500,000-operation warm-up followed by 3 iterations of 2,000,000 operations and reports the median iteration.

| Scenario | Weight | Description |
|----------|--------|-------------|
| Uniform | 30% | Random buy/sell in a narrow price band. Baseline throughput. |
| Realistic | 40% | Market microstructure: bursts, pressure, reversals. |
| Adversarial | 30% | Deep book, wide prices, sweeping orders. Worst-case. |

Operations are roughly 70% adds, 20-25% cancels and 5-10% amends across 5 symbols.

**Leaderboard rank = weighted throughput = 0.30 * uniform + 0.40 * realistic + 0.30 * adversarial**, in operations per second (higher is better). Weighted mean and p99 latency with the same weights are shown next to it.

## Local Development

Requirements: cmake 3.16+, g++ 13+ (C++20) and Ninja.

```bash
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++
cmake --build build

./build/test_correctness
./build/benchmark
```

This matches the server toolchain (`g++ -std=c++20 -O2 -march=native
-DNDEBUG -Wall -Werror`) as closely as CMake's Release flags allow.

### No toolchain? Use the practice server

If you cannot build locally -- no compiler, a locked-down laptop, a Windows
setup that fights you -- let the practice server do it:

```bash
python check.py
```

It uploads your `src/` and `include/`, compiles them with the same g++ 13 the
scoring server uses, runs all 29 correctness tests and prints the result,
usually in under ten seconds. No rate limit, no benchmark, no leaderboard
entry: use it as your edit-compile-test loop and keep `submit.py` for when you
want a score.

## Project Structure

```
matching_engine_challenge_client/
|-- include/exchange/
|   |-- types.h                  # Data types, Listener interface (DO NOT MODIFY)
|   |-- matching_engine.h        # MatchingEngine class (public interface fixed; add private members)
|-- src/
|   |-- matching_engine.cpp      # YOUR IMPLEMENTATION (edit this, add files next to it)
|-- test/
|   |-- test_correctness.cpp     # 29 correctness tests (the specification)
|-- bench/
|   |-- benchmark.cpp            # Benchmark harness (3 scenarios)
|   |-- order_generator.h/.cpp   # Deterministic order stream generator
|-- CMakeLists.txt               # Build (C++20, -O2 -march=native)
|-- config.py                    # TEAM_NAME, PASSWORD, SERVER
|-- check.py                     # Build and test on the practice server (not scored)
|-- submit.py                    # Upload src/ + matching_engine.h and stream the result
|-- test.py                      # Local build + correctness tests
|-- leaderboard.txt              # Leaderboard URL
```

## Tips

1. **Start with correctness.** A fast engine that produces wrong results scores zero. Get all 29 tests passing first.
2. **Use a profiler.** `perf stat ./build/benchmark` (Linux) or Instruments (macOS) shows where time is actually spent. The bottleneck is almost never where you think.
3. **Think about memory.** What data structure holds your price levels (`std::map`, sorted vector, direct-indexed array)? What holds orders at a level (`std::list`, `std::deque`, intrusive list)? How many heap allocations per `addOrder`, and can you get that to zero?
4. **Intern your strings.** Map each symbol to an integer ID once in `addOrder`, then use the integer internally.
5. **Know your data.** Benchmark prices centre around tick 10,000 with bounded drift. If prices are bounded, a direct-indexed array is O(1) lookup with zero allocations.
6. **Measure before and after every change.** Run the benchmark, write down the numbers, make one change, run again. If no improvement, revert.
7. **Compile in Release mode.** Debug builds (`-O0`) can be 5-10x slower.
8. **Read the tests.** `test/test_correctness.cpp` is the specification.
9. **Do not optimize everything.** `getBookSnapshot` and `getOrderCount` are never called during benchmarking. Focus on `addOrder`, `cancelOrder` and `amendOrder`.
