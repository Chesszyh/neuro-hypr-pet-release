from pathlib import Path
import sys
from setuptools import setup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
target = "--target-app" in sys.argv
pet = "--pet-app" in sys.argv
if target:
    sys.argv.remove("--target-app")
if pet:
    sys.argv.remove("--pet-app")
name = "Neuro Pet" if pet else "Neuro macOS Probe Target" if target else "Neuro macOS Probe"
script = "neuro_macos_shimeji.py" if pet else "neuro_macos_probe_target.py" if target else "neuro_macos_probe.py"
setup(
    name=name,
    app=[str(ROOT / "tools" / script)],
    options={"py2app": {
        "argv_emulation": False,
        "packages": ["src", *(["soundfile", "_soundfile_data", "numpy"] if pet else [])],
        "includes": ["AppKit", "Foundation", "ApplicationServices", *(["_cffi_backend"] if pet else [])],
        "frameworks": [str(path) for path in (Path(sys.base_prefix) / "lib").glob("libffi.8.dylib")],
        "resources": [str(ROOT / "packaging/macos/licenses")],
        "plist": {
            "CFBundleIdentifier": "io.github.chesszyh.neuro-hypr-pet" if pet else "io.github.chesszyh.neuro-hypr-pet.probe.target" if target else "io.github.chesszyh.neuro-hypr-pet.probe",
            "CFBundleName": name,
            "CFBundleShortVersionString": "0.1.0",
            "LSUIElement": not target,
            "LSMinimumSystemVersion": "14.0",
            "NSHighResolutionCapable": True,
        },
    }},
)
