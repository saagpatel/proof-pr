"""Check public git refs for non-private email metadata."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EMAIL_PATTERN = (
    r"(^[0-9]+\+[^@]+@users\.noreply\.github\.com$|^noreply@github\.com$)"
)


@dataclass(frozen=True)
class Finding:
    ref: str
    object_id: str
    field: str
    name: str
    email: str


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def _expand_refs(cwd: Path, refspecs: list[str]) -> list[str]:
    refs: list[str] = []
    for refspec in refspecs:
        if any(char in refspec for char in "*?["):
            expanded = [
                line
                for line in _git(cwd, "for-each-ref", "--format=%(refname)", refspec).splitlines()
                if line
            ]
            refs.extend(expanded)
        else:
            refs.append(refspec)
    return sorted(dict.fromkeys(refs))


def _check_email(
    *,
    findings: list[Finding],
    allowed: re.Pattern[str],
    ref: str,
    object_id: str,
    field: str,
    name: str,
    email: str,
) -> None:
    if not allowed.search(email):
        findings.append(Finding(ref, object_id, field, name, email))


def _scan_commits(
    cwd: Path,
    ref: str,
    allowed: re.Pattern[str],
    findings: list[Finding],
    *,
    base_ref: str | None = None,
) -> None:
    revision = f"{base_ref}..{ref}" if base_ref else ref
    output = _git(cwd, "log", revision, "--format=%H%x09%an%x09%ae%x09%cn%x09%ce")
    for line in output.splitlines():
        if not line:
            continue
        commit, author_name, author_email, committer_name, committer_email = line.split("\t")
        _check_email(
            findings=findings,
            allowed=allowed,
            ref=ref,
            object_id=commit,
            field="author",
            name=author_name,
            email=author_email,
        )
        _check_email(
            findings=findings,
            allowed=allowed,
            ref=ref,
            object_id=commit,
            field="committer",
            name=committer_name,
            email=committer_email,
        )


def _scan_tag(cwd: Path, ref: str, allowed: re.Pattern[str], findings: list[Finding]) -> None:
    object_type = _git(cwd, "for-each-ref", "--format=%(objecttype)", ref).strip()
    if object_type != "tag":
        return
    object_id = _git(cwd, "rev-parse", ref).strip()
    tag = _git(cwd, "cat-file", "-p", ref)
    for line in tag.splitlines():
        if not line.startswith("tagger "):
            continue
        identity = line.removeprefix("tagger ")
        if "<" not in identity or ">" not in identity:
            findings.append(Finding(ref, object_id, "tagger", identity, ""))
            return
        name = identity.split("<", 1)[0].strip()
        email = identity.split("<", 1)[1].split(">", 1)[0]
        _check_email(
            findings=findings,
            allowed=allowed,
            ref=ref,
            object_id=object_id,
            field="tagger",
            name=name,
            email=email,
        )
        return


def check_metadata(
    cwd: Path,
    refspecs: list[str],
    email_pattern: str,
    *,
    base_ref: str | None = None,
    scan_tags: bool = True,
) -> list[Finding]:
    allowed = re.compile(email_pattern)
    findings: list[Finding] = []
    refs = _expand_refs(cwd, refspecs)
    if not refs:
        raise ValueError("no refs matched")
    for ref in refs:
        _scan_commits(cwd, ref, allowed, findings, base_ref=base_ref)
        if scan_tags and base_ref is None:
            _scan_tag(cwd, ref, allowed, findings)
    return findings


def check_public_git_metadata(args: argparse.Namespace) -> int:
    try:
        findings = check_metadata(
            Path(args.cwd).resolve(),
            args.refs or ["HEAD"],
            args.allowed_email_regex,
            base_ref=args.base_ref,
            scan_tags=not args.no_tags,
        )
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"metadata check failed: {exc}", file=sys.stderr)
        return 2

    if findings:
        for finding in findings:
            print(
                f"{finding.ref}: {finding.object_id}: {finding.field} "
                f"{finding.name} <{finding.email}> is not allowed"
            )
        return 1

    print("public git metadata ok")
    return 0


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "check-public-git-metadata",
        help="Fail when selected refs use non-noreply public git email metadata",
    )
    parser.add_argument("--cwd", default=".", help="Repository checkout to inspect.")
    parser.add_argument(
        "--ref",
        action="append",
        dest="refs",
        help="Ref or for-each-ref glob to inspect. Repeatable. Defaults to HEAD.",
    )
    parser.add_argument(
        "--allowed-email-regex",
        default=DEFAULT_EMAIL_PATTERN,
        help="Regex for allowed public email metadata.",
    )
    parser.add_argument(
        "--base-ref",
        help=(
            "Only inspect commits reachable from each --ref but not from this base "
            "ref, for example origin/main. Tagger metadata is skipped in range mode."
        ),
    )
    parser.add_argument(
        "--no-tags",
        action="store_true",
        help="Skip annotated tagger metadata checks for selected tag refs.",
    )
    parser.set_defaults(func=check_public_git_metadata)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser(subparsers)
    args = parser.parse_args(["check-public-git-metadata", *sys.argv[1:]])
    return args.func(args)
