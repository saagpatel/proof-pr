# GitHub Action Validation

The first GitHub Action should validate proof receipts and publish reviewable
artifacts. It should not block merges until `proof-pr.v1` has survived real PR
dogfooding.

## Action Responsibilities

1. Check out the PR.
2. Optionally gate public git metadata for repos that require noreply-only live
   history/tags.
3. Validate `proof-pr.json` with `scripts/proof_pr.py validate`.
4. Write advisory `proof-pr receipt-hygiene` output into the job summary.
5. Upload `proof-pr.json` and `proof-pr-artifacts/` when present.
6. Render the Markdown proof block into the job summary.
7. Optionally run `proof-pr finalize --require-ready` after dogfooding proves the
   receipt is ready to act as a soft gate.
8. Leave PR body updates and required-check enforcement disabled for v0.

## Reusable Workflow

`proof-pr` now ships a reusable workflow at
`.github/workflows/proof-pr-receipt.yml`.

Consumer repos can call it after generating or committing a receipt:

```yaml
name: proof-pr

on:
  pull_request:
  workflow_dispatch:

jobs:
  proof:
    permissions:
      contents: read
      actions: read
    uses: saagpatel/proof-pr/.github/workflows/proof-pr-receipt.yml@v0.2.7
    with:
      receipt_path: proof-pr.json
      proof_pr_ref: v0.2.7
      artifact_name: proof-pr
      artifact_glob: proof-pr-artifacts/**
      check_public_git_metadata: false
      receipt_hygiene: true
      receipt_hygiene_strict: false
      # For older repos with legacy public metadata, prefer introduced mode:
      # check_public_git_metadata: true
      # public_git_metadata_mode: introduced
      # For pull_request callers that enable the metadata gate, prefer:
      # public_git_metadata_ref: ${{ github.event.pull_request.head.sha }}
```

The workflow:

- checks out the caller repo;
- installs `proof-pr` from the requested public git ref;
- optionally checks public git metadata for the configured ref and version tags,
  or only for commits introduced by `base..ref`;
- writes the public git metadata scope to the job summary when that check is
  enabled, including `full` versus `introduced` mode and tag scope;
- validates the receipt;
- writes receipt hygiene suggestions to the job summary in advisory mode by
  default;
- renders the proof block into the job summary, anchored to the GitHub run SHA;
- uploads the receipt and optional proof artifacts.

Use a released tag for both the reusable workflow ref and `proof_pr_ref` when a
consumer repo wants stable behavior. Keep required-check enforcement disabled
until dogfooding proves the receipt is reliable enough to gate merges.

Use `check_public_git_metadata: true` with `public_git_metadata_mode:
introduced` for established public repos whose old commits or tags are not
noreply-clean. Keep `full` mode for newly scrubbed repos and release/publication
checks where all selected refs and tags are expected to be clean.

For committed receipts, collect the same posture as a normal evidence item:

```bash
proof-pr collect-public-git-metadata \
  --receipt proof-pr.json \
  --base-ref origin/main \
  --ref HEAD
```

Or add it to `run-config`:

```json
{
  "public_git_metadata": {
    "id": "public-git-metadata",
    "refs": ["HEAD"],
    "base_ref": "origin/main",
    "required": true
  }
}
```

This writes a schema-valid `security` evidence item instead of adding a new
top-level receipt field:

```json
{
  "id": "public-git-metadata",
  "kind": "security",
  "status": "passed",
  "required": true,
  "summary": "Public git metadata checked in introduced mode for origin/main..HEAD; legacy history and tags were not in scope; findings=0."
}
```

Before review, run hygiene in advisory mode:

```bash
proof-pr receipt-hygiene proof-pr.json
proof-pr receipt-hygiene proof-pr.json --explain
proof-pr receipt-hygiene proof-pr.json --explain --check public-git-metadata --fix-only
```

`receipt-hygiene` is read-only. It suggests missing standard evidence by risk
tier. Use `--explain` locally when an author wants copyable commands and compact
receipt patch examples. Use `--check <id>` with `--fix-only` when an author only
wants the command or patch for one hygiene finding. `--strict` makes warnings
fail for repos that want a soft gate after dogfooding.

The reusable workflow runs `receipt-hygiene` by default after validation and
writes the result to the job summary. It also appends a focused public git
metadata fix block when that finding exists, so authors get the compact command
or receipt patch without reading every advisory. Keep
`receipt_hygiene_strict: false` while adopting; set it to `true` only after the
repo's receipts consistently pass hygiene locally and in CI.

Caller workflows should grant explicit read permissions to the reusable workflow
job. Without the `contents: read` and `actions: read` stanza, GitHub can fail a
new caller workflow before any job logs are produced.

For new consumer repos, start with `workflow_dispatch`. After a manual run
passes on `main`, add `pull_request` if the repo wants proof visibility during
review. See `docs/stable-dogfood-contract.md` for the v0.2 adoption boundary and
the advisory versus soft-gate enforcement modes.

## Inline Workflow

```yaml
name: proof-pr

on:
  pull_request:
  workflow_dispatch:

jobs:
  validate-proof:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Check public git metadata
        env:
          PUBLIC_METADATA_REF: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}
          PUBLIC_METADATA_BASE_REF: ${{ github.event_name == 'pull_request' && format('origin/{0}', github.base_ref) || 'origin/main' }}
        run: python3 scripts/proof_pr.py check-public-git-metadata --base-ref "$PUBLIC_METADATA_BASE_REF" --ref "$PUBLIC_METADATA_REF" --summary-format text
      - name: Validate receipt
        run: python3 scripts/proof_pr.py validate proof-pr.json
      - name: Receipt hygiene
        run: python3 scripts/proof_pr.py receipt-hygiene proof-pr.json >> "$GITHUB_STEP_SUMMARY"
      # Enable after dogfooding if the repo wants a non-blocking ready check first:
      # - name: Check finalized decision
      #   run: python3 scripts/proof_pr.py finalize proof-pr.json --require-ready
      - name: Render proof summary
        run: python3 scripts/proof_pr.py render proof-pr.json --head-sha "${GITHUB_SHA}" >> "$GITHUB_STEP_SUMMARY"
      - name: Upload proof bundle
        uses: actions/upload-artifact@v4
        with:
          name: proof-pr
          path: |
            proof-pr.json
            proof-pr-artifacts/**
          if-no-files-found: warn
```

For consuming repos that do not vendor `proof-pr`, replace the validation command
with an install or checkout step for this project. Keep this explicit until the
CLI has a packaged release.

## What Stays Deferred

- Required status checks.
- PR body mutation.
- GitHub App Checks API integration.
- Artifact attestations for ordinary PRs.
- Dashboard/reporting UI.
