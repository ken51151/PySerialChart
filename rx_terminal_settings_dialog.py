from pyqtgraph.Qt import QtCore, QtWidgets

from rx_terminal_config import (
    RX_TERMINAL_TERMINATORS,
    RxTerminalConfig,
    RxTerminalFrameMode,
)


# ========================================================
class RxTerminalSettingsDialog(QtWidgets.QDialog):
    def __init__(self, config, pending_length=0, parent=None):
        super().__init__(parent)
        self._base_config = config

        self.setWindowTitle("RX Terminal Settings")
        self.setModal(True)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)

        self._build_ui(pending_length)
        self.set_from_config(config)

    # ========================================================
    def _build_ui(self, pending_length):
        self.ending_radio = QtWidgets.QRadioButton("Ending")
        self.fixed_length_radio = QtWidgets.QRadioButton("Fixed Length")
        self.ending_radio.toggled.connect(self._update_frame_controls)

        self.ending_box = QtWidgets.QComboBox()
        for name in RX_TERMINAL_TERMINATORS:
            self.ending_box.addItem(name, name)

        self.fixed_length_spin = QtWidgets.QSpinBox()
        self.fixed_length_spin.setRange(1, self._base_config.pending_limit)
        self.fixed_length_spin.setSuffix(" bytes")
        self.fixed_length_spin.setToolTip(
            "Split RX terminal output every N received bytes when Fixed Length is selected."
        )

        self.idle_timeout_spin = QtWidgets.QSpinBox()
        self.idle_timeout_spin.setRange(0, 60000)
        self.idle_timeout_spin.setSuffix(" ms")
        self.idle_timeout_spin.setToolTip(
            "Flush pending RX bytes after this idle time even if no ending or full fixed-length frame arrives."
        )

        self.pending_label = QtWidgets.QLabel(
            f"{pending_length} / {self._base_config.pending_limit} bytes"
        )
        self.pending_label.setToolTip(
            "Current pending RX bytes / maximum pending buffer before forced flush."
        )

        form_layout = QtWidgets.QFormLayout()
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow(self.ending_radio, self.ending_box)
        form_layout.addRow(self.fixed_length_radio, self.fixed_length_spin)
        form_layout.addRow("Idle Flush ", self.idle_timeout_spin)
        form_layout.addRow("Pending Buffer ", self.pending_label)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)

        self.setFixedWidth(320)

    # ========================================================
    def set_from_config(self, config):
        if config.frame_mode == RxTerminalFrameMode.FIXED_LENGTH:
            self.fixed_length_radio.setChecked(True)
        else:
            self.ending_radio.setChecked(True)

        index = self.ending_box.findData(config.terminator_name)
        if index >= 0:
            self.ending_box.setCurrentIndex(index)

        self.fixed_length_spin.setValue(config.fixed_length)
        self.idle_timeout_spin.setValue(config.idle_timeout_ms)
        self._update_frame_controls()

    # ========================================================
    def get_config(self):
        frame_mode = RxTerminalFrameMode.TERMINATOR
        if self.fixed_length_radio.isChecked():
            frame_mode = RxTerminalFrameMode.FIXED_LENGTH

        return RxTerminalConfig(
            display_mode=self._base_config.display_mode,
            frame_mode=frame_mode,
            terminator_name=self.ending_box.currentData(),
            fixed_length=self.fixed_length_spin.value(),
            idle_timeout_ms=self.idle_timeout_spin.value(),
            pending_limit=self._base_config.pending_limit,
        )

    # ========================================================
    def _update_frame_controls(self):
        use_ending = self.ending_radio.isChecked()
        self.ending_box.setEnabled(use_ending)
        self.fixed_length_spin.setEnabled(not use_ending)
