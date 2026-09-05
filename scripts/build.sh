#!/usr/bin/env bash
# Build an optimized, self-contained macOS arm64 binary of RARNinja.
# Output: dist/rarninja  (bundles bin/unrar; no Python needed to run it)
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .buildvenv
.buildvenv/bin/pip -q install --upgrade pip pyinstaller

rm -rf build dist rarninja.spec
.buildvenv/bin/pyinstaller \
  --onefile --name rarninja \
  --target-arch arm64 \
  --optimize 2 --strip \
  --add-binary "bin/unrar:bin" \
  --console \
  RARNinja.py

echo "Built: dist/rarninja"
file dist/rarninja
