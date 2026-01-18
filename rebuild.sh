#!/bin/bash
cd "$(dirname "$0")"
pkill -f "Sit Down. Stand Up" 2>/dev/null
rm -rf build dist
python3 setup.py py2app
open "dist/Sit Down. Stand Up.app"
