import serial.tools.list_ports
from pyqtgraph.Qt import QtCore, QtWidgets

from serial_comm import SerialCommConfig


BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
DATA_BITS = [5, 6, 7, 8]
PARITY_OPTIONS = [
    ("None", "N"),
    ("Even", "E"),
    ("Odd", "O"),
    ("Mark", "M"),
    ("Space", "S"),
]
STOP_BITS = [1, 1.5, 2]
FLOW_CONTROL_OPTIONS = [
    ("None", "none"),
    ("RTS/CTS", "rtscts"),
    ("XON/XOFF", "xonxoff"),
]


# ========================================================
class PortSettingsDialog(QtWidgets.QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._base_config = config

        self.setWindowTitle("COM Port Settings")
        self.setModal(True)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)

        self._build_ui()
        self._fill_parameter_options()
        self.refresh_ports(config.port)
        self.set_from_config(config)

    # ========================================================
    def _build_ui(self):
        self.port_box = QtWidgets.QComboBox()
        self.refresh_button = QtWidgets.QPushButton("&Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)

        port_layout = QtWidgets.QHBoxLayout()
        port_layout.addWidget(self.port_box, 1)
        port_layout.addWidget(self.refresh_button)

        self.baud_box = QtWidgets.QComboBox()
        self.custom_baud_check = QtWidgets.QCheckBox("Custom")
        self.custom_baud_spin = QtWidgets.QSpinBox()
        self.custom_baud_spin.setRange(1, 2147483647)
        self.custom_baud_spin.setValue(115200)
        self.custom_baud_check.toggled.connect(self._set_custom_baud_enabled)

        custom_baud_layout = QtWidgets.QHBoxLayout()
        custom_baud_layout.addWidget(self.custom_baud_spin, 1)
        custom_baud_layout.addWidget(self.custom_baud_check)

        self.data_bits_box = QtWidgets.QComboBox()
        self.parity_box = QtWidgets.QComboBox()
        self.stop_bits_box = QtWidgets.QComboBox()
        self.flow_control_box = QtWidgets.QComboBox()

        form_layout = QtWidgets.QFormLayout()
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("Port Name ", port_layout)
        form_layout.addRow("Baud Rate ", self.baud_box)
        form_layout.addRow("Custom Rate ", custom_baud_layout)
        form_layout.addRow("Data Bits ", self.data_bits_box)
        form_layout.addRow("Parity ", self.parity_box)
        form_layout.addRow("Stop Bits ", self.stop_bits_box)
        form_layout.addRow("Flow Control ", self.flow_control_box)

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
    def _fill_parameter_options(self):
        self.baud_box.clear()
        for baudrate in BAUD_RATES:
            self.baud_box.addItem(str(baudrate), baudrate)

        self.data_bits_box.clear()
        for data_bits in DATA_BITS:
            self.data_bits_box.addItem(str(data_bits), data_bits)

        self.parity_box.clear()
        for label, parity in PARITY_OPTIONS:
            self.parity_box.addItem(label, parity)

        self.stop_bits_box.clear()
        for stop_bits in STOP_BITS:
            self.stop_bits_box.addItem(str(stop_bits), stop_bits)

        self.flow_control_box.clear()
        for label, flow_control in FLOW_CONTROL_OPTIONS:
            self.flow_control_box.addItem(label, flow_control)

    # ========================================================
    def refresh_ports(self, preferred_port=None):
        if not isinstance(preferred_port, str):
            preferred_port = self.port_box.currentText() or self._base_config.port

        self.port_box.clear()
        tooltip_lines = []

        for info in serial.tools.list_ports.comports():
            self.port_box.addItem(info.device)
            description = info.description or ""
            tooltip_lines.append(f"{info.device} : {description}")

        if preferred_port and self.port_box.findText(preferred_port) < 0:
            self.port_box.addItem(preferred_port)

        if preferred_port:
            self.port_box.setCurrentText(preferred_port)

        self.port_box.setToolTip("\n".join(tooltip_lines))

    # ========================================================
    def set_from_config(self, config):
        self.port_box.setCurrentText(config.port)
        self.custom_baud_spin.setValue(config.baudrate)

        baud_index = self.baud_box.findData(config.baudrate)
        use_custom_baud = baud_index < 0
        self.custom_baud_check.setChecked(use_custom_baud)
        if not use_custom_baud:
            self.baud_box.setCurrentIndex(baud_index)
        self._set_custom_baud_enabled(use_custom_baud)

        self._set_combo_by_data(self.data_bits_box, config.bytesize)
        self._set_combo_by_data(self.parity_box, config.parity)
        self._set_combo_by_data(self.stop_bits_box, config.stopbits)
        self._set_combo_by_data(self.flow_control_box, self._flow_control_from_config(config))

    # ========================================================
    def get_config(self):
        baudrate = self.custom_baud_spin.value()
        if not self.custom_baud_check.isChecked():
            baudrate = self.baud_box.currentData()

        flow_control = self.flow_control_box.currentData()

        return SerialCommConfig(
            port=self.port_box.currentText(),
            baudrate=baudrate,
            timeout=self._base_config.timeout,
            write_timeout=self._base_config.write_timeout,
            bytesize=self.data_bits_box.currentData(),
            parity=self.parity_box.currentData(),
            stopbits=self.stop_bits_box.currentData(),
            xonxoff=flow_control == "xonxoff",
            rtscts=flow_control == "rtscts",
            dsrdtr=self._base_config.dsrdtr,
        )

    # ========================================================
    def _set_custom_baud_enabled(self, checked):
        self.baud_box.setEnabled(not checked)
        self.custom_baud_spin.setEnabled(checked)

    # ========================================================
    def _set_combo_by_data(self, combo_box, data):
        index = combo_box.findData(data)
        if index >= 0:
            combo_box.setCurrentIndex(index)

    # ========================================================
    def _flow_control_from_config(self, config):
        if config.rtscts:
            return "rtscts"
        if config.xonxoff:
            return "xonxoff"
        return "none"
