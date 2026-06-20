#!/usr/bin/env python3
"""Regression checks for the examples CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _default_command() -> list[str]:
    return [sys.executable, str(ROOT / "scripts" / "proof_pr.py")]


def _run(proof_pr: list[str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*proof_pr, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _fail(message: str, result: subprocess.CompletedProcess[str]) -> None:
    print(message, file=sys.stderr)
    print(f"stdout: {result.stdout!r}", file=sys.stderr)
    print(f"stderr: {result.stderr!r}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--proof-pr",
        nargs="+",
        default=_default_command(),
        help="proof-pr command to test; defaults to the source-checkout wrapper",
    )
    args = parser.parse_args(argv)
    proof_pr = list(args.proof_pr)

    text_result = _run(proof_pr, "examples")
    if text_result.returncode != 0:
        _fail("examples text output returned non-zero", text_result)
    for expected in [
        "Docs/license only (T0): examples/pr-054-bridge-db-license.json",
        "Test-only maintenance (T1): examples/pr-022-proof-pr-test-harness.json",
        "Schema/concurrency/contract (T3): examples/pr-055-bridge-db-schema-concurrency.json",
    ]:
        if expected not in text_result.stdout:
            _fail(f"examples text output missing {expected!r}", text_result)
    if text_result.stderr:
        _fail("examples text output wrote to stderr", text_result)
    print("examples text output: passed")

    json_result = _run(proof_pr, "examples", "--json")
    if json_result.returncode != 0:
        _fail("examples json output returned non-zero", json_result)
    if json_result.stderr:
        _fail("examples json output wrote to stderr", json_result)
    try:
        payload = json.loads(json_result.stdout)
    except json.JSONDecodeError:
        _fail("examples json output was not valid JSON", json_result)
    examples = payload.get("examples")
    if not isinstance(examples, list) or len(examples) != 5:
        _fail("examples json output did not contain five examples", json_result)
    if examples[0].get("pattern") != "Docs/license only":
        _fail("examples json output changed ordering unexpectedly", json_result)
    print("examples json output: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
