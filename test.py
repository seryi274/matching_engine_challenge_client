#!/usr/bin/env python3
"""
Build in Release mode and run the correctness tests locally.

    python test.py            configure + build + run test_correctness
    python test.py --bench    ... and then run the benchmark as well

Needs cmake (3.16+) and a C++20 compiler on PATH: g++ 13+ or clang++ 16+.
Point the CMAKE environment variable at a cmake binary that is not on PATH.
On Windows use MSYS2/MinGW, WSL, or the Docker dev container (see README).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BUILD_DIR_NAME = "build"


def find_cmake() -> str | None:
    return os.environ.get("CMAKE") or shutil.which("cmake")


def find_binary(build_dir: Path, name: str) -> Path | None:
    for candidate in (
        build_dir / name,
        build_dir / f"{name}.exe",
        build_dir / "Release" / f"{name}.exe",
        build_dir / "Release" / name,
    ):
        if candidate.is_file():
            return candidate
    return None


def build(root: Path, cmake: str) -> tuple[bool, str]:
    """Configure and build; returns (ok, combined output)."""
    build_dir = root / BUILD_DIR_NAME
    steps = [
        [cmake, "-S", str(root), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"],
        [cmake, "--build", str(build_dir), "--config", "Release", "--parallel"],
    ]
    output: list[str] = []
    for cmd in steps:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
        output.append(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            return False, "".join(output)
    return True, "".join(output)


def run_tests(root: Path) -> tuple[bool | None, str, str]:
    """
    Build and run test_correctness.

    Returns (ok, full_output, summary).  ok is None when no toolchain is
    available, True when every test passed, False otherwise.
    """
    cmake = find_cmake()
    if not cmake:
        reason = "cmake not found on PATH (set CMAKE=/path/to/cmake to use one elsewhere)"
        return None, "", reason

    ok, build_output = build(root, cmake)
    if not ok:
        return False, "Build failed:\n" + build_output, "build failed"

    binary = find_binary(root / BUILD_DIR_NAME, "test_correctness")
    if binary is None:
        return False, "Build succeeded but test_correctness was not found:\n" + build_output, "binary missing"

    proc = subprocess.run([str(binary)], capture_output=True, text=True, cwd=str(root))
    output = proc.stdout + proc.stderr
    m = re.search(r"(\d+)/(\d+) tests passed", output)
    passed_all = proc.returncode == 0 and m is not None and m.group(1) == m.group(2)
    if m:
        summary = f"{m.group(1)}/{m.group(2)} tests passed"
    else:
        summary = "tests aborted before the summary line (see output)"
    return passed_all, output, summary


def run_benchmark(root: Path) -> int:
    binary = find_binary(root / BUILD_DIR_NAME, "benchmark")
    if binary is None:
        print("benchmark binary not found; build first", file=sys.stderr)
        return 1
    return subprocess.call([str(binary)], cwd=str(root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and run the correctness tests locally.")
    parser.add_argument("--bench", action="store_true", help="also run the benchmark after the tests")
    parser.add_argument("--dir", help="project root (default: the directory of this script)")
    args = parser.parse_args(argv)
    root = Path(args.dir).resolve() if args.dir else Path(__file__).resolve().parent

    ok, output, summary = run_tests(root)
    if ok is None:
        print(f"Cannot build locally: {summary}", file=sys.stderr)
        return 2
    print(output, end="" if output.endswith("\n") else "\n")
    if not ok:
        print(f"RESULT: {summary}", file=sys.stderr)
        return 1
    if args.bench:
        return run_benchmark(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
