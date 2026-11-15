#!/bin/sh
# Juke: download the AppImage, make it executable and start it. It adds itself to the applications menu on first run.
set -e
[ "$(uname -m)" = "x86_64" ] || { echo "Juke's AppImage is for x86_64 Linux." >&2; exit 1; }
dir="$HOME/Applications"
file="$dir/Juke.AppImage"
mkdir -p "$dir"
echo "Downloading Juke..."
curl -fL --progress-bar -o "$file.part" "https://github.com/vezzulab/juke/releases/latest/download/Juke-x86_64.AppImage"
chmod +x "$file.part"
mv "$file.part" "$file"
echo "Starting Juke..."
nohup "$file" >/dev/null 2>&1 &
