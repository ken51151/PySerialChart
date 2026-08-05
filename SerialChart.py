# pip install PyQt5 pyqtgraph pyserial

import sys
from pathlib import Path
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from enum import IntEnum
from serial_comm import SerialCommConfig, apply_serial_config, create_serial_port
from port_settings_dialog import PortSettingsDialog
from plot_window import PlotWindow
from serial_tx import (
    DEFAULT_TX_CONFIG,
    TX_WRITE_TIMEOUT,
    TxConfig,
    TxHistoryComboBox,
    TxController,
)
from serial_rx import RxParserConfig, RxPlotParser, SerialRxController

DEBUG_LINE_ENABLE = False       # Add debug line(sin wave) while running
WINDOWS_TITLE = 'SerialChart'
VERSION_MAJOR = 0
VERSION_MINOR = 0
VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}"
ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# ===== Serial 設定 =====
PORT = "COM6"
BAUD = 115200

# ===== 圖表/接收模式設定 =====
MAX_POINTS = 50000              # curve ring buffer size
MAX_LINES = 10                  # max curve (only multi line mode)
UPDATE_INTERVAL = 30            # update interval [ms]

# @@@@@ 資料分段方式, 特定資料 or 固定長度
class SEP_MODES(IntEnum):
    CUSTOM_END = 1          # 特定資料分段, 常用在ASCII格式, 可搭配binary使用，但注意數值可能跟結尾符相撞
    LENGTH = 2              # 固定長度分段, 常用在binary格式
SEP_MODE = SEP_MODES.CUSTOM_END

# @@@@@ 線段模式
class LINE_MODES(IntEnum):
    SINGLE_LINE = 1         # 單線段模式, 通常無冗餘資料, 效率上最高
    MULTI_LINE_ASCII = 2    # 多線段模式, 會將各封包再次分析在匹配到各線段, ASCII資料格式為 "<name> = <value>", 最多10條
LINE_MODE = LINE_MODES.MULTI_LINE_ASCII
colors = ['y', 'g', 'r', 'c', 'm', 'w', 'b', (255,165,0), (128,0,128), (0,255,127)]

# @@@@@ 數值處理方式, ASCII or binary
class VALUE_MODES(IntEnum):
    # ASCII
    ASCII_INT = 1           # ASCII interger
    ASCII_FLOAT = 2         # ASCII float
    # binary with Little-endian
    BIN_U8 = 10
    BIN_I8 = 11
    BIN_U16_LE = 12
    BIN_I16_LE = 13
    BIN_U32_LE = 14
    BIN_I32_LE = 15
    BIN_U64_LE = 16
    BIN_I64_LE = 17
    # binary with big-endian
    BIN_U16_BE = 20
    BIN_I16_BE = 21
    BIN_U32_BE = 22
    BIN_I32_BE = 23
    BIN_U64_BE = 24
    BIN_I64_BE = 25
    # binary float/double (IEEE 754)
    BIN_FLOAT  = 40
    BIN_DOUBLE = 41
VALUE_MODE = VALUE_MODES.ASCII_INT

# @@@@@ 特定資料分段設定
ASCII_CR = "\r"             # CR: 0x0D, Carriage Return
ASCII_LF = "\n"             # LF: 0x0A, Line Feed
ASCII_CRLR = "\r\n"         # CRLF: [0D,0A]
CUSTOM_END = ASCII_LF       # 僅在CUSTOM_END模式下有效, 特定資料進行分段

# @@@@@ 固定長度分段設定
LEN_END = 5                 # 僅在LENGTH模式下有效

# @@@@@ General Setting
VAL_OFFSET = 0              # 數值分段後的固定位移, 除了MULTI_LINE_ASCII以外的所有模式都會受影響, 不會檢查是否溢出
SEP = CUSTOM_END.encode()   # 預先計算分隔符避免即時運算的花費


# @@@@@ UI component
X_FOLLOW_WIDTH_DEFAULT = 2000   # default X width while following latest data
UI_FONT_FAMILY = "Microsoft JhengHei UI"
UI_FONT_POINT_DELTA = 2
RX_TERMINAL_FONT_FAMILY = "Cascadia Mono"
RX_TERMINAL_FONT_SIZE = 12

# --------------------------------------------------------
# table for value mode
VALUE_CONFIG_TABLE = {
    VALUE_MODES.ASCII_INT:  ('ASCII', int,   4),    # ASCII mode
    VALUE_MODES.ASCII_FLOAT:('ASCII', float, 4),
	VALUE_MODES.BIN_U8:     ('BIN', '<B',  1),    # binary mode
    VALUE_MODES.BIN_I8:     ('BIN', '<b',  1),
    VALUE_MODES.BIN_U16_LE: ('BIN', '<H',  2),
    VALUE_MODES.BIN_I16_LE: ('BIN', '<h',  2),
    VALUE_MODES.BIN_U32_LE: ('BIN', '<I',  4),
    VALUE_MODES.BIN_I32_LE: ('BIN', '<i',  4),
    VALUE_MODES.BIN_U64_LE: ('BIN', '<Q',  8),
    VALUE_MODES.BIN_I64_LE: ('BIN', '<q',  8),
    VALUE_MODES.BIN_U16_BE: ('BIN', '>H',  2),
    VALUE_MODES.BIN_I16_BE: ('BIN', '>h',  2),
    VALUE_MODES.BIN_U32_BE: ('BIN', '>I',  4),
    VALUE_MODES.BIN_I32_BE: ('BIN', '>i',  4),
    VALUE_MODES.BIN_U64_BE: ('BIN', '>Q',  8),
    VALUE_MODES.BIN_I64_BE: ('BIN', '>q',  8),
    VALUE_MODES.BIN_FLOAT:  ('BIN', '<f',  4),
    VALUE_MODES.BIN_DOUBLE: ('BIN', '<d',  8),
}
# ========================================================
class SerialPlot:
    def __init__(self):
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
        self.comm_config = self.create_comm_config()
        self.tx_config = self.create_tx_config()
   
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
        self.combo_tx_line_end.addItems(self.tx_config.line_endings.keys())
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
        info = ""
        offset = VAL_OFFSET
        self.ser = create_serial_port(self.comm_config)
        if   SEP_MODE == SEP_MODES.CUSTOM_END:          self.rx_sep_mode = "custom_end"         ; info += "特定資料分段模式"
        elif SEP_MODE == SEP_MODES.LENGTH:              self.rx_sep_mode = "length"             ; info += "固定長度分段模式"
        else:                                           print('ERROR, invalid SEP_MODE!!!')     ; info += "!!! 模式錯誤 !!!"

        if   LINE_MODE == LINE_MODES.SINGLE_LINE:
            info += ", 單線段模式"
            self.rx_line_mode = "single"
        elif LINE_MODE == LINE_MODES.MULTI_LINE_ASCII:
            info += ", 多線段ASCII模式"
            self.rx_line_mode = "multi_ascii"
        else:
            info += "!!! 線段設定錯誤 !!!"  
            print('ERROR, invalid LINE_MODE!!!')
        
        if VALUE_MODE in VALUE_CONFIG_TABLE:
            self.rx_value_type, self.rx_value_fmt, self.rx_value_size = VALUE_CONFIG_TABLE[VALUE_MODE]
            if self.rx_value_type == 'ASCII':
                info += " + {}, size={}, offset={}, SEP=[{}]".format(self.rx_value_type, self.rx_value_size, offset, SEP.hex(' ').upper())
            else:
                info += " + {}, size={}, offset={}, Length={}".format(self.rx_value_type, self.rx_value_size, offset, LEN_END)
        else:
            print('ERROR, invalid VALUE_MODE!!!')
            self.rx_value_type, self.rx_value_fmt, self.rx_value_size = ('ASCII', int, 4)
        print(info)

        self.plot_window = PlotWindow(
            MAX_POINTS,
            MAX_LINES,
            X_FOLLOW_WIDTH_DEFAULT,
            self.rx_line_mode,
            colors,
            DEBUG_LINE_ENABLE,
        )
        self.plot_window.hidden.connect(self.plot_window_hidden)
        self.plot_window.clear_requested.connect(self.reset_plot_parser)
        self.plot_window.plot_running_changed.connect(self.set_plot_running)

        # update timer (validation only; RX uses SerialRxController)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)

        # rx controller
        self.rx_controller = SerialRxController(UPDATE_INTERVAL)
        # PlotWindow owns curve buffers; the main window only routes parsed plot batches.
        self.rx_controller.plot_batch_ready.connect(self.plot_window.update_plot_batch)
        self.rx_controller.raw_received.connect(self.handle_terminal_raw_rx)
        self.rx_controller.failed.connect(self.rx_failed)
        self.rx_controller.set_terminal_enabled(True)

        # tx controller
        self.tx_controller = TxController(self.tx_config)
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
        self.main_toolbar.setIconSize(QtCore.QSize(40, 40))
        self.main_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.main_toolbar.setStyleSheet("QToolButton { font-size: 9pt; }")
        self.main_win.addToolBar(QtCore.Qt.TopToolBarArea, self.main_toolbar)

        self.icon_connect = QtGui.QIcon(str(ICON_DIR / "connected.svg"))
        self.icon_disconnect = QtGui.QIcon(str(ICON_DIR / "disconnected.svg"))

        self.action_connect_toggle = QtWidgets.QAction(
            self.icon_disconnect, "Connect", self.main_win
        )
        self.action_com_setting = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "com_setting.svg")), "COM", self.main_win
        )
        self.action_plot = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "plot.svg")), "Plot", self.main_win
        )
        self.action_clear = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "clear.svg")), "Clear", self.main_win
        )
        self.action_close = QtWidgets.QAction(
            QtGui.QIcon(str(ICON_DIR / "close.svg")), "Close", self.main_win
        )

        self.action_connect_toggle.setToolTip("Connect")
        self.action_com_setting.setToolTip("COM Port Settings")
        self.action_plot.setToolTip("Show Plot")
        self.action_clear.setToolTip("Clear")
        self.action_close.setToolTip("Close Application")
        self.action_clear.setEnabled(False)

        self.action_connect_toggle.triggered.connect(self.toggle_serial_connection)
        self.action_com_setting.triggered.connect(self.open_port_settings_dialog)
        self.action_plot.triggered.connect(self.show_plot_window)
        self.action_close.triggered.connect(self.close_application)

        self.main_toolbar.addAction(self.action_connect_toggle)
        self.main_toolbar.addAction(self.action_com_setting)
        self.main_toolbar.addAction(self.action_plot)
        self.main_toolbar.addAction(self.action_clear)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.action_close)
        self.set_toolbar_button_widths()

# ========================================================
    def set_toolbar_button_widths(self):
        button_widths = {
            self.action_connect_toggle: 100,
            self.action_com_setting: 60,
            self.action_plot: 60,
            self.action_rx_display_mode: 90,
            self.action_clear: 60,
            self.action_close: 60,
        }

        for action, width in button_widths.items():
            button = self.main_toolbar.widgetForAction(action)
            if button:
                button.setFixedWidth(width)
                button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)

# ========================================================
    def update_toolbar_actions(self, connected):
        if connected:
            self.action_connect_toggle.setText("Disconnect")
            self.action_connect_toggle.setIcon(self.icon_connect)
            self.action_connect_toggle.setToolTip("Disconnect")
        else:
            self.action_connect_toggle.setText("Connect")
            self.action_connect_toggle.setIcon(self.icon_disconnect)
            self.action_connect_toggle.setToolTip("Connect")

        self.action_com_setting.setEnabled(not connected)

# ========================================================
    def show_plot_window(self):
        if not self.plot_window.isVisible():
            self.plot_window.move(self.main_win.x() + 120, self.main_win.y() + 120)
        self.plot_window.show()
        self.plot_window.raise_()
        self.plot_window.activateWindow()

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
    def create_comm_config(self):
        return SerialCommConfig(
            port=PORT,
            baudrate=BAUD,
            timeout=0.1,
            write_timeout=TX_WRITE_TIMEOUT,
        )

# ========================================================
    def apply_comm_config(self, config):
        if self.ser.is_open:
            self.tx_status.setText("Close COM before changing settings")
            return False

        self.comm_config = config
        try:
            apply_serial_config(self.ser, config)
        except Exception as e:
            print(f"COM config error: {e}")
            self.tx_status.setText("COM config error")
            return False

        self.tx_status.setText(f"{config.port}, {config.baudrate}")
        return True

# ========================================================
    def open_port_settings_dialog(self):
        if self.ser.is_open:
            self.tx_status.setText("Close COM before changing settings")
            return

        dialog = PortSettingsDialog(self.comm_config, self.main_win)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.apply_comm_config(dialog.get_config())

# ========================================================
    def send_tx_input(self):
        text = self.tx_input.currentText()
        line_end = self.tx_config.line_endings[self.combo_tx_line_end.currentText()]
        self.tx_controller.send(self.ser, text, line_end)

# ========================================================
    def create_tx_config(self):
        return TxConfig(
            line_endings=DEFAULT_TX_CONFIG.line_endings,
            prefix_enabled=DEFAULT_TX_CONFIG.prefix_enabled,
        )

# ========================================================
    def apply_tx_config(self, config):
        self.tx_config = config
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
        self.append_terminal_text(raw_rx.decode('ascii'))

    def append_terminal_text(self, text):
        cursor = self.rx_terminal.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(text)
        self.rx_terminal.setTextCursor(cursor)
        self.rx_terminal.ensureCursorVisible()

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
        # Future settings UI can create the same snapshot and pass it to rx_controller.apply_plot_config().
        return RxParserConfig(
            self.rx_sep_mode,
            self.rx_line_mode,
            self.rx_value_type,
            self.rx_value_fmt,
            self.rx_value_size,
            SEP,
            LEN_END,
            VAL_OFFSET,
        )
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

        self.plot_window.clear_data()
        if DEBUG_LINE_ENABLE:
            self.timer.start(UPDATE_INTERVAL)

        try:
            apply_serial_config(self.ser, self.comm_config)
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
