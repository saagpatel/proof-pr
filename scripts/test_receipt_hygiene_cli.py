#!/usr/bin/env python3
"""Regression checks for receipt-hygiene CLI exit/output behavior."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
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


def _expect(
    name: str,
    result: subprocess.CompletedProcess[str],
    *,
    returncode: int,
    stdout_contains: str | None = None,
    stderr_contains: str | None = None,
    stderr_empty: bool = False,
) -> None:
    failures: list[str] = []
    if result.returncode != returncode:
        failures.append(f"returncode {result.returncode} != {returncode}")
    if stdout_contains and stdout_contains not in result.stdout:
        failures.append(f"stdout missing {stdout_contains!r}")
    if stderr_contains and stderr_contains not in result.stderr:
        failures.append(f"stderr missing {stderr_contains!r}")
    if stderr_empty and result.stderr:
        failures.append(f"stderr not empty: {result.stderr!r}")
    if failures:
        print(f"{name}: failed", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        print(f"stdout: {result.stdout!r}", file=sys.stderr)
        print(f"stderr: {result.stderr!r}", file=sys.stderr)
        raise SystemExit(1)
    print(f"{name}: passed")


def _fail(name: str, result: subprocess.CompletedProcess[str]) -> None:
    print(f"{name}: failed", file=sys.stderr)
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

    no_finding_fix_only = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-024-sample-dashboard-rollups.json",
        "--explain",
        "--check",
        "public-git-metadata",
        "--fix-only",
    )
    _expect(
        "focused no-finding fix-only",
        no_finding_fix_only,
        returncode=0,
        stdout_contains="No focused fix suggested for check public-git-metadata.",
        stderr_empty=True,
    )

    finding_fix_only = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-087-github-repo-auditor-dogfood.json",
        "--explain",
        "--check",
        "public-git-metadata",
        "--fix-only",
    )
    _expect(
        "focused finding fix-only",
        finding_fix_only,
        returncode=0,
        stdout_contains="proof-pr collect-public-git-metadata",
        stderr_empty=True,
    )

    normal_no_finding = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-024-sample-dashboard-rollups.json",
        "--check",
        "public-git-metadata",
    )
    _expect(
        "normal no-finding check",
        normal_no_finding,
        returncode=2,
        stderr_contains="receipt hygiene: no finding for check public-git-metadata",
    )

    example_receipt_id = "example-sample-dashboard-pr-24-6d2f94b"
    normal_json = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-024-sample-dashboard-rollups.json",
        "--json",
    )
    _expect(
        "receipt hygiene json summarizes receipt id",
        normal_json,
        returncode=0,
        stdout_contains='"receipt_id": "present"',
        stderr_empty=True,
    )
    if example_receipt_id in normal_json.stdout:
        _fail("receipt hygiene json leaked the raw receipt id", normal_json)

    normal_text = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-024-sample-dashboard-rollups.json",
    )
    _expect(
        "receipt hygiene text summarizes receipt id",
        normal_text,
        returncode=0,
        stdout_contains="receipt hygiene: present",
        stderr_empty=True,
    )
    if example_receipt_id in normal_text.stdout:
        _fail("receipt hygiene text leaked the raw receipt id", normal_text)

    with tempfile.TemporaryDirectory() as tmp:
        source = ROOT / "examples" / "pr-024-sample-dashboard-rollups.json"
        receipt = Path(tmp) / "receipt-with-sensitive-looking-values.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        data["receipt_id"] = "ghp_0123456789abcdefghijklmnop"
        data["risk"]["tier"] = "token=super-secret-value"
        receipt.write_text(json.dumps(data), encoding="utf-8")

        redacted_json = _run(proof_pr, "receipt-hygiene", str(receipt), "--json")
        _expect(
            "receipt hygiene json redacts sensitive-looking values",
            redacted_json,
            returncode=0,
            stdout_contains="[REDACTED]",
            stderr_empty=True,
        )
        if "ghp_0123456789abcdefghijklmnop" in redacted_json.stdout:
            _fail("receipt hygiene json leaked a sensitive-looking token", redacted_json)
        if "super-secret-value" in redacted_json.stdout:
            _fail("receipt hygiene json leaked a sensitive-looking assignment", redacted_json)

        redacted_text = _run(proof_pr, "receipt-hygiene", str(receipt))
        _expect(
            "receipt hygiene text redacts sensitive-looking values",
            redacted_text,
            returncode=0,
            stdout_contains="[REDACTED]",
            stderr_empty=True,
        )
        if "ghp_0123456789abcdefghijklmnop" in redacted_text.stdout:
            _fail("receipt hygiene text leaked a sensitive-looking token", redacted_text)
        if "super-secret-value" in redacted_text.stdout:
            _fail("receipt hygiene text leaked a sensitive-looking assignment", redacted_text)

    missing_operating = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-024-sample-dashboard-rollups.json",
        "--check",
        "operating-decision",
    )
    _expect(
        "T2 agent receipt missing operating-decision",
        missing_operating,
        returncode=0,
        stdout_contains="operating-decision: missing",
        stderr_empty=True,
    )

    missing_operating_strict = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-024-sample-dashboard-rollups.json",
        "--strict",
    )
    _expect(
        "strict hygiene fails when operating-decision is missing",
        missing_operating_strict,
        returncode=1,
        stdout_contains="operating-decision: missing",
        stderr_empty=True,
    )

    present_operating = _run(
        proof_pr,
        "receipt-hygiene",
        "examples/pr-101-agent-operating-decision.json",
        "--check",
        "operating-decision",
    )
    _expect(
        "operating-decision example has no focused finding",
        present_operating,
        returncode=2,
        stderr_contains="receipt hygiene: no finding for check operating-decision",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
