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
TIERS = {"T0", "T1", "T2", "T3", "T4"}
AGENTS = {"codex", "claude-code", "manual", "github-actions", "unknown"}
MODES = {"local", "ci", "manual"}
HEAD_SHA_STATUSES = {"exact", "pending_commit", "external_anchor"}
ROLLBACK_STATUSES = {"documented", "tested", "partial", "blocked", "not_applicable"}
OVERALL_DECISIONS = {"ready", "ready_with_operator_awareness", "revise", "reject"}
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
    if receipt.get("schema_version") != "proof-pr.v1":
        errors.append("schema_version must be proof-pr.v1")

    subject = receipt.get("subject")
    _missing("subject", subject, REQUIRED_SUBJECT, errors)
    if isinstance(subject, dict):
        for key in ("repo", "base_ref", "base_sha", "head_ref", "head_sha"):
            if not isinstance(subject.get(key), str) or not subject[key]:
                errors.append(f"subject.{key} must be a non-empty string")
        head_sha_status = subject.get("head_sha_status", "exact")
        if head_sha_status not in HEAD_SHA_STATUSES:
            errors.append(f"subject.head_sha_status has invalid value: {head_sha_status}")
        if head_sha_status == "exact" and subject.get("head_sha") == "pending-pr-head":
            errors.append("subject.head_sha cannot be pending-pr-head when head_sha_status is exact")
        pr_number = subject.get("pr_number")
        if pr_number is not None and (not isinstance(pr_number, int) or pr_number < 1):
            errors.append("subject.pr_number must be a positive integer or null")

    producer = receipt.get("producer")
    _missing("producer", producer, REQUIRED_PRODUCER, errors)
    if isinstance(producer, dict):
        if producer.get("agent") not in AGENTS:
            errors.append(f"producer.agent has invalid value: {producer.get('agent')}")
        if producer.get("mode") not in MODES:
            errors.append(f"producer.mode has invalid value: {producer.get('mode')}")

    risk = receipt.get("risk")
    _missing("risk", risk, REQUIRED_RISK, errors)
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
    if isinstance(change, dict):
        if not isinstance(change.get("summary"), str) or not change["summary"]:
            errors.append("change.summary must be a non-empty string")
        _string_list("change.files_touched", change.get("files_touched"), errors, allow_empty=True)
        diff_stats = change.get("diff_stats")
        _missing("change.diff_stats", diff_stats, REQUIRED_DIFF_STATS, errors)
        if isinstance(diff_stats, dict):
            for key in REQUIRED_DIFF_STATS:
                if not isinstance(diff_stats.get(key), int) or diff_stats[key] < 0:
                    errors.append(f"change.diff_stats.{key} must be a non-negative integer")

    artifact_ids = set()
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
    else:
        for index, artifact in enumerate(artifacts):
            _missing(f"artifacts[{index}]", artifact, REQUIRED_ARTIFACT, errors)
            if isinstance(artifact, dict):
                artifact_id = artifact.get("id")
                if not isinstance(artifact_id, str) or not artifact_id:
                    errors.append(f"artifacts[{index}].id must be a non-empty string")
                elif artifact_id in artifact_ids:
                    errors.append(f"duplicate artifact id: {artifact_id}")
                else:
                    artifact_ids.add(artifact_id)

    evidence = receipt.get("evidence")
    evidence_statuses: list[str] = []
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty list")
    else:
        evidence_ids = set()
        for index, item in enumerate(evidence):
            _missing(f"evidence[{index}]", item, REQUIRED_EVIDENCE, errors)
            if not isinstance(item, dict):
                continue
            evidence_id = item.get("id")
            if not isinstance(evidence_id, str) or not evidence_id:
                errors.append(f"evidence[{index}].id must be a non-empty string")
            elif evidence_id in evidence_ids:
                errors.append(f"duplicate evidence id: {evidence_id}")
            else:
                evidence_ids.add(evidence_id)
            status = item.get("status")
            if status not in STATUSES:
                errors.append(f"evidence[{index}].status has invalid value: {status}")
            else:
                evidence_statuses.append(status)
            if not isinstance(item.get("required"), bool):
                errors.append(f"evidence[{index}].required must be boolean")
            for artifact_id in item.get("artifact_ids", []):
                if artifact_id not in artifact_ids:
                    errors.append(
                        f"evidence[{index}] references unknown artifact: {artifact_id}"
                    )

    security = receipt.get("security")
    _missing("security", security, {"secrets_scan", "permission_diff", "redaction"}, errors)
    if isinstance(security, dict):
        for key in ("secrets_scan", "permission_diff", "redaction"):
            posture = security.get(key)
            _missing(f"security.{key}", posture, REQUIRED_POSTURE, errors)
            if isinstance(posture, dict):
                if posture.get("status") not in STATUSES:
                    errors.append(
                        f"security.{key}.status has invalid value: {posture.get('status')}"
                    )
                for artifact_id in posture.get("artifact_ids", []):
                    if artifact_id not in artifact_ids:
                        errors.append(
                            f"security.{key} references unknown artifact: {artifact_id}"
                        )

    rollback = receipt.get("rollback")
    _missing("rollback", rollback, {"status", "path"}, errors)
    if isinstance(rollback, dict):
        if rollback.get("status") not in ROLLBACK_STATUSES:
            errors.append(f"rollback.status has invalid value: {rollback.get('status')}")
        if not isinstance(rollback.get("path"), str) or not rollback["path"]:
            errors.append("rollback.path must be a non-empty string")

    _string_list("limitations", receipt.get("limitations"), errors, allow_empty=True)

    overall = receipt.get("overall")
    _missing("overall", overall, {"status", "review_decision"}, errors)
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
