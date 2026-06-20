#!/usr/bin/env python3
"""Regression checks for example pattern authoring metadata."""

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


def _fail(message: str, result: subprocess.CompletedProcess[str]) -> None:
    print(message, file=sys.stderr)
    print(f"stdout: {result.stdout!r}", file=sys.stderr)
    print(f"stderr: {result.stderr!r}", file=sys.stderr)
    raise SystemExit(1)


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise AssertionError("receipt was not a JSON object")
    return data


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

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        receipt = tmpdir / "proof-pr.json"
        config = tmpdir / "proof-pr.config.json"
        config.write_text(
            json.dumps(
                {
                    "risk": {
                        "tier": "T3",
                        "reasons": ["workflow authoring metadata"],
                        "changed_surfaces": ["workflow"],
                    }
                }
            ),
            encoding="utf-8",
        )

        init_result = _run(
            proof_pr,
            "init",
            "--cwd",
            str(ROOT),
            "--tier",
            "T2",
            "--summary",
            "Exercise example pattern metadata",
            "--output",
            str(receipt),
        )
        if init_result.returncode != 0:
            _fail("init with suggested example returned non-zero", init_result)
        payload = _load(receipt)
        pattern = payload.get("producer", {}).get("example_pattern")
        if pattern != {
            "pattern": "UI/API/schema consumer",
            "example": "examples/pr-024-sample-dashboard-rollups.json",
            "tier": "T2",
            "source": "suggested",
        }:
            _fail("init did not attach the expected T2 example pattern", init_result)

        render_result = _run(proof_pr, "render", str(receipt))
        if render_result.returncode != 0:
            _fail("render with example pattern returned non-zero", render_result)
        expected_line = (
            "Pattern: `UI/API/schema consumer` via "
            "`examples/pr-024-sample-dashboard-rollups.json` (`suggested`)"
        )
        if expected_line not in render_result.stdout:
            _fail("render did not show the example pattern line", render_result)

        collect_result = _run(
            proof_pr,
            "collect",
            str(receipt),
            "--cwd",
            str(ROOT),
            "--config",
            str(config),
            "--suggest-example",
        )
        if collect_result.returncode != 0:
            _fail("collect --suggest-example returned non-zero", collect_result)
        payload = _load(receipt)
        pattern = payload.get("producer", {}).get("example_pattern")
        if pattern != {
            "pattern": "Workflow dogfood",
            "example": "examples/pr-087-github-repo-auditor-dogfood.json",
            "tier": "T3",
            "source": "suggested",
        }:
            _fail("collect did not refine the example pattern from workflow surfaces", collect_result)

        validate_result = _run(proof_pr, "validate", str(receipt))
        if validate_result.returncode != 0:
            _fail("receipt with example pattern did not validate", validate_result)

    print("example pattern authoring metadata: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
