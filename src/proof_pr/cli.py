#!/usr/bin/env python3
"""Tiny proof-pr CLI MVP.

Commands:
- init: create a proof-pr.v1 receipt draft from git/gh context.
- collect: update a receipt with changed files and diff stats.
- run: execute one verification command and append evidence.
- run-config: execute configured verification commands.
- finalize: update the overall status and review decision from collected proof.
- render: print the Markdown PR proof block for a receipt.
- validate: validate receipts using the local validator.
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


def _status_line(item: dict[str, Any], *, full_commands: bool = False) -> str:
    status = item.get("status", "unknown")
    summary = item.get("summary", "")
    command = item.get("command")
    label = item.get("id", item.get("kind", "evidence"))
    if command:
        rendered_command = _render_command(command, full_commands=full_commands)
        return f"- {label}: `{rendered_command}` -> `{status}` ({summary})"
    return f"- {label}: `{status}` ({summary})"


def render_markdown(receipt: dict[str, Any], *, full_commands: bool = False) -> str:
    subject = receipt["subject"]
    risk = receipt["risk"]
    overall = receipt["overall"]
    security = receipt["security"]
    rollback = receipt["rollback"]
    head_sha = subject["head_sha"]
    lines = [
        "<!-- proof-pr:v1 start -->",
        "## Proof Bundle",
        "",
        f"Risk: `{risk['tier']}`",
        f"Receipt: `proof-pr.v1` for `{head_sha}`",
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
    if args.finalize:
        _finalize_receipt(
            receipt,
            allow_limitations=args.allow_limitations,
            clear_draft_limitations=not args.keep_draft_limitations,
        )
    _write_receipt(path, receipt)
    message = f"ran {len(commands)} configured command(s)"
    if args.finalize:
        overall = receipt["overall"]
        message += f"; finalized {overall['status']} / {overall['review_decision']}"
    print(message)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    receipt = _load_receipt(Path(args.receipt))
    print(render_markdown(receipt, full_commands=args.full_commands))
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
    render.set_defaults(func=cmd_render)

    validate = subparsers.add_parser("validate", help="Validate proof-pr receipts")
    validate.add_argument("receipts", nargs="+")
    validate.set_defaults(func=cmd_validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
