from html import escape
from pathlib import Path

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets


RESOURCE_DIR = Path(__file__).resolve().parent
REPOSITORY_URL = "https://github.com/ken51151/PySerialChart"


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, app_name, version, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {app_name}")
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.resize(720, 560)
        self.setMinimumSize(520, 400)

        self.tabs = QtWidgets.QTabWidget()
        about_page = QtWidgets.QWidget()
        about_layout = QtWidgets.QVBoxLayout(about_page)
        heading = QtWidgets.QHBoxLayout()
        icon = QtWidgets.QLabel()
        icon.setFixedSize(72, 72)
        pixmap = QtGui.QPixmap(str(RESOURCE_DIR / "assets" / "icons" / "serialchart_app.png"))
        if not pixmap.isNull():
            icon.setPixmap(pixmap.scaled(64, 64, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        heading.addWidget(icon)
        self.title_label = QtWidgets.QLabel(f"<h2>{escape(app_name)}</h2>Version {escape(str(version))}")
        heading.addWidget(self.title_label, 1)
        about_layout.addLayout(heading)
        self.about_text = QtWidgets.QLabel(
            '<p>Copyright (C) 2026 ken51151</p>'
            '<p><b>GPL-3.0-only</b><br>'
            'You may redistribute and modify this program under version 3 only '
            'of the GNU General Public License.</p>'
            '<p>This program comes WITHOUT ANY WARRANTY, including the implied '
            'warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.</p>'
            f'<p>Source: <a href="{REPOSITORY_URL}">{REPOSITORY_URL}</a></p>'
            '<p>This application uses Qt through PyQt5.<br>'
            'Qt Toolkit: Copyright (C) 2017 The Qt Company Ltd.<br>'
            'Qt LGPL/GPL terms and third-party notices are available in Licenses.</p>'
        )
        self.about_text.setWordWrap(True)
        self.about_text.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.about_text.setOpenExternalLinks(True)
        about_layout.addWidget(self.about_text)
        about_layout.addStretch()
        self.license_button = QtWidgets.QPushButton("View Licenses")
        self.license_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
        self.license_button.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        about_layout.addWidget(self.license_button, 0, QtCore.Qt.AlignLeft)
        self.tabs.addTab(about_page, "About")

        licenses_page = QtWidgets.QWidget()
        licenses_layout = QtWidgets.QVBoxLayout(licenses_page)
        self.license_selector = QtWidgets.QComboBox()
        self.license_selector.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.license_selector.setMinimumContentsLength(24)
        for label, filename in (
            ("Project - GNU GPL v3", "LICENSE.txt"),
            ("Project - Copyright and license notice", "COPYRIGHT.txt"),
            ("Third-party notices", "THIRD_PARTY_NOTICES.md"),
            ("Source and release information", "SOURCE.md"),
        ):
            self.license_selector.addItem(label, RESOURCE_DIR / filename)
        for path in sorted((RESOURCE_DIR / "licenses").rglob("*")):
            if path.is_file():
                self.license_selector.addItem(path.relative_to(RESOURCE_DIR / "licenses").as_posix(), path)
        self.license_text = QtWidgets.QPlainTextEdit()
        self.license_text.setReadOnly(True)
        self.license_text.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        licenses_layout.addWidget(self.license_selector)
        licenses_layout.addWidget(self.license_text, 1)
        self.tabs.addTab(licenses_page, "Licenses")
        self.license_selector.currentIndexChanged.connect(self._load_license)
        self._load_license()

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    def _load_license(self):
        path = self.license_selector.currentData()
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            text = f"Unable to read license document: {path.name}\n{error}\n\nPlease obtain a complete distribution of the application."
        self.license_text.setPlainText(text)
