"""Fixture-only C2PA provenance support for proof-pr artifacts.

This module is deliberately optional.  It does not change the proof-pr.v1
receipt schema or establish another receipt store, signer, or trust authority.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

PROFILE = "proof-pr.c2pa.v1"
REPORT_SCHEMA = "proof-pr.artifact-provenance-report.v1"
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
OFFICIAL_FIXTURE_CERT_SERIAL = 640229841392226413189608867977836244731148734950
KNOWN_ASSERTIONS = {
    "c2pa.actions",
    "c2pa.actions.v2",
    "c2pa.ingredient",
    "c2pa.ingredient.v2",
    "c2pa.hash.data",
    "org.proof-pr.receipt",
    "org.proof-pr.receipt.v1",
}
REPORT_KEYS = {
    "schema_version",
    "profile",
    "canonical_authority",
    "manifest_form",
    "c2pa",
    "states",
    "origin",
    "generator",
    "edits",
    "ingredients",
    "binding",
    "signature",
    "validation",
    "unknown_fields",
    "failure_explanations",
    "privacy",
    "claim_boundary",
}
FORMAT_MATRIX = {
    "image/png": {
        "extensions": [".png"],
        "create": True,
        "inspect": True,
        "embedded": True,
        "detached": True,
        "profile_verified": True,
    },
    "image/jpeg": {
        "extensions": [".jpg", ".jpeg"],
        "create": True,
        "inspect": True,
        "embedded": True,
        "detached": True,
        "profile_verified": True,
    },
    "application/pdf": {
        "extensions": [".pdf"],
        "create": False,
        "inspect": True,
        "embedded": False,
        "detached": False,
        "profile_verified": False,
    },
}


class ProvenanceError(ValueError):
    """A bounded, user-facing provenance failure."""


def _c2pa() -> Any:
    try:
        import c2pa  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProvenanceError(
            "C2PA support is optional; install proof-pr[provenance] "
            "(pinned c2pa-python 0.37.8)."
        ) from exc
    return c2pa


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ProvenanceError(f"cannot read {label}: {path.name}: {exc}") from exc
    if size > limit:
        raise ProvenanceError(f"{label} exceeds {limit} byte parser limit: {size}")
    return path.read_bytes()


def _prepare_output(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise ProvenanceError(
            f"output exists: {path}; pass --force to replace this exact path"
        )
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, value: Any, *, force: bool) -> None:
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if len(encoded) > MAX_REPORT_BYTES:
        raise ProvenanceError("derived report exceeds parser/output limit")
    _prepare_output(path, force=force)
    path.write_bytes(encoded)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    for mime, row in FORMAT_MATRIX.items():
        if suffix in row["extensions"]:
            return mime
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _require_format(mime: str, operation: str) -> None:
    row = FORMAT_MATRIX.get(mime)
    if not row or not row.get(operation):
        declared = ", ".join(sorted(FORMAT_MATRIX))
        raise ProvenanceError(
            f"unsupported-format: {mime} is not enabled for {operation}; "
            f"declared formats: {declared}"
        )


def _fixture_signer(cert_path: Path, key_path: Path) -> Any:
    cert_bytes = _read_bounded(cert_path, 128 * 1024, "fixture certificate")
    key_bytes = _read_bounded(key_path, 128 * 1024, "fixture private key")
    try:
        from cryptography import x509

        certs = x509.load_pem_x509_certificates(cert_bytes)
        if not certs:
            raise ValueError("empty certificate chain")
        units = certs[0].subject.get_attributes_for_oid(x509.NameOID.ORGANIZATIONAL_UNIT_NAME)
        if not any(unit.value == "FOR TESTING_ONLY" for unit in units):
            raise ProvenanceError(
                "fixture-only gate rejected certificate without OU=FOR TESTING_ONLY"
            )
        if certs[0].serial_number != OFFICIAL_FIXTURE_CERT_SERIAL:
            raise ProvenanceError(
                "fixture-only gate rejected an unrecognized test certificate"
            )
    except ProvenanceError:
        raise
    except Exception as exc:
        raise ProvenanceError(f"invalid fixture certificate: {exc}") from exc
    c2pa = _c2pa()
    return c2pa.Signer.from_info(c2pa.C2paSignerInfo("es256", cert_bytes, key_bytes, None))


def _context() -> Any:
    c2pa = _c2pa()
    return c2pa.Context.from_dict(
        {
            "builder": {"thumbnail": {"enabled": False}},
            "verify": {
                "verify_after_sign": True,
                "remote_manifest_fetch": False,
            },
        }
    )


def _receipt_projection(receipt_path: Path, artifact_id: str) -> tuple[dict[str, Any], str]:
    try:
        receipt = json.loads(
            _read_bounded(receipt_path, MAX_REPORT_BYTES, "proof-pr receipt")
        )
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"proof-pr receipt is not valid JSON: {exc}") from exc
    if not isinstance(receipt, dict):
        raise ProvenanceError("proof-pr receipt root must be an object")
    if receipt.get("schema_version") != "proof-pr.v1":
        raise ProvenanceError("receipt must use schema_version proof-pr.v1")
    artifacts = receipt.get("artifacts", [])
    if not isinstance(artifacts, list) or not all(
        isinstance(item, dict) for item in artifacts
    ):
        raise ProvenanceError("proof-pr receipt artifacts must be an array of objects")
    artifact = next((item for item in artifacts if item.get("id") == artifact_id), None)
    if artifact is None:
        raise ProvenanceError(f"missing-ingredient: artifact id {artifact_id!r} is absent from receipt")
    subject = receipt.get("subject", {})
    producer = receipt.get("producer", {})
    if not isinstance(subject, dict) or not isinstance(producer, dict):
        raise ProvenanceError("proof-pr receipt subject and producer must be objects")
    projection = {
        "profile": PROFILE,
        "receipt_id": receipt.get("receipt_id"),
        "artifact_id": artifact_id,
        "artifact_sha256": artifact.get("sha256"),
        "commit": {
            "head_sha": subject.get("head_sha"),
            "head_sha_status": subject.get("head_sha_status"),
        },
        "producer": {
            "tool": producer.get("tool"),
            "version": producer.get("version"),
        },
    }
    return projection, str(producer.get("version") or "unknown")


def _manifest(
    projection: dict[str, Any],
    version: str,
    title: str,
    action: str,
    mime: str,
) -> dict[str, Any]:
    actions = []
    if action == "c2pa.edited":
        actions.append(
            {
                "action": "c2pa.opened",
                "softwareAgent": {"name": "proof-pr", "version": version},
                "parameters": {"ingredientIds": ["proof-pr-parent"]},
            }
        )
    actions.append(
        {
            "action": action,
            "softwareAgent": {"name": "proof-pr", "version": version},
            **(
                {
                    "digitalSourceType": (
                        "http://cv.iptc.org/newscodes/digitalsourcetype/"
                        "digitalCreation"
                    )
                }
                if action == "c2pa.created"
                else {}
            ),
        }
    )
    return {
        "claim_generator_info": [{"name": "proof-pr", "version": version}],
        "title": title,
        "format": mime,
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "data": {
                    "actions": actions
                },
            },
            {"label": "org.proof-pr.receipt.v1", "data": projection},
        ],
    }


def create(args: argparse.Namespace) -> int:
    source = Path(args.source)
    output = Path(args.output)
    if source.resolve() == output.resolve():
        raise ProvenanceError("output must not overwrite the source asset")
    if args.detached and not args.manifest_output:
        raise ProvenanceError("--manifest-output is required with --detached")
    if args.action == "c2pa.edited" and not args.ingredient:
        raise ProvenanceError("c2pa.edited requires --ingredient")
    if args.action == "c2pa.created" and args.ingredient:
        raise ProvenanceError("an ingredient requires --action c2pa.edited")
    if args.manifest_output:
        manifest_target = Path(args.manifest_output).resolve()
        if manifest_target in {source.resolve(), output.resolve()}:
            raise ProvenanceError("manifest output must be distinct from asset paths")
    _prepare_output(output, force=args.force)
    if args.detached:
        _prepare_output(Path(args.manifest_output), force=args.force)
    mime = _mime_for(source)
    _require_format(mime, "create")
    source_bytes = _read_bounded(source, MAX_ASSET_BYTES, "source asset")
    projection, version = _receipt_projection(Path(args.receipt), args.artifact_id)
    declared_hash = projection.get("artifact_sha256")
    actual_hash = _sha256(source_bytes)
    if not isinstance(declared_hash, str) or len(declared_hash) != 64:
        raise ProvenanceError(
            "receipt artifact must declare a 64-character sha256 before provenance creation"
        )
    try:
        int(declared_hash, 16)
    except ValueError as exc:
        raise ProvenanceError("receipt artifact sha256 must be lowercase hexadecimal") from exc
    if declared_hash.lower() != declared_hash:
        raise ProvenanceError("receipt artifact sha256 must be lowercase hexadecimal")
    if declared_hash != actual_hash:
        raise ProvenanceError(
            "receipt artifact sha256 does not match source asset; refusing to sign"
        )
    signer = _fixture_signer(Path(args.fixture_cert), Path(args.fixture_key))
    c2pa = _c2pa()
    manifest = _manifest(projection, version, source.name, args.action, mime)
    dest = io.BytesIO()
    try:
        with c2pa.Builder(manifest, context=_context()) as builder:
            if args.ingredient:
                ingredient_path = Path(args.ingredient)
                if not ingredient_path.is_file():
                    raise ProvenanceError(
                        "missing-ingredient: parent asset is unavailable: "
                        f"{ingredient_path.name}"
                    )
                ingredient_bytes = _read_bounded(
                    ingredient_path, MAX_ASSET_BYTES, "ingredient asset"
                )
                ingredient_mime = _mime_for(ingredient_path)
                _require_format(ingredient_mime, "inspect")
                builder.add_ingredient(
                    {
                        "title": ingredient_path.name,
                        "relationship": "parentOf",
                        "format": ingredient_mime,
                        "label": "proof-pr-parent",
                    },
                    ingredient_mime,
                    io.BytesIO(ingredient_bytes),
                )
            if args.detached:
                builder.set_no_embed()
            manifest_bytes = builder.sign(
                signer, mime, io.BytesIO(source_bytes), dest
            )
    except ProvenanceError:
        raise
    except Exception as exc:
        raise ProvenanceError(f"C2PA creation failed safely: {exc}") from exc
    output.write_bytes(dest.getvalue())
    if args.detached:
        manifest_output = Path(args.manifest_output)
        manifest_output.write_bytes(manifest_bytes)
    print(
        json.dumps(
            {
                "profile": PROFILE,
                "output": str(output),
                "output_sha256": _sha256(output.read_bytes()),
                "form": "detached" if args.detached else "embedded",
                "fixture_identity": True,
                "truthfulness": "unknown",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _validation_entries(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for group in raw.get("validation_results", {}).values():
        if not isinstance(group, dict):
            continue
        for severity in ("failure", "informational", "success"):
            for entry in group.get(severity, []) or []:
                if isinstance(entry, dict):
                    out.append(
                        {
                            "severity": severity,
                            "code": entry.get("code", "unknown"),
                            "explanation": entry.get("explanation", ""),
                        }
                    )
    if not out:
        for entry in raw.get("validation_status", []) or []:
            if isinstance(entry, dict):
                out.append(
                    {
                        "severity": "failure",
                        "code": entry.get("code", "unknown"),
                        "explanation": entry.get("explanation", ""),
                    }
                )
    return out


def _report(raw: dict[str, Any], crjson: dict[str, Any] | None, form: str) -> dict[str, Any]:
    active_label = raw.get("active_manifest")
    manifest = raw.get("manifests", {}).get(active_label, {}) if active_label else {}
    assertions = manifest.get("assertions", []) if isinstance(manifest, dict) else []
    assertion_labels = [item.get("label") for item in assertions if isinstance(item, dict)]
    actions: list[dict[str, Any]] = []
    receipt_projection: dict[str, Any] | None = None
    unknown_assertions: list[str] = []
    for item in assertions:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "unknown"))
        if label.startswith("c2pa.actions"):
            actions.extend(item.get("data", {}).get("actions", []) or [])
        elif label in {"org.proof-pr.receipt", "org.proof-pr.receipt.v1"}:
            receipt_projection = item.get("data")
        if label not in KNOWN_ASSERTIONS:
            unknown_assertions.append(label)
    ingredients = manifest.get("ingredients", []) if isinstance(manifest, dict) else []
    entries = _validation_entries(raw)
    codes = {entry["code"] for entry in entries}
    failures = [entry for entry in entries if entry["severity"] == "failure"]
    state = str(raw.get("validation_state", "Unknown"))
    signature_present = bool(manifest.get("signature_info")) if isinstance(manifest, dict) else False
    signature_valid = "claimSignature.validated" in codes
    binding_match = "assertion.dataHash.match" in codes
    binding_mismatch = "assertion.dataHash.mismatch" in codes
    trust_unknown = "signingCredential.untrusted" in codes
    malformed = any("malformed" in code.lower() for code in codes)
    explicitly_untrusted = any(
        token in code.lower()
        for code in codes
        for token in ("revoked", "expired", "notvalid", "outsidevalidity")
    )
    states = {
        "well_formed": "yes" if active_label and not malformed else "no",
        "bound": "yes" if binding_match and not binding_mismatch else ("no" if binding_mismatch else "unknown"),
        "signed": "yes" if signature_present else "no",
        "signature_valid": "yes" if signature_valid else ("no" if signature_present else "unknown"),
        "valid": "yes" if state in {"Valid", "Trusted"} else "no",
        "trusted": (
            "yes"
            if state == "Trusted"
            else ("no" if explicitly_untrusted else ("unknown" if trust_unknown or signature_present else "no"))
        ),
        "truthful": "unknown",
    }
    generator = manifest.get("claim_generator_info", []) if isinstance(manifest, dict) else []
    return {
        "schema_version": REPORT_SCHEMA,
        "profile": PROFILE,
        "canonical_authority": "proof-pr.v1 receipt; this report is derived",
        "manifest_form": form,
        "c2pa": {
            "validation_state": state,
            "spec_version": (crjson or {}).get("specVersion")
            or (crjson or {}).get("spec_version"),
            "claim_version": manifest.get("claim_version")
            if isinstance(manifest, dict)
            else None,
            "active_manifest": active_label,
        },
        "states": states,
        "origin": {
            "title": manifest.get("title") if isinstance(manifest, dict) else None,
            "instance_id": manifest.get("instance_id") if isinstance(manifest, dict) else None,
            "receipt_projection": receipt_projection,
        },
        "generator": generator,
        "edits": actions,
        "ingredients": ingredients,
        "binding": {
            "status": states["bound"],
            "method": "C2PA hard binding (asset data hash)",
        },
        "signature": manifest.get("signature_info") if isinstance(manifest, dict) else None,
        "validation": entries,
        "unknown_fields": {
            "assertion_labels": sorted(set(unknown_assertions)),
            "all_assertion_labels": assertion_labels,
        },
        "failure_explanations": failures,
        "privacy": {
            "remote_manifest_fetch": False,
            "embedded_paths": False,
            "embedded_prompts": False,
            "embedded_location": False,
        },
        "claim_boundary": (
            "Integrity and validation state do not establish that the underlying claim is true."
        ),
    }


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = REPORT_KEYS - set(report)
    unknown = set(report) - REPORT_KEYS
    if missing:
        errors.append("missing report fields: " + ", ".join(sorted(missing)))
    if unknown:
        errors.append("unknown report fields: " + ", ".join(sorted(unknown)))
    if report.get("schema_version") != REPORT_SCHEMA:
        errors.append("schema_version must be proof-pr.artifact-provenance-report.v1")
    if report.get("profile") != PROFILE:
        errors.append("profile must be proof-pr.c2pa.v1")
    states = report.get("states")
    required = {"well_formed", "bound", "signed", "signature_valid", "valid", "trusted", "truthful"}
    if not isinstance(states, dict):
        errors.append("states must be an object")
    else:
        if set(states) != required:
            errors.append("states must contain exactly the seven trust-language states")
        for key, value in states.items():
            if value not in {"yes", "no", "unknown"}:
                errors.append(f"states.{key} must be yes, no, or unknown")
    if (states if isinstance(states, dict) else {}).get("truthful") != "unknown":
        errors.append("truthful must remain unknown; validation cannot establish truth")
    for key in ("c2pa", "origin", "binding", "unknown_fields", "privacy"):
        if not isinstance(report.get(key), dict):
            errors.append(f"{key} must be an object")
    for key in (
        "generator",
        "edits",
        "ingredients",
        "validation",
        "failure_explanations",
    ):
        if not isinstance(report.get(key), list):
            errors.append(f"{key} must be an array")
    if report.get("signature") is not None and not isinstance(
        report.get("signature"), dict
    ):
        errors.append("signature must be an object or null")
    for key in ("canonical_authority", "manifest_form", "claim_boundary"):
        if not isinstance(report.get(key), str) or not report.get(key):
            errors.append(f"{key} must be a non-empty string")

    def exact_object(key: str, required_keys: set[str]) -> dict[str, Any] | None:
        value = report.get(key)
        if not isinstance(value, dict):
            return None
        if set(value) != required_keys:
            errors.append(
                f"{key} must contain exactly: {', '.join(sorted(required_keys))}"
            )
        return value

    c2pa_value = exact_object(
        "c2pa", {"validation_state", "spec_version", "claim_version", "active_manifest"}
    )
    if c2pa_value is not None:
        if not isinstance(c2pa_value.get("validation_state"), str):
            errors.append("c2pa.validation_state must be a string")
        if c2pa_value.get("spec_version") is not None and not isinstance(
            c2pa_value.get("spec_version"), str
        ):
            errors.append("c2pa.spec_version must be a string or null")
        if c2pa_value.get("claim_version") is not None and not isinstance(
            c2pa_value.get("claim_version"), int
        ):
            errors.append("c2pa.claim_version must be an integer or null")
        if c2pa_value.get("active_manifest") is not None and not isinstance(
            c2pa_value.get("active_manifest"), str
        ):
            errors.append("c2pa.active_manifest must be a string or null")

    exact_object("origin", {"title", "instance_id", "receipt_projection"})
    binding_value = exact_object("binding", {"status", "method"})
    if binding_value is not None:
        if binding_value.get("status") not in {"yes", "no", "unknown"}:
            errors.append("binding.status must be yes, no, or unknown")
        if not isinstance(binding_value.get("method"), str):
            errors.append("binding.method must be a string")

    unknown_value = exact_object(
        "unknown_fields", {"assertion_labels", "all_assertion_labels"}
    )
    if unknown_value is not None:
        for key in ("assertion_labels", "all_assertion_labels"):
            if not isinstance(unknown_value.get(key), list):
                errors.append(f"unknown_fields.{key} must be an array")

    privacy_value = exact_object(
        "privacy",
        {
            "remote_manifest_fetch",
            "embedded_paths",
            "embedded_prompts",
            "embedded_location",
        },
    )
    if privacy_value is not None:
        for key, value in privacy_value.items():
            if value is not False:
                errors.append(f"privacy.{key} must be false")

    for key in ("generator", "edits", "ingredients", "validation", "failure_explanations"):
        value = report.get(key)
        if isinstance(value, list) and not all(isinstance(item, dict) for item in value):
            errors.append(f"{key} items must be objects")
    return errors


def validate_report_file(args: argparse.Namespace) -> int:
    try:
        value = json.loads(_read_bounded(Path(args.report), MAX_REPORT_BYTES, "report"))
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"report is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProvenanceError("report root must be an object")
    errors = validate_report(value)
    if errors:
        for error in errors:
            print(f"{args.report}: invalid: {error}", file=sys.stderr)
        return 2
    print(f"{args.report}: valid derived provenance report")
    return 0


def inspect_asset(args: argparse.Namespace, *, verify_exit: bool = False) -> int:
    asset = Path(args.asset)
    mime = _mime_for(asset)
    _require_format(mime, "inspect")
    asset_bytes = _read_bounded(asset, MAX_ASSET_BYTES, "asset")
    manifest_bytes = None
    form = "embedded"
    if args.manifest:
        manifest_bytes = _read_bounded(Path(args.manifest), MAX_MANIFEST_BYTES, "manifest")
        form = "detached"
    c2pa = _c2pa()
    try:
        with c2pa.Reader(
            mime,
            io.BytesIO(asset_bytes),
            manifest_data=manifest_bytes,
            context=_context(),
        ) as reader:
            raw = json.loads(reader.json())
            try:
                crjson = json.loads(reader.crjson())
            except Exception:
                crjson = None
    except Exception as exc:
        if "ManifestNotFound" not in str(exc):
            raise ProvenanceError(f"manifest parse/validation failed safely: {exc}") from exc
        report = {
            "schema_version": REPORT_SCHEMA,
            "profile": PROFILE,
            "canonical_authority": "proof-pr.v1 receipt; this report is derived",
            "manifest_form": "absent",
            "c2pa": {
                "validation_state": "NoManifest",
                "spec_version": None,
                "claim_version": None,
                "active_manifest": None,
            },
            "states": {
                "well_formed": "no",
                "bound": "unknown",
                "signed": "no",
                "signature_valid": "unknown",
                "valid": "no",
                "trusted": "no",
                "truthful": "unknown",
            },
            "origin": {"title": asset.name, "instance_id": None, "receipt_projection": None},
            "generator": [],
            "edits": [],
            "ingredients": [],
            "binding": {"status": "unknown", "method": "No C2PA manifest present"},
            "signature": None,
            "validation": [],
            "unknown_fields": {"assertion_labels": [], "all_assertion_labels": []},
            "failure_explanations": [
                {"severity": "failure", "code": "manifest.absent", "explanation": "No C2PA manifest is present in or supplied with the asset."}
            ],
            "privacy": {
                "remote_manifest_fetch": False,
                "embedded_paths": False,
                "embedded_prompts": False,
                "embedded_location": False,
            },
            "claim_boundary": (
                "Integrity and validation state do not establish that the underlying claim is true."
            ),
        }
    else:
        try:
            report = _report(raw, crjson, form)
        except Exception as exc:
            raise ProvenanceError(
                f"manifest projection failed safely: {exc}"
            ) from exc
    errors = validate_report(report)
    if errors:
        raise ProvenanceError("invalid derived report: " + "; ".join(errors))
    if args.output:
        _write_json(Path(args.output), report, force=args.force)
    print(json.dumps(report, indent=2, sort_keys=True))
    if verify_exit:
        states = report["states"]
        if states["valid"] != "yes" or states["bound"] != "yes":
            return 2
        if args.require_trusted and states["trusted"] != "yes":
            return 3
    return 0


def tamper(args: argparse.Namespace) -> int:
    source = Path(args.source)
    mime = _mime_for(source)
    if mime not in {"image/png", "image/jpeg"}:
        raise ProvenanceError("tamper fixture supports only profile-verified PNG and JPEG")
    data = _read_bounded(source, MAX_ASSET_BYTES, "source asset")
    payload = b"proof-pr deterministic tamper"
    if mime == "image/png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ProvenanceError("invalid PNG signature")
        marker = data.rfind(b"IEND")
        if marker < 4:
            raise ProvenanceError("PNG lacks IEND chunk")
        start = marker - 4
        chunk_type = b"tEXt"
        chunk = (
            struct.pack(">I", len(payload))
            + chunk_type
            + payload
            + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
        )
        tampered = data[:start] + chunk + data[start:]
    else:
        if not data.startswith(b"\xff\xd8"):
            raise ProvenanceError("invalid JPEG start-of-image marker")
        comment = b"\xff\xfe" + struct.pack(">H", len(payload) + 2) + payload
        tampered = data[:2] + comment + data[2:]
    output = Path(args.output)
    if source.resolve() == output.resolve():
        raise ProvenanceError("tamper output must not overwrite the source asset")
    _prepare_output(output, force=args.force)
    output.write_bytes(tampered)
    print(f"wrote parseable tampered {mime}: {output}")
    return 0


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    root = subparsers.add_parser(
        "provenance", help="Create and inspect fixture-only C2PA artifact provenance"
    )
    children = root.add_subparsers(dest="provenance_command", required=True)
    create_parser = children.add_parser(
        "create", help="Create a fixture-signed PNG or JPEG"
    )
    create_parser.add_argument("--source", required=True)
    create_parser.add_argument("--output", required=True)
    create_parser.add_argument("--receipt", required=True)
    create_parser.add_argument("--artifact-id", required=True)
    create_parser.add_argument("--fixture-cert", required=True)
    create_parser.add_argument("--fixture-key", required=True)
    create_parser.add_argument("--ingredient")
    create_parser.add_argument(
        "--action", choices=["c2pa.created", "c2pa.edited"], default="c2pa.created"
    )
    create_parser.add_argument("--detached", action="store_true")
    create_parser.add_argument("--manifest-output")
    create_parser.add_argument("--force", action="store_true")
    create_parser.set_defaults(func=create)

    for name, help_text, verify_exit in (
        ("inspect", "Inspect an embedded or detached manifest", False),
        ("verify", "Verify binding and manifest validity", True),
    ):
        parser = children.add_parser(name, help=help_text)
        parser.add_argument("asset")
        parser.add_argument("--manifest")
        parser.add_argument("--output")
        parser.add_argument("--require-trusted", action="store_true")
        parser.add_argument("--force", action="store_true")
        parser.set_defaults(func=lambda args, v=verify_exit: inspect_asset(args, verify_exit=v))

    tamper_parser = children.add_parser(
        "tamper", help="Create a parseable tampered PNG or JPEG"
    )
    tamper_parser.add_argument("source")
    tamper_parser.add_argument("output")
    tamper_parser.add_argument("--force", action="store_true")
    tamper_parser.set_defaults(func=tamper)

    validate_parser = children.add_parser(
        "validate-report", help="Validate a derived provenance report contract"
    )
    validate_parser.add_argument("report")
    validate_parser.set_defaults(func=validate_report_file)


def cli_error(exc: Exception) -> int:
    print(f"provenance error: {exc}", file=sys.stderr)
    return 2
