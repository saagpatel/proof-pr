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

## Example Workflow

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
