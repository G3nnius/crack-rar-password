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
  --add-binary "bin/macos-arm64/unrar:bin/macos-arm64" \
  --console \
  RARNinja.py

# --- GUI .app -----------------------------------------------------------
[ -f assets/RARNinja.icns ] || python3 scripts/make_icon.py
.buildvenv/bin/pyinstaller \
  --windowed --name RARNinja --distpath dist/app \
  --target-arch arm64 --optimize 2 \
  --icon assets/RARNinja.icns \
  --add-binary "bin/macos-arm64/unrar:bin/macos-arm64" \
  --add-data "assets/icon_1024.png:assets" \
  gui.py

cp dist/cli/rarninja dist/rarninja

# --- zip the app (+ easy-start launcher + first-run guide) --------------
if [ -d dist/app/RARNinja.app ]; then
  rm -rf dist/pkg && mkdir -p dist/pkg/RARNinja
  cp -R dist/app/RARNinja.app "dist/pkg/RARNinja/RARNinja.app"
  cp "scripts/Start RARNinja.command" "dist/pkg/RARNinja/Start RARNinja.command"
  cp FIRST-RUN.txt "dist/pkg/RARNinja/FIRST-RUN.txt"
  chmod +x "dist/pkg/RARNinja/Start RARNinja.command"
  ( cd dist/pkg && ditto -c -k --keepParent RARNinja ../RARNinja-macos-arm64.zip )
fi

echo
echo "Built:"
file dist/rarninja
echo "dist/app/RARNinja.app"
ls -lh dist/RARNinja-macos-arm64.zip 2>/dev/null || true
