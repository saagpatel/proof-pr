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
- `docs/dogfood-sample-dashboard.md` - first local dogfood run notes.

## Validate

```bash
python3 scripts/validate_receipts.py examples/*.json
python3 scripts/proof_pr.py validate examples/*.json
python3 scripts/proof_pr.py render examples/pr-024-sample-dashboard-rollups.json
```

The validator is intentionally lightweight. It checks structure, required
fields, enum values, and the tier/evidence basics. It does not decide whether a
claim is true; the receipt author still owns honest evidence.

## Install

From a local checkout:

```bash
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
python3 scripts/proof_pr.py render --full-commands proof-pr.json
python3 scripts/proof_pr.py validate proof-pr.json
```

The CLI is local-only in v0. It can draft receipt identity and diff stats, run
configured commands into log artifacts, synthesize the final review decision,
render the Markdown block, and validate examples. It does not update PR bodies,
upload artifacts, or enforce merges yet.

By default, `render` compacts long command lines so PR bodies stay scannable.
Use `--full-commands` when a reviewer wants complete commands inline; receipt
JSON always keeps the full command array.

`finalize` is intentionally conservative: failed required proof rejects the
receipt, blocked required proof keeps it in revise, skipped/stale/partial
required proof remains partial, and unresolved limitations prevent a ready
decision unless `--allow-limitations` is set. The default draft limitation is
cleared during finalization after evidence has been collected.
