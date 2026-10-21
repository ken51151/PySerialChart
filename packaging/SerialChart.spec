from importlib.metadata import distribution
from pathlib import Path
import os

packaging_dir = Path(SPECPATH).resolve()
root = packaging_dir.parent
os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"
documents = ("LICENSE.txt", "COPYRIGHT.txt", "THIRD_PARTY_NOTICES.md", "SOURCE.md")
datas = [(str(root / "assets" / "icons"), "assets/icons"),
         (str(root / "licenses"), "licenses")]
datas += [(str(root / name), ".") for name in documents]
# Retain PyInstaller's bootloader license/exception alongside the existing notices.
pyinstaller_dist = distribution("pyinstaller")
for file in pyinstaller_dist.files:
    if str(file).endswith("licenses/COPYING.txt"):
        datas.append((str(pyinstaller_dist.locate_file(file)), "licenses/PyInstaller"))

a = Analysis(
    [str(packaging_dir / "release_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["PyQt5.QtSvg"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide2", "PySide6", "PyQt6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SerialChart",
    debug=False,
    strip=False,
    upx=False,
    console=os.environ.get("SERIALCHART_BUILD_CONSOLE") == "1",
    icon=str(root / "assets" / "icons" / "serialchart_app.ico"),
    contents_directory="_internal",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SerialChart")
