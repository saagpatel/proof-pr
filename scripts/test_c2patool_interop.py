#!/usr/bin/env python3
"""Bidirectional fixture-only proof-pr/c2patool interoperability checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_provenance_cli import fixture_jpeg, fixture_png

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "provenance"
EXPECTED_C2PATOOL_VERSION = "c2patool 0.27.16"


def checked(
    command: list[str],
    *,
    env: dict[str, str],
    expect: int = 0,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"command returned {result.returncode}, expected {expect}: {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def proof_command(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return checked([sys.executable, "-m", "proof_pr.cli", *args], env=env)


def assert_tool_valid(result: subprocess.CompletedProcess[str]) -> None:
    value = json.loads(result.stdout)
    assert value["validation_state"] == "Valid"
    assert value["manifests"][value["active_manifest"]]["claim_version"] == 2
    codes = {item["code"] for item in value.get("validation_status", [])}
    assert codes <= {"signingCredential.untrusted"}, codes


def assert_proof_valid(result: subprocess.CompletedProcess[str]) -> None:
    states = json.loads(result.stdout)["states"]
    assert states == {
        "bound": "yes",
        "signature_valid": "yes",
        "signed": "yes",
        "trusted": "unknown",
        "truthful": "unknown",
        "valid": "yes",
        "well_formed": "yes",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c2patool", default=os.environ.get("C2PATOOL"))
    args = parser.parse_args()
    if not args.c2patool:
        parser.error("pass --c2patool or set C2PATOOL")
    tool = str(Path(args.c2patool).resolve())

    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = str(ROOT / "src")
    version = checked([tool, "-V"], env=base_env).stdout.strip()
    assert version == EXPECTED_C2PATOOL_VERSION, version

    with tempfile.TemporaryDirectory(prefix="proof-pr-c2patool-") as raw_tmp:
        tmp = Path(raw_tmp)
        base_env["XDG_CONFIG_HOME"] = str(tmp / "isolated-config")
        cert = FIXTURES / "es256_certs.fixture.pem"
        key = FIXTURES / "es256_private.fixture.pem"
        sources = {
            "png": (tmp / "fixture.png", "image/png", "interop-png"),
            "jpeg": (tmp / "fixture.jpg", "image/jpeg", "interop-jpeg"),
        }
        sources["png"][0].write_bytes(fixture_png())
        sources["jpeg"][0].write_bytes(fixture_jpeg())
        receipt = tmp / "receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": "proof-pr.v1",
                    "receipt_id": "interop-fixture-receipt",
                    "subject": {
                        "head_sha": "0" * 40,
                        "head_sha_status": "exact",
                    },
                    "producer": {"tool": "proof-pr", "version": "interop-test"},
                    "artifacts": [
                        {
                            "id": artifact_id,
                            "kind": "screenshot",
                            "path_or_url": source.name,
                            "description": f"synthetic {name} fixture",
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                            "required": True,
                        }
                        for name, (source, _mime, artifact_id) in sources.items()
                    ],
                }
            )
        )
        tool_manifest = tmp / "c2patool-manifest.json"
        tool_manifest.write_text(
            json.dumps(
                {
                    "claim_version": 2,
                    "alg": "es256",
                    "private_key": str(key),
                    "sign_cert": str(cert),
                    "claim_generator_info": [
                        {
                            "name": "c2patool fixture-only interoperability probe",
                            "version": "0.27.16",
                        }
                    ],
                    "title": "synthetic fixture",
                    "assertions": [
                        {
                            "label": "c2pa.actions.v2",
                            "data": {
                                "actions": [
                                    {
                                        "action": "c2pa.created",
                                        "digitalSourceType": (
                                            "http://cv.iptc.org/newscodes/"
                                            "digitalsourcetype/digitalCreation"
                                        ),
                                        "softwareAgent": {
                                            "name": "c2patool",
                                            "version": "0.27.16",
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                }
            )
        )

        combinations = 0
        for name, (source, _mime, artifact_id) in sources.items():
            suffix = source.suffix
            proof_embedded = tmp / f"proof-pr-embedded-{name}{suffix}"
            proof_command(
                base_env,
                "provenance", "create",
                "--source", str(source), "--output", str(proof_embedded),
                "--receipt", str(receipt), "--artifact-id", artifact_id,
                "--fixture-cert", str(cert), "--fixture-key", str(key),
            )
            assert_tool_valid(checked([tool, str(proof_embedded)], env=base_env))
            combinations += 1

            proof_detached = tmp / f"proof-pr-detached-{name}{suffix}"
            proof_sidecar = tmp / f"proof-pr-detached-{name}.c2pa"
            proof_command(
                base_env,
                "provenance", "create",
                "--source", str(source), "--output", str(proof_detached),
                "--receipt", str(receipt), "--artifact-id", artifact_id,
                "--fixture-cert", str(cert), "--fixture-key", str(key),
                "--detached", "--manifest-output", str(proof_sidecar),
            )
            assert_tool_valid(
                checked(
                    [tool, "--external-manifest", str(proof_sidecar), str(proof_detached)],
                    env=base_env,
                )
            )
            combinations += 1

            tool_embedded = tmp / f"c2patool-embedded-{name}{suffix}"
            checked(
                [
                    tool, str(source), "--manifest", str(tool_manifest),
                    "--output", str(tool_embedded),
                ],
                env=base_env,
            )
            assert_proof_valid(
                proof_command(base_env, "provenance", "verify", str(tool_embedded))
            )
            combinations += 1

            tool_detached = tmp / f"c2patool-detached-{name}{suffix}"
            checked(
                [
                    tool, str(source), "--sidecar", "--manifest", str(tool_manifest),
                    "--output", str(tool_detached),
                ],
                env=base_env,
            )
            tool_sidecar = tool_detached.with_suffix(".c2pa")
            assert_proof_valid(
                proof_command(
                    base_env,
                    "provenance", "verify", str(tool_detached),
                    "--manifest", str(tool_sidecar),
                )
            )
            combinations += 1

        print(
            "c2patool interoperability: passed "
            f"({combinations} PNG/JPEG embedded/detached bidirectional combinations; "
            "fixture trust remains unknown)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
