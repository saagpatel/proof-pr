#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Cursor Cloud images do not guarantee uv. Bootstrap one exact release without
# changing shell profiles or enabling a self-updater in the build VM.
uv_version="0.12.12"
uv_install_dir="${HOME}/.local/bin"
uv_bin=""

if command -v uv >/dev/null 2>&1; then
	candidate_uv="$(command -v uv)"
	candidate_version="$("$candidate_uv" --version | awk '{print $2}')"
	if [ "$candidate_version" = "$uv_version" ]; then
		uv_bin="$candidate_uv"
	fi
fi

if [ -z "$uv_bin" ]; then
	uv_bin="$uv_install_dir/uv"
	if [ ! -x "$uv_bin" ] || [ "$("$uv_bin" --version | awk '{print $2}')" != "$uv_version" ]; then
		mkdir -p "$uv_install_dir"
		curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
			"https://astral.sh/uv/${uv_version}/install.sh" \
			| UV_UNMANAGED_INSTALL="$uv_install_dir" sh
	fi
fi

if [ ! -x "$uv_bin" ] || [ "$("$uv_bin" --version | awk '{print $2}')" != "$uv_version" ]; then
	echo "expected uv ${uv_version} at ${uv_bin}" >&2
	exit 1
fi

# Use an explicit project-local interpreter and venv so no system Python
# ensurepip/venv module is required by the Cloud build image.
"$uv_bin" python install 3.12
# Replace a partial or stale environment left by an earlier failed build.
"$uv_bin" venv --clear --python 3.12 .venv
"$uv_bin" pip install --python .venv/bin/python '.[provenance]'

for validation_script in \
	scripts/test_validation_contract.py \
	scripts/test_examples_cli.py \
	scripts/test_example_pattern_cli.py \
	scripts/test_receipt_hygiene_cli.py \
	scripts/test_workflow_template_cli.py \
	scripts/test_provenance_cli.py; do
	.venv/bin/python "$validation_script"
done
