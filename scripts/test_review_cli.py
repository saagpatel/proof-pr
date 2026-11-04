#!/usr/bin/env python3
"""End-to-end CLI tests for signed two-key review attestations."""
from __future__ import annotations

import argparse
import base64
import hashlib
import shutil
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = "example/project"
PR = 17
BASE = "a" * 40
HEAD = "b" * 40
PROOF_PR: list[str] = []
USE_INSTALLED = False
GH_PREFIX: Path | None = None


def command(*args: str, expect: int | None = 0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if not USE_INSTALLED:
        env["PYTHONPATH"] = str(ROOT / "src")
    else:
        env.pop("PYTHONPATH", None)
    if GH_PREFIX is not None:
        env["PATH"] = str(GH_PREFIX) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [*PROOF_PR, *args], cwd=ROOT, env=env, text=True,
        capture_output=True, check=False,
    )
    if expect is not None and result.returncode != expect:
        raise AssertionError(
            f"command returned {result.returncode}, expected {expect}: {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def assert_core_without_extras() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-S", "-m", "proof_pr.cli", "--help"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "review" in result.stdout


def setup_key(out_dir: Path, vendor: str, runner: str) -> dict[str, Any]:
    result = command("review", "keygen", "--vendor", vendor, "--runner", runner,
                    "--out-dir", str(out_dir))
    keyid = result.stdout.strip().splitlines()[-1]
    private = out_dir / f"{vendor}-{runner}.private.pem"
    public = out_dir / f"{vendor}-{runner}.public.pem"
    metadata = out_dir / f"{vendor}-{runner}.json"
    assert private.is_file(), list(out_dir.iterdir())
    assert public.is_file()
    assert metadata.is_file()
    assert private.stat().st_mode & 0o777 == 0o600
    return {"keyid": keyid, "vendor": vendor, "runner": runner,
            "private": private, "public": public, "metadata": metadata}


def write_allowlist(path: Path, *keys: dict[str, Any], overrides: dict[str, str] | None = None) -> None:
    entries = []
    for key in keys:
        entries.append({
            "keyid": key["keyid"],
            "vendor": (overrides or {}).get(key["keyid"], key["vendor"]),
            "runner": key["runner"],
            "public_key_path": str(key["public"]),
        })
    path.write_text(json.dumps(entries))


def attest(key: dict[str, Any], store: Path, *, verdict: str = "approve",
           run_id: str = "run-1", vendor: str | None = None,
           repo: str = REPO, pr: int = PR, base: str = BASE,
           head: str = HEAD, findings: bytes = b"synthetic findings\n") -> Path:
    findings_path = store.parent / f"findings-{run_id}-{verdict}.txt"
    findings_path.write_bytes(findings)
    attested_vendor = vendor or key["vendor"]
    command(
        "review", "attest", "--key", str(key["private"]), "--repo", repo,
        "--pr", str(pr), "--base", base, "--head", head,
        "--vendor", attested_vendor, "--tool", "fixture-reviewer",
        "--run-id", run_id, "--verdict", verdict,
        "--findings", str(findings_path), "--store", str(store),
    )
    return (store / repo.split("/", 1)[0] / repo.split("/", 1)[1] /
            f"pr-{pr}" / head / f"{attested_vendor}-{run_id}.dsse.json")


def report(allowlist: Path, store: Path, *, head: str = HEAD, base: str = BASE,
           expected: int | None = None, from_gh: bool = False) -> dict[str, Any]:
    args = ["review", "verify-two-key", "--repo", REPO, "--pr", str(PR),
            "--allowlist", str(allowlist), "--store", str(store)]
    if from_gh:
        args.append("--from-gh")
    else:
        args.extend(["--head", head, "--base", base])
    result = command(*args, expect=expected)
    data = json.loads(result.stdout)
    assert data["proves"] == "runner keys, not served models"
    assert data["status"] in {"PASS", "FAIL", "UNKNOWN"}
    assert isinstance(data["envelopes"], list)
    expected_status_code = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[data["status"]]
    assert result.returncode == expected_status_code, (result.returncode, data)
    return data


def reasons(data: dict[str, Any]) -> set[str]:
    return {item.get("reason") for item in data["envelopes"]}


def assert_status(data: dict[str, Any], status: str, reason: str | None = None) -> None:
    assert data["status"] == status, data
    if reason:
        assert reason in reasons(data), data


def mutate_envelope(path: Path, mutate_payload: bool = False) -> None:
    envelope = json.loads(path.read_text())
    if mutate_payload:
        payload = json.loads(base64.b64decode(envelope["payload"]))
        payload["predicate"]["run_id"] = "altered-after-signing"
        envelope["payload"] = base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
    else:
        sig = bytearray(base64.b64decode(envelope["signatures"][0]["sig"]))
        sig[0] ^= 1
        envelope["signatures"][0]["sig"] = base64.b64encode(sig).decode()
    path.write_text(json.dumps(envelope))


def copy_into_expected_pr(store: Path, source: Path, filename: str) -> Path:
    target_dir = store / "example" / "project" / f"pr-{PR}" / HEAD
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    shutil.copyfile(source, target)
    assert target.is_file()
    return target


def new_case(root: Path, name: str, keys: dict[str, dict[str, Any]],
             allow_keys: tuple[dict[str, Any], ...] | None = None) -> tuple[Path, Path]:
    case = root / name
    store = case / "store"
    store.mkdir(parents=True)
    allowlist = case / "allowlist.json"
    write_allowlist(allowlist, *(allow_keys or tuple(keys.values())))
    return store, allowlist


def main() -> int:
    global PROOF_PR, USE_INSTALLED, GH_PREFIX
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof-pr", help="installed proof-pr executable")
    args = parser.parse_args()
    PROOF_PR = [args.proof_pr] if args.proof_pr else [sys.executable, "-m", "proof_pr.cli"]
    USE_INSTALLED = bool(args.proof_pr)

    try:
        import checkseal  # noqa: F401
    except ImportError:
        print("review CLI tests: failed (install proof-pr[review])", file=sys.stderr)
        return 1

    assert_core_without_extras()
    temp_root = Path(os.environ.get("TMPDIR", ROOT / ".tmp"))
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="proof-pr-review-", dir=temp_root) as raw:
        root = Path(raw)
        keys_dir = root / "keys"
        keys_dir.mkdir()
        keys = {
            "anthropic": setup_key(keys_dir, "anthropic", "runner-a"),
            "openai": setup_key(keys_dir, "openai", "runner-b"),
        }
        keys_dir2 = root / "keys2"
        keys_dir2.mkdir()
        keys["anthropic2"] = setup_key(keys_dir2, "anthropic", "runner-c")
        keys["openai2"] = setup_key(keys_dir2, "openai", "runner-d")

        collision = command("review", "keygen", "--vendor", "anthropic", "--runner",
                            "runner-a", "--out-dir", str(keys_dir), expect=2)
        assert "exist" in collision.stderr.lower()

        store, allow = new_case(root, "genuine", keys)
        opaque_findings = b"private finding text stays outside the envelope\n"
        genuine_path = attest(keys["anthropic"], store, run_id="a-run", findings=opaque_findings)
        attest(keys["openai"], store, run_id="o-run")
        assert_status(report(allow, store), "PASS")
        genuine_envelope = json.loads(genuine_path.read_text())
        genuine_statement = json.loads(base64.b64decode(genuine_envelope["payload"]))
        predicate = genuine_statement["predicate"]
        assert genuine_statement["_type"] == "https://in-toto.io/Statement/v1"
        assert genuine_statement["predicateType"] == "https://github.com/saagpatel/proof-pr/review-attestation/v1"
        assert genuine_statement["subject"] == [{
            "name": f"git+https://github.com/{REPO}@{HEAD}",
            "digest": {"gitCommit": HEAD},
        }]
        assert predicate["scope"] == f"{BASE}..{HEAD}"
        assert predicate["findings"] == {
            "sha256": hashlib.sha256(opaque_findings).hexdigest(),
            "bytes": len(opaque_findings),
        }
        assert opaque_findings not in base64.b64decode(genuine_envelope["payload"])

        store, allow = new_case(root, "tampered-signature", keys)
        first = attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        mutate_envelope(first)
        assert_status(report(allow, store), "FAIL", "bad_signature")

        store, allow = new_case(root, "unknown-key", keys, (keys["openai"],))
        attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        assert_status(report(allow, store), "FAIL", "unknown_key")

        store, allow = new_case(root, "stale-head", keys)
        attest(keys["anthropic"], store, run_id="a-run", head="c" * 40)
        attest(keys["openai"], store, run_id="o-run")
        assert_status(report(allow, store), "FAIL", "stale_head")

        store, allow = new_case(root, "same-vendor", keys)
        attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["anthropic2"], store, run_id="a2-run")
        assert_status(report(allow, store), "FAIL")

        store, allow = new_case(root, "vendor-mismatch", keys)
        attest(keys["anthropic"], store, run_id="a-run", vendor="openai")
        attest(keys["openai"], store, run_id="o-run")
        assert_status(report(allow, store), "FAIL", "vendor_key_mismatch")

        store, allow = new_case(root, "altered-predicate", keys)
        first = attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        mutate_envelope(first, mutate_payload=True)
        assert_status(report(allow, store), "FAIL", "bad_signature")

        store, allow = new_case(root, "not-approved", keys)
        attest(keys["anthropic"], store, run_id="a-run", verdict="comment")
        attest(keys["openai"], store, run_id="o-run")
        assert_status(report(allow, store), "FAIL", "not_approved")

        store, allow = new_case(root, "duplicate-run", keys)
        attest(keys["anthropic"], store, run_id="shared-run")
        attest(keys["openai"], store, run_id="shared-run")
        assert_status(report(allow, store), "FAIL", "duplicate_run")

        store, allow = new_case(root, "same-findings", keys)
        same_findings = b"both reviewers found the same thing\n"
        attest(keys["anthropic"], store, run_id="a-run", findings=same_findings)
        attest(keys["openai"], store, run_id="o-run", findings=same_findings)
        assert_status(report(allow, store), "PASS")

        store, allow = new_case(root, "stale-veto-is-ignored", keys)
        attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        attest(keys["anthropic2"], store, run_id="old-veto", head="c" * 40,
               verdict="changes_requested")
        assert_status(report(allow, store), "PASS")

        store, allow = new_case(root, "current-head-veto-wrong-base", keys)
        attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        attest(keys["anthropic2"], store, run_id="veto-run", base="d" * 40,
               verdict="changes_requested")
        assert_status(report(allow, store), "FAIL", "not_approved")

        store, allow = new_case(root, "duplicate-pair-with-later-usable-key", keys)
        attest(keys["anthropic"], store, run_id="shared-run")
        attest(keys["openai"], store, run_id="shared-run")
        attest(keys["openai2"], store, run_id="valid-openai-run")
        assert_status(report(allow, store), "PASS")

        store, allow = new_case(root, "same-key-only", keys)
        first = attest(keys["anthropic"], store, run_id="a-run")
        copy_into_expected_pr(store, first, "anthropic-copy.dsse.json")
        data = report(allow, store)
        assert_status(data, "FAIL", "same_key")

        store, allow = new_case(root, "malformed-envelope", keys)
        attest(keys["anthropic"], store, run_id="a-run")
        malformed_dir = store / "example" / "project" / f"pr-{PR}" / HEAD
        (malformed_dir / "malformed.dsse.json").write_text("{not json")
        data = report(allow, store)
        assert_status(data, "FAIL", "malformed")

        store, allow = new_case(root, "unreadable-envelope", keys)
        attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        unreadable_path = store / "example" / "project" / f"pr-{PR}" / HEAD / "openai-o-run.dsse.json"
        original_mode = unreadable_path.stat().st_mode & 0o777
        try:
            unreadable_path.chmod(0)
            assert_status(report(allow, store, expected=2), "UNKNOWN")
        finally:
            unreadable_path.chmod(original_mode)

        store, allow = new_case(root, "wrong-base", keys)
        attest(keys["anthropic"], store, run_id="a-run", base="d" * 40)
        attest(keys["openai"], store, run_id="o-run")
        assert_status(report(allow, store), "FAIL", "wrong_base")

        store, allow = new_case(root, "wrong-repo-pr", keys)
        wrong_repo = attest(keys["anthropic"], store, run_id="a-run", repo="example/other")
        wrong_pr = attest(keys["openai"], store, run_id="o-run", pr=18)
        copy_into_expected_pr(store, wrong_repo, "wrong-repo.dsse.json")
        copy_into_expected_pr(store, wrong_pr, "wrong-pr.dsse.json")
        assert_status(report(allow, store), "FAIL", "wrong_repo_or_pr")

        store, allow = new_case(root, "subject-mismatch", keys)
        first = attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        envelope = json.loads(first.read_text())
        payload = json.loads(base64.b64decode(envelope["payload"]))
        payload["subject"][0]["digest"]["gitCommit"] = "c" * 40
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        envelope["payload"] = base64.b64encode(payload_bytes).decode()
        from checkseal import dsse
        from checkseal.sign.local import load_private_signer
        unsigned = dsse.Envelope(payload_bytes, envelope["payloadType"], [])
        signature = load_private_signer(str(keys["anthropic"]["private"])).sign(
            unsigned.signing_bytes()
        )
        envelope["signatures"] = [{
            "sig": base64.b64encode(signature.sig).decode(), "keyid": signature.keyid,
        }]
        first.write_text(json.dumps(envelope))
        assert_status(report(allow, store), "FAIL", "stale_head")

        store, allow = new_case(root, "changes-requested", keys)
        attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        attest(keys["anthropic2"], store, run_id="veto-run", verdict="changes_requested")
        assert_status(report(allow, store), "FAIL", "not_approved")

        missing = root / "missing-store"
        allow = root / "missing-allowlist.json"
        write_allowlist(allow, *keys.values())
        assert_status(report(allow, missing, expected=2), "UNKNOWN")

        store, allow = new_case(root, "from-gh", keys)
        attest(keys["anthropic"], store, run_id="a-run")
        attest(keys["openai"], store, run_id="o-run")
        gh_bin = root / "gh-bin"
        gh_bin.mkdir()
        gh = gh_bin / "gh"
        gh.write_text("#!/bin/sh\nprintf '%s\\n' '{\"headRefOid\":\"" + HEAD +
                      "\",\"baseRefOid\":\"" + BASE + "\"}'\n")
        gh.chmod(0o755)
        GH_PREFIX = gh_bin
        assert_status(report(allow, store, from_gh=True), "PASS")
        gh.write_text("#!/bin/sh\nexit 1\n")
        gh.chmod(0o755)
        assert_status(report(allow, store, expected=2, from_gh=True), "UNKNOWN")

    print("review CLI end-to-end and adversarial checks: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
