#!/usr/bin/env python3
"""Golden negative fixtures for the closed proof-pr.v1 receipt contract."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proof_pr.validate_receipts import (  # noqa: E402
    ARTIFACT_KINDS,
    EVIDENCE_KINDS,
    validate_receipt,
)


Mutator = Callable[[dict[str, Any]], None]


def _errors_for(payload: dict[str, Any]) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipt.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return validate_receipt(path)


def _errors_for_raw(raw: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipt.json"
        path.write_text(raw, encoding="utf-8")
        return validate_receipt(path)


def _expect_invalid(
    base: dict[str, Any], name: str, mutate: Mutator, fragment: str
) -> None:
    payload = copy.deepcopy(base)
    mutate(payload)
    errors = _errors_for(payload)
    if not any(fragment in error for error in errors):
        raise AssertionError(f"{name}: expected {fragment!r}, got {errors!r}")


def _add_extra(path: tuple[Any, ...]) -> Mutator:
    def mutate(payload: dict[str, Any]) -> None:
        target: Any = payload
        for key in path:
            target = target[key]
        target["unexpected"] = True

    return mutate


def _test_ready_decisions() -> None:
    base = json.loads((ROOT / "examples" / "pr-024-sample-dashboard-rollups.json").read_text())
    base["limitations"] = []
    cli = [sys.executable, str(ROOT / "scripts" / "proof_pr.py")]
    with tempfile.TemporaryDirectory() as tmp:
        receipt = Path(tmp) / "receipt.json"

        def finalize(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
            receipt.write_text(json.dumps(payload))
            return subprocess.run([*cli, "finalize", str(receipt), "--require-ready"], capture_output=True, text=True)

        assert finalize(copy.deepcopy(base)).returncode == 0
        for mutation in ("missing-status", "unknown-status", "missing-security", "invalid-required", "missing-limitations"):
            payload = copy.deepcopy(base)
            if mutation == "missing-status":
                del payload["evidence"][0]["status"]
            elif mutation == "unknown-status":
                payload["evidence"][0]["status"] = "unknown"
            elif mutation == "missing-security":
                del payload["security"]["redaction"]
            elif mutation == "invalid-required":
                payload["evidence"][0]["required"] = "yes"
            else:
                del payload["limitations"]
            result = finalize(payload)
            assert result.returncode != 0, (mutation, result.stdout, result.stderr)
            assert json.loads(receipt.read_text())["overall"]["review_decision"] == "revise"

        for malformed in (None, 42, {"reason": "unresolved review"}):
            for extra in ([], ["--allow-limitations"]):
                payload = copy.deepcopy(base)
                payload["limitations"] = [malformed]
                receipt.write_text(json.dumps(payload))
                result = subprocess.run(
                    [*cli, "finalize", str(receipt), "--require-ready", *extra],
                    capture_output=True, text=True,
                )
                assert result.returncode == 1, (malformed, extra, result.stdout)
                updated = json.loads(receipt.read_text())
                assert updated["limitations"] == [malformed]
                assert updated["overall"]["review_decision"] == "revise"

        receipt.write_text(json.dumps(base))
        result = subprocess.run([*cli, "run", "--receipt", str(receipt), "--id", "tests", "--", sys.executable, "-c", "raise SystemExit(1)"], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        updated = json.loads(receipt.read_text())
        assert next(item for item in updated["evidence"] if item["id"] == "tests")["status"] == "failed"
        assert updated["overall"] == {"status": "stale", "review_decision": "revise"}
        result = subprocess.run([*cli, "finalize", str(receipt), "--require-ready"], capture_output=True, text=True)
        assert result.returncode == 1
        assert json.loads(receipt.read_text())["overall"]["status"] == "failed"

        receipt.write_text(json.dumps(base))
        result = subprocess.run([*cli, "collect", str(receipt), "--cwd", str(ROOT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(receipt.read_text())["overall"]["review_decision"] == "revise"

        receipt.write_text(json.dumps(base))
        config = Path(tmp) / "config.json"
        config.write_text(json.dumps({"commands": []}))
        result = subprocess.run([*cli, "run-config", str(receipt), "--config", str(config), "--cwd", str(ROOT)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(receipt.read_text())["overall"]["review_decision"] == "revise"
        result = subprocess.run([*cli, "finalize", str(receipt), "--require-ready"], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def main() -> int:
    _test_ready_decisions()
    base = json.loads(
        (ROOT / "examples" / "pr-022-proof-pr-test-harness.json").read_text()
    )
    schema = json.loads((ROOT / "schemas" / "proof-pr.v1.schema.json").read_text())
    if _errors_for(base):
        raise AssertionError("canonical base fixture must validate")

    canonical = (ROOT / "examples" / "pr-022-proof-pr-test-harness.json").read_text(
        encoding="utf-8"
    )
    duplicated = canonical.replace(
        '"schema_version": "proof-pr.v1",',
        '"schema_version": "proof-pr.invalid",\n  '
        '"schema_version": "proof-pr.v1",',
        1,
    )
    duplicate_errors = _errors_for_raw(duplicated)
    if not any(
        "duplicate JSON object key: 'schema_version'" in error
        for error in duplicate_errors
    ):
        raise AssertionError(
            f"duplicate schema_version was not rejected: {duplicate_errors!r}"
        )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipt.json"
        path.write_text(duplicated, encoding="utf-8")
        rendered = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "proof_pr.py"), "render", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert rendered.returncode == 2, rendered
        assert "duplicate JSON object key: 'schema_version'" in rendered.stderr, rendered
        assert not rendered.stdout, rendered

    schema_closed_objects = {
        "receipt": schema,
        "subject": schema["properties"]["subject"],
        "producer": schema["properties"]["producer"],
        "producer.example_pattern": schema["properties"]["producer"]["properties"][
            "example_pattern"
        ],
        "risk": schema["properties"]["risk"],
        "change": schema["properties"]["change"],
        "change.diff_stats": schema["properties"]["change"]["properties"]["diff_stats"],
        "evidence[0]": schema["$defs"]["evidence_item"],
        "operating_decision": schema["$defs"]["operating_decision"],
        "operator_contract_ref": schema["$defs"]["operator_contract_ref"],
        "operant_binding": schema["$defs"]["operant_binding"],
        "security": schema["properties"]["security"],
        "security.secrets_scan": schema["$defs"]["posture"],
        "rollback": schema["properties"]["rollback"],
        "artifacts[0]": schema["$defs"]["artifact"],
        "overall": schema["properties"]["overall"],
    }
    not_closed = [
        label
        for label, object_schema in schema_closed_objects.items()
        if object_schema.get("additionalProperties") is not False
    ]
    if not_closed:
        raise AssertionError(f"schema objects unexpectedly open: {not_closed}")

    schema_evidence_kinds = set(
        schema["$defs"]["evidence_item"]["properties"]["kind"]["enum"]
    )
    schema_artifact_kinds = set(
        schema["$defs"]["artifact"]["properties"]["kind"]["enum"]
    )
    if schema_evidence_kinds != EVIDENCE_KINDS:
        raise AssertionError("validator evidence kinds drifted from the v1 schema")
    if schema_artifact_kinds != ARTIFACT_KINDS:
        raise AssertionError("validator artifact kinds drifted from the v1 schema")

    closed_objects = {
        "receipt": (),
        "subject": ("subject",),
        "producer": ("producer",),
        "risk": ("risk",),
        "change": ("change",),
        "change.diff_stats": ("change", "diff_stats"),
        "evidence[0]": ("evidence", 0),
        "security": ("security",),
        "security.secrets_scan": ("security", "secrets_scan"),
        "rollback": ("rollback",),
        "artifacts[0]": ("artifacts", 0),
        "overall": ("overall",),
    }
    for label, path in closed_objects.items():
        _expect_invalid(
            base,
            label,
            _add_extra(path),
            f"{label} unexpected fields: unexpected",
        )

    def add_invalid_example_pattern(payload: dict[str, Any]) -> None:
        payload["producer"]["example_pattern"] = {
            "pattern": "Contract migration",
            "example": "examples/pr-022-proof-pr-test-harness.json",
            "tier": "T1",
            "source": "explicit",
            "unexpected": True,
        }

    _expect_invalid(
        base,
        "producer.example_pattern",
        add_invalid_example_pattern,
        "producer.example_pattern unexpected fields: unexpected",
    )

    _expect_invalid(
        base,
        "artifact kind enum",
        lambda payload: payload["artifacts"][0].__setitem__("kind", "not-in-schema"),
        "artifacts[0].kind has invalid value",
    )
    _expect_invalid(
        base,
        "evidence kind enum",
        lambda payload: payload["evidence"][0].__setitem__("kind", "not-in-schema"),
        "evidence[0].kind has invalid value",
    )
    _expect_invalid(
        base,
        "short base sha",
        lambda payload: payload["subject"].__setitem__("base_sha", "short"),
        "subject.base_sha must be at least 7 characters",
    )
    _expect_invalid(
        base,
        "boolean pr number",
        lambda payload: payload["subject"].__setitem__("pr_number", True),
        "subject.pr_number must be a positive integer or null",
    )
    _expect_invalid(
        base,
        "boolean diff count",
        lambda payload: payload["change"]["diff_stats"].__setitem__("files", True),
        "change.diff_stats.files must be a non-negative integer",
    )

    operating = json.loads(
        (ROOT / "examples" / "pr-101-agent-operating-decision.json").read_text()
    )
    if _errors_for(operating):
        raise AssertionError("operating-decision example must validate")
    operating_index = next(
        index
        for index, item in enumerate(operating["evidence"])
        if item.get("kind") == "operating-decision"
    )

    _expect_invalid(
        operating,
        "operating-decision label enum",
        lambda payload: payload["evidence"][operating_index]["operating_decision"].__setitem__(
            "decision", "MAYBE"
        ),
        f"evidence[{operating_index}].operating_decision.decision has invalid value",
    )
    _expect_invalid(
        operating,
        "operating-decision payload required",
        lambda payload: payload["evidence"][operating_index].pop("operating_decision"),
        f"evidence[{operating_index}] missing fields: operating_decision",
    )
    _expect_invalid(
        operating,
        "operating_decision",
        lambda payload: payload["evidence"][operating_index]["operating_decision"].__setitem__(
            "unexpected", True
        ),
        f"evidence[{operating_index}].operating_decision unexpected fields: unexpected",
    )
    _expect_invalid(
        operating,
        "operator_contract_ref",
        lambda payload: payload["evidence"][operating_index]["operating_decision"][
            "operator_contract"
        ].__setitem__("unexpected", True),
        f"evidence[{operating_index}].operating_decision.operator_contract unexpected fields: unexpected",
    )
    _expect_invalid(
        operating,
        "operant_binding",
        lambda payload: payload["evidence"][operating_index]["operating_decision"][
            "operant"
        ].__setitem__("unexpected", True),
        f"evidence[{operating_index}].operating_decision.operant unexpected fields: unexpected",
    )
    _expect_invalid(
        operating,
        "operator contract sha256",
        lambda payload: payload["evidence"][operating_index]["operating_decision"][
            "operator_contract"
        ].__setitem__("sha256", "not-a-digest"),
        f"evidence[{operating_index}].operating_decision.operator_contract.sha256 must be a 64-character lowercase hex SHA-256",
    )
    _expect_invalid(
        base,
        "null operating_decision on other evidence",
        lambda payload: payload["evidence"][0].__setitem__("operating_decision", None),
        "evidence[0] operating_decision is only valid for kind operating-decision",
    )

    print(
        "validation contract: schema closure and kind enums aligned; canonical fixture accepted; "
        f"{len(closed_objects) + 1} closed-object, 2 enum, 3 type/boundary, and 7 "
        "operating-decision negative controls rejected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
