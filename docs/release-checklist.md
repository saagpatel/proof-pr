# Release Checklist

Use this checklist before tagging a `proof-pr` release.

## Preflight

- Confirm `main` is clean and synced with `origin/main`.
- Confirm `pyproject.toml` and `src/proof_pr/__init__.py` carry the intended
  version.
- Confirm the `proof-pr` workflow is passing on `main`; it gates public git
  metadata for the PR head or main workflow SHA plus version tags.
- Review `PUBLICATION.md` for public-safety posture changes.

## Local Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/proof_pr.py validate examples/pr-*.json
python3 scripts/test_receipt_hygiene_cli.py
python3 scripts/check_public_git_metadata.py --ref HEAD --ref 'refs/tags/v*'
tmpdir=$(mktemp -d)
python3 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install .
"$tmpdir/venv/bin/python" scripts/test_receipt_hygiene_cli.py --proof-pr "$tmpdir/venv/bin/proof-pr"
"$tmpdir/venv/bin/proof-pr" check-public-git-metadata --ref HEAD --ref 'refs/tags/v*'
"$tmpdir/venv/bin/proof-pr" validate examples/pr-*.json
"$tmpdir/venv/bin/proof-pr" render examples/pr-024-sample-dashboard-rollups.json
rm -rf "$tmpdir"
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
git tag -a vX.Y.Z -m "proof-pr vX.Y.Z"
git push origin vX.Y.Z
```

Do not treat the receipt JSON as release provenance. Release artifacts should
add checksums and attestations separately when the project starts publishing
build artifacts.
