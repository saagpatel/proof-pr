#!/usr/bin/env python3
"""Compatibility wrapper for running proof-pr from a source checkout."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    cli_main = import_module("proof_pr.cli").main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
