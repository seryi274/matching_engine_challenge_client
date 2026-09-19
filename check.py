#!/usr/bin/env python3
"""
check.py -- try your engine on the practice server.

    python3 check.py

Uploads your code, builds it and runs the 29 correctness tests on the
challenge's practice server, then prints the result. You do NOT need a C++
compiler on your machine: the practice server compiles for you.

Use it as often as you like. The practice server has no rate limit, it does
not benchmark you, and it does not touch the leaderboard.

When the tests pass and you are happy with your engine, submit for real:

    python3 submit.py

That one is scored, rate limited, and is what puts you on the leaderboard.

Set TEAM_NAME and PASSWORD in config.py first -- the same ones you use for
submit.py. Options are passed straight through:

    python3 check.py --dir some/other/project
    python3 check.py --team alpha --password hunter2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import submit  # noqa: E402  (needs SCRIPT_DIR on the path first)

# Practice server, set by the organisers. Override it by adding a line
#   TEST_SERVER = "host:port"
# to config.py, or by passing --server.
PRACTICE_SERVER = "34.243.65.206:8000"


def configured_practice_server(*directories: Path) -> str:
    """TEST_SERVER from the first config.py that defines it, else the default."""
    for directory in directories:
        path = directory / "config.py"
        if not path.is_file():
            continue
        namespace: dict = {}
        try:
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        except Exception:
            continue  # a broken config.py is submit.py's problem to report
        value = str(namespace.get("TEST_SERVER") or "").strip()
        if value:
            return value
    return PRACTICE_SERVER


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and test your matching engine on the practice server."
    )
    parser.add_argument("--team", help="team name (default: TEAM_NAME in config.py)")
    parser.add_argument("--password", help="team password (default: PASSWORD in config.py)")
    parser.add_argument("--dir", help="project root to upload (default: this directory)")
    parser.add_argument("--server", help="practice server host:port (default: TEST_SERVER in config.py)")
    parser.add_argument("--no-wait", action="store_true", help="do not wait for the result")
    args = parser.parse_args(argv)

    root = Path(args.dir).resolve() if args.dir else SCRIPT_DIR
    server = args.server or configured_practice_server(root, SCRIPT_DIR)

    print(f"Practice run on {server} -- not scored, not rate limited, not on the leaderboard.")
    print("When you are ready for the real thing, use: python3 submit.py\n")

    # --no-test: the point of the practice server is that you do not need a
    # local toolchain, so never insist on building here first.
    forwarded = ["--server", server, "--no-test"]
    for flag in ("team", "password", "dir"):
        value = getattr(args, flag)
        if value:
            forwarded += [f"--{flag}", value]
    if args.no_wait:
        forwarded.append("--no-wait")

    return submit.main(forwarded)


if __name__ == "__main__":
    sys.exit(main())
