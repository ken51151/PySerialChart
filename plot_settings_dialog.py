from dataclasses import replace
from html import escape

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from plot_config import LINE_MODES, SEP_MODES, VALUE_MODES, VALUE_CONFIG_TABLE
from plot_preview import build_preview_html, format_bytes


class PlotSettingsDialog(QtWidgets.QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._base_config = config
        self.setWindowTitle("Plot Settings")
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)

        self.ending_radio = QtWidgets.QRadioButton("Ending")
        self.length_radio = QtWidgets.QRadioButton("Fixed Length")
        self.frame_group = QtWidgets.QButtonGroup(self)
        self.frame_group.addButton(self.ending_radio)
        self.frame_group.addButton(self.length_radio)
        self.ending_box = QtWidgets.QComboBox()
        for name, value in (("LF", b"\n"), ("CR", b"\r"), ("CRLF", b"\r\n"), ("Custom HEX", None)):
            label = f"{name} ({' '.join(f'0x{byte:02X}' for byte in value)})" if value else name
            self.ending_box.addItem(label, value)
        self.custom_ending = QtWidgets.QLineEdit(config.separator.hex(" ").upper())
        self._custom_ending_text = self.custom_ending.text()
        self.custom_ending.setToolTip("Ending bytes in hexadecimal, for example: 0D 0A. The ending is removed before parsing.")
        self.ending_ascii = QtWidgets.QLineEdit()
        self.ending_ascii.setReadOnly(True)
        self.ending_ascii.setToolTip("ASCII representation of the ending bytes. Control bytes are shown in brackets.")
        ending_fields = QtWidgets.QHBoxLayout()
        ending_fields.addWidget(self.custom_ending, 1)
        ending_fields.addWidget(QtWidgets.QLabel("ASCII"))
        ending_fields.addWidget(self.ending_ascii, 1)
        self.length_spin = self._spin(1, 2147483647, config.packet_length, " bytes")
        self.line_box = QtWidgets.QComboBox()
        self.line_box.addItem("Single", LINE_MODES.SINGLE_LINE)
        self.line_box.addItem("Multi-line ASCII", LINE_MODES.MULTI_LINE_ASCII)
        self.line_box.setToolTip("Multi-line ASCII expects name = value in each packet.")
        self.value_box = QtWidgets.QComboBox()
        for mode in VALUE_MODES:
            label = mode.name.replace("_", " ")
            if mode == VALUE_MODES.BIN_FLOAT:
                label = "BIN FLOAT32 LE"
            elif mode == VALUE_MODES.BIN_DOUBLE:
                label = "BIN FLOAT64 LE"
            value_type, value_fmt, _ = VALUE_CONFIG_TABLE[mode]
            conversion = f"{value_fmt.__name__}()" if value_type == "ASCII" else value_fmt
            self.value_box.addItem(f"{label} ({conversion})", mode)
        self.offset_spin = self._spin(0, 2147483647, config.offset, " bytes")
        self.offset_spin.setToolTip("Single-line byte offset. ASCII with a nonzero offset reads a 4-byte slice; offset 0 reads the whole packet.")
        self.points_spin = self._spin(1, max(1000000, config.max_points), config.max_points, " pts")
        self.points_spin.setToolTip("Reducing capacity retains the newest points on each existing line.")
        self.lines_spin = self._spin(1, max(100, config.max_lines), config.max_lines)
        self.lines_spin.setToolTip("Limits new lines; existing lines are not removed when the limit is reduced.")

        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.addRow(self.ending_radio, self.ending_box)
        form.addRow("Ending Bytes (HEX)", ending_fields)
        form.addRow(self.length_radio, self.length_spin)
        form.addRow("Line Mode", self.line_box)
        form.addRow("Value Format", self.value_box)
        form.addRow("Offset", self.offset_spin)
        form.addRow("Points per Line", self.points_spin)
        form.addRow("Maximum Lines", self.lines_spin)
        self.error_label = QtWidgets.QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #B3261E;")
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QtWidgets.QLabel("Parsing Preview"))
        self.preview = QtWidgets.QTextBrowser()
        preview_font = QtGui.QFont("Consolas")
        preview_font.setStyleHint(QtGui.QFont.Monospace)
        preview_font.setFixedPitch(True)
        preview_font.setPointSizeF(self.font().pointSizeF())
        self.preview.setFont(preview_font)
        self.preview.document().setDefaultFont(preview_font)
        self.preview.setOpenLinks(False)
        self.preview.setMinimumHeight(250)
        layout.addWidget(self.preview, 1)
        notice = QtWidgets.QLabel("Applying changes preserves existing lines and pauses plotting.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)
        self.setMinimumWidth(580)

        # Qt's QVariant matching does not reliably compare Python bytes in findData().
        ending_index = next((i for i in range(self.ending_box.count())
                             if self.ending_box.itemData(i) == config.separator), 3)
        self.ending_box.setCurrentIndex(ending_index)
        self.line_box.setCurrentIndex(self.line_box.findData(config.line_mode))
        self.value_box.setCurrentIndex(self.value_box.findData(config.value_mode))
        self.ending_radio.setChecked(config.sep_mode == SEP_MODES.CUSTOM_END)
        self.length_radio.setChecked(config.sep_mode == SEP_MODES.LENGTH)
        self.ending_radio.toggled.connect(self._update_controls)
        self.ending_box.currentIndexChanged.connect(self._update_controls)
        self.line_box.currentIndexChanged.connect(self._update_controls)
        self._update_controls()
        self.custom_ending.textChanged.connect(self._remember_custom_ending)
        for signal in (
            self.ending_radio.toggled, self.ending_box.currentIndexChanged,
            self.custom_ending.textChanged, self.length_spin.valueChanged,
            self.line_box.currentIndexChanged, self.value_box.currentIndexChanged,
            self.offset_spin.valueChanged, self.points_spin.valueChanged,
            self.lines_spin.valueChanged,
        ):
            signal.connect(self._update_preview)
        self._update_preview()

    def _update_preview(self):
        self.error_label.clear()
        try:
            ending = self.ending_box.currentData()
            if ending is None:
                ending = bytes.fromhex(self.custom_ending.text())
            self.ending_ascii.setText(format_bytes(ending, False))
        except ValueError:
            self.ending_ascii.setText("Invalid HEX")
        try:
            html = build_preview_html(self.get_config())
        except ValueError as error:
            html = f'<p style="color:#B3261E">{escape(str(error))}</p>'
        self.preview.setHtml(html)

    def _remember_custom_ending(self, text):
        if self.ending_box.currentData() is None:
            self._custom_ending_text = text

    @staticmethod
    def _spin(minimum, maximum, value, suffix=""):
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _update_controls(self):
        use_ending = self.ending_radio.isChecked()
        self.ending_box.setEnabled(use_ending)
        self.custom_ending.setEnabled(use_ending and self.ending_box.currentData() is None)
        ending = self.ending_box.currentData()
        self.custom_ending.setText(self._custom_ending_text if ending is None else ending.hex(" ").upper())
        self.ending_ascii.setEnabled(use_ending)
        self.length_spin.setEnabled(not use_ending)
        multi = self.line_box.currentData() == LINE_MODES.MULTI_LINE_ASCII
        self.offset_spin.setEnabled(not multi)
        self.lines_spin.setEnabled(multi)
        for index in range(self.value_box.count()):
            mode = self.value_box.itemData(index)
            self.value_box.model().item(index).setEnabled(not multi or VALUE_CONFIG_TABLE[mode][0] == "ASCII")
        if multi and VALUE_CONFIG_TABLE[self.value_box.currentData()][0] != "ASCII":
            self.value_box.setCurrentIndex(self.value_box.findData(VALUE_MODES.ASCII_INT))

    def get_config(self):
        separator = self._base_config.separator
        if self.ending_radio.isChecked():
            separator = self.ending_box.currentData()
            if separator is None:
                try:
                    separator = bytes.fromhex(self.custom_ending.text())
                except ValueError:
                    raise ValueError("Ending bytes must be complete HEX pairs, for example 0D 0A.") from None
        config = replace(
            self._base_config,
            sep_mode=SEP_MODES.CUSTOM_END if self.ending_radio.isChecked() else SEP_MODES.LENGTH,
            separator=separator,
            packet_length=self.length_spin.value(),
            line_mode=self.line_box.currentData(),
            value_mode=self.value_box.currentData(),
            offset=self.offset_spin.value(),
            max_points=self.points_spin.value(),
            max_lines=self.lines_spin.value(),
            x_follow_width=min(self._base_config.x_follow_width, self.points_spin.value()),
        )
        config.validate()
        return config

    def accept(self):
        try:
            self.get_config()
        except ValueError as error:
            self.error_label.setText(str(error))
            return
        super().accept()
