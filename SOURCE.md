# Source and Release Information

Project: https://github.com/ken51151/PySerialChart
Releases: https://github.com/ken51151/PySerialChart/releases
Project license: GPL-3.0-only (see COPYRIGHT.txt and LICENSE.txt).

## Current Status

These documents prepare the source project for distribution. No binary release,
version tag, source archive or reproducible packaging configuration is created
by this change. The repository URL alone is not a version-matched source offer.

## Running the Source

The inspected environment is Windows, Python 3.11.4, with PyQt5 5.15.11,
PyQt5-Qt5 5.15.2, PyQt5-sip 12.18.0, pyqtgraph 0.14.0, NumPy 2.4.6,
pyserial 3.5 and colorama 0.4.6. This is an inventory, not a dependency lockfile.

From a Python environment containing those dependencies:

```text
python SerialChart.py
python -m unittest discover -s tests -v
```

## Binary Release Checklist

Before publishing a Windows onedir ZIP:

1. Record the exact project commit/tag and binary version, without changing
   the version merely to match this document.
2. Publish the matching project source archive alongside the executable download,
   including assets, tests, license documents, dependency versions and build scripts.
3. Provide the complete corresponding source required by the licenses of the
   bundled GPL/LGPL components, including applicable patches and build information.
   An automatically generated archive of this repository does not contain those
   dependencies. Arrange the appropriate version-matched source downloads and
   identify their locations clearly on the release page and in this document.
4. Include this document, LICENSE.txt, COPYRIGHT.txt, THIRD_PARTY_NOTICES.md and
   licenses/ in the binary package; verify that About / Licenses reads them offline.
5. Replace this preparation checklist with the actual release commit, archive
   locations and verified build instructions for that release. Test on a clean
   Windows environment and verify Qt plugin/native-library notices.

Do not describe a future or missing source download as available. Keep each
binary's corresponding source available as required by its applicable licenses.
