#!/usr/bin/env python3
"""Regression checks for receipt-hygiene CLI exit/output behavior."""

from __future__ import annotations

import argparse
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
