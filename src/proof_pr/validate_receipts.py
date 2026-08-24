#!/usr/bin/env python3
"""Validate proof-pr.v1 receipt files.

This validator is deliberately small and dependency-free. It checks the v0
contract shape and a few proof-specific consistency rules; it does not decide
whether the evidence itself is true.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STATUSES = {
    "passed",
    "passed_with_warnings",
    "failed",
    "blocked",
    "skipped",
    "stale",
    "partial",
    "not_applicable",
}
EVIDENCE_KINDS = {
    "diff-review",
    "repo-native",
    "test",
    "ci",
    "lint",
    "typecheck",
    "build",
    "screenshot",
    "health",
    "smoke",
    "security",
    "permission-diff",
    "attestation",
    "release",
    "manual-review",
}
ARTIFACT_KINDS = {
    "log",
    "screenshot",
    "json",
    "report",
    "proof-package",
    "verification-result",
    "attestation",
    "summary",
}
TIERS = {"T0", "T1", "T2", "T3", "T4"}
AGENTS = {"codex", "claude-code", "manual", "github-actions", "unknown"}
MODES = {"local", "ci", "manual"}
HEAD_SHA_STATUSES = {"exact", "pending_commit", "external_anchor"}
ROLLBACK_STATUSES = {"documented", "tested", "partial", "blocked", "not_applicable"}
OVERALL_DECISIONS = {"ready", "ready_with_operator_awareness", "revise", "reject"}
EXAMPLE_PATTERN_SOURCES = {"suggested", "explicit"}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "receipt_id",
    "generated_at",
    "subject",
    "producer",
    "risk",
    "change",
    "evidence",
    "security",
    "rollback",
    "artifacts",
    "limitations",
    "overall",
}
REQUIRED_SUBJECT = {"repo", "base_ref", "base_sha", "head_ref", "head_sha"}
REQUIRED_PRODUCER = {"tool", "version", "agent", "mode"}
REQUIRED_RISK = {"tier", "reasons", "changed_surfaces"}
REQUIRED_CHANGE = {"summary", "files_touched", "diff_stats"}
REQUIRED_DIFF_STATS = {"files", "additions", "deletions"}
REQUIRED_EVIDENCE = {"id", "kind", "status", "required", "summary"}
REQUIRED_POSTURE = {"status", "summary"}
REQUIRED_ARTIFACT = {"id", "kind", "path_or_url", "description", "required"}
ALLOWED_SUBJECT = REQUIRED_SUBJECT | {"pr_number", "pr_url", "head_sha_status"}
ALLOWED_PRODUCER = REQUIRED_PRODUCER | {"example_pattern"}
ALLOWED_EXAMPLE_PATTERN = {"pattern", "example", "tier", "source"}
ALLOWED_CHANGE = REQUIRED_CHANGE | {"scope_notes"}
ALLOWED_EVIDENCE = REQUIRED_EVIDENCE | {
    "command",
    "artifact_ids",
    "freshness_hours",
    "reason",
}
ALLOWED_POSTURE = REQUIRED_POSTURE | {"artifact_ids", "reason"}
ALLOWED_ROLLBACK = {"status", "path", "notes"}
ALLOWED_ARTIFACT = REQUIRED_ARTIFACT | {"sha256", "external"}


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("receipt must be a JSON object")
    return data


def _missing(name: str, obj: Any, required: set[str], errors: list[str]) -> None:
    if not isinstance(obj, dict):
        errors.append(f"{name} must be an object")
        return
    missing = sorted(required - set(obj))
    if missing:
        errors.append(f"{name} missing fields: {', '.join(missing)}")


def _closed(name: str, obj: Any, allowed: set[str], errors: list[str]) -> None:
    """Enforce every ``additionalProperties: false`` object in the v1 schema."""
    if not isinstance(obj, dict):
        return
    unexpected = sorted(set(obj) - allowed)
    if unexpected:
        errors.append(f"{name} unexpected fields: {', '.join(unexpected)}")


def _non_empty_string(name: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{name} must be a non-empty string")


def _string_list(name: str, value: Any, errors: list[str], *, allow_empty: bool) -> None:
    if not isinstance(value, list):
        errors.append(f"{name} must be a list")
        return
    if not allow_empty and not value:
        errors.append(f"{name} must not be empty")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            errors.append(f"{name}[{index}] must be a non-empty string")


def validate_receipt(path: Path) -> list[str]:
    errors: list[str] = []
    receipt = _load(path)

    _missing("receipt", receipt, REQUIRED_TOP_LEVEL, errors)
    _closed("receipt", receipt, REQUIRED_TOP_LEVEL, errors)
    if receipt.get("schema_version") != "proof-pr.v1":
        errors.append("schema_version must be proof-pr.v1")
    _non_empty_string("receipt_id", receipt.get("receipt_id"), errors)
    _non_empty_string("generated_at", receipt.get("generated_at"), errors)

    subject = receipt.get("subject")
    _missing("subject", subject, REQUIRED_SUBJECT, errors)
    _closed("subject", subject, ALLOWED_SUBJECT, errors)
    if isinstance(subject, dict):
        for key in ("repo", "base_ref", "base_sha", "head_ref", "head_sha"):
            if not isinstance(subject.get(key), str) or not subject[key]:
                errors.append(f"subject.{key} must be a non-empty string")
        for key in ("base_sha", "head_sha"):
            value = subject.get(key)
            if isinstance(value, str) and value and len(value) < 7:
                errors.append(f"subject.{key} must be at least 7 characters")
        head_sha_status = subject.get("head_sha_status", "exact")
        if head_sha_status not in HEAD_SHA_STATUSES:
            errors.append(f"subject.head_sha_status has invalid value: {head_sha_status}")
        if head_sha_status == "exact" and subject.get("head_sha") == "pending-pr-head":
            errors.append("subject.head_sha cannot be pending-pr-head when head_sha_status is exact")
        pr_number = subject.get("pr_number")
        if pr_number is not None and (
            not isinstance(pr_number, int)
            or isinstance(pr_number, bool)
            or pr_number < 1
        ):
            errors.append("subject.pr_number must be a positive integer or null")
        pr_url = subject.get("pr_url")
        if pr_url is not None and not isinstance(pr_url, str):
            errors.append("subject.pr_url must be a string or null")

    producer = receipt.get("producer")
    _missing("producer", producer, REQUIRED_PRODUCER, errors)
    _closed("producer", producer, ALLOWED_PRODUCER, errors)
    if isinstance(producer, dict):
        _non_empty_string("producer.tool", producer.get("tool"), errors)
        _non_empty_string("producer.version", producer.get("version"), errors)
        if producer.get("agent") not in AGENTS:
            errors.append(f"producer.agent has invalid value: {producer.get('agent')}")
        if producer.get("mode") not in MODES:
            errors.append(f"producer.mode has invalid value: {producer.get('mode')}")
        example_pattern = producer.get("example_pattern")
        if example_pattern is not None:
            _missing(
                "producer.example_pattern",
                example_pattern,
                {"pattern", "example", "tier", "source"},
                errors,
            )
            _closed(
                "producer.example_pattern",
                example_pattern,
                ALLOWED_EXAMPLE_PATTERN,
                errors,
            )
            if isinstance(example_pattern, dict):
                for key in ("pattern", "example"):
                    if not isinstance(example_pattern.get(key), str) or not example_pattern[key]:
                        errors.append(f"producer.example_pattern.{key} must be a non-empty string")
                if example_pattern.get("tier") not in TIERS:
                    errors.append(
                        "producer.example_pattern.tier has invalid value: "
                        f"{example_pattern.get('tier')}"
                    )
                if example_pattern.get("source") not in EXAMPLE_PATTERN_SOURCES:
                    errors.append(
                        "producer.example_pattern.source has invalid value: "
                        f"{example_pattern.get('source')}"
                    )

    risk = receipt.get("risk")
    _missing("risk", risk, REQUIRED_RISK, errors)
    _closed("risk", risk, REQUIRED_RISK, errors)
    tier = None
    if isinstance(risk, dict):
        tier = risk.get("tier")
        if tier not in TIERS:
            errors.append(f"risk.tier has invalid value: {tier}")
        _string_list("risk.reasons", risk.get("reasons"), errors, allow_empty=False)
        _string_list(
            "risk.changed_surfaces", risk.get("changed_surfaces"), errors, allow_empty=False
        )

    change = receipt.get("change")
    _missing("change", change, REQUIRED_CHANGE, errors)
    _closed("change", change, ALLOWED_CHANGE, errors)
    if isinstance(change, dict):
        if not isinstance(change.get("summary"), str) or not change["summary"]:
            errors.append("change.summary must be a non-empty string")
        _string_list("change.files_touched", change.get("files_touched"), errors, allow_empty=True)
        diff_stats = change.get("diff_stats")
        _missing("change.diff_stats", diff_stats, REQUIRED_DIFF_STATS, errors)
        _closed("change.diff_stats", diff_stats, REQUIRED_DIFF_STATS, errors)
        if isinstance(diff_stats, dict):
            for key in REQUIRED_DIFF_STATS:
                value = diff_stats.get(key)
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 0
                ):
                    errors.append(f"change.diff_stats.{key} must be a non-negative integer")
        scope_notes = change.get("scope_notes")
        if scope_notes is not None and not isinstance(scope_notes, str):
            errors.append("change.scope_notes must be a string")

    artifact_ids = set()
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
    else:
        for index, artifact in enumerate(artifacts):
            _missing(f"artifacts[{index}]", artifact, REQUIRED_ARTIFACT, errors)
            _closed(f"artifacts[{index}]", artifact, ALLOWED_ARTIFACT, errors)
            if isinstance(artifact, dict):
                artifact_id = artifact.get("id")
                if not isinstance(artifact_id, str) or not artifact_id:
                    errors.append(f"artifacts[{index}].id must be a non-empty string")
                elif artifact_id in artifact_ids:
                    errors.append(f"duplicate artifact id: {artifact_id}")
                else:
                    artifact_ids.add(artifact_id)
                if artifact.get("kind") not in ARTIFACT_KINDS:
                    errors.append(
                        f"artifacts[{index}].kind has invalid value: {artifact.get('kind')}"
                    )
                _non_empty_string(
                    f"artifacts[{index}].path_or_url", artifact.get("path_or_url"), errors
                )
                _non_empty_string(
                    f"artifacts[{index}].description", artifact.get("description"), errors
                )
                if not isinstance(artifact.get("required"), bool):
                    errors.append(f"artifacts[{index}].required must be boolean")
                sha256 = artifact.get("sha256")
                if sha256 is not None and not isinstance(sha256, str):
                    errors.append(f"artifacts[{index}].sha256 must be a string or null")
                external = artifact.get("external")
                if external is not None and not isinstance(external, bool):
                    errors.append(f"artifacts[{index}].external must be boolean")

    evidence = receipt.get("evidence")
    evidence_statuses: list[str] = []
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty list")
    else:
        evidence_ids = set()
        for index, item in enumerate(evidence):
            _missing(f"evidence[{index}]", item, REQUIRED_EVIDENCE, errors)
            _closed(f"evidence[{index}]", item, ALLOWED_EVIDENCE, errors)
            if not isinstance(item, dict):
                continue
            evidence_id = item.get("id")
            if not isinstance(evidence_id, str) or not evidence_id:
                errors.append(f"evidence[{index}].id must be a non-empty string")
            elif evidence_id in evidence_ids:
                errors.append(f"duplicate evidence id: {evidence_id}")
            else:
                evidence_ids.add(evidence_id)
            if item.get("kind") not in EVIDENCE_KINDS:
                errors.append(f"evidence[{index}].kind has invalid value: {item.get('kind')}")
            status = item.get("status")
            if status not in STATUSES:
                errors.append(f"evidence[{index}].status has invalid value: {status}")
            else:
                evidence_statuses.append(status)
            if not isinstance(item.get("required"), bool):
                errors.append(f"evidence[{index}].required must be boolean")
            _non_empty_string(f"evidence[{index}].summary", item.get("summary"), errors)
            command = item.get("command")
            if command is not None:
                _string_list(f"evidence[{index}].command", command, errors, allow_empty=True)
            evidence_artifact_ids = item.get("artifact_ids")
            if evidence_artifact_ids is not None:
                _string_list(
                    f"evidence[{index}].artifact_ids",
                    evidence_artifact_ids,
                    errors,
                    allow_empty=True,
                )
                if isinstance(evidence_artifact_ids, list):
                    for artifact_id in evidence_artifact_ids:
                        if isinstance(artifact_id, str) and artifact_id not in artifact_ids:
                            errors.append(
                                f"evidence[{index}] references unknown artifact: {artifact_id}"
                            )
            freshness_hours = item.get("freshness_hours")
            if freshness_hours is not None and (
                not isinstance(freshness_hours, int)
                or isinstance(freshness_hours, bool)
                or freshness_hours < 0
            ):
                errors.append(
                    f"evidence[{index}].freshness_hours must be a non-negative integer or null"
                )
            reason = item.get("reason")
            if reason is not None and not isinstance(reason, str):
                errors.append(f"evidence[{index}].reason must be a string")

    security = receipt.get("security")
    _missing("security", security, {"secrets_scan", "permission_diff", "redaction"}, errors)
    _closed("security", security, {"secrets_scan", "permission_diff", "redaction"}, errors)
    if isinstance(security, dict):
        for key in ("secrets_scan", "permission_diff", "redaction"):
            posture = security.get(key)
            _missing(f"security.{key}", posture, REQUIRED_POSTURE, errors)
            _closed(f"security.{key}", posture, ALLOWED_POSTURE, errors)
            if isinstance(posture, dict):
                if posture.get("status") not in STATUSES:
                    errors.append(
                        f"security.{key}.status has invalid value: {posture.get('status')}"
                    )
                _non_empty_string(f"security.{key}.summary", posture.get("summary"), errors)
                posture_artifact_ids = posture.get("artifact_ids")
                if posture_artifact_ids is not None:
                    _string_list(
                        f"security.{key}.artifact_ids",
                        posture_artifact_ids,
                        errors,
                        allow_empty=True,
                    )
                    if isinstance(posture_artifact_ids, list):
                        for artifact_id in posture_artifact_ids:
                            if isinstance(artifact_id, str) and artifact_id not in artifact_ids:
                                errors.append(
                                    f"security.{key} references unknown artifact: {artifact_id}"
                                )
                reason = posture.get("reason")
                if reason is not None and not isinstance(reason, str):
                    errors.append(f"security.{key}.reason must be a string")

    rollback = receipt.get("rollback")
    _missing("rollback", rollback, {"status", "path"}, errors)
    _closed("rollback", rollback, ALLOWED_ROLLBACK, errors)
    if isinstance(rollback, dict):
        if rollback.get("status") not in ROLLBACK_STATUSES:
            errors.append(f"rollback.status has invalid value: {rollback.get('status')}")
        if not isinstance(rollback.get("path"), str) or not rollback["path"]:
            errors.append("rollback.path must be a non-empty string")
        notes = rollback.get("notes")
        if notes is not None and not isinstance(notes, str):
            errors.append("rollback.notes must be a string")

    _string_list("limitations", receipt.get("limitations"), errors, allow_empty=True)

    overall = receipt.get("overall")
    _missing("overall", overall, {"status", "review_decision"}, errors)
    _closed("overall", overall, {"status", "review_decision"}, errors)
    if isinstance(overall, dict):
        if overall.get("status") not in STATUSES:
            errors.append(f"overall.status has invalid value: {overall.get('status')}")
        if overall.get("review_decision") not in OVERALL_DECISIONS:
            errors.append(
                f"overall.review_decision has invalid value: {overall.get('review_decision')}"
            )

    if tier in {"T1", "T2", "T3", "T4"} and evidence_statuses:
        if not any(status in {"passed", "passed_with_warnings", "partial"} for status in evidence_statuses):
            errors.append(f"{tier} receipts need at least one positive evidence item")
    if tier in {"T3", "T4"} and isinstance(rollback, dict):
        if rollback.get("status") not in {"documented", "tested", "partial"}:
            errors.append(f"{tier} receipts need a rollback path or explicit partial rollback")
    if tier == "T4" and not any(
        isinstance(item, dict) and item.get("kind") in {"attestation", "release"}
        for item in evidence or []
    ):
        errors.append("T4 receipts need release or attestation evidence")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", nargs="+", type=Path)
    args = parser.parse_args()

    failed = False
    for receipt_path in args.receipts:
        errors = validate_receipt(receipt_path)
        if errors:
            failed = True
            for error in errors:
                print(f"{receipt_path}: invalid: {error}")
        else:
            print(f"{receipt_path}: valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
