# Portable provenance privacy threat model

## Assets and trust boundaries

The protected assets are local artifact contents, private task metadata,
prompts, filesystem paths, location, user identity, signing keys, and proof-pr's
existing ownership model. The boundary contains the proof-pr CLI, a pinned local
C2PA SDK, fixture files, an input receipt, and explicitly selected synthetic or
public test artifacts. C2PA output can cross ordinary file handoff boundaries;
the source receipt remains local and canonical.

## Threats and controls

| Threat | Control | Residual risk |
| --- | --- | --- |
| Production key or user identity is used accidentally | Creation requires explicit certificate/key paths and rejects a leaf without `OU=FOR TESTING_ONLY`. No Keychain/Secure Enclave integration exists. | A caller could deliberately alter source code; this profile is not a production policy boundary. |
| Local paths or task metadata leak into a portable asset | Only basenames and a minimal receipt projection are embedded. Tests search for the temporary absolute path. | Receipt/artifact IDs and commit SHA may still be sensitive; operators must choose whether portability is appropriate. |
| Prompt, location, thumbnail, or private assertion leaks | The profile has no prompt/location inputs, disables thumbnails, emits no task body, repo URL, PR URL, changed files, or arbitrary receipt fields. Its own manifests report these fields absent; third-party or manifest-free inputs report `unknown` rather than asserting absence without inspection. | Future assertion additions require renewed privacy review. |
| Network retrieval exfiltrates asset identifiers | Remote manifest fetch is disabled for create and inspect. No timestamp authority is configured. | Dependency installation itself requires a separately authorized network action. |
| Malicious manifest exhausts parser resources | Input and generated asset, sidecar, and report sizes are bounded; generated outputs are checked before either artifact path is written, and exceptions become concise non-traceback failures. | Native parser CPU complexity is not fully controlled by byte limits. Run untrusted bulk inputs in an OS sandbox. |
| Valid signature is mistaken for honest content | Inspector exposes well-formed, bound, signed, signature-valid, valid, trusted, and truthful independently; truthful is always unknown. | Downstream UI can still mislabel results if it ignores the report contract. |
| crJSON becomes a second authority | It is treated only as a derived view and never as signing or validation input. | Copying crJSON without its asset/manifest can mislead an uninformed consumer. |
| Sidecar is separated from its asset | Detached verification requires both asset and manifest; a sidecar alone cannot pass binding. | Ordinary handoff can omit one file, producing an explicit absent/mismatch result. |
| A fixture run overwrites an existing artifact | Destinations refuse collisions by default; `--force` applies only to the exact named destination and cannot make it equal the source. | An operator can still intentionally replace an output with `--force`. |
| Copy/export strips embedded provenance | Byte-copy survival and manifest-free export are separate corpus cases. | Transcoding/editing tools may preserve, update, or remove manifests differently; no universal survival claim is made. |
| Unknown or revoked credentials are shown as trusted | Unknown fixture trust remains unknown; deterministic projection tests cover revoked and invalid-time failures. | No live revocation or external trust infrastructure is consulted, so freshness is unknown. |
| An interoperability tool reads user trust configuration or contacts a timestamp service | The pinned `c2patool` test uses an isolated `XDG_CONFIG_HOME`, a manifest with no timestamp URL, public fixture keys only, and no trust subcommand. | The tools share `c2pa-rs`, so common parser/signing defects remain possible. |

## Data minimization checklist

- Embed receipt ID, artifact ID/hash, commit SHA/status, and producer name/version only.
- Exclude repository URL, PR URL, task prompt, evidence commands/output, usernames,
  machine names, absolute paths, EXIF location, and thumbnails.
- Do not contact remote manifest, timestamp, identity, trust, or revocation services.
- Store no new canonical receipt; write only explicitly requested artifact/report paths.
- Treat JSON/terminal reports as derived, disposable views.

## Quarantined features

Production signing identities, public credentials, trust-anchor registration,
live revocation, timestamp authorities, user/private content, and deployment are
outside this profile. Their exact unblock condition is a separately approved
identity/trust design with secrets handling, lifecycle, revocation, privacy,
rollback, and independent interoperability evidence.
