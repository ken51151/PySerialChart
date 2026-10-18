# pip install PyQt5 pyqtgraph pyserial

import sys
from pathlib import Path
from dataclasses import replace
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from app_config import AppConfig
from serial_comm import apply_serial_config, create_serial_port
from port_settings_dialog import PortSettingsDialog
from plot_window import PlotWindow
from plot_settings_dialog import PlotSettingsDialog
from rx_terminal_config import (
    RxTerminalDisplayMode as RX_TERMINAL_DISPLAY_MODES,
    RxTerminalFrameMode as RX_TERMINAL_FRAME_MODES,
)
from rx_terminal_settings_dialog import RxTerminalSettingsDialog
from serial_tx import (
    TX_WRITE_TIMEOUT,
    TxHistoryComboBox,
    TxController,
)
from serial_rx import RxPlotParser, SerialRxController

WINDOWS_TITLE = 'SerialChart'
VERSION_MAJOR = 0
VERSION_MINOR = 0
VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}"
ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# @@@@@ UI component
UI_FONT_FAMILY = "Microsoft JhengHei UI"
UI_FONT_POINT_DELTA = 2
RX_TERMINAL_FONT_FAMILY = "Cascadia Mono"
RX_TERMINAL_FONT_SIZE = 12

ASCII_CONTROL_NAMES = (
    "NUL", "SOH", "STX", "ETX", "EOT", "ENQ", "ACK", "BEL",
    "BS", "TAB", "LF", "VT", "FF", "CR", "SO", "SI",
    "DLE", "DC1", "DC2", "DC3", "DC4", "NAK", "SYN", "ETB",
    "CAN", "EM", "SUB", "ESC", "FS", "GS", "RS", "US",
)
ASCII_CONTROL_LABELS = {value: f"[{name}]" for value, name in enumerate(ASCII_CONTROL_NAMES)}
ASCII_CONTROL_LABELS[0x7F] = "[DEL]"

# ========================================================
class SerialPlot:
    def __init__(self, config=None):
        self.config = config if config is not None else AppConfig()
        # 初始化 Qt Window
        self.app = QtWidgets.QApplication(sys.argv)
        font = self.app.font()
        font.setFamily(UI_FONT_FAMILY)
        if font.pointSize() > 0:
            font.setPointSize(font.pointSize() + UI_FONT_POINT_DELTA)
        else:
            font.setPointSizeF(font.pointSizeF() + UI_FONT_POINT_DELTA)
        self.app.setFont(font)
        self.main_win = QtWidgets.QMainWindow()
        self.main_win.setWindowTitle(f"{WINDOWS_TITLE} v{VERSION}")
        self.main_win.resize(800, 600)
        self.main_win.closeEvent = self.main_window_close_event
        self.central_widget = QtWidgets.QWidget()
        self.main_win.setCentralWidget(self.central_widget)
        self.layout = QtWidgets.QVBoxLayout(self.central_widget)
        self.rx_terminal_pending = bytearray()
   
        # Toolbar on top
        self.create_toolbar()

        # 傳送控制區
        self.tx_layout = QtWidgets.QHBoxLayout()
        self.tx_layout.setSpacing(12)
        self.tx_label = QtWidgets.QLabel("TX: ")
        self.tx_input = TxHistoryComboBox()
        self.tx_input.setFixedHeight(30)
        self.tx_input.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.tx_input.lineEdit().returnPressed.connect(self.send_tx_input)
        self.combo_tx_line_end = QtWidgets.QComboBox()
        self.combo_tx_line_end.setFixedSize(90, 30)
        self.combo_tx_line_end.addItems(self.config.tx.line_endings.keys())
        self.combo_tx_line_end.setCurrentText('LF (\\n)')
        self.btn_send = QtWidgets.QPushButton("&Send")
        self.btn_send.setFixedSize(80, 30)
        self.btn_send.clicked.connect(self.send_tx_input)
        self.tx_layout.addWidget(self.tx_label, 0)
        self.tx_layout.addWidget(self.tx_input, 1)
        self.tx_layout.addWidget(self.combo_tx_line_end)
        self.tx_layout.addWidget(self.btn_send)
        # self.tx_layout.addStretch()       // add stretch in right side

        # 接收資料顯示區
        self.rx_terminal = QtWidgets.QPlainTextEdit()
        self.rx_terminal.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.rx_terminal.setMinimumHeight(300)
        terminal_font = QtGui.QFont(RX_TERMINAL_FONT_FAMILY, RX_TERMINAL_FONT_SIZE)
        terminal_font.setStyleHint(QtGui.QFont.Monospace)
        self.rx_terminal.setFont(terminal_font)
        self.rx_terminal_flush_timer = QtCore.QTimer()
        self.rx_terminal_flush_timer.setSingleShot(True)
        self.rx_terminal_flush_timer.timeout.connect(self.flush_rx_terminal_pending)

        # 狀態列
        self.com_status_icon = QtWidgets.QLabel("")
        self.tx_status = QtWidgets.QLabel("")
        self.status_bar = QtWidgets.QStatusBar()
        self.status_bar.addWidget(self.com_status_icon)
        self.status_bar.addWidget(self.tx_status, 1)

        # 將元件加入layout
        self.layout.addLayout(self.tx_layout)
        self.layout.addWidget(self.rx_terminal)
        self.main_win.setStatusBar(self.status_bar)

        # others
        print(f"{WINDOWS_TITLE} v{VERSION}")
        self.ser = create_serial_port(self.config.comm)
        plot_config = self.config.plot
        parser_config = self.create_rx_parser_config()
        print(
            f"{parser_config.sep_mode}, {parser_config.line_mode}, "
            f"{parser_config.value_type}, size={parser_config.value_size}, "
            f"offset={parser_config.offset}, SEP=[{parser_config.sep.hex(' ').upper()}], "
            f"Length={parser_config.len_end}"
        )

        self.plot_window = PlotWindow(
            plot_config.max_points,
            plot_config.max_lines,
            plot_config.x_follow_width,
            parser_config.line_mode,
            plot_config.colors,
            plot_config.debug_line_enabled,
        )
        self.plot_window.hidden.connect(self.plot_window_hidden)
        self.plot_window.clear_requested.connect(self.reset_plot_parser)
        self.plot_window.plot_running_changed.connect(self.set_plot_running)
        self.plot_window.settings_requested.connect(self.open_plot_settings_dialog)

        # update timer (validation only; RX uses SerialRxController)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)

        # rx controller
        self.rx_controller = SerialRxController(self.config.rx_interval_ms)
        # PlotWindow owns curve buffers; the main window only routes parsed plot batches.
        self.rx_controller.plot_batch_ready.connect(self.handle_plot_batch)
        self.rx_controller.stopped.connect(self.update_plot_settings_enabled)
        self.rx_controller.raw_received.connect(self.handle_terminal_raw_rx)
        self.rx_controller.failed.connect(self.rx_failed)
        self.rx_controller.set_terminal_enabled(True)

        # tx controller
        self.tx_controller = TxController(self.config.tx)
        self.tx_controller.started.connect(self.tx_started)
        self.tx_controller.finished.connect(self.tx_finished)
        self.tx_controller.failed.connect(self.tx_failed)
        self.tx_controller.rejected.connect(self.tx_status.setText)
        self.disconnect_serial()

# ========================================================
# ========================================================        
# ========================================================
    def create_toolbar(self):
        self.main_toolbar = QtWidgets.QToolBar("Main", self.main_win)
        self.main_toolbar.setIconSize(QtCore.QSize(52, 52))
        self.main_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.main_toolbar.setStyleSheet("QToolButton { font-size: 9pt; }")
        self.main_win.addToolBar(QtCore.Qt.TopToolBarArea, self.main_toolbar)

        self.icon_connect = QtGui.QIcon(str(ICON_DIR / "connected.svg"))
        self.icon_disconnect = QtGui.QIcon(str(ICON_DIR / "disconnected.svg"))
        self.rx_display_mode_icons = {
            RX_TERMINAL_DISPLAY_MODES.ASCII: QtGui.QIcon(str(ICON_DIR / "rx_mode_ascii_256.png")),
            RX_TERMINAL_DISPLAY_MODES.ASCII_HEX: QtGui.QIcon(str(ICON_DIR / "rx_mode_ascii_hex_256.png")),
            RX_TERMINAL_DISPLAY_MODES.HEX: QtGui.QIcon(str(ICON_DIR / "rx_mode_hex_256.png")),
        }

        self.action_connect_toggle = QtWidgets.QAction(
            self.icon_disconnect, "Disconnected", self.main_win
        )
        self.action_com_setting = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "com_setting.svg")), "COM", self.main_win
        )
        self.action_plot = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "plot.svg")), "Plot", self.main_win
        )
        self.action_rx_display_mode = QtWidgets.QAction(
            self.rx_display_mode_icons[self.config.terminal.display_mode],
            "RxMode",
            self.main_win,
        )
        self.action_clear = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "clear.svg")), "Clear", self.main_win
        )
        self.action_close = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "close.svg")), "Close", self.main_win
        )

        self.action_connect_toggle.setToolTip("Disconnected")
        self.action_com_setting.setToolTip("COM Port Settings")
        self.action_plot.setToolTip("Show Plot")
        self.update_rx_display_mode_action()
        self.action_clear.setToolTip("Clear Terminal")
        self.action_close.setToolTip("Close Application")
        self.action_clear.setEnabled(True)

        self.action_connect_toggle.triggered.connect(self.toggle_serial_connection)
        self.action_com_setting.triggered.connect(self.open_port_settings_dialog)
        self.action_plot.triggered.connect(self.show_plot_window)
        self.action_rx_display_mode.triggered.connect(self.cycle_rx_display_mode)
        self.action_clear.triggered.connect(self.clear_terminal)
        self.action_close.triggered.connect(self.close_application)

        self.main_toolbar.addAction(self.action_connect_toggle)
        self.main_toolbar.addAction(self.action_com_setting)
        self.main_toolbar.addAction(self.action_plot)
        self.create_rx_display_tool_button()
        self.main_toolbar.addAction(self.action_clear)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.action_close)
        self.set_toolbar_button_widths()

# ========================================================
    def create_rx_display_tool_button(self):
        self.rx_display_menu = QtWidgets.QMenu(self.main_win)
        self.rx_display_action_group = QtWidgets.QActionGroup(self.main_win)
        self.rx_display_action_group.setExclusive(True)
        self.rx_display_actions = {}

        for mode in RX_TERMINAL_DISPLAY_MODES:
            action = QtWidgets.QAction(self.rx_display_mode_label(mode), self.main_win)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, selected=mode: self.set_rx_display_mode(selected))
            self.rx_display_action_group.addAction(action)
            self.rx_display_menu.addAction(action)
            self.rx_display_actions[mode] = action

        self.rx_display_menu.addSeparator()
        self.action_rx_terminal_settings = QtWidgets.QAction("Frame Settings...", self.main_win)
        self.action_rx_terminal_settings.triggered.connect(self.open_rx_terminal_settings_dialog)
        self.rx_display_menu.addAction(self.action_rx_terminal_settings)

        self.rx_display_tool_button = QtWidgets.QToolButton(self.main_win)
        self.rx_display_tool_button.setDefaultAction(self.action_rx_display_mode)
        self.rx_display_tool_button.setMenu(self.rx_display_menu)
        self.rx_display_tool_button.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.rx_display_tool_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.main_toolbar.addWidget(self.rx_display_tool_button)
        self.update_rx_terminal_menu_actions()

# ========================================================
    def set_toolbar_button_widths(self):
        button_widths = {
            self.action_connect_toggle: 120,
            self.action_com_setting: 90,
            self.action_plot: 90,
            self.action_clear: 90,
            self.action_close: 90,
        }

        for action, width in button_widths.items():
            button = self.main_toolbar.widgetForAction(action)
            if button:
                button.setFixedWidth(width)
                button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)

        self.rx_display_tool_button.setFixedWidth(100)
        self.rx_display_tool_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)

# ========================================================
    def update_toolbar_actions(self, connected):
        if connected:
            self.action_connect_toggle.setText("Connected")
            self.action_connect_toggle.setIcon(self.icon_connect)
            self.action_connect_toggle.setToolTip("Connected")
        else:
            self.action_connect_toggle.setText("Disconnected")
            self.action_connect_toggle.setIcon(self.icon_disconnect)
            self.action_connect_toggle.setToolTip("Disconnected")

        self.action_com_setting.setEnabled(not connected)

# ========================================================
    def rx_display_mode_label(self, mode=None):
        mode = self.config.terminal.display_mode if mode is None else mode
        if mode == RX_TERMINAL_DISPLAY_MODES.ASCII_HEX:
            return "ASCII+HEX"
        if mode == RX_TERMINAL_DISPLAY_MODES.HEX:
            return "HEX"
        return "ASCII"

# ========================================================
    def update_rx_display_mode_action(self):
        label = self.rx_display_mode_label()
        self.action_rx_display_mode.setText("RxMode")
        self.action_rx_display_mode.setIcon(
            self.rx_display_mode_icons[self.config.terminal.display_mode]
        )
        self.action_rx_display_mode.setToolTip(f"RX Display: {label}, {self.rx_terminal_frame_label()}")

# ========================================================
    def update_rx_terminal_menu_actions(self):
        self.rx_display_actions[self.config.terminal.display_mode].setChecked(True)

# ========================================================
    def cycle_rx_display_mode(self):
        next_value = (int(self.config.terminal.display_mode) + 1) % len(RX_TERMINAL_DISPLAY_MODES)
        self.set_rx_display_mode(RX_TERMINAL_DISPLAY_MODES(next_value))

# ========================================================
    def set_rx_display_mode(self, mode):
        self.flush_rx_terminal_pending()
        self.config.terminal = replace(self.config.terminal, display_mode=mode)
        self.update_rx_display_mode_action()
        self.update_rx_terminal_menu_actions()
        self.tx_status.setText(f"RX display: {self.rx_display_mode_label()}")

# ========================================================
    def apply_rx_terminal_config(self, config):
        self.flush_rx_terminal_pending()
        self.config.terminal = config
        self.update_rx_display_mode_action()
        self.update_rx_terminal_menu_actions()
        self.tx_status.setText(f"RX frame: {self.rx_terminal_frame_label()}")

# ========================================================
    def open_rx_terminal_settings_dialog(self):
        dialog = RxTerminalSettingsDialog(
            self.config.terminal,
            len(self.rx_terminal_pending),
            self.main_win,
        )
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.apply_rx_terminal_config(dialog.get_config())

# ========================================================
    def rx_terminal_frame_label(self):
        if self.config.terminal.frame_mode == RX_TERMINAL_FRAME_MODES.FIXED_LENGTH:
            return f"Fixed {self.config.terminal.fixed_length}"
        return f"Ending {self.config.terminal.terminator_name}"

# ========================================================
    def show_plot_window(self):
        if not self.plot_window.isVisible():
            self.plot_window.move(self.main_win.x() + 120, self.main_win.y() + 120)
        self.plot_window.show()
        self.plot_window.raise_()
        self.plot_window.activateWindow()

    def can_edit_plot_settings(self):
        # Wait for controller cleanup as well as COM close; stop() has a bounded wait.
        return not self.ser.is_open and self.rx_controller.thread is None

    def update_plot_settings_enabled(self):
        self.plot_window.set_settings_enabled(self.can_edit_plot_settings())

    def open_plot_settings_dialog(self):
        if not self.can_edit_plot_settings():
            return
        dialog = PlotSettingsDialog(self.config.plot, self.plot_window)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.apply_plot_config(dialog.get_config())

    def apply_plot_config(self, config):
        if not self.can_edit_plot_settings():
            return False
        try:
            config.validate()
        except ValueError as error:
            self.tx_status.setText(str(error))
            return False
        if config == self.config.plot:
            return True
        self.plot_window.apply_config(config)
        self.config.plot = config
        self.tx_status.setText("Plot settings applied; existing lines preserved")
        return True

    def handle_plot_batch(self, batch):
        # Discard queued batches from a closed connection.
        if self.ser.is_open:
            self.plot_window.update_plot_batch(batch)

# ========================================================
    def plot_window_hidden(self):
        pass

# ========================================================
    def set_plot_running(self, running):
        self.rx_controller.set_plot_enabled(running)

# ========================================================
    def reset_plot_parser(self):
        self.rx_controller.reset_plot_parser()

# ========================================================
    def toggle_serial_connection(self):
        if self.ser.is_open:
            self.disconnect_serial()
        else:
            self.connect_serial()

# ========================================================
    def close_application(self):
        self.main_win.close()

# ========================================================
    def main_window_close_event(self, event):
        if self.ser.is_open:
            self.disconnect_serial()
        self.plot_window.hide()
        event.accept()

# ========================================================
    def apply_comm_config(self, config):
        if self.ser.is_open:
            self.tx_status.setText("Close COM before changing settings")
            return False

        try:
            apply_serial_config(self.ser, config)
        except Exception as e:
            print(f"COM config error: {e}")
            self.tx_status.setText("COM config error")
            return False

        self.config.comm = config
        self.tx_status.setText(f"{config.port}, {config.baudrate}")
        return True

# ========================================================
    def open_port_settings_dialog(self):
        if self.ser.is_open:
            self.tx_status.setText("Close COM before changing settings")
            return

        dialog = PortSettingsDialog(self.config.comm, self.main_win)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.apply_comm_config(dialog.get_config())

# ========================================================
    def send_tx_input(self):
        text = self.tx_input.currentText()
        line_end = self.config.tx.line_endings[self.combo_tx_line_end.currentText()]
        self.tx_controller.send(self.ser, text, line_end)

# ========================================================
    def apply_tx_config(self, config):
        self.config.tx = config
        current_line_end = self.combo_tx_line_end.currentText()
        self.combo_tx_line_end.clear()
        self.combo_tx_line_end.addItems(config.line_endings.keys())
        if current_line_end in config.line_endings:
            self.combo_tx_line_end.setCurrentText(current_line_end)
        elif config.line_endings:
            self.combo_tx_line_end.setCurrentIndex(0)

        self.tx_controller.apply_config(config)

# ========================================================
    def tx_started(self, is_hex):
        self.btn_send.setEnabled(False)
        self.tx_status.setText("Sending HEX..." if is_hex else "Sending...")

# ========================================================
    def tx_finished(self, bytes_sent, total_bytes, text):
        if self.ser.is_open:
            self.btn_send.setEnabled(True)
        status_prefix = "Queued" if TX_WRITE_TIMEOUT == 0 else "Sent"
        self.tx_status.setText(f"{status_prefix} {bytes_sent}/{total_bytes} bytes")
        self.flush_rx_terminal_pending()
        self.append_terminal_text(f">> {text}\n")
        self.tx_input.remember(text)

# ========================================================
    def tx_failed(self, status, detail, text):
        if self.ser.is_open:
            self.btn_send.setEnabled(True)
        self.tx_status.setText(f"{status}: {text}")
        print(detail)

# ========================================================
# ========================================================
# ========================================================
    def handle_terminal_raw_rx(self, raw_rx):
        self.rx_terminal_pending.extend(raw_rx)
        text = self.take_complete_rx_terminal_frames()
        if text:
            self.append_terminal_text(text)

        if self.rx_terminal_pending:
            if len(self.rx_terminal_pending) >= self.config.terminal.pending_limit:
                self.flush_rx_terminal_pending()
            else:
                self.rx_terminal_flush_timer.start(self.config.terminal.idle_timeout_ms)
        else:
            self.rx_terminal_flush_timer.stop()

    def clear_terminal(self):
        self.rx_terminal_flush_timer.stop()
        self.rx_terminal_pending.clear()
        self.rx_terminal.clear()

    def append_terminal_text(self, text):
        cursor = self.rx_terminal.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        self.rx_terminal.setTextCursor(cursor)
        self.rx_terminal.ensureCursorVisible()

    def take_complete_rx_terminal_frames(self):
        if self.config.terminal.frame_mode == RX_TERMINAL_FRAME_MODES.FIXED_LENGTH:
            return self.take_fixed_length_rx_terminal_frames()
        return self.take_terminator_rx_terminal_frames()

    def take_terminator_rx_terminal_frames(self):
        output = []
        terminator = self.config.terminal.terminator
        terminator_len = len(terminator)

        while True:
            index = self.rx_terminal_pending.find(terminator)
            if index < 0:
                break

            end = index + terminator_len
            output.append(self.format_rx_terminal_line(bytes(self.rx_terminal_pending[:end])))
            del self.rx_terminal_pending[:end]

        return "".join(output)

    def take_fixed_length_rx_terminal_frames(self):
        output = []
        length = self.config.terminal.fixed_length

        while len(self.rx_terminal_pending) >= length:
            output.append(self.format_rx_terminal_line(bytes(self.rx_terminal_pending[:length])))
            del self.rx_terminal_pending[:length]

        return "".join(output)

    def flush_rx_terminal_pending(self):
        if not self.rx_terminal_pending:
            return

        self.rx_terminal_flush_timer.stop()
        text = self.format_rx_terminal_line(bytes(self.rx_terminal_pending))
        self.rx_terminal_pending.clear()
        self.append_terminal_text(text)

    def format_rx_terminal_line(self, raw_rx):
        if self.config.terminal.display_mode == RX_TERMINAL_DISPLAY_MODES.ASCII_HEX:
            return f"ASCII: {self.format_rx_ascii(raw_rx, preserve_layout=False)} | HEX: {self.format_rx_hex(raw_rx)}\n"

        if self.config.terminal.display_mode == RX_TERMINAL_DISPLAY_MODES.HEX:
            return f"HEX: {self.format_rx_hex(raw_rx)}\n"

        if self.config.terminal.frame_mode == RX_TERMINAL_FRAME_MODES.FIXED_LENGTH:
            return f"{self.format_rx_ascii(raw_rx, preserve_layout=True)}\n"

        return self.format_rx_ascii(raw_rx, preserve_layout=True)

    def format_rx_ascii(self, raw_rx, preserve_layout):
        text_parts = []
        for value in raw_rx:
            if 0x20 <= value <= 0x7E:
                text_parts.append(chr(value))
            elif preserve_layout and value in (0x09, 0x0A, 0x0D):
                text_parts.append(chr(value))
            else:
                text_parts.append(ASCII_CONTROL_LABELS.get(value, f"[0x{value:02X}]"))
        return "".join(text_parts)

    def format_rx_hex(self, raw_rx):
        return raw_rx.hex(" ").upper()

# ========================================================
# ========================================================
# ========================================================
    def create_rx_plot_parser(self):
        config = self.create_rx_parser_config()
        return RxPlotParser(
            config.sep_mode,
            config.line_mode,
            config.value_type,
            config.value_fmt,
            config.value_size,
            config.sep,
            config.len_end,
            config.offset,
        )
# ========================================================
    def create_rx_parser_config(self):
        return self.config.plot.to_parser_config()
# ========================================================
    def rx_failed(self, message):
        print(message)
        self.disconnect_serial("RX failed")
# ========================================================
    def update(self):
        self.plot_window.update_validation_data()

# ========================================================
    # ----- Start/Stop
    def connect_serial(self):
        if self.ser.is_open:
            return
        if self.rx_controller.thread is not None:
            self.tx_status.setText("Waiting for RX to stop")
            return

        self.plot_window.clear_data()
        if self.config.plot.debug_line_enabled:
            self.timer.start(self.config.rx_interval_ms)

        try:
            apply_serial_config(self.ser, self.config.comm)
            self.ser.open()
            self.ser.reset_input_buffer()
            self.rx_controller.start(self.ser, self.create_rx_plot_parser())
        except Exception as e:
            print(f"COM open error: {e}")
            self.timer.stop()
            if self.ser.is_open:
                self.ser.close()
            self.set_connected_ui(False, "COM open error")
            return

        self.set_connected_ui(True)

    def disconnect_serial(self, status_text="COM closed"):
        self.timer.stop()
        self.rx_controller.stop()
        if self.ser.is_open:
            self.ser.close()
        self.set_connected_ui(False, status_text)

    def set_connected_ui(self, connected, status_text=None):
        self.tx_input.setEnabled(connected)
        self.combo_tx_line_end.setEnabled(connected)
        self.btn_send.setEnabled(connected)
        self.update_toolbar_actions(connected)
        self.update_plot_settings_enabled()
        self.com_status_icon.setText("🟢" if connected else "🔴")
        if status_text is None:
            status_text = "COM opened" if connected else "COM closed"
        self.tx_status.setText(status_text)


# ========================================================
    def run(self):
        self.main_win.show()
        sys.exit(self.app.exec())
# ========================================================
# ========================================================
if __name__ == "__main__":
    w = SerialPlot()
    w.run()
# ========================================================
