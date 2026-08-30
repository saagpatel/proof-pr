#!/usr/bin/env python3
"""Frozen fixture/adversarial checks for optional artifact provenance support."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "provenance"
sys.path.insert(0, str(ROOT / "src"))


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def fixture_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(b"\x00\x20\x60\xa0\x20\x60\xa0\x00\x20\x60\xa0\x20\x60\xa0", 9))
        + png_chunk(b"IEND", b"")
    )


def fixture_jpeg() -> bytes:
    """Return a frozen synthetic 2x2 JFIF fixture with no user metadata."""
    return base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
        "BwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQME"
        "BAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
        "FBQUFBQUFBQUFBQUFBT/wAARCAACAAIDAREAAhEBAxEB/8QAFAABAAAAAAAAAAAA"
        "AAAAAAAAB//EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAA"
        "AAAH/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8ACjmHH//Z"
    )


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "proof_pr.cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"command returned {result.returncode}, expected {expect}: {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def project_adversarial_states() -> None:
    from proof_pr.provenance import _report, validate_report

    base_manifest = {
        "title": "fixture.png",
        "signature_info": {"alg": "Es256"},
        "assertions": [
            {"label": "c2pa.actions.v2", "data": {"actions": [{"action": "c2pa.edited"}]}},
            {"label": "example.unknown.private", "data": {"redacted": True}},
        ],
    }

    def raw(state: str, failures: list[dict[str, str]]) -> dict[str, object]:
        return {
            "active_manifest": "urn:c2pa:test",
            "manifests": {"urn:c2pa:test": base_manifest},
            "validation_state": state,
            "validation_results": {"activeManifest": {"failure": failures, "success": []}},
        }

    invalid_time = _report(
        raw(
            "Invalid",
            [{"code": "claimSignature.outsideValidity", "explanation": "outside validity"}],
        ),
        {"specVersion": "2.3.0"},
        "synthetic-projection",
    )
    assert invalid_time["states"]["well_formed"] == "yes"
    assert invalid_time["states"]["valid"] == "no"
    assert invalid_time["states"]["trusted"] == "no"
    revoked = _report(
        raw(
            "Invalid",
            [{"code": "signingCredential.revoked", "explanation": "certificate revoked"}],
        ),
        {"specVersion": "2.3.0"},
        "synthetic-projection",
    )
    assert revoked["states"]["trusted"] == "no"
    assert revoked["states"]["truthful"] == "unknown"
    assert revoked["unknown_fields"]["assertion_labels"] == ["example.unknown.private"]
    assert not validate_report(revoked)


def main() -> int:
    try:
        import c2pa
    except ImportError:
        print("provenance CLI tests: skipped (install proof-pr[provenance])")
        return 0

    corpus = json.loads((FIXTURES / "corpus.json").read_text())
    expected_ids = {
        case["id"]
        for group in ("native_sdk_cases", "projection_only_cases")
        for case in corpus[group]
    }
    covered: set[str] = set()

    with tempfile.TemporaryDirectory(prefix="proof-pr-provenance-") as raw_tmp:
        tmp = Path(raw_tmp)
        source = tmp / "fixture.png"
        source.write_bytes(fixture_png())
        jpeg_source = tmp / "fixture.jpg"
        jpeg_source.write_bytes(fixture_jpeg())
        receipt = tmp / "receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": "proof-pr.v1",
                    "receipt_id": "fixture-receipt",
                    "subject": {
                        "head_sha": "3392875d40823d6b19f98228d7c8f1d161dd3a16",
                        "head_sha_status": "exact",
                    },
                    "producer": {"tool": "proof-pr", "version": "0.2.14"},
                    "artifacts": [
                        {
                            "id": "fixture-png",
                            "kind": "screenshot",
                            "path_or_url": "fixture.png",
                            "description": "synthetic fixture PNG",
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                            "required": True,
                        },
                        {
                            "id": "fixture-jpeg",
                            "kind": "screenshot",
                            "path_or_url": "fixture.jpg",
                            "description": "synthetic fixture JPEG",
                            "sha256": hashlib.sha256(jpeg_source.read_bytes()).hexdigest(),
                            "required": True,
                        },
                    ],
                }
            )
        )
        cert = FIXTURES / "es256_certs.fixture.pem"
        key = FIXTURES / "es256_private.fixture.pem"
        embedded = tmp / "embedded.png"
        embedded_report = tmp / "embedded-report.json"

        started = time.perf_counter()
        run(
            "provenance", "create",
            "--source", str(source),
            "--output", str(embedded),
            "--receipt", str(receipt),
            "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert),
            "--fixture-key", str(key),
        )
        creation_ms = (time.perf_counter() - started) * 1000
        inspected = run(
            "provenance", "verify", str(embedded),
            "--output", str(embedded_report),
        )
        embedded_data = json.loads(inspected.stdout)
        assert embedded_data["states"] == {
            "bound": "yes",
            "signature_valid": "yes",
            "signed": "yes",
            "trusted": "unknown",
            "truthful": "unknown",
            "valid": "yes",
            "well_formed": "yes",
        }
        assert embedded_data["c2pa"]["spec_version"] is None
        assert embedded_data["c2pa"]["claim_version"] == 2
        assert embedded_data["origin"]["receipt_projection"]["receipt_id"] == "fixture-receipt"
        assert embedded_data["privacy"]["remote_manifest_fetch"] is False
        assert str(tmp) not in embedded.read_bytes().decode("latin-1", errors="ignore")
        collision = run(
            "provenance", "create",
            "--source", str(source), "--output", str(embedded),
            "--receipt", str(receipt), "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
            expect=2,
        )
        assert "output exists" in collision.stderr
        run("provenance", "validate-report", str(embedded_report))
        invalid_report = tmp / "invalid-report.json"
        invalid_value = json.loads(embedded_report.read_text())
        invalid_value["states"]["truthful"] = "yes"
        invalid_report.write_text(json.dumps(invalid_value))
        invalid_result = run(
            "provenance", "validate-report", str(invalid_report), expect=2
        )
        assert "truthful must remain unknown" in invalid_result.stderr
        incomplete_report = tmp / "incomplete-report.json"
        incomplete_report.write_text(
            json.dumps(
                {
                    "schema_version": "proof-pr.artifact-provenance-report.v1",
                    "profile": "proof-pr.c2pa.v1",
                    "states": {
                        "well_formed": "yes", "bound": "yes", "signed": "yes",
                        "signature_valid": "yes", "valid": "yes",
                        "trusted": "unknown", "truthful": "unknown",
                    },
                }
            )
        )
        incomplete_result = run(
            "provenance", "validate-report", str(incomplete_report), expect=2
        )
        assert "missing report fields" in incomplete_result.stderr
        nested_invalid_report = tmp / "nested-invalid-report.json"
        nested_invalid_value = json.loads(embedded_report.read_text())
        nested_invalid_value["c2pa"] = {}
        nested_invalid_value["origin"] = {}
        nested_invalid_value["binding"] = {}
        nested_invalid_value["unknown_fields"] = {}
        nested_invalid_value["privacy"] = {}
        nested_invalid_report.write_text(json.dumps(nested_invalid_value))
        nested_invalid_result = run(
            "provenance", "validate-report", str(nested_invalid_report), expect=2
        )
        assert "c2pa must contain exactly" in nested_invalid_result.stderr
        covered.add("embedded-valid-unknown-trust")

        copied = tmp / "copied.png"
        shutil.copyfile(embedded, copied)
        copied_data = json.loads(run("provenance", "verify", str(copied)).stdout)
        assert copied.read_bytes() == embedded.read_bytes()
        assert copied_data["states"]["bound"] == "yes"
        covered.add("byte-copy")

        detached_asset = tmp / "detached.png"
        sidecar = tmp / "detached.c2pa"
        run(
            "provenance", "create",
            "--source", str(source),
            "--output", str(detached_asset),
            "--receipt", str(receipt),
            "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert),
            "--fixture-key", str(key),
            "--detached", "--manifest-output", str(sidecar),
        )
        detached_data = json.loads(
            run("provenance", "verify", str(detached_asset), "--manifest", str(sidecar)).stdout
        )
        assert detached_data["manifest_form"] == "detached"
        assert detached_data["states"]["bound"] == "yes"
        covered.add("detached-valid")

        tampered = tmp / "tampered.png"
        run("provenance", "tamper", str(embedded), str(tampered))
        tampered_data = json.loads(run("provenance", "verify", str(tampered), expect=2).stdout)
        assert tampered_data["states"]["bound"] == "no"
        assert tampered_data["states"]["valid"] == "no"
        covered.add("tampered-asset")

        unsigned = json.loads(run("provenance", "inspect", str(source)).stdout)
        assert unsigned["states"]["signed"] == "no"
        assert unsigned["states"]["valid"] == "no"
        covered.add("export-without-manifest")

        missing = run(
            "provenance", "create",
            "--source", str(source), "--output", str(tmp / "missing.png"),
            "--receipt", str(receipt), "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
            "--ingredient", str(tmp / "absent-parent.png"),
            "--action", "c2pa.edited",
            expect=2,
        )
        assert "missing-ingredient" in missing.stderr
        covered.add("missing-ingredient")

        no_hash_receipt = tmp / "receipt-without-hash.json"
        no_hash_value = json.loads(receipt.read_text())
        no_hash_value["artifacts"][0]["sha256"] = None
        no_hash_receipt.write_text(json.dumps(no_hash_value))
        no_hash_result = run(
            "provenance", "create",
            "--source", str(source), "--output", str(tmp / "no-hash.png"),
            "--receipt", str(no_hash_receipt), "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
            expect=2,
        )
        assert "must declare a 64-character sha256" in no_hash_result.stderr

        malformed_receipt = tmp / "malformed-receipt.json"
        malformed_value = json.loads(receipt.read_text())
        malformed_value["artifacts"] = {}
        malformed_receipt.write_text(json.dumps(malformed_value))
        malformed_result = run(
            "provenance", "create",
            "--source", str(source), "--output", str(tmp / "malformed.png"),
            "--receipt", str(malformed_receipt), "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
            expect=2,
        )
        assert "artifacts must be an array of objects" in malformed_result.stderr

        unsupported = tmp / "artifact.json"
        unsupported.write_text("{}")
        result = run(
            "provenance", "create",
            "--source", str(unsupported), "--output", str(tmp / "nope.json"),
            "--receipt", str(receipt), "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
            expect=2,
        )
        assert "unsupported-format" in result.stderr
        covered.add("unsupported-format")

        oversize = tmp / "oversize.c2pa"
        with oversize.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        result = run(
            "provenance", "inspect", str(source), "--manifest", str(oversize), expect=2
        )
        assert "parser limit" in result.stderr
        covered.add("oversize-manifest")

        malicious = tmp / "malicious.c2pa"
        malicious.write_bytes(b"not-a-c2pa-manifest\x00\xff")
        result = run(
            "provenance", "inspect", str(source), "--manifest", str(malicious), expect=2
        )
        assert "failed safely" in result.stderr
        covered.add("malicious-manifest")

        edited = tmp / "edited.png"
        run(
            "provenance", "create",
            "--source", str(source), "--output", str(edited),
            "--receipt", str(receipt), "--artifact-id", "fixture-png",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
            "--ingredient", str(embedded), "--action", "c2pa.edited",
        )
        edited_report = json.loads(run("provenance", "verify", str(edited)).stdout)
        assert [item["action"] for item in edited_report["edits"]] == [
            "c2pa.opened",
            "c2pa.edited",
        ]
        assert edited_report["ingredients"]

        jpeg_embedded = tmp / "embedded.jpg"
        jpeg_started = time.perf_counter()
        run(
            "provenance", "create",
            "--source", str(jpeg_source), "--output", str(jpeg_embedded),
            "--receipt", str(receipt), "--artifact-id", "fixture-jpeg",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
        )
        jpeg_creation_ms = (time.perf_counter() - jpeg_started) * 1000
        jpeg_data = json.loads(run("provenance", "verify", str(jpeg_embedded)).stdout)
        assert jpeg_data["states"]["bound"] == "yes"
        assert jpeg_data["states"]["valid"] == "yes"
        assert jpeg_data["states"]["trusted"] == "unknown"
        assert jpeg_data["states"]["truthful"] == "unknown"
        assert jpeg_data["origin"]["receipt_projection"]["artifact_id"] == "fixture-jpeg"
        covered.add("jpeg-embedded-valid")

        jpeg_copy = tmp / "copied.jpg"
        shutil.copyfile(jpeg_embedded, jpeg_copy)
        jpeg_copy_data = json.loads(run("provenance", "verify", str(jpeg_copy)).stdout)
        assert jpeg_copy.read_bytes() == jpeg_embedded.read_bytes()
        assert jpeg_copy_data["states"]["bound"] == "yes"
        covered.add("jpeg-byte-copy")

        jpeg_detached = tmp / "detached.jpg"
        jpeg_sidecar = tmp / "detached-jpeg.c2pa"
        run(
            "provenance", "create",
            "--source", str(jpeg_source), "--output", str(jpeg_detached),
            "--receipt", str(receipt), "--artifact-id", "fixture-jpeg",
            "--fixture-cert", str(cert), "--fixture-key", str(key),
            "--detached", "--manifest-output", str(jpeg_sidecar),
        )
        jpeg_detached_data = json.loads(
            run(
                "provenance", "verify", str(jpeg_detached),
                "--manifest", str(jpeg_sidecar),
            ).stdout
        )
        assert jpeg_detached_data["manifest_form"] == "detached"
        assert jpeg_detached_data["states"]["bound"] == "yes"
        covered.add("jpeg-detached-valid")

        jpeg_tampered = tmp / "tampered.jpg"
        run("provenance", "tamper", str(jpeg_embedded), str(jpeg_tampered))
        jpeg_tampered_data = json.loads(
            run("provenance", "verify", str(jpeg_tampered), expect=2).stdout
        )
        assert jpeg_tampered_data["states"]["bound"] == "no"
        assert jpeg_tampered_data["states"]["valid"] == "no"
        covered.add("jpeg-tampered-asset")

        jpeg_unsigned = json.loads(run("provenance", "inspect", str(jpeg_source)).stdout)
        assert jpeg_unsigned["states"]["signed"] == "no"
        assert jpeg_unsigned["states"]["valid"] == "no"
        covered.add("jpeg-export-without-manifest")

        project_adversarial_states()
        covered.update({"redacted-assertion", "invalid-time", "revoked-trust", "unknown-assertion"})

        assert covered == expected_ids, (covered, expected_ids)
        overhead = embedded.stat().st_size - source.stat().st_size
        metrics = {
            "sdk_version": c2pa.sdk_version(),
            "source_bytes": source.stat().st_size,
            "embedded_bytes": embedded.stat().st_size,
            "embedded_overhead_bytes": overhead,
            "embedded_overhead_ratio": round(embedded.stat().st_size / source.stat().st_size, 3),
            "detached_manifest_bytes": sidecar.stat().st_size,
            "creation_ms_single_sample": round(creation_ms, 3),
            "corpus_cases": len(covered),
            "jpeg_source_bytes": jpeg_source.stat().st_size,
            "jpeg_embedded_bytes": jpeg_embedded.stat().st_size,
            "jpeg_embedded_overhead_bytes": (
                jpeg_embedded.stat().st_size - jpeg_source.stat().st_size
            ),
            "jpeg_embedded_overhead_ratio": round(
                jpeg_embedded.stat().st_size / jpeg_source.stat().st_size, 3
            ),
            "jpeg_detached_manifest_bytes": jpeg_sidecar.stat().st_size,
            "jpeg_creation_ms_single_sample": round(jpeg_creation_ms, 3),
        }
        print("provenance fixture/adversarial corpus: passed")
        print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
