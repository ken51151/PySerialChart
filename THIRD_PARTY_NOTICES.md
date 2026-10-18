# Third-Party Notices

SerialChart is licensed under GPL-3.0-only. Its dependencies retain their
own licenses and copyrights; they are not relicensed by this project.

This inventory records the development environment inspected on 2026-10-18.
It is not a manifest of a completed executable release. Refresh it against
the exact build environment before distributing a binary.

| Component | Inspected version | License / local document |
| --- | --- | --- |
| Python | 3.11.4 | PSF license and bundled notices: licenses/Python/LICENSE.txt |
| PyQt5 | 5.15.11 | GPL v3; LICENSE.txt and licenses/PyQt5/NOTICE.txt |
| Qt (PyQt5-Qt5 wheel) | 5.15.2 | LGPL v3, GPL v3 and component-specific terms: licenses/Qt/LICENSE |
| PyQt5-sip | 12.18.0 | BSD-2-Clause: licenses/PyQt5-sip/licenses/LICENSE |
| pyqtgraph | 0.14.0 | MIT: licenses/pyqtgraph/licenses/LICENSE.txt; CET data notice in licenses/pyqtgraph/CET-colormaps.txt |
| NumPy | 2.4.6 | BSD-3-Clause and bundled component notices: licenses/NumPy/licenses/ |
| pyserial | 3.5 | BSD-3-Clause: licenses/pyserial/LICENSE.txt |
| colorama | 0.4.6 | BSD-3-Clause: licenses/colorama/licenses/LICENSE.txt |

## Qt and PyQt

This application uses the Qt GUI Toolkit through PyQt5.
The Qt Toolkit is Copyright (C) 2017 The Qt Company Ltd., as stated in
the inspected Qt wheel's notice. Qt and its use are covered by the
applicable LGPL/GPL terms; the full texts are included in licenses/Qt/LICENSE
and LICENSE.txt. Qt's third-party components may carry additional terms.

PyQt5 is Copyright (c) 2024 Riverbank Computing Limited, as stated in the
installed PyQt5 package. This project uses PyQt5 under GPL v3, not a
Riverbank commercial license. See licenses/PyQt5/NOTICE.txt.

## Provenance

- LICENSE.txt: https://www.gnu.org/licenses/gpl-3.0.txt (verbatim).
- pyserial: https://raw.githubusercontent.com/pyserial/pyserial/v3.5/LICENSE.txt (verbatim).
- PyQt5 notice: header of the installed PyQt5/__init__.py.
- Other documents: copied verbatim from the versions listed above, including
  Python's installation license, package distribution license files and
  pyqtgraph's CET color-map notice. NumPy's notices include bundled OpenBLAS,
  LAPACK and other components; retain the full documents, not just the BSD summary.

## Before Binary Distribution

Include LICENSE.txt, COPYRIGHT.txt, this file, SOURCE.md and the full licenses/
directory in the release. Make them available to the About / Licenses dialog
at the same resource-relative paths used by the source checkout.

Audit the actual bundled Qt modules/plugins, Python components, NumPy native
libraries, packaging runtime and any system redistributables. Add their required
notices and source provisions. The documents collected here do not replace
that final audit or the obligation to provide corresponding source where required.
Do not bundle installed fonts merely because the UI uses their family names.

Use SOURCE.md as the release checklist for version-matched source and build files.
