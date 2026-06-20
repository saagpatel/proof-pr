# Release Checklist

Use this checklist before tagging a `proof-pr` release.

## Preflight

- Confirm `main` is clean and synced with `origin/main`.
- Confirm `pyproject.toml` and `src/proof_pr/__init__.py` carry the intended
  version.
- Review `PUBLICATION.md` for public-safety posture changes.

## Local Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/proof_pr.py validate examples/pr-*.json
python3 -m pip install .
proof-pr validate examples/pr-*.json
proof-pr render examples/pr-024-sample-dashboard-rollups.json
gitleaks detect --source . --no-banner --redact --verbose
```

Run the targeted public-reference scan from `PUBLICATION.md` when examples,
dogfood notes, or publication docs change.

## GitHub Verification

- Open a PR that carries a `proof-pr.v1` block.
- Confirm the `validate-proof` workflow passes on the PR.
- Merge through the PR path.
- Trigger `workflow_dispatch` on `main` and confirm it passes.

## Tagging

```bash
git tag -a v0.1.0 -m "proof-pr v0.1.0"
git push origin v0.1.0
```

Do not treat the receipt JSON as release provenance. Release artifacts should
add checksums and attestations separately when the project starts publishing
build artifacts.
