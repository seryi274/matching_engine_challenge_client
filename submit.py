#!/usr/bin/env python3
"""
Submit your matching engine to the challenge server.

    python3 submit.py              build + test locally, upload, wait for the server's verdict
    python3 submit.py --no-test    skip the local build and test step
    python3 submit.py --no-wait    upload and return immediately

TEAM_NAME, PASSWORD and SERVER come from config.py next to this file;
--team, --password and --server override them.

What is uploaded: every file directly inside src/ with one of these extensions
    .cpp .cc .h .hpp .hh .inl .ipp
plus include/exchange/matching_engine.h (so you can add private members).
Nothing else. The server compiles your files against its own copy of
types.h, the tests, the benchmark and CMakeLists.txt.

Only the Python standard library is used; there is nothing to install.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import io
import json
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Shared client credentials. Not a secret: they only keep stray traffic off the
# server. Your team is protected by the PASSWORD in config.py.
CLIENT_USERNAME = "challenge"
CLIENT_PASSWORD = "matching-engine"

SOURCE_EXTENSIONS = {".cpp", ".cc", ".h", ".hpp", ".hh", ".inl", ".ipp"}
COMPILED_EXTENSIONS = {".cpp", ".cc"}
HEADER_OVERRIDE = Path("include", "exchange", "matching_engine.h")
TEAM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
MAX_UPLOAD_BYTES = 1024 * 1024

POLL_INTERVAL_S = 3
WAIT_TIMEOUT_S = 30 * 60
TERMINAL_STATES = {"complete", "failed"}
SCENARIO_WEIGHTS = {"uniform": 0.30, "realistic": 0.40, "adversarial": 0.30}


class SubmitError(Exception):
    pass


# ---------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------

def load_config(directory: Path) -> dict[str, str]:
    """Read TEAM_NAME / PASSWORD / SERVER from config.py in `directory`, if present."""
    path = directory / "config.py"
    if not path.is_file():
        return {}
    namespace: dict = {}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
    return {key: str(namespace.get(key) or "") for key in ("TEAM_NAME", "PASSWORD", "SERVER")}


def normalise_server(server: str) -> str:
    server = server.strip().rstrip("/")
    if not server.startswith(("http://", "https://")):
        server = "http://" + server
    return server


# ---------------------------------------------------------------
#  Packaging
# ---------------------------------------------------------------

def collect_files(root: Path) -> list[Path]:
    """Relative paths of everything that will be uploaded."""
    files: list[Path] = []
    src = root / "src"
    if src.is_dir():
        for p in sorted(src.iterdir()):
            if p.is_file() and p.suffix.lower() in SOURCE_EXTENSIONS:
                files.append(p.relative_to(root))
    if (root / HEADER_OVERRIDE).is_file():
        files.append(HEADER_OVERRIDE)
    return files


def pack(root: Path, files: list[Path]) -> bytes:
    """Gzipped tarball of the given files, without owner names or ids."""
    def scrub(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in files:
            tar.add(root / rel, arcname=rel.as_posix(), recursive=False, filter=scrub)
    return buf.getvalue()


# ---------------------------------------------------------------
#  HTTP (standard library only)
# ---------------------------------------------------------------

def http_json(method: str, url: str, body: dict | None = None, auth: bool = False,
              timeout: float = 60) -> tuple[int, object]:
    """Send a JSON request; return (status, decoded JSON body or raw text)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        token = base64.b64encode(f"{CLIENT_USERNAME}:{CLIENT_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw.decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise SubmitError(f"Cannot reach {url}: {exc.reason}") from exc


def error_message(payload: object) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail") or payload.get("error") or payload)
    return str(payload)


# ---------------------------------------------------------------
#  Local build + test (delegates to test.py next to this file)
# ---------------------------------------------------------------

def run_local_tests(root: Path) -> tuple[bool | None, str, str]:
    """Returns (ok, full_output, summary); ok is None when no toolchain is available."""
    test_path = Path(__file__).resolve().with_name("test.py")
    spec = importlib.util.spec_from_file_location("me_local_test", test_path)
    if spec is None or spec.loader is None:
        return None, "", f"test.py not found next to {Path(__file__).name}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_tests(root)


# ---------------------------------------------------------------
#  Waiting for the verdict
# ---------------------------------------------------------------

def wait_for_result(server: str, submission_id: int) -> dict:
    url = f"{server}/api/submission/{submission_id}"
    last_status = None
    deadline = time.monotonic() + WAIT_TIMEOUT_S
    while time.monotonic() < deadline:
        status_code, payload = http_json("GET", url)
        if status_code != 200 or not isinstance(payload, dict):
            raise SubmitError(f"Status lookup failed (HTTP {status_code}): {error_message(payload)}")
        status = payload.get("status")
        if status != last_status:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {status}")
            last_status = status
        if status in TERMINAL_STATES:
            return payload
        time.sleep(POLL_INTERVAL_S)
    raise SubmitError(f"Timed out waiting for the server; check the leaderboard or {url} later")


def tail(text: str, lines: int = 30) -> str:
    parts = text.rstrip().splitlines()
    return "\n".join(parts[-lines:])


def print_result(sub: dict) -> None:
    print()
    build = sub.get("build") or {}
    if build:
        state = "OK" if build.get("success") else "FAILED"
        print(f"Build:     {state} ({build.get('duration_s', 0):.1f}s)")
        if not build.get("success"):
            print(tail(build.get("log", "")))
    tests = sub.get("tests") or {}
    if tests:
        print(f"Tests:     {tests.get('passed', 0)}/{tests.get('total', 0)} passed")
        if tests.get("passed") != tests.get("total"):
            details = tests.get("details") or {}
            raw = details.get("raw_output", "") if isinstance(details, dict) else ""
            print(tail(raw))
    benches = sub.get("benchmarks") or {}
    if benches:
        print("Benchmark (best of 3 runs, each the median of 3 iterations):")
        print(f"  {'scenario':<12} {'p50 ns':>9} {'p99 ns':>9} {'throughput ops/s':>18}")
        weighted_p50 = 0.0
        weighted_tp = 0.0
        for name in ("uniform", "realistic", "adversarial"):
            s = benches.get(name)
            if not s:
                continue
            print(f"  {name:<12} {s['p50_ns']:>9,.0f} {s['p99_ns']:>9,.0f} {s['throughput_ops']:>18,.0f}")
            weight = SCENARIO_WEIGHTS[name]
            weighted_p50 += weight * s["p50_ns"]
            weighted_tp += weight * s["throughput_ops"]
        print(f"  {'weighted':<12} {weighted_p50:>9,.0f} {'':>9} {weighted_tp:>18,.0f}")
    if sub.get("status") == "failed" and sub.get("error"):
        print(f"Error:     {sub['error']}")
    print(f"Status:    {sub.get('status')}")


# ---------------------------------------------------------------
#  Main
# ---------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload your matching engine to the challenge server.")
    parser.add_argument("--team", help="team name (default: TEAM_NAME in config.py)")
    parser.add_argument("--password", help="team password (default: PASSWORD in config.py)")
    parser.add_argument("--server", help="host:port of the server (default: SERVER in config.py)")
    parser.add_argument("--dir", help="project root to upload (default: the directory of this script)")
    parser.add_argument("--no-test", action="store_true", help="skip the local build and test step")
    parser.add_argument("--force", action="store_true", help="upload even if local tests fail")
    parser.add_argument("--no-wait", action="store_true", help="do not wait for the server's result")
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    root = Path(args.dir).resolve() if args.dir else script_dir
    cfg = load_config(root) or load_config(script_dir)
    team = (args.team or cfg.get("TEAM_NAME", "")).strip()
    password = args.password or cfg.get("PASSWORD", "")
    server = args.server or cfg.get("SERVER", "")

    try:
        if not team or not password or not server:
            raise SubmitError(
                "Set TEAM_NAME, PASSWORD and SERVER in config.py (or pass --team/--password/--server)"
            )
        if not TEAM_NAME_RE.match(team):
            raise SubmitError("TEAM_NAME may only contain letters, digits, '-' and '_' (max 32 characters)")
        server = normalise_server(server)

        files = collect_files(root)
        if not any(f.suffix.lower() in COMPILED_EXTENSIONS for f in files):
            raise SubmitError(f"No .cpp/.cc files found in {root / 'src'}")
        print(f"Collecting files from {root}")
        for f in files:
            print(f"  {f.as_posix()} ({(root / f).stat().st_size / 1024:.1f} KB)")
        payload_bytes = pack(root, files)
        print(f"Upload size: {len(payload_bytes) / 1024:.1f} KB")
        if len(payload_bytes) > MAX_UPLOAD_BYTES:
            raise SubmitError("Upload exceeds 1 MB; remove generated or binary files from src/")

        if not args.no_test:
            print("Running local build and tests (skip with --no-test)...")
            ok, output, summary = run_local_tests(root)
            if ok is None:
                print(f"  Skipped: {summary}")
            elif ok:
                print(f"  {summary}")
            elif args.force:
                print("  Local tests failed; uploading anyway because of --force")
            else:
                print(output)
                raise SubmitError("Local tests failed. Fix them, or upload anyway with --force")

        body = {
            "team": team,
            "password": password,
            "time": datetime.now(timezone.utc).isoformat(),
            "format": "tar.gz+base64",
            "files": [f.as_posix() for f in files],
            "submission": base64.b64encode(payload_bytes).decode("ascii"),
        }
        print(f"Uploading as team '{team}' to {server} ...")
        status_code, response = http_json("POST", f"{server}/receive", body, auth=True)
        if status_code != 200 or not isinstance(response, dict):
            raise SubmitError(f"Submission rejected (HTTP {status_code}): {error_message(response)}")

        submission_id = response.get("submission_id")
        if response.get("new_team"):
            print(f"Registered new team '{team}'. Keep using this password.")
        print(
            f"Submission #{submission_id} queued "
            f"(position {response.get('queue_position', '?')}). Leaderboard: {server}/"
        )

        if args.no_wait or submission_id is None:
            return 0
        result = wait_for_result(server, int(submission_id))
        print_result(result)
        return 0 if result.get("status") == "complete" else 1

    except SubmitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. If the upload was accepted it is still being processed.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
