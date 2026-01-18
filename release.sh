#!/bin/bash
set -e
cd "$(dirname "$0")"

# Check for version argument
if [ -z "$1" ]; then
    echo "Usage: ./release.sh <version> <release_notes>"
    echo "Example: ./release.sh 1.7.0 \"Bug fixes and improvements\""
    exit 1
fi

VERSION=$1
RELEASE_NOTES=${2:-"Bug fixes and improvements"}

echo "==> Releasing v$VERSION"

# Update version in files
echo "==> Updating version numbers..."
sed -i '' "s/^VERSION = \".*\"/VERSION = \"$VERSION\"/" standup_reminder.py
sed -i '' "s/'CFBundleVersion': \".*\"/'CFBundleVersion': \"$VERSION\"/" setup.py
sed -i '' "s/'CFBundleShortVersionString': \".*\"/'CFBundleShortVersionString': \"$VERSION\"/" setup.py

# Update version.json
cat > version.json << EOF
{
  "version": "$VERSION",
  "download_url": "https://github.com/ricardogo/sit-down-stand-up/releases/download/v$VERSION/SitDown.StandUp.app.zip",
  "notes": "$RELEASE_NOTES"
}
EOF

# Kill running app
echo "==> Stopping app..."
pkill -f "Sit Down. Stand Up" 2>/dev/null || true

# Build
echo "==> Building..."
rm -rf build dist
python3 setup.py py2app

# Create zip
echo "==> Creating zip..."
cd dist
zip -r SitDown.StandUp.app.zip "Sit Down. Stand Up.app"
cd ..

# Commit and tag
echo "==> Committing..."
git add -A
git commit -m "v$VERSION: $RELEASE_NOTES"
git tag "v$VERSION"

# Push
echo "==> Pushing to GitHub..."
git push origin main --tags

# Create release
echo "==> Creating GitHub release..."
gh release create "v$VERSION" dist/SitDown.StandUp.app.zip --title "v$VERSION" --notes "$RELEASE_NOTES"

echo "==> Done! Released v$VERSION"
echo "https://github.com/ricardogo/sit-down-stand-up/releases/tag/v$VERSION"
