# proof-pr.v1

`proof-pr.v1` is a pull-request proof receipt. It wraps repo-native verification
without replacing it: tests, screenshots, health checks, proof packages,
cross-system smoke outputs, CI artifacts, and human review notes stay in their
own formats, while the PR gets one compact contract that points at the evidence.

## Target Consumer

v0 optimizes for agent-generated PRs in a solo/operator workflow. The reviewer is
usually one human operator deciding whether an agent-created diff is safe to
merge. The same structure can later serve open-source maintainers and internal
teams, but those audiences should not drive v0 complexity.

## Relationship To Existing Contracts

`proof-pr.v1` borrows from:

- `proof-package.v1`: durable claim-to-artifact mapping for done-state proof.
- `VerificationResultV1`: normalized status, agent, steps, artifacts, and
  mutation class for verification adapters.

`proof-pr.v1` adds PR-specific anchoring:

- repository, PR number when known, base/head refs, and base/head SHAs;
- risk tier and changed surfaces;
- required evidence by blast radius;
- reviewer-facing Markdown block;
- rollback path and merge decision.

Local receipt JSON is not supply-chain provenance. For release/build tiers,
checksums and GitHub artifact attestations may be linked as evidence, but the
receipt itself should not pretend to be SLSA provenance.

## Status Vocabulary

All proof states are first-class:

- `passed`: evidence ran and supports the claim.
- `passed_with_warnings`: evidence ran but leaves bounded caveats.
- `failed`: evidence ran and found a blocking issue.
- `blocked`: evidence could not run because a dependency or permission blocked it.
- `skipped`: evidence was intentionally not run.
- `stale`: evidence exists but is outside its freshness window.
- `partial`: evidence supports only part of the claim.
- `not_applicable`: the evidence category does not apply to this PR.

Receipts must never collapse `skipped`, `stale`, `partial`, `blocked`, or
`not_applicable` into green proof.

## Risk Tiers

| Tier | Scope | Required Evidence | Optional Evidence | Explicitly Skippable |
|---|---|---|---|---|
| `T0` | Docs, comments, license, metadata with no runtime effect | diff summary, files touched, rollback path, security posture marked `not_applicable` or scanned | link check, spelling check | tests/build/screenshots when no executable or visual behavior changed |
| `T1` | Small code change with narrow blast radius | focused test or reasoned `not_applicable`, lint/typecheck when repo-native, files touched, rollback path | full suite, benchmark | screenshots, runtime health when no UI/runtime path changed |
| `T2` | User-visible behavior, API, schema, UI, cross-repo consumer behavior | focused + broader tests, build/typecheck where native, compatibility note, rollback path, screenshots or smoke when user-visible | cross-system smoke, fixture proof package | runtime health if no running service is affected |
| `T3` | Auth, permissions, CI/workflows, data writes, migrations, agent/tool access, cross-system contract | T2 evidence plus secrets scan or explicit posture, permission/workflow diff, dry-run/read-back or health check, human gate note | contract smoke, dogfood receipt | screenshots when no visual surface changed |
| `T4` | Release, deploy, migration, notarization, security-sensitive artifact, irreversible external change | T3 evidence plus artifact digests, install/deploy smoke, rollback rehearsal, release notes or migration plan | SBOM, GitHub artifact attestation, SLSA provenance link | local-only receipt as supply-chain provenance |

Risk tier is selected by blast radius, not line count.

## Receipt Shape

Required top-level fields:

- `schema_version`
- `receipt_id`
- `generated_at`
- `subject`
- `producer`
- `risk`
- `change`
- `evidence`
- `security`
- `rollback`
- `artifacts`
- `limitations`
- `overall`

The canonical schema is `schemas/proof-pr.v1.schema.json`.

## Markdown PR Block

```markdown
<!-- proof-pr:v1 start -->
## Proof Bundle

Risk: `T2`
Receipt: `proof-pr.v1` for `<head_sha>`
Decision: `ready`

Evidence:
- Tests: `<command>` -> `<status>` (`<summary>`)
- Typecheck/build: `<command>` -> `<status>`
- Screenshot/UI: `<status>` (`<artifact or reason>`)
- Health/smoke: `<status>` (`<artifact or reason>`)
- Secrets/security: `<status>` (`<tool or reason>`)
- Rollback: `<path>`

Known gaps:
- `<none, or explicit skipped/stale/partial/blocked/not_applicable item>`
<!-- proof-pr:v1 end -->
```

Rules:

- Keep the block short enough to scan in a PR.
- Put detailed logs and screenshots in artifacts, not the body.
- Link the receipt or artifact bundle when available.
- Use the exact status vocabulary; do not hide skipped proof.
- Anchor the block to the receipt head SHA.

## CLI MVP

`proof-pr init`

- Detect repo, branch, base/head refs, base/head SHAs, and PR number if `gh` can
  resolve one.
- Create an in-memory receipt draft.

`proof-pr collect`

- Gather changed files and diff stats.
- Run configured or operator-supplied checks.
- Attach artifact references.
- Mark missing categories as `skipped`, `blocked`, or `not_applicable` with a
  reason instead of pretending they passed.

`proof-pr finalize`

- Promote collected diff metadata to passed evidence without claiming semantic
  human review.
- Set `overall.status` and `overall.review_decision` from required evidence,
  security posture, rollback posture, and limitations.
- Keep failed required evidence as `reject`, blocked required evidence as
  `revise`, and skipped/stale/partial required evidence as `partial`.
- Allow explicit `ready_with_operator_awareness` when warnings or accepted
  limitations remain.

`proof-pr render`

- Render the Markdown PR block from `proof-pr.json`.
- Optionally print only, update clipboard, or patch a PR body in a later version.

`proof-pr validate`

- Validate schema, required fields, enum values, artifact references, and
  required evidence by risk tier.
- Return nonzero on invalid receipts.

## GitHub Action Follow-Up

After local dogfooding, add an Action that:

- validates `proof-pr.json`;
- uploads receipt artifacts;
- writes a Markdown job summary;
- optionally comments on the PR or updates the proof block;
- does not block merges until the format survives real use.

Strict enforcement, GitHub App Checks integration, dashboards, and heavy
provenance are intentionally deferred.

## Deferred From v0

- GitHub App and custom check-run orchestration.
- Strict required-check enforcement.
- Dashboard or product UI.
- SLSA-heavy provenance for ordinary PRs.
- SBOM and artifact attestations except for `T4` release/build proof.
- Automatic expensive broad verification.

## First Dogfood Lane

Dogfood on a cross-repo producer -> dashboard truth/schema PR. That lane
naturally exercises PR sequencing, schema compatibility, repo-native tests,
rollback notes, and stale/skipped evidence.
