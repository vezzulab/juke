#!/usr/bin/env bash
# Part of Juke (Vezzu Studio). Not documented for use by anyone else.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${BUILD_DIR:-$ROOT/build/macos}"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
PYTHON="${PYTHON:-python3}"
VLC_APP="${VLC_APP:-/Applications/VLC.app}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/juke/__init__.py")"
DMG="$OUT_DIR/Juke-macos-arm64.dmg"

[ "$(uname -s)" = Darwin ] || { echo "this builds the Mac app: run it on a Mac" >&2; exit 1; }
[ "$("$PYTHON" -c 'import platform; print(platform.machine())')" = arm64 ] || { echo "PYTHON must be an arm64 Python (this one is not)" >&2; exit 1; }
[ -d "$VLC_APP" ] || { echo "VLC.app not found at $VLC_APP (set VLC_APP)" >&2; exit 1; }

rm -rf "$BUILD"
mkdir -p "$BUILD" "$OUT_DIR"

echo "==> Build environment"
"$PYTHON" -m venv "$BUILD/venv"
PY="$BUILD/venv/bin/python"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet pyinstaller "$ROOT"

echo "==> libVLC from $VLC_APP"
"$PY" "$ROOT/packaging/macos/prepare_vlc.py" "$VLC_APP" "$BUILD/vlc"

echo "==> Icon"
QT_QPA_PLATFORM=offscreen PYTHONPATH="$ROOT" "$PY" "$ROOT/packaging/macos/make_icns.py" "$BUILD/Juke.icns"

echo "==> Juke.app"
export JUKE_BUILD="${JUKE_BUILD:-$(date +%s)}"
echo "   build id $JUKE_BUILD (put <!-- juke-build:mac=$JUKE_BUILD --> in the release notes so a rebuild is offered as an update)"
JUKE_VLC_RUNTIME="$BUILD/vlc" JUKE_ICNS="$BUILD/Juke.icns" \
    "$PY" -m PyInstaller --noconfirm --clean --log-level WARN --distpath "$BUILD/dist" --workpath "$BUILD/work" \
    "$ROOT/packaging/macos/juke.spec"
APP="$BUILD/dist/Juke.app"

echo "==> Signing (ad hoc)"
# inside out: every library and plugin first, the app itself last
find "$APP" -type f \( -name '*.dylib' -o -name '*.so' \) -print0 | xargs -0 -n 50 codesign --force --sign - --timestamp=none >/dev/null
find "$APP/Contents/Frameworks" -maxdepth 3 -type d -name '*.framework' -print0 | while IFS= read -r -d '' fw; do
    codesign --force --sign - --timestamp=none "$fw" >/dev/null 2>&1 || true
done
codesign --force --sign - --timestamp=none "$APP"
codesign --verify --deep --strict "$APP"

echo "==> Disk image"
STAGE="$BUILD/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$ROOT/LICENSE" "$ROOT/NOTICE.md" "$STAGE/"
rm -f "$DMG"
hdiutil create -quiet -volname "Juke $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO -imagekey zlib-level=9 -ov "$DMG"
ls -lh "$DMG"
