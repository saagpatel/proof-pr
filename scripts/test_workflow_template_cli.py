#!/usr/bin/env python3
"""Regression checks for the workflow-template CLI command."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROOF_PR = [sys.executable, str(ROOT / "scripts" / "proof_pr.py")]


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*PROOF_PR, *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _expect_success(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        raise AssertionError(
            f"{label} failed with {result.returncode}: {result.stdout!r} {result.stderr!r}"
        )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manual = root / "manual.yml"
        result = _run("workflow-template", "--output", str(manual))
        _expect_success(result, "manual template")
        content = manual.read_text(encoding="utf-8")
        manual_content = content
        expected = [
            "on:\n  workflow_dispatch:\n",
            "uses: saagpatel/proof-pr/.github/workflows/proof-pr-receipt.yml@v0.2.14",
            'proof_pr_ref: "v0.2.14"',
            'receipt_path: "proof-pr.json"',
            'artifact_glob: "proof-pr-artifacts/**"',
            "receipt_hygiene_strict: false",
        ]
        for fragment in expected:
            if fragment not in content:
                raise AssertionError(f"manual template missing {fragment!r}")
        if "pull_request:" in content:
            raise AssertionError("manual template unexpectedly enables pull_request")

        pull_request = root / "pull-request.yml"
        result = _run(
            "workflow-template",
            "--output",
            pull_request.name,
            "--pull-request",
            "--receipt-path",
            "evidence/proof.json",
            "--artifact-glob",
            "evidence/**",
            "--proof-pr-ref",
            "v9.9.9",
            cwd=root,
        )
        _expect_success(result, "pull request template")
        content = pull_request.read_text(encoding="utf-8")
        for fragment in [
            "  pull_request:\n    paths:\n",
            '      - "evidence/proof.json"',
            '      - "evidence/**"',
            '      - "pull-request.yml"',
            'uses: saagpatel/proof-pr/.github/workflows/proof-pr-receipt.yml@v9.9.9',
        ]:
            if fragment not in content:
                raise AssertionError(f"pull request template missing {fragment!r}")

        result = _run("workflow-template", "--output", str(manual))
        if result.returncode != 2 or "refusing to overwrite" not in result.stderr:
            raise AssertionError(
                f"existing output was not protected: {result.returncode} {result.stderr!r}"
            )
        if manual.read_text(encoding="utf-8") != manual_content:
            raise AssertionError("existing output was changed after overwrite refusal")

        invalid_ref = _run(
            "workflow-template",
            "--output",
            str(root / "invalid-ref.yml"),
            "--proof-pr-ref",
            "v1.0 # untrusted",
        )
        if invalid_ref.returncode != 2 or "unsupported characters" not in invalid_ref.stderr:
            raise AssertionError(f"unsafe proof-pr ref accepted: {invalid_ref.stderr!r}")

        invalid = _run(
            "workflow-template",
            "--output",
            str(root / "invalid.yml"),
            "--receipt-path",
            "../outside/proof-pr.json",
        )
        if invalid.returncode != 2 or "normalized repo-relative" not in invalid.stderr:
            raise AssertionError(f"parent-traversal receipt path accepted: {invalid.stderr!r}")

        invalid_glob = _run(
            "workflow-template",
            "--output",
            str(root / "invalid-glob.yml"),
            "--artifact-glob",
            "../outside/**",
        )
        if invalid_glob.returncode != 2 or "normalized repo-relative" not in invalid_glob.stderr:
            raise AssertionError(f"parent-traversal artifact glob accepted: {invalid_glob.stderr!r}")

    print("workflow-template CLI: manual/pull-request templates and overwrite guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
