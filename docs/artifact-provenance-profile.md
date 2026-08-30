# proof-pr portable artifact provenance profile

Status: fixture-only experimental profile (`proof-pr.c2pa.v1`)

This profile extends the existing `proof-pr.v1` receipt model with portable
C2PA Content Credentials. It does not replace the receipt, create a second
receipt store, establish an identity system, or make C2PA validation an
authority over proof-pr claims. The receipt remains canonical; a C2PA manifest
contains a privacy-minimized projection that points back to one receipt
artifact.

The design was evaluated against the current C2PA 2.4 specification. The pinned
`c2pa-python` 0.37.8 package (current on PyPI at the 2026-08-30 readback) uses
`c2pa-rs` 0.90.15. Its fixture output carries C2PA claim version 2, while its
current crJSON view does not report a specification version. Therefore this
implementation uses stable concepts evaluated against 2.4 and does **not**
claim full C2PA 2.4 conformance. A pinned `c2patool` 0.27.16 readback provides
bidirectional independent CLI/process evidence, but not independent-codebase
interoperability: both tools use `c2pa-rs` (`0.90.15` through Python and
`0.90.16` through the CLI), so parser and signing behavior have a common-mode
dependency.

## Ownership and field mapping

| Existing owner/fact | C2PA representation | Meaning and boundary |
| --- | --- | --- |
| `receipt_id` | authored `org.proof-pr.receipt.v1` assertion; SDK-normalized readers may expose `org.proof-pr.receipt` | Reference back to the canonical local receipt; not a second receipt. |
| `artifacts[].id` | `artifact_id` in that assertion | Identifies the existing receipt artifact. |
| `artifacts[].sha256` | Projection plus C2PA hard binding | A lowercase SHA-256 is required and checked before creation; the C2PA asset binding protects the resulting asset. Neither proves the claim true. |
| `subject.head_sha` and status | `commit` object in the assertion | Descriptive task/commit context; it is not the C2PA instance ID or asset hash. |
| `producer.tool` and version | claim generator and software agent | Describes the local generator. |
| create/edit operation | `c2pa.actions.v2` | `created`, or `opened` followed by `edited` for a parent ingredient. |
| previous asset | C2PA ingredient linked by `ingredientIds` | Carries the parent manifest and validation readback where supported. |
| SDK validation results | derived JSON/terminal provenance report | Inspection evidence only; never written back as canonical claim truth. |
| crJSON | optional derived inspection input | Human/tool-friendly view only; not canonical, signed, or independently verifiable. |

The existing `proof-pr.v1` schema remains closed and unchanged. Consumers attach
the signed asset, detached `.c2pa` manifest, or JSON inspection report through
existing `artifacts[]` entries (`attestation`, `json`, `report`,
or the underlying artifact kind) and reference them through existing
`evidence[].artifact_ids`. Older consumers can ignore these artifact entries.

## Trust language

The inspector reports independent states rather than one ambiguous green badge:

| Term | Profile meaning |
| --- | --- |
| well-formed | A manifest was parsed and no malformed-structure failure was reported. |
| bound | The C2PA hard binding matches the supplied asset. |
| signed | Signature information is present. |
| signature valid | The cryptographic claim signature validated. |
| valid | The SDK reports `Valid` or `Trusted`, including binding and signature checks. |
| trusted | The signing credential resolved to an accepted trust anchor. Fixture certificates normally remain `unknown`. |
| truthful | Always `unknown`; intact provenance does not establish that a claim is honest or factually true. |

`valid` is not a synonym for `trusted`, and neither is a synonym for `truthful`.
The fixture chain is intentionally untrusted, so a successful local fixture
normally reads `valid=yes`, `trusted=unknown`, `truthful=unknown`.

## Declared format matrix

| Format | Create | Inspect | Embedded | Detached | Bounded-profile evidence |
| --- | --- | --- | --- | --- | --- |
| PNG (`image/png`) | yes | yes | yes | yes | Native corpus covers create, inspect, verify, edit/ingredient, tamper, byte-copy, and manifest-free export. |
| JPEG (`image/jpeg`) | yes | yes | yes | yes | Native corpus covers create, inspect, verify, tamper, byte-copy, manifest-free export, and detached form. |
| PDF (`application/pdf`) | no | read path enabled | no | no | Current Reader advertises PDF but current Builder does not; no successful fixture is claimed. |
| JSON, text, Office documents, other media | no | no | no | no | Continue as normal proof-pr artifacts without portable provenance. |

This is deliberately narrower than the formats allowed by the C2PA
specification. PDF/document creation is quarantined until the pinned builder or
an independently verified implementation can produce and round-trip it without
adding another authority.

## Fixture-only workflow

Install the optional pinned dependency in an isolated environment:

```bash
python3 -m pip install -e '.[provenance]'
```

Create and verify an embedded PNG or JPEG:

```bash
proof-pr provenance create \
  --source fixture.png --output signed.png \
  --receipt proof-pr.json --artifact-id fixture-png \
  --fixture-cert tests/fixtures/provenance/es256_certs.fixture.pem \
  --fixture-key tests/fixtures/provenance/es256_private.fixture.pem
proof-pr provenance verify signed.png \
  --output provenance-report.json
proof-pr provenance validate-report provenance-report.json
```

Add `--detached --manifest-output signed.c2pa` to create a sidecar. Verification
must receive both asset and sidecar:

```bash
proof-pr provenance verify fixture.png --manifest signed.c2pa
```

Derived assets can add `--ingredient parent.png --action c2pa.edited`; the
profile emits the required opened→edited sequence and links the parent.

The public fixture key/certificate are accepted only when the leaf subject
contains `OU=FOR TESTING_ONLY` and its serial matches the frozen official sample.
No timestamp authority, remote manifest fetch,
system trust-anchor registration, Keychain, Secure Enclave, or production key
path exists in this profile.

Output, sidecar, report, and tamper destinations fail closed when a path already
exists. `--force` is an explicit opt-in to replace only the exact named output;
source and output paths must remain distinct.

## Frozen corpus and failure behavior

`tests/fixtures/provenance/corpus.json` separates native SDK cases from
projection-only cases. Native cases cover PNG and JPEG embedded, detached,
tampered, byte-copied, and manifest-free export behavior plus missing receipt
artifact, unsupported format, oversized manifest, and malformed manifest.
Parser limits are 64 MiB per asset, 8 MiB per sidecar, and 2 MiB per derived
report.

Invalid-time, revoked trust, redacted/private assertion, and unknown-assertion
branches use deterministic reader-JSON projection tests. They are not presented
as external trust-service evidence. The actual fixture supplies the
unknown-trust branch through an untrusted test chain.

`scripts/test_c2patool_interop.py` adds eight bidirectional combinations:
proof-pr→`c2patool` and `c2patool`→proof-pr for PNG/JPEG and embedded/detached
forms. It requires the exact `c2patool 0.27.16` executable, isolates its config
directory, uses only the public fixture certificate/key, and performs no remote
trust or timestamp lookup. The official macOS archive SHA-256 is
`2c2cd9f949c7231a71bce26b0d4f7e7b45db2128bf93cd0e3189ad0172e9039e`;
the Linux CI archive SHA-256 is
`62eed34f0c90a24b696b1969c8aad4340e11ec7264e1cf6fc375ad15c1db7663`.
Both are from the official
[`c2patool-v0.27.16` release](https://github.com/contentauth/c2pa-rs/releases/tag/c2patool-v0.27.16).

## Size and performance evidence

One local Apple Silicon sample on 2026-08-30 with `c2pa-rs` 0.90.15 produced:

- source synthetic PNG: 73 bytes;
- embedded signed PNG: 14,028 bytes (13,955-byte overhead, 192.164× because the source is intentionally tiny);
- detached manifest: 13,943 bytes;
- source synthetic JPEG: 285 bytes;
- embedded signed JPEG: 14,241 bytes (13,956-byte overhead, 49.968× because the source is intentionally tiny);
- detached JPEG manifest: 13,944 bytes;
- one fixture creation: 75–185 ms across the latest observed PNG/JPEG run;
- adversarial corpus: 18 cases in about two seconds wall time;
- interoperability corpus: 8 bidirectional combinations in about one second wall time.

These are bounded local measurements, not general benchmarks. Real-image
percentage overhead will be much smaller, while absolute manifest overhead will
vary with assertions, ingredients, certificate chains, and format.

## Migration recommendation

Keep `proof-pr.v1` authoritative and introduce portable provenance as optional
artifact evidence:

1. Add signed/sidecar/report artifacts with existing artifact kinds; do not add
   a required receipt field.
2. Let current consumers ignore the optional artifacts and let provenance-aware
   consumers inspect them lazily.
3. Require a valid hard binding for integrity-sensitive automation, but keep
   `trusted` and `truthful` as separate policy decisions.
4. Keep JPEG optional but enabled after its frozen native and pinned CLI
   readbacks; graduate PDF only after a writer and frozen round trip exist.
5. Design any production signer/trust policy as a separately authorized project;
   it must not reuse the public fixture identity or silently become a new
   proof-pr authority.

Independent-codebase and external-ecosystem interoperability remain `UNKNOWN`.
The demonstrated claim is limited to a current independent CLI/process surface
with shared `c2pa-rs` lineage.

The repository is CLI/report-only and has no supported UI surface, so the
conditional UI accessibility check is not applicable. Inspector output is
structured JSON with explicit text states and a closed report validator; no
color, pointer, or visual-only interpretation is required.
