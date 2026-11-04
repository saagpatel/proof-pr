# Signed review attestations

`proof-pr review` records review decisions as signed in-toto Statement v1
attestations. `verify-two-key` checks that an Anthropic-run reviewer and an
OpenAI-run reviewer approved the same pull request head and base. This is
advisory infrastructure: it reports evidence for a caller to inspect and does
not configure branch protection or enforce a merge.

## What the signatures mean

Each envelope uses checkseal's local Ed25519 signer. A valid signature proves
that the private key corresponding to an allowlisted public key signed the
statement bytes. The runner label comes from key metadata and must match the
allowlist; the vendor supplied to `attest` must also match that key's
allowlisted vendor. The verifier's output says `proves: runner keys, not served
models`.

The findings file is treated as an opaque artifact. Its SHA-256 digest and byte
size are included in the statement; its contents are not copied into the
attestation. The statement binds the review to one repository, pull request,
base, and head commit. A new head requires new approvals. A current-head
`changes_requested` attestation for the expected repository, PR, and head
vetoes PASS even when its base differs or approval attestations also exist.
Unrelated and stale attestations are reported but do not veto a valid pair.

The [predicate schema](../schemas/proof-pr.review-attestation.v1.schema.json)
documents the signed review fields.

## Threat model

The caller trusts the allowlist, the private keys, each key's local metadata
sidecar, and the selected attestation store. A compromised, mislabeled, or
shared key can undermine the claimed separation between reviewers. The
signature does not establish independent reasoning, a correct or complete
review, which served model ran, or that the store is immutable or complete.
Deleted or suppressed attestations are outside the proof. The CLI does not
enforce storage locations: keep private keys and any overridden store outside
every repository.

## Keys and allowlist

Install the optional review extra with Python 3.12 or later:

```bash
python3 -m pip install '.[review]'
```

Keep private keys outside every repository, in a directory restricted to the
key owner. `keygen` refuses to overwrite existing key files, writes the private
key with mode `0600`, and emits `<vendor>-<runner>.private.pem`,
`<vendor>-<runner>.public.pem`, and the required `<vendor>-<runner>.json`
metadata sidecar. The runner label is read from that sidecar beside the private
key; the verifier requires it to match the runner in the allowlist. Runner and
run-id values are single safe filename tokens containing letters, digits,
dots, underscores, or hyphens, and beginning with a letter or digit.

```bash
proof-pr review keygen --vendor anthropic --runner reviewer-a --out-dir "$KEY_DIR"
proof-pr review keygen --vendor openai --runner reviewer-b --out-dir "$KEY_DIR"
```

Each command prints its keyid. Add one allowlist entry per public key, using
the corresponding keyid and the exact vendor and runner labels. The public key
path is read locally by the verifier:

```json
[
  {
    "keyid": "KEYID_FROM_KEYGEN",
    "vendor": "anthropic",
    "runner": "reviewer-a",
    "public_key_path": "PATH_TO_ANTHROPIC_PUBLIC_KEY"
  },
  {
    "keyid": "KEYID_FROM_KEYGEN",
    "vendor": "openai",
    "runner": "reviewer-b",
    "public_key_path": "PATH_TO_OPENAI_PUBLIC_KEY"
  }
]
```

Treat the allowlist as a trust decision: a key is authorized for exactly one
vendor. Relative `public_key_path` values are resolved from the allowlist
file's directory. To rotate a key, add the new keyid and remove the old keyid
from the allowlist. Retaining an old key keeps its attestations trusted.

## Store layout

Attestations are stored outside the PR tree so writing one does not change the
commit it names. By default the store is
`~/.local/share/proof-pr/review-attestations/`; `PROOF_PR_REVIEW_STORE` or the
`--store` option can select another location. Files are placed at:

```text
<store>/<owner>/<name>/pr-<N>/<head>/<vendor>-<run_id>.dsse.json
```

The verifier scans every `*.dsse.json` below the repository and PR directory,
including earlier head folders, so stale attestations appear in the report.
Each considered envelope receives an accept or reject reason. Missing or
unreadable stores and unavailable GitHub head/base data produce UNKNOWN, never
PASS. Exit status is 0 for PASS, 1 for FAIL, and 2 for UNKNOWN. An `accept`
means the envelope is individually eligible; the `counted` list names the
selected pair. The counted approvals must have different keys and run IDs;
identical findings digests are allowed.

## Usage walkthrough

The caller prepares one findings artifact and decides each review verdict. The
artifact should live outside the PR worktree if producing it there would alter
the head under review. Create one attestation per independent review, using
different run IDs and different signing keys:

```bash
proof-pr review attest \
  --key "$KEY_DIR/anthropic-reviewer-a.private.pem" \
  --repo OWNER/NAME --pr N --base BASE_SHA --head HEAD_SHA \
  --vendor anthropic --tool TOOL --run-id RUN_A \
  --verdict approve --findings "$FINDINGS_A"

proof-pr review attest \
  --key "$KEY_DIR/openai-reviewer-b.private.pem" \
  --repo OWNER/NAME --pr N --base BASE_SHA --head HEAD_SHA \
  --vendor openai --tool TOOL --run-id RUN_B \
  --verdict approve --findings "$FINDINGS_B"
```

Verify against explicit commit values, or use `--from-gh` to read `headRefOid`
and `baseRefOid` from the pull request with `gh`:

```bash
proof-pr review verify-two-key \
  --repo OWNER/NAME --pr N --allowlist "$ALLOWLIST" \
  --head HEAD_SHA --base BASE_SHA
```

Proceed only when the JSON report says `PASS`, and pin the merge to that same
verified head so a later push cannot change what is merged:

```bash
gh pr merge N --repo OWNER/NAME --match-head-commit HEAD_SHA
```
