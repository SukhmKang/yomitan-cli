#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

INSTALL_APP=true
case "${1:-}" in
  "")
    ;;
  --build-only)
    INSTALL_APP=false
    ;;
  *)
    echo "Usage: $0 [--build-only]"
    exit 2
    ;;
esac

export PYINSTALLER_CONFIG_DIR="$PROJECT_DIR/build/.pyinstaller"
PYTHON="$PROJECT_DIR/.venv/bin/python"
ICON_SOURCE="$PROJECT_DIR/assets/jp-companion-icon.png"
ICONSET="$PROJECT_DIR/build/JP Companion.iconset"
ICON="$PROJECT_DIR/build/JP Companion.icns"
BUILT_APP="$PROJECT_DIR/dist/JP Companion.app"
INSTALLED_APP="$HOME/Applications/JP Companion.app"

if [ ! -x "$PYTHON" ]; then
  echo "Missing project environment: $PROJECT_DIR/.venv"
  echo "Create it with: /opt/homebrew/bin/python3.11 -m venv .venv"
  exit 1
fi

if [ "$("$PYTHON" -c 'import platform; print(platform.machine())')" != "arm64" ]; then
  echo "Refusing to build: .venv is not running as arm64."
  exit 1
fi

mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$ICON_SOURCE" \
    --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double_size=$((size * 2))
  sips -z "$double_size" "$double_size" "$ICON_SOURCE" \
    --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICON"

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "JP Companion" \
  --icon "$ICON" \
  --osx-bundle-identifier "com.sukhmkang.jp-companion" \
  --collect-all unidic_lite \
  jp_companion.py

codesign --verify --deep --strict "$BUILT_APP"
if ! file "$BUILT_APP/Contents/MacOS/JP Companion" | grep -q "arm64"; then
  echo "Refusing to install: the built app is not arm64."
  exit 1
fi

echo "Built and verified: $BUILT_APP"

if [ "$INSTALL_APP" = false ]; then
  exit 0
fi

osascript -e 'quit app "JP Companion"' 2>/dev/null || true
sleep 1
mkdir -p "$HOME/Applications"
rm -rf "$INSTALLED_APP"
ditto "$BUILT_APP" "$INSTALLED_APP"
codesign --verify --deep --strict "$INSTALLED_APP"
open "$INSTALLED_APP"

rm -rf "$PROJECT_DIR/build" "$PROJECT_DIR/dist" "$PROJECT_DIR/JP Companion.spec"
echo "Installed and opened: $INSTALLED_APP"
