#!/usr/bin/env bash
# Build Juke-<arch>.AppImage.
#
#   packaging/build-appimage.sh
#
# Environment:
#   PYTHON_PREFIX        relocatable Python install to bundle (e.g. python-build-standalone).
#                        Default: the host's own Python.
#   APPIMAGETOOL         path to appimagetool. If absent, the AppImage is assembled with
#                        mksquashfs and the runtime of an existing AppImage:
#   RUNTIME_FROM         an existing AppImage whose runtime (the ELF header part) is reused.
#   OUT_DIR              where to write the result (default: <repo>/dist)
#
# Build on the *oldest* distribution you want to support: the AppImage needs at least the glibc it
# was built against (CI uses Ubuntu 22.04).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${BUILD_DIR:-$ROOT/build}"
APPDIR="$BUILD/AppDir"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
ARCH="${ARCH:-$(uname -m)}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/juke/__init__.py")"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/python" "$OUT_DIR"

echo "==> Python"
if [ -n "${PYTHON_PREFIX:-}" ]; then
    PYBIN="$PYTHON_PREFIX/bin/python3"
    cp -a "$PYTHON_PREFIX/." "$APPDIR/usr/python/"
else
    PYBIN="$(command -v python3)"
    PYVER="$("$PYBIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PYLIB="$("$PYBIN" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')"
    STDLIB="$("$PYBIN" -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
    PLATLIB="$("$PYBIN" -c 'import sys; print(sys.platlibdir)')"   # "lib64" on Fedora, "lib" elsewhere
    mkdir -p "$APPDIR/usr/python/bin" "$APPDIR/usr/python/lib" "$APPDIR/usr/python/$PLATLIB"
    cp -L "$PYBIN" "$APPDIR/usr/python/bin/python3"
    cp -a "$PYLIB"/libpython"$PYVER"*.so* "$APPDIR/usr/python/lib/"
    rsync -a --exclude 'test' --exclude 'tests' --exclude 'idlelib' --exclude 'tkinter' --exclude 'turtledemo' \
        --exclude 'ensurepip' --exclude '__pycache__' --exclude 'site-packages' "$STDLIB/" "$APPDIR/usr/python/$PLATLIB/python$PYVER/"
fi
PYVER="$("$PYBIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
SITE="$APPDIR/usr/python/site-packages"   # AppRun puts this on PYTHONPATH, whatever the Python's own layout
mkdir -p "$SITE"

echo "==> Python packages (Juke + dependencies)"
"$PYBIN" -m pip install --quiet --no-cache-dir --no-compile --target "$SITE" "$ROOT"

echo "==> Pruning unused Qt parts"
QT="$SITE/PySide6"
rm -rf "$QT/Qt/qml" "$QT/Qt/translations" "$QT/Qt/libexec" "$QT/include" "$QT/typesystems" "$QT/glue" "$QT/scripts" \
       "$QT/examples" "$QT/support"
rm -f "$QT"/{assistant,designer,linguist,lupdate,lrelease,rcc,uic,svgtoqml,qmllint,qmlformat,qmlls,pyside6-*} 2>/dev/null || true
rm -f "$QT"/Qt/lib/libQt6{Quick,Qml,Pdf,Designer,3D,Test,ShaderTools,Labs,QuickControls2}*.so* \
      "$QT"/Qt/lib/libQt6{WebEngine,Multimedia,Charts,DataVisualization,Graphs,Location,Sensors,SerialPort,Nfc,Bluetooth}*.so* 2>/dev/null || true
rm -f "$QT"/Qt{Quick,Qml,Pdf,Designer,3D,Test,ShaderTools,Labs,QuickControls2}*.abi3.so 2>/dev/null || true
find "$SITE" -name '*.pyi' -delete
find "$SITE" -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "==> libVLC + plugins"
python3 "$ROOT/packaging/bundle_libs.py" "$APPDIR"

echo "==> Qt platform helper libraries"
# Qt's xcb plugin needs these; many desktops lack libxcb-cursor. Copied when present on the build host.
for lib in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 libxcb-render-util.so.0 \
           libxcb-shape.so.0 libxcb-xkb.so.1 libxkbcommon-x11.so.0 libxcb-xinerama.so.0; do
    # (no early `exit` in awk: with pipefail its SIGPIPE would abort the whole script)
    path="$(ldconfig -p | awk -v l="$lib" '$1==l && /x86-64|64/ {print $NF}' | head -n1 || true)"
    if [ -n "$path" ]; then cp -L "$path" "$APPDIR/usr/lib/"; else echo "   (skipped $lib: not installed here)"; fi
done

echo "==> Desktop entry, icons, launcher"
install -m 755 "$ROOT/packaging/AppRun" "$APPDIR/AppRun"
install -m 644 "$ROOT/packaging/juke.desktop" "$APPDIR/juke.desktop"
mkdir -p "$APPDIR/usr/share/applications"
install -m 644 "$ROOT/packaging/juke.desktop" "$APPDIR/usr/share/applications/juke.desktop"
QT_QPA_PLATFORM=offscreen PYTHONPATH="$SITE" LD_LIBRARY_PATH="$APPDIR/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$PYBIN" "$ROOT/packaging/make_icons.py" "$APPDIR"
ln -sf juke.png "$APPDIR/.DirIcon"
desktop-file-validate "$APPDIR/juke.desktop" 2>/dev/null || echo "   (desktop-file-validate unavailable or reported hints)"

OUT="$OUT_DIR/Juke-$ARCH.AppImage"
rm -f "$OUT"
echo "==> Packing $OUT"
if [ -n "${APPIMAGETOOL:-}" ] && [ -x "${APPIMAGETOOL}" ]; then
    ARCH="$ARCH" "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUT" 2>/dev/null \
        || ARCH="$ARCH" "$APPIMAGETOOL" "$APPDIR" "$OUT"
else
    : "${RUNTIME_FROM:?set APPIMAGETOOL, or RUNTIME_FROM=<existing .AppImage> to reuse its runtime}"
    python3 - "$RUNTIME_FROM" "$BUILD/runtime" <<'PY'
import struct, sys
data = open(sys.argv[1], "rb").read(4 * 1024 * 1024)
shoff, = struct.unpack_from("<Q", data, 0x28)
shentsize, shnum = struct.unpack_from("<HH", data, 0x3A)
end = shoff + shentsize * shnum          # the runtime is an ELF; the squashfs image starts right after it
with open(sys.argv[1], "rb") as f:
    f.seek(end)
    if f.read(4) != b"hsqs":
        sys.exit("could not locate the squashfs image after the ELF runtime")
    f.seek(0)
    open(sys.argv[2], "wb").write(f.read(end))
print("runtime size:", end)
PY
    mksquashfs "$APPDIR" "$BUILD/juke.squashfs" -root-owned -noappend -comp zstd -Xcompression-level 19 -quiet
    cat "$BUILD/runtime" "$BUILD/juke.squashfs" > "$OUT"
    chmod +x "$OUT"
fi
ls -lh "$OUT"
