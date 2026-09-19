# AGENTS.md - Matching Engine Challenge Client

## Project Overview
This repository is the participant side of the Matching Engine Challenge: the fixed C++ interface, a skeleton implementation, the 29 correctness tests, the benchmark, and the scripts to test locally and submit to the challenge server.

## Key Conventions & Constraints

### 1. Fixed Interface (Strict)
- `include/exchange/types.h` must not change. The server compiles against its own copy.
- The public interface of `MatchingEngine` in `include/exchange/matching_engine.h` (constructor, `addOrder`, `cancelOrder`, `amendOrder`, `getBookSnapshot`, `getOrderCount`) must not change. Private members, helper types and `#include`s may be added.
- `test/`, `bench/` and `CMakeLists.txt` are the harness. Local edits do not affect scoring.

### 2. What Gets Submitted
- Every `.cpp .cc .h .hpp .hh .inl .ipp` file directly inside `src/` (no sub-directories) plus `include/exchange/matching_engine.h`. Nothing else is uploaded or accepted.
- The engine must be single-threaded: no threads, async, coroutines or extra processes.
- The server builds with `g++ -std=c++20 -O2 -march=native -DNDEBUG -Wall -Werror`; warnings are errors.

### 3. Commands
- Build and run tests locally: `python test.py` (or `cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build && ./build/test_correctness`).
- Benchmark locally: `./build/benchmark`.
- Submit: fill in `config.py` (`TEAM_NAME`, `PASSWORD`, `SERVER`) and run `python submit.py`. The password is set on the team's first submission and must be reused.
- `submit.py` and `test.py` use only the Python standard library.

### 4. Guidelines
- Correctness first: all 29 tests must pass before a submission is ranked.
- Do NOT use emojis in code, commits, or documentation.
