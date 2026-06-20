#!/usr/bin/env python3
"""Compatibility wrapper for public git metadata checks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from proof_pr.public_git_metadata import main


if __name__ == "__main__":
    raise SystemExit(main())
