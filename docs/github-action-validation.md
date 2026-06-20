# GitHub Action Validation

The first GitHub Action should validate proof receipts and publish reviewable
artifacts. It should not block merges until `proof-pr.v1` has survived real PR
dogfooding.

## Action Responsibilities

1. Check out the PR.
2. Validate `proof-pr.json` with `scripts/proof_pr.py validate`.
3. Upload `proof-pr.json` and `proof-pr-artifacts/` when present.
4. Render the Markdown proof block into the job summary.
5. Optionally run `proof-pr finalize --require-ready` after dogfooding proves the
   receipt is ready to act as a soft gate.
6. Leave PR body updates and required-check enforcement disabled for v0.

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
    uses: saagpatel/proof-pr/.github/workflows/proof-pr-receipt.yml@v0.1.3
    with:
      receipt_path: proof-pr.json
      proof_pr_ref: v0.1.3
      artifact_name: proof-pr
      artifact_glob: proof-pr-artifacts/**
```

The workflow:

- checks out the caller repo;
- installs `proof-pr` from the requested public git ref;
- validates the receipt;
- renders the proof block into the job summary;
- uploads the receipt and optional proof artifacts.

Use a released tag for both the reusable workflow ref and `proof_pr_ref` when a
consumer repo wants stable behavior. Keep required-check enforcement disabled
until dogfooding proves the receipt is reliable enough to gate merges.

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
      - name: Validate receipt
        run: python3 scripts/proof_pr.py validate proof-pr.json
      # Enable after dogfooding if the repo wants a non-blocking ready check first:
      # - name: Check finalized decision
      #   run: python3 scripts/proof_pr.py finalize proof-pr.json --require-ready
      - name: Render proof summary
        run: python3 scripts/proof_pr.py render proof-pr.json >> "$GITHUB_STEP_SUMMARY"
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
