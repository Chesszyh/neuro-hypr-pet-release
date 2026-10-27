#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python="${PYTHON:-.venv-macos/bin/python}"
"$python" packaging/macos/setup.py --pet-app py2app
app="dist/Neuro Pet.app"
"$python" - "$app/Contents/Info.plist" <<'PYTHON'
import plistlib
import sys
from pathlib import Path
path = Path(sys.argv[1])
info = plistlib.loads(path.read_bytes())
# py2app records the build interpreter path; standalone apps use their bundled interpreter.
info.get("PythonInfoDict", {}).pop("PythonExecutable", None)
path.write_bytes(plistlib.dumps(info))
PYTHON
mkdir -p "$app/Contents/Resources/ProjectNotices"
cp LICENSE THIRD_PARTY_NOTICES.md "$app/Contents/Resources/ProjectNotices/"
cp -R LICENSES "$app/Contents/Resources/ProjectNotices/"
if command -v local-codesign >/dev/null 2>&1; then
    local-codesign --identifier io.github.chesszyh.neuro-hypr-pet "$app"
else
    codesign --force --deep --sign - --identifier io.github.chesszyh.neuro-hypr-pet "$app"
fi
codesign --verify --deep --strict "$app"
staging="$(mktemp -d "${TMPDIR:-/tmp}/neuro-pet-dmg.XXXXXX")"
trap 'rm -rf "$staging"' EXIT
ditto "$app" "$staging/Neuro Pet.app"
ln -s /Applications "$staging/Applications"
cp packaging/macos/README.md "$staging/Install.md"
arch="$(uname -m)"
hdiutil create -ov -volname 'Neuro Pet' -srcfolder "$staging" -format UDZO "dist/Neuro-Pet-macos-$arch.dmg"
