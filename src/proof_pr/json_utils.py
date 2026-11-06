"""Strict JSON decoding helpers shared by proof and review trust boundaries."""

from __future__ import annotations

import json
from typing import Any


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        data[key] = value
    return data


def loads_unique_json(raw: str | bytes) -> Any:
    """Parse JSON while rejecting ambiguous objects with duplicate names."""
    return json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)
