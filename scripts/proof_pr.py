#!/usr/bin/env python3
"""Compatibility wrapper for running proof-pr from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    from proof_pr.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
