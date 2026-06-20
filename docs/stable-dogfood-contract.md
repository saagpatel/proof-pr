# Stable Dogfood Contract

`proof-pr` should not call itself stable because the schema exists. It becomes
stable when ordinary repos can use it without a human remembering hidden rules.

`v0.2.0` is the first candidate for that boundary.

## Contract Boundary

The stable dogfood contract is:

- receipt JSON validates with `proof-pr validate`;
- `proof-pr render` produces a short PR block without losing full command truth;
- committed receipts can mark `subject.head_sha_status` as `pending_commit` and
  render PR/check summaries with an explicit final head SHA;
- the reusable workflow validates a committed receipt;
- the reusable workflow writes the rendered proof block to the job summary;
- the reusable workflow uploads the receipt and optional artifacts;
- consumer workflows use explicit read permissions;
- enforcement remains advisory unless a repo opts into a soft required check.

This is still review evidence, not supply-chain provenance. Release/build tiers
may link attestations or artifact digests, but ordinary PR receipts do not become
SLSA provenance by existing in CI.

## Consumer Workflow Shape

Use a released tag for both the reusable workflow and the installed CLI:

```yaml
name: proof-pr

on:
  workflow_dispatch:

jobs:
  proof:
    permissions:
      contents: read
      actions: read
    uses: saagpatel/proof-pr/.github/workflows/proof-pr-receipt.yml@v0.2.2
    with:
      receipt_path: proof-pr.json
      proof_pr_ref: v0.2.2
      artifact_name: proof-pr
      artifact_glob: proof-pr-artifacts/**
      check_public_git_metadata: false
      # Established repos can opt into new-commit metadata checks with:
      # public_git_metadata_mode: introduced
```

Start with `workflow_dispatch` when adopting the workflow in a new repo. After a
manual run passes on `main`, add `pull_request` if the repo wants every PR to
publish proof.

## Manual Versus Pull Request Triggers

Use `workflow_dispatch` when:

- introducing the workflow itself;
- validating a historical or committed receipt;
- debugging permissions or artifact paths;
- avoiding noisy checks while a repo is still learning the receipt shape.

Use `pull_request` when:

- the repo already has a stable receipt location;
- authors know how to update or regenerate the receipt;
- startup failures and permissions have been proven on `main`;
- failed validation should be visible during review.

For PR-triggered usage, keep path filters narrow at first:

```yaml
on:
  pull_request:
    paths:
      - proof-pr.json
      - proof-pr-artifacts/**
      - .github/workflows/proof-pr.yml
  workflow_dispatch:
```

## Enforcement Modes

`proof-pr` has three practical enforcement modes:

| Mode | Behavior | When to Use |
|---|---|---|
| Advisory | Validate, render, and upload proof, but do not block merge. | Default for v0.2 dogfood and new consumer repos. |
| Soft required check | Make the workflow a required check, but allow receipts with `ready_with_operator_awareness` when limitations are explicit. | Repos with repeated successful dogfood runs. |
| Strict gate | Require a finalized ready receipt and fail on skipped/stale/partial required evidence. | Deferred until the format has broader use. |

`v0.2.2` should ship advisory mode as the documented default. Soft required
checks can be documented as an opt-in pattern, not as the baseline.

`v0.2.1` keeps the `v0.2.0` receipt contract and adds the public git metadata
gate as an opt-in reusable workflow input for consumers.

`v0.2.2` keeps that contract and adds introduced-only metadata checks so older
repos can gate new commits without rewriting legacy public history.

Established public repos should start with `public_git_metadata_mode:
introduced`, which checks only commits introduced by the workflow ref relative
to the configured base. Full-history mode is appropriate once a repo's live
history and version tags are known to be noreply-clean.

## Ready For v0.2.0

The project is ready to tag `v0.2.0` when:

- at least two consumer repos have passed `workflow_dispatch` with the released
  reusable workflow;
- one consumer has proven the caller permissions shape;
- release receipts are attached for recent proof-pr tags;
- docs clearly separate review evidence from provenance;
- the reusable workflow interface is small enough to support without churn.

Current status: `bridge-db` has passed the `v0.1.3` reusable workflow path with
explicit caller permissions. `GithubRepoAuditor` has also passed the manual
consumer workflow path, and exposed the commit-time SHA anchoring gap now covered
by `subject.head_sha_status`.
