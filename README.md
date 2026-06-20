# proof-pr

`proof-pr` is a small standard and future CLI for pull requests that carry their
own proof bundle: risk tier, files touched, verification commands, screenshots,
health checks, security posture, rollback notes, and a machine-readable receipt.

The v0 target consumer is agent-generated PRs in a solo/operator workflow. The
format is intentionally portable enough for open-source maintainers and internal
teams later, but v0 optimizes for fast human review of agent-created changes.

## Current Contents

- `docs/proof-pr-v1.md` - v0 standard, Markdown block, risk tiers, CLI plan, and
  GitHub Action follow-up.
- `docs/release-checklist.md` - release preflight and verification checklist.
- `PUBLICATION.md` - public safety posture and publication checks.
- `schemas/proof-pr.v1.schema.json` - machine-readable receipt schema.
- `examples/` - compact historical receipts from real PRs.
- `src/proof_pr/` - dependency-free CLI and receipt validator package.
- `scripts/` - source-checkout compatibility wrappers.
- `examples/proof-pr.config.example.json` - sample command config for a
  dashboard truth/schema consumer PR.
- `docs/github-action-validation.md` - GitHub Action validation plan and example.
- `docs/stable-dogfood-contract.md` - v0.2 candidate contract for consumer
  adoption, triggers, and enforcement modes.
- `.github/workflows/proof-pr-receipt.yml` - reusable workflow that validates a
  receipt, uploads proof artifacts, and writes a job summary.
- `.github/workflows/proof-pr-validate.yml` - self-check workflow that validates
  receipts and gates public git metadata for live history/tags.
- `docs/dogfood-sample-dashboard.md` - first local dogfood run notes.

## Validate

```bash
python3 scripts/validate_receipts.py examples/pr-*.json
python3 scripts/proof_pr.py validate examples/pr-*.json
python3 scripts/proof_pr.py render examples/pr-024-sample-dashboard-rollups.json
python3 scripts/check_public_git_metadata.py --ref HEAD --ref 'refs/tags/v*'
proof-pr check-public-git-metadata --ref HEAD --ref 'refs/tags/v*'
```

The validator is intentionally lightweight. It checks structure, required
fields, enum values, and the tier/evidence basics. It does not decide whether a
claim is true; the receipt author still owns honest evidence.

## Install

From a local checkout inside a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
proof-pr validate examples/pr-*.json
proof-pr render examples/pr-024-sample-dashboard-rollups.json
```

From GitHub:

```bash
python3 -m pip install git+https://github.com/saagpatel/proof-pr.git
```

## CLI MVP

```bash
python3 scripts/proof_pr.py init --cwd /path/to/repo --tier T2 --summary "Short PR summary" --output proof-pr.json
python3 scripts/proof_pr.py collect proof-pr.json --cwd /path/to/repo --config examples/proof-pr.config.example.json
python3 scripts/proof_pr.py run --receipt proof-pr.json --cwd /path/to/repo --id tests --kind test -- python3 -m pytest -q
python3 scripts/proof_pr.py run-config proof-pr.json --cwd /path/to/repo --config examples/proof-pr.config.example.json --finalize
python3 scripts/proof_pr.py finalize proof-pr.json --require-ready
python3 scripts/proof_pr.py render proof-pr.json
python3 scripts/proof_pr.py render proof-pr.json --head-sha <pr-head-sha>
python3 scripts/proof_pr.py render --full-commands proof-pr.json
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json --explain
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json --explain --check public-git-metadata --fix-only
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json --json
python3 scripts/proof_pr.py validate proof-pr.json
proof-pr check-public-git-metadata --ref HEAD --ref 'refs/tags/v*'
proof-pr check-public-git-metadata --base-ref origin/main --ref HEAD
proof-pr check-public-git-metadata --base-ref origin/main --ref HEAD --summary-format text
proof-pr collect-public-git-metadata --receipt proof-pr.json --base-ref origin/main --ref HEAD
```

The CLI is local-only in v0. It can draft receipt identity and diff stats, run
configured commands into log artifacts, synthesize the final review decision,
render the Markdown block, and validate examples. It does not update PR bodies,
upload artifacts, or enforce merges yet.

By default, `render` compacts long command lines so PR bodies stay scannable.
Use `--full-commands` when a reviewer wants complete commands inline; receipt
JSON always keeps the full command array.

Use `--head-sha` when rendering a PR body or CI summary for a committed receipt
whose `subject.head_sha_status` is `pending_commit`. The JSON can remain honest
about its commit-time placeholder while the rendered block anchors to the final
PR or check-run SHA.

`finalize` is intentionally conservative: failed required proof rejects the
receipt, blocked required proof keeps it in revise, skipped/stale/partial
required proof remains partial, and unresolved limitations prevent a ready
decision unless `--allow-limitations` is set. The default draft limitation is
cleared during finalization after evidence has been collected.

`check-public-git-metadata` is a public-release guardrail. It fails when selected
refs contain commit or annotated-tag email metadata outside GitHub noreply
patterns, and it is enforced by this repository's self-check workflow. Use
`--base-ref origin/main --ref HEAD` to check only newly introduced commits in
older repos whose existing public history is not fully noreply-clean.
Use `--summary-format text` or `--summary-format json` when the check output is
being copied into CI summaries or receipts; the summary records whether the
scope was `full` or `introduced`, the checked refs, the base ref, and tag scope.

Use `collect-public-git-metadata` when a receipt should carry that result as a
normal `security` evidence item. The command upserts `public-git-metadata`
without changing the receipt schema, so public metadata posture remains review
evidence rather than supply-chain provenance.

Use `receipt-hygiene` as a read-only pre-review nudge. It inspects an existing
receipt and suggests missing standard evidence for the risk tier, starting with
public git metadata, secrets posture, workflow permission posture, and rollback
specificity. Add `--explain` to include copyable commands and compact receipt
patch examples for missing evidence. Add `--check <id>` to focus on one finding
and `--fix-only` to print just the remediation command/patch block. Add
`--strict` when a repo wants hygiene warnings to fail CI.
The reusable workflow writes these suggestions to the job summary by default in
advisory mode.
