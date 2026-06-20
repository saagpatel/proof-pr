# Dogfood: Sample Dashboard Receipt Collection

Date: 2026-06-20

This dogfood pass exercised `proof_pr.py` against
a dashboard-style app using the first truth/schema consumer config. It was a
local smoke on a `main` checkout, not an open PR body update. Identifiers are
anonymized so this repository can be published safely.

## Command Shape

```bash
tmpdir=$(mktemp -d /tmp/proof-pr-dogfood.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python3 scripts/proof_pr.py init \
  --cwd /path/to/sample-dashboard \
  --tier T2 \
  --summary 'Sample dashboard truth/schema dogfood receipt' \
  --output "$tmpdir/proof-pr.json"
PYTHONDONTWRITEBYTECODE=1 python3 scripts/proof_pr.py run-config \
  "$tmpdir/proof-pr.json" \
  --cwd /path/to/sample-dashboard \
  --config examples/proof-pr.config.example.json \
  --artifact-dir "$tmpdir/proof-pr-artifacts" \
  --finalize
PYTHONDONTWRITEBYTECODE=1 python3 scripts/proof_pr.py validate "$tmpdir/proof-pr.json"
PYTHONDONTWRITEBYTECODE=1 python3 scripts/proof_pr.py render "$tmpdir/proof-pr.json"
```

## Result

- Receipt validation: passed.
- Final decision: `ready`.
- Repo slug: `example/sample-dashboard`.
- Head SHA: `bdf125f99a452d831f099c9ce058cbf67c610f3a`.
- `pnpm typecheck`: passed.
- `pnpm test`: passed, `67 passed`.
- `cargo check --manifest-path src-tauri/Cargo.toml`: passed.

## Rendered Block

```markdown
<!-- proof-pr:v1 start -->
## Proof Bundle

Risk: `T2`
Receipt: `proof-pr.v1` for `bdf125f99a452d831f099c9ce058cbf67c610f3a`
Decision: `ready`

Evidence:
- diff-review: `passed` (Diff metadata collected: changed files and diff stats are present. Semantic review remains the reviewer's responsibility.)
- typecheck: `pnpm typecheck` -> `passed` (TypeScript typecheck for the dashboard app. Exit code 0.)
- tests: `pnpm test` -> `passed` (Dashboard app test suite. Exit code 0.)
- rust-check: `cargo check --manifest-path src-tauri/Cargo.toml` -> `passed` (Tauri/Rust shell check for IPC and file-load changes. Exit code 0.)
- secrets: `not_applicable` (No secret-bearing files expected; update if workflow/env/config files change.)
- permissions: `not_applicable` (No workflow, Tauri permission, connector, or agent-access change expected.)
- redaction: `not_applicable` (No screenshots attached by default; mark fixture-backed or redacted if added.)
- rollback: `documented` (Revert the PR; keep producer/consumer fallback behavior documented.)

Known gaps:
- None
<!-- proof-pr:v1 end -->
```

## Lessons

- `run-config` is enough to collect repo-native command evidence into log
  artifacts.
- `--finalize` is the missing review-decision step: it clears the draft
  limitation, promotes collected diff metadata, and keeps non-green required
  evidence from becoming ready.
- Remote URL normalization must handle HTTPS before SSH-style `host:path`
  parsing; the dogfood run caught and fixed that bug.
