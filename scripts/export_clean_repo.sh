#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${1:-$ROOT_DIR/release/llm_satd_clean}"

if [[ -e "$TARGET_DIR" ]]; then
  echo "Target already exists: $TARGET_DIR" >&2
  echo "Refusing to overwrite an existing export." >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"

copy_if_exists() {
  local rel="$1"
  if [[ -e "$ROOT_DIR/$rel" ]]; then
    mkdir -p "$TARGET_DIR/$(dirname "$rel")"
    cp -R "$ROOT_DIR/$rel" "$TARGET_DIR/$rel"
  fi
}

# Top-level docs and config that belong with the code.
for rel in README.md requirements.txt .gitignore .gitattributes __init__.py; do
  copy_if_exists "$rel"
done

# Compressed datasets only.
mkdir -p "$TARGET_DIR/data"
find "$ROOT_DIR/data" -maxdepth 1 -type f -name '*.zip' -print0 | while IFS= read -r -d '' file; do
  cp "$file" "$TARGET_DIR/data/"
done

# Small validation datasets needed to reproduce classifier checks.
for rel in \
  classify_validation/alt_test_labels.csv \
  classify_validation/alt_test_labels_nonperfect_consensus.csv \
  classify_validation/alt_test_metrics.csv \
  classify_validation/llm_validate_labels.csv \
  classify_validation/llm_validate_kappa.csv; do
  copy_if_exists "$rel"
done

# Keep code and notebook sources, but drop caches, outputs, and raw CSV datasets.
while IFS= read -r -d '' file; do
  rel="${file#$ROOT_DIR/}"
  mkdir -p "$TARGET_DIR/$(dirname "$rel")"
  cp "$file" "$TARGET_DIR/$rel"
done < <(
  find \
    "$ROOT_DIR/analysis" \
    "$ROOT_DIR/utils" \
    "$ROOT_DIR/dataset_construction" \
    "$ROOT_DIR/classify_validation" \
    "$ROOT_DIR/scripts" \
    -type f \
    \( \
      -name '*.py' -o \
      -name '*.ipynb' -o \
      -name '*.sh' -o \
      -name '*.sql' -o \
      -name '*.txt' -o \
      -name '*.json' -o \
      -name '*.md' \
    \) \
    ! -path '*/__pycache__/*' \
    ! -path '*/old/*' \
    ! -name '.DS_Store' \
    -print0
)

(
  cd "$TARGET_DIR"
  git init -b main >/dev/null
  git add .
  git commit -m "Initial import" >/dev/null
)

echo "Created clean export at: $TARGET_DIR"
echo "New git history initialized with a single commit."
