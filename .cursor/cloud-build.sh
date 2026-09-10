#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Cursor Cloud images do not guarantee the stdlib environment support.
# Install one pinned virtualenv package through the system pip; no standalone
# binary bootstrap is needed.  A fresh target keeps the bootstrap isolated from
# user-site packages and honours the image's configured PyPI/files.pythonhosted.org
# policy.
virtualenv_version="20.35.4"
bootstrap_dir="$(mktemp -d "${TMPDIR:-/tmp}/proof-pr-virtualenv.XXXXXXXX")"
trap 'rm -rf "$bootstrap_dir"' EXIT

python3 -m pip install \
	--disable-pip-version-check \
	--no-input \
	--no-cache-dir \
	--target "$bootstrap_dir" \
	"virtualenv==${virtualenv_version}"

# Use an explicit project-local interpreter and venv.  `--no-download` keeps
# virtualenv on its bundled seed wheel and prevents a second package host from
# being contacted before the project install below.
PYTHONPATH="$bootstrap_dir${PYTHONPATH:+:$PYTHONPATH}" \
	python3 -m virtualenv \
		--clear \
		--no-download \
		--app-data "$bootstrap_dir/app-data" \
		--python python3 \
		.venv

.venv/bin/python -m pip install \
	--disable-pip-version-check \
	--no-input \
	--no-cache-dir \
	'.[provenance]'

for validation_script in \
	scripts/test_validation_contract.py \
	scripts/test_examples_cli.py \
	scripts/test_example_pattern_cli.py \
	scripts/test_receipt_hygiene_cli.py \
	scripts/test_workflow_template_cli.py \
	scripts/test_provenance_cli.py; do
	.venv/bin/python "$validation_script"
done
