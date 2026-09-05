#!/bin/bash
# RARNinja easy-start for macOS.
# Right-click this file -> Open -> Open (once). It removes the quarantine flag
# from RARNinja.app so it launches without Gatekeeper warnings, then opens it.
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/RARNinja.app"
if [ ! -d "$APP" ]; then
  echo "RARNinja.app not found next to this launcher."
  echo "Keep this file in the same folder as RARNinja.app."
  read -r -p "Press Return to close."
  exit 1
fi
echo "Preparing RARNinja for first launch..."
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
open "$APP" && echo "Launched. You can now open RARNinja.app directly next time."
