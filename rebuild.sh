#!/bin/bash
set -e
cd "$(dirname "$0")"
pkill -f "Get up, Stand up" 2>/dev/null || true
rm -rf build dist
python3 setup.py py2app

# Fix embedded Python path
install_name_tool -change "@executable_path/../../../../Python3" \
  "@executable_path/../Frameworks/Python3.framework/Versions/3.9/Python3" \
  "dist/Get up, Stand up.app/Contents/MacOS/python"

# Re-sign the app with ad-hoc signature
codesign --force --deep --sign - "dist/Get up, Stand up.app"

open "dist/Get up, Stand up.app"
