#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

export PYINSTALLER_CONFIG_DIR="$PROJECT_DIR/build/.pyinstaller"
PYTHON="$PROJECT_DIR/.venv/bin/python"
ICON_SOURCE="$PROJECT_DIR/assets/jp-companion-icon.png"
ICONSET="$PROJECT_DIR/build/JP Companion.iconset"
ICON="$PROJECT_DIR/build/JP Companion.icns"

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

echo "Built: $PROJECT_DIR/dist/JP Companion.app"
