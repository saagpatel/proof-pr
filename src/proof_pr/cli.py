#!/usr/bin/env python3
"""Tiny proof-pr CLI MVP.

Commands:
- init: create a proof-pr.v1 receipt draft from git/gh context.
- collect: update a receipt with changed files and diff stats.
- run: execute one verification command and append evidence.
- run-config: execute configured verification commands.
- collect-public-git-metadata: run the public metadata check into receipt evidence.
- receipt-hygiene: suggest missing standard proof evidence by risk tier.
- finalize: update the overall status and review decision from collected proof.
- render: print the Markdown PR proof block for a receipt.
- validate: validate receipts using the local validator.
- check-public-git-metadata: fail when public git metadata leaks non-noreply emails.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from . import public_git_metadata
from .validate_receipts import validate_receipt

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
DRAFT_LIMITATION = "Draft receipt; evidence has not been fully collected."
NON_GREEN_REQUIRED = {"failed", "blocked", "skipped", "stale", "partial", "not_applicable"}
NON_GREEN_SECURITY = {"failed", "blocked", "skipped", "stale", "partial"}
MAX_RENDERED_COMMAND_CHARS = 96
PASSING_STATUSES = {"passed", "passed_with_warnings"}
ATTENTION_STATUSES = {"failed", "blocked", "skipped", "stale", "partial"}
WORKFLOW_SURFACES = {
    "ci",
    "github-actions",
    "permissions",
    "workflow",
    "workflows",
    "agent-access",
    "agent access",
}
DEFAULT_ROLLBACK_PATH = "Revert the PR unless a more specific rollback path is added."


def _run(args: list[str], *, cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _run_with_log(args: list[str], *, cwd: Path, log_path: Path) -> tuple[str, int | None]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError as exc:
        log_path.write_text(str(exc) + "\n", encoding="utf-8")
        return "blocked", None
    log_path.write_text(result.stdout, encoding="utf-8")
    return ("passed" if result.returncode == 0 else "failed"), result.returncode


def _format_command(command: list[str]) -> str:
    return shlex.join(str(part) for part in command)


def _render_command(command: list[str], *, full_commands: bool = False) -> str:
    formatted = _format_command(command)
    if full_commands or len(formatted) <= MAX_RENDERED_COMMAND_CHARS:
        return formatted
    command_name = str(command[0]) if command else "command"
    return f"{command_name} ... ({len(command)} args; full command in receipt)"


def _git(cwd: Path, *args: str) -> str | None:
    return _run(["git", *args], cwd=cwd)


def _repo_slug(cwd: Path) -> str:
    remote = _git(cwd, "remote", "get-url", "origin") or cwd.name
    if remote.endswith(".git"):
        remote = remote[:-4]
    if remote.startswith("https://github.com/"):
        remote = remote.removeprefix("https://github.com/")
    elif remote.startswith("git@github.com:"):
        remote = remote.removeprefix("git@github.com:")
    elif ":" in remote and "/" in remote:
        remote = remote.split(":", 1)[1]
    return remote if "/" in remote else cwd.name


def _gh_pr(cwd: Path) -> dict[str, Any]:
    raw = _run(
        [
            "gh",
            "pr",
            "view",
            "--json",
            "number,url,headRefName,baseRefName,headRefOid,baseRefOid",
        ],
        cwd=cwd,
    )
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _default_receipt(cwd: Path, *, tier: str, summary: str, agent: str, mode: str) -> dict[str, Any]:
    pr = _gh_pr(cwd)
    head_ref = pr.get("headRefName") or _git(cwd, "branch", "--show-current") or "unknown"
    base_ref = pr.get("baseRefName") or "main"
    head_sha = pr.get("headRefOid") or _git(cwd, "rev-parse", "HEAD") or "unknown"
    base_sha = (
        pr.get("baseRefOid")
        or _git(cwd, "rev-parse", f"origin/{base_ref}")
        or _git(cwd, "merge-base", base_ref, "HEAD")
        or "unknown"
    )
    repo = _repo_slug(cwd)
    pr_number = pr.get("number")
    short_sha = head_sha[:7] if isinstance(head_sha, str) else "unknown"
    receipt_id = f"{repo.replace('/', '-')}-pr-{pr_number or 'local'}-{short_sha}"

    return {
        "schema_version": "proof-pr.v1",
        "receipt_id": receipt_id,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "subject": {
            "repo": repo,
            "pr_number": pr_number,
            "pr_url": pr.get("url"),
            "base_ref": base_ref,
            "base_sha": base_sha,
            "head_ref": head_ref,
            "head_sha": head_sha,
            "head_sha_status": "exact",
        },
        "producer": {
            "tool": "proof-pr",
            "version": __version__,
            "agent": agent,
            "mode": mode,
        },
        "risk": {
            "tier": tier,
            "reasons": ["draft receipt; update before merge"],
            "changed_surfaces": ["unknown"],
        },
        "change": {
            "summary": summary,
            "files_touched": [],
            "diff_stats": {"files": 0, "additions": 0, "deletions": 0},
            "scope_notes": "",
        },
        "evidence": [
            {
                "id": "diff-review",
                "kind": "diff-review",
                "status": "partial",
                "required": True,
                "summary": "Draft receipt generated with PR identity and diff metadata; review evidence before merge.",
                "reason": "Diff metadata collected, but the change has not been fully reviewed yet",
            }
        ],
        "security": {
            "secrets_scan": {
                "status": "skipped",
                "summary": "Not collected yet."
            },
            "permission_diff": {
                "status": "skipped",
                "summary": "Not collected yet."
            },
            "redaction": {
                "status": "not_applicable",
                "summary": "No screenshots attached yet."
            },
        },
        "rollback": {
            "status": "documented",
            "path": "Revert the PR unless a more specific rollback path is added.",
        },
        "artifacts": [],
        "limitations": [DRAFT_LIMITATION],
        "overall": {
            "status": "partial",
            "review_decision": "revise",
        },
    }


def _load_receipt(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
        handle.write("\n")


def _load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _diff_range(receipt: dict[str, Any]) -> str:
    subject = receipt.get("subject", {})
    base_sha = subject.get("base_sha")
    head_sha = subject.get("head_sha")
    if isinstance(base_sha, str) and isinstance(head_sha, str):
        return f"{base_sha}...{head_sha}"
    return "HEAD"


def _collect_diff(cwd: Path, receipt: dict[str, Any]) -> None:
    diff_range = _diff_range(receipt)
    names = _git(cwd, "diff", "--name-only", diff_range)
    files = [line for line in (names or "").splitlines() if line]
    receipt["change"]["files_touched"] = files

    numstat = _git(cwd, "diff", "--numstat", diff_range)
    additions = 0
    deletions = 0
    counted_files = 0
    for line in (numstat or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        counted_files += 1
        if parts[0].isdigit():
            additions += int(parts[0])
        if parts[1].isdigit():
            deletions += int(parts[1])
    receipt["change"]["diff_stats"] = {
        "files": len(files) or counted_files,
        "additions": additions,
        "deletions": deletions,
    }


def _apply_config(receipt: dict[str, Any], config: dict[str, Any]) -> None:
    risk = config.get("risk")
    if isinstance(risk, dict):
        receipt["risk"].update({k: v for k, v in risk.items() if k in receipt["risk"]})
    change = config.get("change")
    if isinstance(change, dict):
        for key in ("summary", "scope_notes"):
            if key in change:
                receipt["change"][key] = change[key]
    rollback = config.get("rollback")
    if isinstance(rollback, dict):
        receipt["rollback"].update(rollback)
    security = config.get("security")
    if isinstance(security, dict):
        for key in ("secrets_scan", "permission_diff", "redaction"):
            if isinstance(security.get(key), dict):
                receipt["security"][key].update(security[key])


def _upsert_artifact(receipt: dict[str, Any], artifact: dict[str, Any]) -> None:
    artifacts = receipt.setdefault("artifacts", [])
    for index, existing in enumerate(artifacts):
        if existing.get("id") == artifact["id"]:
            artifacts[index] = artifact
            return
    artifacts.append(artifact)


def _upsert_evidence(receipt: dict[str, Any], item: dict[str, Any]) -> None:
    evidence = receipt.setdefault("evidence", [])
    for index, existing in enumerate(evidence):
        if existing.get("id") == item["id"]:
            evidence[index] = item
            return
    evidence.append(item)


def _remove_draft_limitations(receipt: dict[str, Any]) -> None:
    limitations = receipt.get("limitations")
    if not isinstance(limitations, list):
        return
    receipt["limitations"] = [
        item for item in limitations if isinstance(item, str) and item != DRAFT_LIMITATION
    ]


def _has_diff_metadata(receipt: dict[str, Any]) -> bool:
    change = receipt.get("change", {})
    if not isinstance(change, dict):
        return False
    files = change.get("files_touched")
    stats = change.get("diff_stats")
    return isinstance(files, list) and isinstance(stats, dict)


def _normalize_diff_metadata(receipt: dict[str, Any]) -> None:
    if not _has_diff_metadata(receipt):
        return
    for item in receipt.get("evidence", []):
        if not isinstance(item, dict):
            continue
        if item.get("id") == "diff-review" and item.get("status") == "partial":
            item["status"] = "passed"
            item["summary"] = (
                "Diff metadata collected: changed files and diff stats are present. "
                "Semantic review remains the reviewer's responsibility."
            )
            item.pop("reason", None)


def _security_statuses(receipt: dict[str, Any]) -> list[str]:
    security = receipt.get("security", {})
    statuses: list[str] = []
    if not isinstance(security, dict):
        return statuses
    for key in ("secrets_scan", "permission_diff", "redaction"):
        posture = security.get(key)
        if isinstance(posture, dict) and isinstance(posture.get("status"), str):
            statuses.append(posture["status"])
    return statuses


def _finalize_receipt(
    receipt: dict[str, Any],
    *,
    allow_limitations: bool,
    clear_draft_limitations: bool,
) -> None:
    if clear_draft_limitations:
        _remove_draft_limitations(receipt)
    _normalize_diff_metadata(receipt)

    evidence = [item for item in receipt.get("evidence", []) if isinstance(item, dict)]
    required = [item for item in evidence if item.get("required") is True]
    required_statuses = [
        item.get("status") for item in required if isinstance(item.get("status"), str)
    ]
    security_statuses = _security_statuses(receipt)
    limitations = receipt.get("limitations")
    has_limitations = isinstance(limitations, list) and bool(limitations)

    overall = receipt.setdefault("overall", {})
    if "failed" in required_statuses or "failed" in security_statuses:
        overall.update({"status": "failed", "review_decision": "reject"})
        return
    if "blocked" in required_statuses or "blocked" in security_statuses:
        overall.update({"status": "blocked", "review_decision": "revise"})
        return
    if not required or any(status in NON_GREEN_REQUIRED for status in required_statuses):
        overall.update({"status": "partial", "review_decision": "revise"})
        return
    if any(status in NON_GREEN_SECURITY for status in security_statuses):
        overall.update({"status": "partial", "review_decision": "revise"})
        return
    if has_limitations and not allow_limitations:
        overall.update({"status": "partial", "review_decision": "revise"})
        return

    optional_statuses = [
        item.get("status")
        for item in evidence
        if item.get("required") is False and isinstance(item.get("status"), str)
    ]
    has_warning = (
        "passed_with_warnings" in required_statuses
        or "passed_with_warnings" in security_statuses
        or has_limitations
        or any(status in {"failed", "blocked", "stale", "partial"} for status in optional_statuses)
    )
    if has_warning:
        overall.update(
            {
                "status": "passed_with_warnings",
                "review_decision": "ready_with_operator_awareness",
            }
        )
    else:
        overall.update({"status": "passed", "review_decision": "ready"})


def _run_evidence(
    *,
    cwd: Path,
    receipt_path: Path,
    receipt: dict[str, Any],
    evidence_id: str,
    kind: str,
    command: list[str],
    required: bool,
    summary: str,
    artifact_dir: Path | None,
) -> None:
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"invalid evidence kind: {kind}")
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("command must not be empty")
    root = artifact_dir or receipt_path.parent / "proof-pr-artifacts"
    log_path = root / f"{evidence_id}.log"
    status, exit_code = _run_with_log(command, cwd=cwd, log_path=log_path)
    artifact_id = f"{evidence_id}-log"
    _upsert_artifact(
        receipt,
        {
            "id": artifact_id,
            "kind": "log",
            "path_or_url": str(log_path),
            "description": f"Combined stdout/stderr for {_format_command(command)}",
            "sha256": None,
            "required": required,
            "external": False,
        },
    )
    detail = summary
    if exit_code is not None:
        detail = f"{summary} Exit code {exit_code}."
    _upsert_evidence(
        receipt,
        {
            "id": evidence_id,
            "kind": kind,
            "command": command,
            "status": status,
            "required": required,
            "summary": detail,
            "artifact_ids": [artifact_id],
        },
    )


def _metadata_scope_sentence(summary: public_git_metadata.CheckSummary) -> str:
    refs = ", ".join(summary.refs)
    if summary.mode == "introduced":
        scope = f"{summary.base_ref or 'base'}..{refs}"
        tag_note = "legacy history and tags were not in scope"
    else:
        scope = refs
        tag_note = f"tag scope: {summary.tag_scope}"
    return (
        f"Public git metadata checked in {summary.mode} mode for {scope}; "
        f"{tag_note}; findings={summary.finding_count}."
    )


def _metadata_check_command(
    *,
    refs: list[str],
    base_ref: str | None,
    email_pattern: str,
    scan_tags: bool,
) -> list[str]:
    command = ["proof-pr", "check-public-git-metadata"]
    for ref in refs:
        command.extend(["--ref", ref])
    if base_ref:
        command.extend(["--base-ref", base_ref])
    if email_pattern != public_git_metadata.DEFAULT_EMAIL_PATTERN:
        command.extend(["--allowed-email-regex", email_pattern])
    if not scan_tags:
        command.append("--no-tags")
    command.extend(["--summary-format", "text"])
    return command


def _collect_public_git_metadata(
    *,
    cwd: Path,
    receipt: dict[str, Any],
    evidence_id: str,
    refs: list[str],
    base_ref: str | None,
    email_pattern: str,
    scan_tags: bool,
    required: bool,
) -> str:
    try:
        findings = public_git_metadata.check_metadata(
            cwd,
            refs,
            email_pattern,
            base_ref=base_ref,
            scan_tags=scan_tags,
        )
    except (subprocess.CalledProcessError, ValueError) as exc:
        status = "blocked"
        summary = public_git_metadata.summarize_metadata_check(
            refs=refs,
            email_pattern=email_pattern,
            findings=[],
            status=status,
            base_ref=base_ref,
            scan_tags=scan_tags,
        )
        item: dict[str, Any] = {
            "id": evidence_id,
            "kind": "security",
            "command": _metadata_check_command(
                refs=refs,
                base_ref=base_ref,
                email_pattern=email_pattern,
                scan_tags=scan_tags,
            ),
            "status": status,
            "required": required,
            "summary": _metadata_scope_sentence(summary),
            "reason": f"metadata check failed: {exc}",
        }
        _upsert_evidence(receipt, item)
        return status

    status = "failed" if findings else "passed"
    summary = public_git_metadata.summarize_metadata_check(
        refs=refs,
        email_pattern=email_pattern,
        findings=findings,
        status=status,
        base_ref=base_ref,
        scan_tags=scan_tags,
    )
    item = {
        "id": evidence_id,
        "kind": "security",
        "command": _metadata_check_command(
            refs=refs,
            base_ref=base_ref,
            email_pattern=email_pattern,
            scan_tags=scan_tags,
        ),
        "status": status,
        "required": required,
        "summary": _metadata_scope_sentence(summary),
    }
    if findings:
        item["reason"] = (
            f"{len(findings)} public git metadata finding(s); run the command for details."
        )
    _upsert_evidence(receipt, item)
    return status


def _evidence_items(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in receipt.get("evidence", []) if isinstance(item, dict)]


def _evidence_by_id(receipt: dict[str, Any], evidence_id: str) -> dict[str, Any] | None:
    for item in _evidence_items(receipt):
        if item.get("id") == evidence_id:
            return item
    return None


def _hygiene_finding(
    *,
    check: str,
    status: str,
    severity: str,
    message: str,
    suggestion: str,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "check": check,
        "status": status,
        "severity": severity,
        "message": message,
        "suggestion": suggestion,
    }
    return finding


def _with_command(finding: dict[str, Any], command: list[str]) -> dict[str, Any]:
    finding["command"] = command
    return finding


def _with_patch(finding: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    finding["receipt_patch"] = patch
    return finding


def _posture_status(receipt: dict[str, Any], key: str) -> str | None:
    posture = receipt.get("security", {}).get(key)
    if isinstance(posture, dict) and isinstance(posture.get("status"), str):
        return posture["status"]
    return None


def _changed_surfaces(receipt: dict[str, Any]) -> set[str]:
    risk = receipt.get("risk", {})
    surfaces = risk.get("changed_surfaces") if isinstance(risk, dict) else []
    return {str(surface).lower() for surface in surfaces if isinstance(surface, str)}


def _receipt_hygiene_findings(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    risk = receipt.get("risk", {})
    tier = risk.get("tier") if isinstance(risk, dict) else None
    tier_index = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4}.get(str(tier), -1)
    changed_surfaces = _changed_surfaces(receipt)
    findings: list[dict[str, str]] = []

    public_metadata = _evidence_by_id(receipt, "public-git-metadata")
    if tier_index >= 3:
        if not public_metadata:
            findings.append(
                _with_command(
                    _with_patch(
                        _hygiene_finding(
                            check="public-git-metadata",
                            status="missing",
                            severity="warning",
                            message=(
                                "T3/T4 receipts should state whether public git metadata "
                                "was checked."
                            ),
                            suggestion=(
                                "Run the metadata collector, or add an explicit "
                                "not_applicable evidence item with the reason."
                            ),
                        ),
                        {
                            "evidence": [
                                {
                                    "id": "public-git-metadata",
                                    "kind": "security",
                                    "status": "not_applicable",
                                    "required": False,
                                    "summary": (
                                        "Public git metadata check was not applicable "
                                        "for this private/local-only change."
                                    ),
                                    "reason": "Replace with the bounded reason.",
                                }
                            ]
                        },
                    ),
                    [
                        "proof-pr",
                        "collect-public-git-metadata",
                        "--receipt",
                        "<path>",
                        "--base-ref",
                        "origin/main",
                        "--ref",
                        "HEAD",
                    ],
                )
            )
        elif public_metadata.get("status") not in PASSING_STATUSES:
            findings.append(
                _hygiene_finding(
                    check="public-git-metadata",
                    status=str(public_metadata.get("status", "unknown")),
                    severity="warning",
                    message="Public git metadata evidence exists but is not passing.",
                    suggestion="Resolve metadata findings or make the limitation explicit before merge.",
                )
            )

    secrets_status = _posture_status(receipt, "secrets_scan")
    if tier_index >= 3 and secrets_status not in PASSING_STATUSES:
        findings.append(
            _with_patch(
                _hygiene_finding(
                    check="secrets-scan",
                    status=secrets_status or "missing",
                    severity="warning",
                    message="T3/T4 receipts should carry a passing secrets posture.",
                    suggestion=(
                        "Run the repo secrets scan, or document a bounded partial/skipped "
                        "reason if it cannot run."
                    ),
                ),
                {
                    "security": {
                        "secrets_scan": {
                            "status": "partial",
                            "summary": "Secrets scan could not be completed before review.",
                            "reason": "Replace with the bounded reason and follow-up.",
                        }
                    }
                },
            )
        )
    elif secrets_status in ATTENTION_STATUSES:
        findings.append(
            _hygiene_finding(
                check="secrets-scan",
                status=secrets_status,
                severity="info",
                message="Secrets posture is not passing.",
                suggestion="Consider running a secrets scan before review if the change is public or sensitive.",
            )
        )

    permission_status = _posture_status(receipt, "permission_diff")
    workflow_touched = bool(changed_surfaces & WORKFLOW_SURFACES)
    if workflow_touched and permission_status not in PASSING_STATUSES:
        findings.append(
            _with_patch(
                _hygiene_finding(
                    check="permission-posture",
                    status=permission_status or "missing",
                    severity="warning",
                    message=(
                        "Workflow/permission surfaces changed without a passing "
                        "permission posture."
                    ),
                    suggestion="Review workflow permissions and record the posture.",
                ),
                {
                    "security": {
                        "permission_diff": {
                            "status": "passed",
                            "summary": (
                                "Workflow permissions were reviewed; no write or secret "
                                "access was introduced."
                            ),
                        }
                    }
                },
            )
        )
    elif tier_index >= 3 and permission_status in ATTENTION_STATUSES:
        findings.append(
            _hygiene_finding(
                check="permission-posture",
                status=permission_status,
                severity="info",
                message="Permission posture is not passing.",
                suggestion="Confirm whether permissions are truly unchanged or need review evidence.",
            )
        )

    rollback = receipt.get("rollback", {})
    rollback_status = rollback.get("status") if isinstance(rollback, dict) else None
    rollback_path = rollback.get("path") if isinstance(rollback, dict) else None
    if rollback_status not in {"documented", "tested", "partial"}:
        findings.append(
            _with_patch(
                _hygiene_finding(
                    check="rollback",
                    status=str(rollback_status or "missing"),
                    severity="warning",
                    message="Rollback posture is missing or not actionable.",
                    suggestion="Add a concrete revert, disable, rollback, or mitigation path.",
                ),
                {
                    "rollback": {
                        "status": "documented",
                        "path": "Revert this PR, or disable the changed workflow/feature.",
                    }
                },
            )
        )
    elif not isinstance(rollback_path, str) or not rollback_path:
        findings.append(
            _with_patch(
                _hygiene_finding(
                    check="rollback",
                    status="missing-path",
                    severity="warning",
                    message="Rollback status exists but the path is empty.",
                    suggestion="Add a concrete rollback path.",
                ),
                {
                    "rollback": {
                        "path": "Revert this PR, or disable the changed workflow/feature."
                    }
                },
            )
        )
    elif tier_index >= 2 and rollback_path == DEFAULT_ROLLBACK_PATH:
        findings.append(
            _with_patch(
                _hygiene_finding(
                    check="rollback",
                    status="generic",
                    severity="info",
                    message="Rollback path is still the generic draft default.",
                    suggestion="Replace it with the repo-specific rollback path before review.",
                ),
                {
                    "rollback": {
                        "path": "Revert this PR, or disable the changed workflow/feature."
                    }
                },
            )
        )

    if not findings:
        findings.append(
            _hygiene_finding(
                check="receipt-hygiene",
                status="passed",
                severity="ok",
                message="Standard hygiene checks found no missing evidence.",
                suggestion="No action needed.",
            )
        )
    return findings


def _render_hygiene(
    receipt: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    explain: bool = False,
) -> str:
    tier = receipt.get("risk", {}).get("tier", "unknown")
    receipt_id = receipt.get("receipt_id", "unknown")
    lines = [
        f"receipt hygiene: {receipt_id}",
        f"risk tier: {tier}",
    ]
    for finding in findings:
        lines.append(
            "- "
            f"{finding['severity']} {finding['check']}: "
            f"{finding['status']} - {finding['message']} "
            f"Suggestion: {finding['suggestion']}"
        )
        if explain and finding.get("command"):
            lines.append(f"  command: `{_format_command(finding['command'])}`")
        if explain and finding.get("receipt_patch"):
            patch = json.dumps(finding["receipt_patch"], indent=2, sort_keys=True)
            lines.append("  receipt patch:")
            lines.extend(f"    {line}" for line in patch.splitlines())
    return "\n".join(lines)


def _status_line(item: dict[str, Any], *, full_commands: bool = False) -> str:
    status = item.get("status", "unknown")
    summary = item.get("summary", "")
    command = item.get("command")
    label = item.get("id", item.get("kind", "evidence"))
    if command:
        rendered_command = _render_command(command, full_commands=full_commands)
        return f"- {label}: `{rendered_command}` -> `{status}` ({summary})"
    return f"- {label}: `{status}` ({summary})"


def render_markdown(
    receipt: dict[str, Any],
    *,
    full_commands: bool = False,
    head_sha_override: str | None = None,
) -> str:
    subject = receipt["subject"]
    risk = receipt["risk"]
    overall = receipt["overall"]
    security = receipt["security"]
    rollback = receipt["rollback"]
    head_sha = subject["head_sha"]
    head_sha_status = subject.get("head_sha_status", "exact")
    rendered_head_sha = head_sha_override or head_sha
    lines = [
        "<!-- proof-pr:v1 start -->",
        "## Proof Bundle",
        "",
        f"Risk: `{risk['tier']}`",
        f"Receipt: `proof-pr.v1` for `{rendered_head_sha}`",
        f"Decision: `{overall['review_decision']}`",
        "",
        "Evidence:",
    ]
    lines.extend(
        _status_line(item, full_commands=full_commands)
        for item in receipt.get("evidence", [])
    )
    lines.extend(
        [
            _status_line({"id": "secrets", **security["secrets_scan"]}),
            _status_line({"id": "permissions", **security["permission_diff"]}),
            _status_line({"id": "redaction", **security["redaction"]}),
            f"- rollback: `{rollback['status']}` ({rollback['path']})",
            "",
            "Known gaps:",
        ]
    )
    gaps = receipt.get("limitations") or []
    if gaps:
        lines.extend(f"- {gap}" for gap in gaps)
    else:
        lines.append("- None")
    if head_sha_override and head_sha_override != head_sha:
        lines.extend(
            [
                "",
                "Anchoring:",
                f"- Receipt JSON head: `{head_sha}` (`{head_sha_status}`)",
                f"- Rendered PR/check anchor: `{head_sha_override}`",
            ]
        )
    elif head_sha_status != "exact":
        lines.extend(
            [
                "",
                "Anchoring:",
                f"- Receipt JSON head: `{head_sha}` (`{head_sha_status}`)",
            ]
        )
    lines.append("<!-- proof-pr:v1 end -->")
    return "\n".join(lines)


def cmd_init(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    receipt = _default_receipt(
        cwd,
        tier=args.tier,
        summary=args.summary,
        agent=args.agent,
        mode=args.mode,
    )
    _collect_diff(cwd, receipt)
    _write_receipt(Path(args.output), receipt)
    print(f"created {args.output}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    path = Path(args.receipt)
    receipt = _load_receipt(path)
    if args.config:
        _apply_config(receipt, _load_config(Path(args.config)))
    _collect_diff(cwd, receipt)
    _write_receipt(path, receipt)
    print(f"updated {path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    path = Path(args.receipt)
    receipt = _load_receipt(path)
    _run_evidence(
        cwd=cwd,
        receipt_path=path,
        receipt=receipt,
        evidence_id=args.id,
        kind=args.kind,
        command=args.command,
        required=args.required,
        summary=args.summary,
        artifact_dir=Path(args.artifact_dir) if args.artifact_dir else None,
    )
    _write_receipt(path, receipt)
    item = next(item for item in receipt["evidence"] if item["id"] == args.id)
    print(f"ran {args.id}: {item['status']}")
    return 0


def cmd_run_config(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    path = Path(args.receipt)
    receipt = _load_receipt(path)
    config = _load_config(Path(args.config))
    _apply_config(receipt, config)
    _collect_diff(cwd, receipt)
    commands = config.get("commands", [])
    if not isinstance(commands, list):
        raise ValueError("config.commands must be a list")
    for command_config in commands:
        if not isinstance(command_config, dict):
            raise ValueError("each config command must be an object")
        _run_evidence(
            cwd=cwd,
            receipt_path=path,
            receipt=receipt,
            evidence_id=command_config["id"],
            kind=command_config.get("kind", "repo-native"),
            command=command_config["command"],
            required=bool(command_config.get("required", True)),
            summary=command_config.get("summary", command_config["id"]),
            artifact_dir=Path(args.artifact_dir) if args.artifact_dir else None,
        )
    metadata_config = config.get("public_git_metadata")
    metadata_status = None
    if isinstance(metadata_config, dict) and metadata_config.get("enabled", True):
        refs = metadata_config.get("refs") or ["HEAD"]
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            raise ValueError("config.public_git_metadata.refs must be a list of strings")
        base_ref = metadata_config.get("base_ref")
        if base_ref is not None and not isinstance(base_ref, str):
            raise ValueError("config.public_git_metadata.base_ref must be a string")
        email_pattern = metadata_config.get(
            "allowed_email_regex",
            public_git_metadata.DEFAULT_EMAIL_PATTERN,
        )
        if not isinstance(email_pattern, str):
            raise ValueError("config.public_git_metadata.allowed_email_regex must be a string")
        evidence_id = metadata_config.get("id", "public-git-metadata")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError("config.public_git_metadata.id must be a non-empty string")
        metadata_status = _collect_public_git_metadata(
            cwd=cwd,
            receipt=receipt,
            evidence_id=evidence_id,
            refs=refs,
            base_ref=base_ref,
            email_pattern=email_pattern,
            scan_tags=not bool(metadata_config.get("no_tags", False)),
            required=bool(metadata_config.get("required", True)),
        )
    if args.finalize:
        _finalize_receipt(
            receipt,
            allow_limitations=args.allow_limitations,
            clear_draft_limitations=not args.keep_draft_limitations,
        )
    _write_receipt(path, receipt)
    message = f"ran {len(commands)} configured command(s)"
    if metadata_status:
        message += f"; public git metadata {metadata_status}"
    if args.finalize:
        overall = receipt["overall"]
        message += f"; finalized {overall['status']} / {overall['review_decision']}"
    print(message)
    return 0


def cmd_collect_public_git_metadata(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    path = Path(args.receipt)
    receipt = _load_receipt(path)
    status = _collect_public_git_metadata(
        cwd=cwd,
        receipt=receipt,
        evidence_id=args.id,
        refs=args.refs or ["HEAD"],
        base_ref=args.base_ref,
        email_pattern=args.allowed_email_regex,
        scan_tags=not args.no_tags,
        required=args.required,
    )
    _write_receipt(path, receipt)
    print(f"collected {args.id}: {status}")
    return 0


def cmd_receipt_hygiene(args: argparse.Namespace) -> int:
    receipt = _load_receipt(Path(args.receipt))
    findings = _receipt_hygiene_findings(receipt)
    if args.json:
        print(
            json.dumps(
                {
                    "receipt_id": receipt.get("receipt_id"),
                    "risk_tier": receipt.get("risk", {}).get("tier"),
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        print(_render_hygiene(receipt, findings, explain=args.explain))
    has_warning = any(finding["severity"] == "warning" for finding in findings)
    return 1 if args.strict and has_warning else 0


def cmd_render(args: argparse.Namespace) -> int:
    receipt = _load_receipt(Path(args.receipt))
    print(
        render_markdown(
            receipt,
            full_commands=args.full_commands,
            head_sha_override=args.head_sha,
        )
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    failed = False
    for receipt in args.receipts:
        errors = validate_receipt(Path(receipt))
        if errors:
            failed = True
            for error in errors:
                print(f"{receipt}: invalid: {error}")
        else:
            print(f"{receipt}: valid")
    return 1 if failed else 0


def cmd_finalize(args: argparse.Namespace) -> int:
    path = Path(args.receipt)
    receipt = _load_receipt(path)
    _finalize_receipt(
        receipt,
        allow_limitations=args.allow_limitations,
        clear_draft_limitations=not args.keep_draft_limitations,
    )
    _write_receipt(path, receipt)
    overall = receipt["overall"]
    print(f"finalized {path}: {overall['status']} / {overall['review_decision']}")
    if args.require_ready and overall["review_decision"] not in {
        "ready",
        "ready_with_operator_awareness",
    }:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a proof-pr receipt draft")
    init.add_argument("--cwd", default=".")
    init.add_argument("--output", default="proof-pr.json")
    init.add_argument("--tier", choices=["T0", "T1", "T2", "T3", "T4"], default="T1")
    init.add_argument("--summary", default="Draft proof-pr receipt")
    init.add_argument(
        "--agent",
        choices=["codex", "claude-code", "manual", "github-actions", "unknown"],
        default="codex",
    )
    init.add_argument("--mode", choices=["local", "ci", "manual"], default="local")
    init.set_defaults(func=cmd_init)

    collect = subparsers.add_parser("collect", help="Update a receipt with git diff stats")
    collect.add_argument("receipt")
    collect.add_argument("--cwd", default=".")
    collect.add_argument("--config")
    collect.set_defaults(func=cmd_collect)

    run = subparsers.add_parser("run", help="Run one command and append evidence")
    run.add_argument("--receipt", required=True)
    run.add_argument("--cwd", default=".")
    run.add_argument("--id", required=True)
    run.add_argument("--kind", choices=sorted(EVIDENCE_KINDS), default="repo-native")
    run.add_argument("--summary", default="Command evidence collected.")
    run.add_argument("--artifact-dir")
    run.add_argument("--required", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=cmd_run)

    run_config = subparsers.add_parser("run-config", help="Run configured commands")
    run_config.add_argument("receipt")
    run_config.add_argument("--config", required=True)
    run_config.add_argument("--cwd", default=".")
    run_config.add_argument("--artifact-dir")
    run_config.add_argument("--finalize", action="store_true")
    run_config.add_argument("--allow-limitations", action="store_true")
    run_config.add_argument("--keep-draft-limitations", action="store_true")
    run_config.set_defaults(func=cmd_run_config)

    metadata = subparsers.add_parser(
        "collect-public-git-metadata",
        help="Run the public metadata check and upsert receipt evidence",
    )
    metadata.add_argument("--receipt", required=True)
    metadata.add_argument("--cwd", default=".")
    metadata.add_argument("--id", default="public-git-metadata")
    metadata.add_argument(
        "--ref",
        action="append",
        dest="refs",
        help="Ref to inspect. Repeatable. Defaults to HEAD.",
    )
    metadata.add_argument("--base-ref")
    metadata.add_argument(
        "--allowed-email-regex",
        default=public_git_metadata.DEFAULT_EMAIL_PATTERN,
    )
    metadata.add_argument("--no-tags", action="store_true")
    metadata.add_argument("--required", action=argparse.BooleanOptionalAction, default=True)
    metadata.set_defaults(func=cmd_collect_public_git_metadata)

    hygiene = subparsers.add_parser(
        "receipt-hygiene",
        help="Suggest missing standard receipt evidence by risk tier",
    )
    hygiene.add_argument("receipt")
    hygiene.add_argument("--json", action="store_true")
    hygiene.add_argument(
        "--explain",
        action="store_true",
        help="Include copyable commands and compact receipt patch examples",
    )
    hygiene.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when hygiene warnings are present",
    )
    hygiene.set_defaults(func=cmd_receipt_hygiene)

    finalize = subparsers.add_parser("finalize", help="Update the overall decision")
    finalize.add_argument("receipt")
    finalize.add_argument("--allow-limitations", action="store_true")
    finalize.add_argument("--keep-draft-limitations", action="store_true")
    finalize.add_argument("--require-ready", action="store_true")
    finalize.set_defaults(func=cmd_finalize)

    render = subparsers.add_parser("render", help="Render the Markdown PR block")
    render.add_argument("receipt")
    render.add_argument(
        "--full-commands",
        action="store_true",
        help="Render complete command lines instead of compacting long commands",
    )
    render.add_argument(
        "--head-sha",
        help="Render the PR block against a final head SHA without mutating the receipt",
    )
    render.set_defaults(func=cmd_render)

    validate = subparsers.add_parser("validate", help="Validate proof-pr receipts")
    validate.add_argument("receipts", nargs="+")
    validate.set_defaults(func=cmd_validate)

    public_git_metadata.add_parser(subparsers)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
