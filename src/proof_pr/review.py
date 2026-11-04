"""Advisory, locally signed review attestations; optional signing imports are lazy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PREDICATE_TYPE = "https://github.com/saagpatel/proof-pr/review-attestation/v1"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PAYLOAD_TYPE = "application/vnd.in-toto+json"
PROVES = "runner keys, not served models"
VENDORS = ("anthropic", "openai")
INSTALL_HINT = "Review signing requires Python 3.12+ and pip install 'proof-pr[review]'"
TOKEN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
SHA = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"


class ReviewError(Exception):
    """Invalid review input or local configuration."""


def signing() -> tuple[Any, Any, Any]:
    if sys.version_info < (3, 12):
        raise ReviewError(INSTALL_HINT)
    try:
        from checkseal import dsse
        from checkseal.model import VCRError
        from checkseal.sign import local
        # checkseal itself imports without the signing extra installed.
        local._require_crypto()
    except Exception as exc:
        # Missing cryptography is reported by checkseal as a VCRError.
        raise ReviewError(INSTALL_HINT) from exc
    return dsse, local, VCRError


def token(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(TOKEN, value):
        raise argparse.ArgumentTypeError("must be a safe single-component identifier")
    return value


def repo_name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(f"{TOKEN}/{TOKEN}", value):
        raise argparse.ArgumentTypeError("repo must be OWNER/NAME")
    return value


def commit_sha(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(SHA, value):
        raise argparse.ArgumentTypeError("must be a full lowercase Git commit SHA (40 or 64 hex digits)")
    return value


def positive_pr(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("PR must be positive")
    return number


def store_path(value: str | None) -> Path:
    return Path(value or os.environ.get("PROOF_PR_REVIEW_STORE") or
                "~/.local/share/proof-pr/review-attestations").expanduser()


def metadata_path(private: Path) -> Path:
    if not private.name.endswith(".private.pem"):
        raise ReviewError("--key must name a keygen .private.pem file with its .json sidecar")
    return private.with_name(private.name.removesuffix(".private.pem") + ".json")


def keygen(args: argparse.Namespace) -> int:
    _, local, _ = signing()
    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    stem = f"{args.vendor}-{args.runner}"
    private = out / f"{stem}.private.pem"
    public = out / f"{stem}.public.pem"
    metadata = out / f"{stem}.json"
    signer = local.LocalKeySigner.generate()
    created: list[Path] = []
    try:
        # Reserve all outputs exclusively before checkseal's PEM helpers write.
        # In particular, the private inode is mode 0600 before any secret bytes.
        for path in (private, public, metadata):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            os.close(fd)
        local.write_private_pem(signer, str(private))
        local.write_public_pem(signer, str(public))
        metadata.write_text(json.dumps({"keyid": signer.keyid, "vendor": args.vendor,
                                        "runner": args.runner}, indent=2) + "\n")
    except Exception:
        for path in created:
            path.unlink()
        raise
    print(signer.keyid)
    return 0


def attest(args: argparse.Namespace) -> int:
    dsse, local, _ = signing()
    private = Path(args.key).expanduser()
    signer = local.load_private_signer(str(private))
    metadata = json.loads(metadata_path(private).read_text())
    if not isinstance(metadata, dict) or metadata.get("keyid") != signer.keyid:
        raise ReviewError("key metadata keyid does not match the private key")
    runner = token(metadata.get("runner", ""))
    # Findings are opaque bytes, never interpreted or embedded.
    digest = hashlib.sha256()
    size = 0
    with Path(args.findings).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    predicate = {
        "repo": args.repo, "pr": args.pr, "base": args.base, "head": args.head,
        "scope": f"{args.base}..{args.head}",
        "reviewer": {"vendor": args.vendor, "tool": args.tool, "runner": runner},
        "run_id": args.run_id, "verdict": args.verdict,
        "findings": {"sha256": digest.hexdigest(), "bytes": size},
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    statement = {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": f"git+https://github.com/{args.repo}@{args.head}",
                     "digest": {"gitCommit": args.head}}],
        "predicateType": PREDICATE_TYPE, "predicate": predicate,
    }
    validate_statement(statement)
    payload = json.dumps(statement, sort_keys=True, separators=(",", ":")).encode()
    envelope = dsse.Envelope(payload, PAYLOAD_TYPE, [])
    envelope = dsse.Envelope(payload, PAYLOAD_TYPE, [signer.sign(envelope.signing_bytes())])
    dest = store_path(args.store) / args.repo / f"pr-{args.pr}" / args.head
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{args.vendor}-{args.run_id}.dsse.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(envelope.to_jsonable(), stream, indent=2)
        stream.write("\n")
    print(path)
    return 0


def exact_keys(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and value.keys() == keys


def validate_statement(statement: Any) -> dict[str, Any]:
    """Validate the signed shape without adding a dependency to the core CLI."""
    if not exact_keys(statement, {"_type", "subject", "predicateType", "predicate"}):
        raise ReviewError("invalid Statement v1 shape")
    if statement["_type"] != STATEMENT_TYPE or statement["predicateType"] != PREDICATE_TYPE:
        raise ReviewError("wrong statement or predicate type")
    p = statement["predicate"]
    if not exact_keys(p, {"repo", "pr", "base", "head", "scope", "reviewer", "run_id",
                          "verdict", "findings", "created_at"}):
        raise ReviewError("invalid predicate fields")
    repo_name(p["repo"])
    commit_sha(p["head"])
    commit_sha(p["base"])
    token(p["run_id"])
    if type(p["pr"]) is not int or p["pr"] < 1 or p["scope"] != f'{p["base"]}..{p["head"]}':
        raise ReviewError("invalid PR or scope")
    reviewer = p["reviewer"]
    if not exact_keys(reviewer, {"vendor", "tool", "runner"}):
        raise ReviewError("invalid reviewer")
    if reviewer["vendor"] not in VENDORS or not isinstance(reviewer["tool"], str) or not reviewer["tool"].strip():
        raise ReviewError("invalid vendor or tool")
    token(reviewer["runner"])
    findings = p["findings"]
    if (not exact_keys(findings, {"sha256", "bytes"}) or
            not isinstance(findings["sha256"], str) or
            not re.fullmatch(r"[0-9a-f]{64}", findings["sha256"]) or
            type(findings["bytes"]) is not int or findings["bytes"] < 0):
        raise ReviewError("invalid findings digest or size")
    if p["verdict"] not in ("approve", "changes_requested", "comment"):
        raise ReviewError("invalid verdict")
    created = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))
    if created.utcoffset() is None or created.utcoffset().total_seconds() != 0:
        raise ReviewError("created_at must be UTC ISO 8601")
    subjects = statement["subject"]
    if (not isinstance(subjects, list) or len(subjects) != 1 or
            not exact_keys(subjects[0], {"name", "digest"}) or
            not exact_keys(subjects[0]["digest"], {"gitCommit"})):
        raise ReviewError("invalid subject")
    commit_sha(subjects[0]["digest"]["gitCommit"])
    if subjects[0]["digest"]["gitCommit"] != p["head"]:
        raise ReviewError("subject digest must match the predicate head")
    if subjects[0]["name"] != f'git+https://github.com/{p["repo"]}@{p["head"]}':
        raise ReviewError("subject name must identify the predicate repo and head")
    return p


def load_allowlist(path: Path, local: Any) -> dict[str, dict[str, Any]]:
    entries = json.loads(path.read_text())
    if not isinstance(entries, list):
        raise ReviewError("allowlist must be a list")
    result = {}
    for entry in entries:
        if not exact_keys(entry, {"keyid", "vendor", "runner", "public_key_path"}):
            raise ReviewError("malformed allowlist entry")
        if not isinstance(entry["keyid"], str) or entry["vendor"] not in VENDORS:
            raise ReviewError("invalid allowlist keyid or vendor")
        token(entry["runner"])
        if entry["keyid"] in result:
            raise ReviewError("each keyid must appear exactly once in the allowlist")
        public = Path(entry["public_key_path"]).expanduser()
        if not public.is_absolute():
            public = path.parent / public
        result[entry["keyid"]] = {**entry, "verifier": local.load_public_verifier(str(public))}
    return result


def report_result(report: dict[str, Any], status: str, detail: str) -> int:
    report.update(status=status, detail=detail)
    print(json.dumps(report, indent=2))
    return {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[status]


def verify_two_key(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {"proves": PROVES, "repo": args.repo, "pr": args.pr,
                              "head": args.head, "base": args.base, "envelopes": []}
    try:
        dsse, local, signature_error = signing()
    except ReviewError as exc:
        print(str(exc), file=sys.stderr)
        return report_result(report, "UNKNOWN", str(exc))
    if args.from_gh:
        try:
            response = subprocess.run(
                ["gh", "pr", "view", str(args.pr), "--repo", args.repo,
                 "--json", "headRefOid,baseRefOid"],
                check=True, capture_output=True, text=True, timeout=30,
            )
            refs = json.loads(response.stdout)
            args.head = commit_sha(refs["headRefOid"])
            args.base = commit_sha(refs["baseRefOid"])
            report.update(head=args.head, base=args.base)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError,
                argparse.ArgumentTypeError) as exc:
            return report_result(report, "UNKNOWN", f"--from-gh failed: {exc}")
    root = store_path(args.store) / args.repo / f"pr-{args.pr}"
    paths: list[Path] = []
    try:
        if not root.is_dir():
            raise OSError("review store for this PR is missing or unreadable")
        def walk_error(exc: OSError) -> None:
            raise exc
        for directory, _, files in os.walk(root, onerror=walk_error):
            paths.extend(Path(directory) / name for name in files if name.endswith(".dsse.json"))
    except OSError as exc:
        return report_result(report, "UNKNOWN", str(exc))
    try:
        allowlist = load_allowlist(Path(args.allowlist).expanduser(), local)
    except (OSError, ValueError, TypeError, ReviewError, argparse.ArgumentTypeError, signature_error) as exc:
        return report_result(report, "FAIL", f"malformed allowlist: {exc}")
    approvals: list[dict[str, Any]] = []
    veto = False
    unreadable = False
    for path in sorted(paths):
        item: dict[str, Any] = {"path": str(path), "status": "reject", "reason": "malformed"}
        report["envelopes"].append(item)
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                item["detail"] = "not a regular file"
                continue
            envelope = dsse.Envelope.from_jsonable(json.loads(path.read_text()))
            # This profile has exactly one local signing key per review.
            if envelope.payload_type != PAYLOAD_TYPE or len(envelope.signatures) != 1:
                raise ReviewError("expected one local signature and in-toto payload type")
            sig = envelope.signatures[0]
            entry = allowlist.get(sig.keyid)
            item["keyid"] = sig.keyid
            if entry is None:
                item["reason"] = "unknown_key"
                continue
            try:
                entry["verifier"].verify(envelope.signing_bytes(), sig)
            except signature_error:
                item["reason"] = "bad_signature"
                continue
            statement = json.loads(envelope.payload)
            p = validate_statement(statement)
            item.update(vendor=p["reviewer"]["vendor"], run_id=p["run_id"], verdict=p["verdict"])
            if (entry["vendor"] != p["reviewer"]["vendor"] or
                    entry["runner"] != p["reviewer"]["runner"]):
                item["reason"] = "vendor_key_mismatch"
            elif p["repo"] != args.repo or p["pr"] != args.pr:
                item["reason"] = "wrong_repo_or_pr"
            elif p["head"] != args.head or statement["subject"][0]["digest"]["gitCommit"] != args.head:
                item["reason"] = "stale_head"
            elif p["verdict"] == "changes_requested":
                item["reason"] = "not_approved"
                veto = True
            elif p["base"] != args.base:
                item["reason"] = "wrong_base"
            elif p["verdict"] != "approve":
                item["reason"] = "not_approved"
            else:
                item.update(status="accept", reason="approved")
                approvals.append(item)
        except OSError as exc:
            unreadable = True
            item["detail"] = f"unreadable envelope: {exc}"
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, ReviewError,
                argparse.ArgumentTypeError, signature_error) as exc:
            item["detail"] = str(exc)
    # Search all combinations: an early duplicate cannot hide a later valid pair.
    pair = None
    for a in approvals:
        for b in approvals:
            if a["vendor"] != b["vendor"] and a["keyid"] != b["keyid"] and a["run_id"] != b["run_id"]:
                pair = [a, b]
                break
        if pair:
            break
    if not pair:
        for a in approvals:
            for b in approvals:
                if a is b:
                    continue
                if a["keyid"] == b["keyid"] or a["run_id"] == b["run_id"]:
                    a.update(status="reject", reason="same_key" if a["keyid"] == b["keyid"] else "duplicate_run")
    report["counted"] = [item["path"] for item in pair] if pair and not veto and not unreadable else []
    if unreadable:
        return report_result(report, "UNKNOWN", "one or more review envelopes could not be read")
    if veto:
        return report_result(report, "FAIL", "authenticated changes_requested for the current head")
    if not pair:
        return report_result(report, "FAIL", "no independent anthropic/openai approval pair")
    return report_result(report, "PASS", "two independent allowlisted runner keys approved the expected commit")


def command(args: argparse.Namespace) -> int:
    try:
        return args.review_func(args)
    except (ReviewError, OSError, ValueError, TypeError, argparse.ArgumentTypeError) as exc:
        print(f"review error: {exc}", file=sys.stderr)
        return 2


def add_parser(subparsers: Any) -> None:
    root = subparsers.add_parser("review", help="Sign and verify advisory runner-key review attestations")
    children = root.add_subparsers(dest="review_command", required=True)
    key = children.add_parser("keygen", help="Generate a local Ed25519 runner key and metadata sidecar")
    key.add_argument("--vendor", choices=VENDORS, required=True)
    key.add_argument("--runner", type=token, required=True)
    key.add_argument("--out-dir", required=True)
    key.set_defaults(func=command, review_func=keygen)
    att = children.add_parser("attest", help="Sign an opaque findings artifact's hash and review verdict")
    att.add_argument("--key", required=True)
    att.add_argument("--vendor", choices=VENDORS, required=True)
    att.add_argument("--tool", required=True)
    att.add_argument("--run-id", type=token, required=True)
    att.add_argument("--verdict", choices=("approve", "changes_requested", "comment"), required=True)
    att.add_argument("--findings", required=True)
    verify = children.add_parser("verify-two-key", help="Verify runner keys, not served models (JSON report)")
    verify.add_argument("--allowlist", required=True)
    source = verify.add_mutually_exclusive_group(required=True)
    source.add_argument("--head", type=commit_sha)
    source.add_argument("--from-gh", action="store_true")
    verify.add_argument("--base", type=commit_sha)
    verify.set_defaults(func=verify_command, review_func=verify_two_key)
    for parser in (att, verify):
        parser.add_argument("--repo", type=repo_name, required=True)
        parser.add_argument("--pr", type=positive_pr, required=True)
        parser.add_argument("--store")
    att.add_argument("--head", type=commit_sha, required=True)
    att.add_argument("--base", type=commit_sha, required=True)
    att.set_defaults(func=command, review_func=attest)


def verify_command(args: argparse.Namespace) -> int:
    if (not args.from_gh and not args.base) or (args.from_gh and args.base):
        report = {"proves": PROVES, "envelopes": []}
        return report_result(report, "FAIL", "use --head with --base, or --from-gh alone")
    try:
        return verify_two_key(args)
    except Exception as exc:
        report = {"proves": PROVES, "repo": args.repo, "pr": args.pr,
                  "head": args.head, "base": args.base, "envelopes": []}
        return report_result(report, "UNKNOWN", f"unexpected verification error: {exc}")
