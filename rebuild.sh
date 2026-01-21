#!/bin/bash
set -e
cd "$(dirname "$0")"
pkill -f "Sit Down. Stand Up" 2>/dev/null || true
rm -rf build dist
python3 setup.py py2app

# Fix embedded Python path
install_name_tool -change "@executable_path/../../../../Python3" \
  "@executable_path/../Frameworks/Python3.framework/Versions/3.9/Python3" \
  "dist/Sit Down. Stand Up.app/Contents/MacOS/python"

# Re-sign the app with ad-hoc signature
codesign --force --deep --sign - "dist/Sit Down. Stand Up.app"

open "dist/Sit Down. Stand Up.app"
