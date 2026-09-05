#!/usr/bin/env bash
# Build RARNinja for macOS arm64.
#   dist/rarninja                    - CLI binary (no Python needed)
#   dist/RARNinja.app                - GUI app    (double-click to run)
#   dist/RARNinja-macos-arm64.zip    - zipped app, ready to attach to a release
# Both bundle the arm64 `unrar` backend, so nothing else is required to run them.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .buildvenv
.buildvenv/bin/pip -q install --upgrade pip pyinstaller

rm -rf build dist rarninja.spec RARNinja.spec
mkdir -p dist

# CLI and GUI go to separate distpaths: on a case-insensitive filesystem
# "rarninja" and "RARNinja" are the same name and would collide otherwise.

# --- CLI (onefile, stripped) --------------------------------------------
.buildvenv/bin/pyinstaller \
  --onefile --name rarninja --distpath dist/cli \
  --target-arch arm64 --optimize 2 --strip \
  --add-binary "bin/unrar:bin" \
  --console \
  RARNinja.py

# --- GUI .app -----------------------------------------------------------
.buildvenv/bin/pyinstaller \
  --windowed --name RARNinja --distpath dist/app \
  --target-arch arm64 --optimize 2 \
  --add-binary "bin/unrar:bin" \
  gui.py

cp dist/cli/rarninja dist/rarninja

# --- zip the app for distribution ---------------------------------------
if [ -d dist/app/RARNinja.app ]; then
  ( cd dist/app && ditto -c -k --keepParent RARNinja.app ../RARNinja-macos-arm64.zip )
fi

echo
echo "Built:"
file dist/rarninja
echo "dist/app/RARNinja.app"
ls -lh dist/RARNinja-macos-arm64.zip 2>/dev/null || true
