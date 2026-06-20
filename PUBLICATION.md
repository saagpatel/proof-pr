# Publication Notes

`proof-pr` is public at <https://github.com/saagpatel/proof-pr>.

The public repository is a fresh scrubbed snapshot. An earlier private working
repository was preserved as a private archive for operator continuity, but it is
not the public source of record.

## Public Safety Posture

- Example receipts use public or anonymized repository identifiers.
- Local filesystem paths and private-repository names are not part of the public
  content.
- The public repository has fresh history and no pull request history from the
  private working repo.
- The workflow uses GitHub-hosted `ubuntu-latest` runners.

## Publication Checks

Before widening visibility or cutting releases, run:

```bash
gitleaks detect --source . --no-banner --redact --verbose
rg -n --hidden --glob '!/.git/**' '(<private-repo>|<local-path>|<token-prefix>)'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/proof_pr.py validate examples/pr-*.json
python3 -m pip install .
proof-pr validate examples/pr-*.json
```

The receipt JSON is review proof, not supply-chain provenance. Release-grade
builds should add artifact checksums and attestations separately.
