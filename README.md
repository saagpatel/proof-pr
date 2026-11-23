# proof-pr

`proof-pr` is a small standard and CLI for pull requests that carry their
own proof bundle: risk tier, files touched, verification commands, screenshots,
health checks, security posture, rollback notes, and a machine-readable receipt.

The v0 target consumer is agent-generated PRs in a solo/operator workflow. The
format is intentionally portable enough for open-source maintainers and internal
teams later, but v0 optimizes for fast human review of agent-created changes.

## Current Contents

- `docs/proof-pr-v1.md` - v0 standard, Markdown block, risk tiers, CLI usage, and
  GitHub Action follow-up.
- `docs/example-receipts.md` - example receipt patterns by risk tier and PR
  shape.
- `docs/release-checklist.md` - release preflight and verification checklist.
- `PUBLICATION.md` - public safety posture and publication checks.
- `schemas/proof-pr.v1.schema.json` - machine-readable receipt schema.
- `docs/artifact-provenance-profile.md` - optional fixture-only C2PA artifact
  profile, trust vocabulary, format matrix, and migration path.
- `docs/provenance-privacy-threat-model.md` - portable metadata and parser threat
  model.
- `docs/review-attestations.md` - optional signed review attestations and
  two-key verification.
- `schemas/proof-pr.review-attestation.v1.schema.json` - signed review predicate
  schema.
- `schemas/proof-pr.artifact-provenance-report.v1.schema.json` - schema for the
  derived, non-authoritative inspector report.
- `examples/` - historical and illustrative receipts, plus sample configs.
- `examples/pr-101-agent-operating-decision.json` - T3 agent PR with optional
  OPERANT-style `operating-decision` evidence.
- `examples/proof-pr-self-template.config.example.json` - config template for
  using proof-pr to document its own PRs.
- `src/proof_pr/` - dependency-free CLI and receipt validator package.
- `scripts/` - source-checkout compatibility wrappers.
- `scripts/test_examples_cli.py` - CLI smoke tests over the bundled examples.
- `examples/proof-pr.config.example.json` - sample command config for a
  dashboard truth/schema consumer PR.
- `docs/github-action-validation.md` - GitHub Action validation plan and example.
- `docs/stable-dogfood-contract.md` - v0.2 candidate contract for consumer
  adoption, triggers, and enforcement modes.
- `.github/workflows/proof-pr-receipt.yml` - reusable workflow that validates a
  receipt, uploads proof artifacts, and writes a job summary.
- `proof-pr workflow-template` - non-overwriting generator for a pinned consumer
  workflow, starting with manual dispatch and optional narrow PR triggers.
- `.github/workflows/proof-pr-validate.yml` - self-check workflow that validates
  receipts and gates public git metadata for live history/tags.
- `docs/dogfood-sample-dashboard.md` - first local dogfood run notes.

## Install

From the checkout root, create and activate a virtual environment with Python 3.11 or later:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install .
proof-pr validate examples/pr-*.json
proof-pr render examples/pr-024-sample-dashboard-rollups.json
```

Portable provenance support is optional and pins the native-backed SDK used by
the frozen fixture corpus:

```bash
python3 -m pip install -e '.[provenance]'
python3 scripts/test_provenance_cli.py
```

Signed review attestations are optional and require Python 3.12 or later:

```bash
python3 -m pip install '.[review]'
python3 scripts/test_review_cli.py --proof-pr proof-pr
```

See [signed review attestations](docs/review-attestations.md) for the two-key
walkthrough and threat model. Signatures prove runner keys, not served models.

With the provenance extra installed and the checksum-verified official
`c2patool` 0.27.16 binary on your `PATH`, run
the pinned PNG/JPEG embedded/detached bidirectional readback:

```bash
python3 scripts/test_c2patool_interop.py --c2patool "$(command -v c2patool)"
```

This proves an independent CLI/process surface only. Both paths use
`c2pa-rs`, fixture trust remains unknown, and truthfulness is never inferred.

From GitHub (pin to a tag — consumers should not track `main` tip):

```bash
# Latest release
python3 -m pip install "git+https://github.com/saagpatel/proof-pr.git@v0.2.14"

# Or track main tip (not recommended for production use)
python3 -m pip install git+https://github.com/saagpatel/proof-pr.git
```

## Validate

```bash
python3 scripts/validate_receipts.py examples/pr-*.json
python3 scripts/proof_pr.py validate examples/pr-*.json
python3 scripts/proof_pr.py render examples/pr-024-sample-dashboard-rollups.json
```

The validator is intentionally lightweight. It checks structure, required
fields, enum values, and the tier/evidence basics. It does not decide whether a
claim is true; the receipt author still owns honest evidence.

To audit Git history and release tags, use either metadata checker. Both exit 1
on this checkout because historical email metadata falls outside the default
allowlist. Use the `--base-ref` example below to check only newly introduced commits.

```bash
python3 scripts/check_public_git_metadata.py --ref HEAD --ref 'refs/tags/v*'
proof-pr check-public-git-metadata --ref HEAD --ref 'refs/tags/v*'
```

## Contributor verification

Run these commands from the repository root with Python 3.11 or later. The core
CLI has no runtime dependencies; source wrappers work without installing the
package. Start with a focused harness for the changed surface, for example
`python3 scripts/test_validation_contract.py` for receipt/schema changes.

The core fixture baseline mirrors
[the self-check workflow](.github/workflows/proof-pr-validate.yml):

```bash
python3 scripts/test_receipt_hygiene_cli.py
python3 scripts/test_examples_cli.py
python3 scripts/test_example_pattern_cli.py
python3 scripts/test_workflow_template_cli.py
python3 scripts/test_validation_contract.py
python3 scripts/proof_pr.py validate examples/pr-*.json
python3 scripts/proof_pr.py render examples/pr-024-sample-dashboard-rollups.json
```

These checks use committed examples and temporary synthetic receipts/workflows;
they do not require provider credentials, publish a PR, or run commands from your
own receipt config. `run` and `run-config` execute configured commands and create
logs, so they are not substitutes for this fixture baseline.

For installation/packaging changes, use the virtual environment in
[Install](#install), install with `python3 -m pip install .`, and run the CLI
harnesses accepting `--proof-pr` with `--proof-pr proof-pr` to check the installed
entry point. There is no dedicated lint, format, or static typecheck tool
configured here. The fixture harnesses and the actual CI checks remain the
baseline; do not substitute an unconfigured pytest command.

Review-attestation changes additionally need Python 3.12 or later and the
optional signing extra: install with `python3 -m pip install '.[review]'`, then run
`python3 scripts/test_review_cli.py --proof-pr proof-pr`. This mirrors the `review`
lane in [the self-check workflow](.github/workflows/proof-pr-validate.yml); the core
fixture baseline above does not exercise signing.

Provenance changes additionally need the optional SDK and pinned c2patool fixture
lanes described in [Install](#install) and
[the provenance profile](docs/artifact-provenance-profile.md). Those dependencies
and platform binaries are separate prerequisites, not evidence from a core CLI
pass. If rendered receipt output or workflow summaries change, inspect the
rendered sample Markdown and the corresponding PR/CI summary; there is no web
application or mandatory browser check for a pure documentation change.

## CLI Usage

From the checkout root, choose one `init` command for a new receipt and one
`workflow-template` command for a new workflow. Copy the self-template to start
a config for this PR.

```bash
python3 scripts/proof_pr.py init --tier T2 --summary "Short PR summary" --output proof-pr.json
# Or: python3 scripts/proof_pr.py init --tier T3 --example "Workflow dogfood" --summary "Short PR summary" --output proof-pr.json
python3 scripts/proof_pr.py workflow-template
# Or: python3 scripts/proof_pr.py workflow-template --pull-request --receipt-path proof-pr.json
cp -i examples/proof-pr-self-template.config.example.json proof-pr.config.json
```

Edit `proof-pr.config.json` before continuing. Both `collect` and `run-config`
apply its values to the receipt. Replace the template's T0 risk tier, reasons,
and changed surfaces with those for this PR. Set the change summary and scope
notes, record the actual status and rationale for each security check, and give
the rollback steps for this change. Set `commands` to the checks that verify
the change. The template only validates bundled example receipts.

```bash
python3 scripts/proof_pr.py collect proof-pr.json --config proof-pr.config.json --suggest-example
python3 scripts/proof_pr.py run --receipt proof-pr.json --id tests --kind test -- python3 scripts/test_examples_cli.py
python3 scripts/proof_pr.py run-config proof-pr.json --config proof-pr.config.json --finalize
python3 scripts/proof_pr.py finalize proof-pr.json --require-ready
python3 scripts/proof_pr.py render proof-pr.json
python3 scripts/proof_pr.py render examples/pr-101-agent-operating-decision.json
python3 scripts/proof_pr.py render --full-commands proof-pr.json
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json --explain
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json --explain --check public-git-metadata --fix-only
python3 scripts/proof_pr.py receipt-hygiene proof-pr.json --json
python3 scripts/proof_pr.py examples
python3 scripts/proof_pr.py examples --json
python3 scripts/proof_pr.py examples --json --tier T3
python3 scripts/test_receipt_hygiene_cli.py
python3 scripts/test_example_pattern_cli.py
python3 scripts/proof_pr.py validate proof-pr.json
proof-pr check-public-git-metadata --base-ref origin/main --ref HEAD
proof-pr check-public-git-metadata --base-ref origin/main --ref HEAD --summary-format text
proof-pr collect-public-git-metadata --receipt proof-pr.json --base-ref origin/main --ref HEAD
```

With the provenance extra installed, the following pair signs and verifies a
synthetic `fixture.png`. Supply that file and a `fixture-png` entry in the
receipt's `artifacts` with its matching lowercase SHA-256. For a self-contained
example that creates both inputs, run `python3 scripts/test_provenance_cli.py`.

```bash
proof-pr provenance create --source fixture.png --output signed.png --receipt proof-pr.json --artifact-id fixture-png --fixture-cert tests/fixtures/provenance/es256_certs.fixture.pem --fixture-key tests/fixtures/provenance/es256_private.fixture.pem
proof-pr provenance verify signed.png --output provenance-report.json
```

The receipt-authoring CLI runs locally: it can draft receipt identity and diff
stats, run configured commands into log artifacts, synthesize the final review
decision, render the Markdown block, and validate examples. The reusable GitHub
workflow validates committed receipts, renders a check summary, and uploads
artifacts. `workflow-template` creates that consumer workflow without
overwriting an existing path; it does not create a receipt, update PR bodies, or
enforce merges.

`provenance` is a fixture-only optional extension. It leaves the closed
`proof-pr.v1` receipt unchanged and embeds only a minimal reference to an
existing receipt artifact. The inspector reports well-formed, bound, signed,
signature-valid, valid, trusted, and truthful separately; truthful is always
unknown. See [the profile](docs/artifact-provenance-profile.md) before using it.

By default, `render` compacts long command lines so PR bodies stay scannable.
Use `--full-commands` when a reviewer wants complete commands inline; receipt
JSON always keeps the full command array.

To render the current PR's own committed `proof-pr.json` for a PR body or CI
summary, use `--head-sha` if `subject.head_sha_status` is `pending_commit`.
Run this from a clean checkout of the receipt after verifying that `HEAD`
matches the PR's final head SHA. The override sets the displayed SHA and leaves
the recorded evidence and decision intact.

```bash
python3 scripts/proof_pr.py render proof-pr.json --head-sha "$(git rev-parse HEAD)"
```

`init` attaches a suggested `producer.example_pattern` from the receipt tier, or
an explicit one from `--example`. `collect --suggest-example` refreshes that
metadata after config changes the risk tier or changed surfaces. `render` shows
the selected pattern as authoring guidance; it is not evidence and does not
claim that the PR copied the example correctly.

`finalize` is intentionally conservative: failed required proof rejects the
receipt, blocked required proof keeps it in revise, skipped/stale/partial
required proof remains partial, and unresolved limitations prevent a ready
decision unless `--allow-limitations` is set. The default draft limitation is
cleared during finalization unless `--keep-draft-limitations` is set.
Missing or unrecognized evidence and security statuses cannot produce a ready
decision. Collecting new metadata or evidence marks an earlier ready decision
stale; run `finalize` again to evaluate the updated receipt.

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
public git metadata, secrets posture, workflow permission posture, rollback
specificity, and operating-decision evidence on agent T2+ receipts. Add
`--explain` for command templates and receipt patch examples. Use `--check <id>`
to focus on one finding and `--explain --fix-only` to print just the suggested fix. Add
`--strict` when a repo wants hygiene warnings to fail CI.
The reusable workflow writes these suggestions to the job summary by default in
advisory mode, followed by a focused public git metadata fix block when that
finding exists. If no focused fix is needed, `--fix-only` prints a clean
no-action-needed note and exits successfully.
