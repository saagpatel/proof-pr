# Example Receipts

Use these examples as copy points for common proof-pr shapes. They are compact
historical receipts from real or realistic PRs, and every `pr-*.json` example is
validated by the repository workflow.

| Pattern | Example | Tier | Copy When |
| --- | --- | --- | --- |
| Docs/license only | `examples/pr-054-bridge-db-license.json` | `T0` | A PR changes repository metadata, prose, comments, or static text with no executable behavior. |
| Test-only maintenance | `examples/pr-022-proof-pr-test-harness.json` | `T1` | A PR adds or changes test coverage, validation scripts, or CI test steps without changing runtime behavior. |
| UI/API/schema consumer | `examples/pr-024-sample-dashboard-rollups.json` | `T2` | A PR changes user-visible behavior, typed contracts, IPC/API consumption, or dashboard truth surfaces. |
| Workflow dogfood | `examples/pr-087-github-repo-auditor-dogfood.json` | `T3` | A PR adds proof-pr adoption, GitHub Actions wiring, committed receipts, or public proof evidence. |
| Schema/concurrency/contract | `examples/pr-055-bridge-db-schema-concurrency.json` | `T3` | A PR changes persistence, migrations, health checks, contracts, or concurrent write behavior. |

## Picking A Pattern

Start with the lowest tier that honestly describes the changed surface, then add
required evidence only for claims the PR actually makes.

- Use the docs/license example when tests would only prove that static text
  exists. Mark tests and screenshots `not_applicable` with a bounded reason.
- Use the test-only example when the PR improves proof or validation around
  existing behavior. Include both the new test command and the CI run that proves
  the test now runs in automation.
- Use the UI/API/schema consumer example when a downstream surface consumes
  producer-owned truth. Include type checks, smoke evidence, and screenshots only
  when the changed surface needs visual review.
- Use the workflow dogfood example when GitHub Actions or proof artifacts change.
  Include workflow permissions, public metadata posture, and rollback by removing
  the workflow or pinning an older proof-pr tag.
- Use the schema/concurrency example when a PR touches data shape, migrations, or
  write paths. Include focused tests, health checks, and an explicit rollback or
  migration mitigation.

## Validation

Validate examples before copying from them:

```bash
python3 scripts/proof_pr.py validate examples/pr-*.json
python3 scripts/proof_pr.py receipt-hygiene examples/pr-022-proof-pr-test-harness.json --explain
python3 scripts/proof_pr.py render examples/pr-022-proof-pr-test-harness.json
```
