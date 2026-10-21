# Windows Release Build

Use Windows x64 and 64-bit Python 3.11 (initial build tested with 3.11.4).
The build script creates an isolated `.venv-build`; it does not install packages
into your global Python. Initial setup requires access to the Python package index.
Run the following commands from the project root. Build tools live in `packaging/`;
the runtime `requirements.txt`, `.venv-build`, `build/` and `dist/` remain at the root.

```text
python packaging/build_release.py
```

This installs the pinned runtime/build dependencies, runs unit tests, builds a
PyInstaller onedir executable, and runs an offscreen smoke test of the frozen
application from a different working directory. The smoke test checks icons,
plot/dialog rendering and offline license documents. It never opens a COM port.
Only a successful build and smoke test produces the ZIP and SHA256 file.

After dependencies are installed, an offline rebuild is available:

```text
python packaging/build_release.py --skip-install
```

## Output

```text
dist/
  SerialChart/
    SerialChart.exe
    _internal/
    BUILD_INFO.json
    LICENSE.txt
    COPYRIGHT.txt
    THIRD_PARTY_NOTICES.md
    SOURCE.md
  SerialChart-v<major>.<minor>-windows-x64.zip
  SerialChart-v<major>.<minor>-windows-x64.zip.sha256
```

Version numbers are read from `VERSION_MAJOR` and `VERSION_MINOR` in
`SerialChart.py`; the build never changes them. Each rebuild replaces its onedir
output and same-version ZIP. Keep previous releases elsewhere when needed.
Users must extract the entire ZIP, not copy the EXE alone. Assets, licenses and
native libraries are in `_internal`; their paths do not depend on the launch directory.
Build tools, tests, Python source files and installed fonts are not deliberately
included as release assets. No installer, code signing, automatic upload or file
error logging is implemented by this build.

For a console-enabled diagnostic build (separate output under `dist/console/`):

```text
python packaging/build_release.py --console
```

To invoke PyInstaller manually after installing requirements, run
`.venv-build\Scripts\python.exe -m PyInstaller packaging/SerialChart.spec`.
That bypasses the tests, smoke test, manifest and ZIP creation; use the build script
for release candidates. The `.spec` uses Qt5 only and includes SVG support.

## Before Uploading to GitHub Releases

- Set the intended application version yourself and commit/tag the exact source.
  `BUILD_INFO.json` records HEAD and dirty state; a dirty build is a local test candidate,
  not evidence that the committed source matches the executable.
- Rebuild from that source and test the ZIP on a clean Windows computer without
  Python installed. Check real COM connect/disconnect, TX/RX, Plot, settings and exit.
- Follow `SOURCE.md` for matching project and third-party corresponding source,
  required license documents, and final dependency/native-library notice review.
  A successful build does not certify distribution-license compliance.
- Upload the ZIP, checksum and matching source materials to the intended GitHub
  Release. Nothing in this script creates a tag, commit or remote release.
- Unsigned binaries may trigger Windows/antivirus reputation warnings. Signing
  is a separate future release step, not a requirement for this local build.

The spec follows the PyInstaller spec-file and resource-path conventions:
https://pyinstaller.org/en/stable/spec-files.html
https://pyinstaller.org/en/stable/runtime-information.html
