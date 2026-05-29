# pip install PyQt5 pyqtgraph pyserial

import sys
import serial
import struct
import math
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
from enum import IntEnum
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
        self.central_widget = QtWidgets.QWidget()
        self.main_win.setCentralWidget(self.central_widget)
        self.layout = QtWidgets.QVBoxLayout(self.central_widget)
        self.tx_config = self.create_tx_config()
   

        # 頂部控制區
        self.controls_layout = QtWidgets.QHBoxLayout()
        self.btn_cursor = QtWidgets.QCheckBox("&Cursor")
        self.btn_cursor.toggled.connect(self.cursor_toggle)
        self.btn_rectMode = QtWidgets.QCheckBox("&RectMode")
        self.btn_rectMode.toggled.connect(self.rect_mode_toggle)
        self.btn_connect = QtWidgets.QPushButton("")
        self.btn_connect.setFixedSize(100, 30)
        self.btn_connect.setCheckable(True)
        self.btn_connect.toggled.connect(self.conncet_toggle)
        self.btn_autoY = QtWidgets.QPushButton("Auto&Y")
        self.btn_autoY.setFixedSize(80, 30)
        self.btn_autoY.clicked.connect(self.auto_y)
        self.btn_followX = QtWidgets.QCheckBox("Follow&X")
        self.btn_followX.setChecked(True)
        self.btn_followX.toggled.connect(self.follow_x_toggle)
        self.spin_x_width = QtWidgets.QSpinBox()
        self.spin_x_width.setRange(1, MAX_POINTS)
        self.spin_x_width.setValue(X_FOLLOW_WIDTH_DEFAULT)
        self.spin_x_width.setSuffix(" pts")
        self.spin_x_width.setFixedSize(120, 30)
        self.spin_x_width.setSingleStep(100)
        self.spin_x_width.valueChanged.connect(self.update_x_range)
        self.btn_clear = QtWidgets.QPushButton("Clear🧹")
        self.btn_clear.setFixedSize(100, 30)
        self.btn_clear.clicked.connect(self.clear_data)
        self.controls_layout.addWidget(self.btn_connect)
        self.controls_layout.addWidget(self.btn_cursor)
        self.controls_layout.addWidget(self.btn_rectMode)
        self.controls_layout.addWidget(self.btn_autoY)
        self.controls_layout.addWidget(self.btn_followX)
        self.controls_layout.addWidget(self.spin_x_width)
        self.controls_layout.addWidget(self.btn_clear)
        self.controls_layout.addStretch()

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

        # 曲線圖
        self.win = pg.GraphicsLayoutWidget()
        self.win.setMinimumHeight(200)
        self.plot = self.win.addPlot()
        self.plot.showGrid(x=True, y=True)
        self.plot.setYRange(-2000, 2000, padding=0.05)
        self.plot.setXRange(0, X_FOLLOW_WIDTH_DEFAULT, padding=0)

        # 狀態列
        self.com_status_icon = QtWidgets.QLabel("")
        self.tx_status = QtWidgets.QLabel("")
        self.status_bar = QtWidgets.QStatusBar()
        self.status_bar.addWidget(self.com_status_icon)
        self.status_bar.addWidget(self.tx_status, 1)

        # 將元件加入layout
        self.layout.addLayout(self.controls_layout)
        self.layout.addLayout(self.tx_layout)
        self.layout.addWidget(self.win)
        self.main_win.setStatusBar(self.status_bar)

        # 輔助線
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen='w')
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen='w')
        self.label = pg.TextItem(anchor=(1,1), color='y')
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)
        self.plot.addItem(self.label)
        self.mouse_proxy = None 
        self.cursor_hide()
        # 省效能設定
        # self.plot.setDownsampling(mode='peak')  # 降取樣功能, 'peak'或是 'mean', 
        # self.plot.setClipToView(True)           # 只畫出目前視窗看得到的點

        # others
        print(f"{WINDOWS_TITLE} v{VERSION}")
        info = ""
        offset = VAL_OFFSET
        self.ser = serial.Serial(baudrate=BAUD, timeout=0.1, write_timeout=TX_WRITE_TIMEOUT)
        self.ser.port = PORT
        if   SEP_MODE == SEP_MODES.CUSTOM_END:          self.rx_sep_mode = "custom_end"         ; info += "特定資料分段模式"
        elif SEP_MODE == SEP_MODES.LENGTH:              self.rx_sep_mode = "length"             ; info += "固定長度分段模式"
        else:                                           print('ERROR, invalid SEP_MODE!!!')     ; info += "!!! 模式錯誤 !!!"

        self.max_current_idx = 0
        self.curves_data = {}   # 字典管理多條線段： { "name": {"buf": array, "idx": 0, "curve": pg_object} }
        if   LINE_MODE == LINE_MODES.SINGLE_LINE:
            info += ", 單線段模式"
            buf = np.full(MAX_POINTS, np.nan)  # curve 原始資料
            curve = self.plot.plot(pen=colors[0])
            curve.setData(buf, connect="finite")
            self.curves_data["default"] = {"buf": buf, "idx": 0, "curve": curve}
            self.rx_line_mode = "single"
        elif LINE_MODE == LINE_MODES.MULTI_LINE_ASCII:
            info += ", 多線段ASCII模式"
            # 多線段會動態新增線段
            self.plot.addLegend()   # 多線段模式建議開啟圖例
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

        # update timer (validation only; RX uses SerialRxController)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)

        # rx controller
        self.rx_controller = SerialRxController(UPDATE_INTERVAL)
        # RX thread emits already parsed plot batches; main thread only updates UI/curves.
        self.rx_controller.plot_batch_ready.connect(self.update_plot_batch)
        self.rx_controller.raw_received.connect(self.handle_terminal_raw_rx)
        self.rx_controller.failed.connect(self.rx_failed)

        # tx controller
        self.tx_controller = TxController(self.tx_config)
        self.tx_controller.started.connect(self.tx_started)
        self.tx_controller.finished.connect(self.tx_finished)
        self.tx_controller.failed.connect(self.tx_failed)
        self.tx_controller.rejected.connect(self.tx_status.setText)
        self.conncet_toggle(False)

        # debug
        self.validation_sin_phase = 0.0     # only for validation function: update_validation_sin()

# ========================================================
# ========================================================        
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
    def update_line_single_values(self, values):
        # 單線模式直接對應到 "default" 線段
        curve_info = self.curves_data.get("default")

        try:
            if not values:
                return

            self._append_curve_values(curve_info, values)
            self.max_current_idx = curve_info["idx"]
            v_len = self.max_current_idx        # 有效資料點數量 (僅傳有效資料給curve)
            curve_info["curve"].setData(curve_info["buf"][:v_len], connect="finite")
            # curve_info["curve"].setData(buf[::2], connect="finite")     # 更新curve, 2點取1點, 當資料過大時可考慮
            self.update_x_range()

        except ValueError as e:
            print(f"Data conversion error: {e}")
# ========================================================
    def _get_or_create_curve(self, name):
        # 根據名稱取得線段資訊，若不存在則動態建立 (最多10條)
        if name not in self.curves_data:
            if len(self.curves_data) >= MAX_LINES:
                return None # 超過數量限制不處理
            
            # 建立新的線段與 Buffer
            buf = np.full(MAX_POINTS, np.nan)
            # 自動給予不同顏色 (簡單輪詢)
            color = colors[len(self.curves_data) % len(colors)]
            
            curve = self.plot.plot(pen=color, name=name)
            self.curves_data[name] = {"buf": buf, "idx": 0, "curve": curve}
            
        return self.curves_data[name]
# ========================================================
    def _append_curve_value(self, curve_info, value):
        buf = curve_info["buf"]
        idx = curve_info["idx"]
        if idx < MAX_POINTS:
            buf[idx] = value
            curve_info["idx"] += 1
        else:
            buf[:-1] = buf[1:]
            buf[-1] = value
# ========================================================
    def _append_curve_values(self, curve_info, values):
        num_new = len(values)
        if num_new == 0:
            return

        buf = curve_info["buf"]
        idx = curve_info["idx"]

        if num_new >= MAX_POINTS:
            buf[:] = values[-MAX_POINTS:]
            curve_info["idx"] = MAX_POINTS
        elif idx + num_new <= MAX_POINTS:
            buf[idx : idx + num_new] = values
            curve_info["idx"] += num_new
        else:
            overflow = idx + num_new - MAX_POINTS
            keep_len = idx - overflow
            buf[:keep_len] = buf[overflow:idx]
            buf[keep_len:] = values
            curve_info["idx"] = MAX_POINTS
# ========================================================
    def update_line_ascii_series(self, series):
        try:
            # 同一批資料依線段分組後再批次更新Buffer，避免滿Buffer時逐筆搬移
            for name, values in series.items():
                curve_info = self._get_or_create_curve(name)
                if not curve_info:      continue        # 取得線條資料失敗
                self._append_curve_values(curve_info, values)

            # 尋找資料最長的線段
            if self.curves_data:
                self.max_current_idx = max(info["idx"] for info in self.curves_data.values())

            # 更新繪圖與自動調整畫面
            for name in series:
                if name not in self.curves_data:
                    continue
                info = self.curves_data[name]
                v_len = self.max_current_idx        # 有效資料點數量 (僅傳有效資料給curve)
                info["curve"].setData(info["buf"][:v_len], connect="finite")
            
            # 調整 X 軸範圍 (從 0 到最長點)
            if self.max_current_idx > 0:
                self.update_x_range()

        except Exception as e:
            print(f"Multi-line process error: {e}")
# ========================================================
    def update_plot_batch(self, batch):
        if batch["mode"] == "single":
            self.update_line_single_values(batch["values"])
        elif batch["mode"] == "multi_ascii":
            self.update_line_ascii_series(batch["series"])
# ========================================================
# ========================================================
# ========================================================
    def handle_terminal_raw_rx(self, raw_rx):
        # Reserved for the future terminal window raw-data pipeline.
        pass

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
        self.tx_status.setText("RX failed")
        if self.btn_connect.isChecked():
            self.btn_connect.setChecked(False)
        else:
            self.conncet_toggle(False)
# ========================================================
# ========================================================
# ========================================================
    def update_validation_sin(self):
        VALIDATION_SIN_POINTS = 5       # 每次Timer更新新增幾個sin點
        VALIDATION_SIN_STEP = 0.08      # sin相位步進
        VALIDATION_SIN_AMPLITUDE = 24689
        VALIDATION_SIN_OFFSET = 7777

        if LINE_MODE == LINE_MODES.SINGLE_LINE:
            curve_info = self.curves_data.get("default")
        else:
            curve_info = self._get_or_create_curve("sin")

        if not curve_info:
            return

        for _ in range(VALIDATION_SIN_POINTS):
            value = (math.sin(self.validation_sin_phase) * VALIDATION_SIN_AMPLITUDE) + VALIDATION_SIN_OFFSET
            self._append_curve_value(curve_info, value)
            self.validation_sin_phase += VALIDATION_SIN_STEP

        self.max_current_idx = max(info["idx"] for info in self.curves_data.values())
        v_len = self.max_current_idx
        curve_info["curve"].setData(curve_info["buf"][:v_len], connect="finite")

        if self.max_current_idx > 0:
            self.update_x_range()
# ========================================================
    def update(self):
        if DEBUG_LINE_ENABLE:
            self.update_validation_sin()        # test line feature
# ========================================================
    def mouseMoved(self, evt):
        pos = evt[0]        # 滑鼠在 Scene 中的位置
        if self.plot.sceneBoundingRect().contains(pos):
            mousePoint = self.plot.vb.mapSceneToView(pos)
            self.vLine.setPos(mousePoint.x())       # 更新十字線位置
            self.hLine.setPos(mousePoint.y())
            self.label.setText(f"X: {mousePoint.x():.1f}\nY: {mousePoint.y():.2f}")
            self.label.setPos(mousePoint.x(), mousePoint.y())   # 跟著滑鼠跑
            
# ========================================================
    # ----- Start/Stop
    def conncet_toggle(self, checked):
        if checked:
            self.btn_connect.setStyleSheet("background-color : palegreen")
            self.btn_connect.setText("🟢 Running")
            self.clear_data()
            if DEBUG_LINE_ENABLE:
                self.timer.start(UPDATE_INTERVAL)
            self.ser.open()
            self.ser.reset_input_buffer()
            self.rx_controller.start(self.ser, self.create_rx_plot_parser())
            self.tx_input.setEnabled(True)
            self.combo_tx_line_end.setEnabled(True)
            self.btn_send.setEnabled(True)
            self.com_status_icon.setText("🟢")
            self.tx_status.setText("COM opened")
        else:
            self.timer.stop()
            self.btn_connect.setStyleSheet("background-color : lightpink")
            self.btn_connect.setText("🔴 Stop")
            self.rx_controller.stop()
            if self.ser.is_open:
                self.ser.close()
            self.tx_input.setEnabled(False)
            self.combo_tx_line_end.setEnabled(False)
            self.btn_send.setEnabled(False)
            self.com_status_icon.setText("🔴")
            self.tx_status.setText("COM closed")


    # ----- RectMode
    def rect_mode_toggle(self, checked):
        if checked:     self.plot.vb.setMouseMode(pg.ViewBox.RectMode)
        else:           self.plot.vb.setMouseMode(pg.ViewBox.PanMode)
    # ----- Follow X
    def follow_x_toggle(self, checked):
        self.spin_x_width.setEnabled(checked)
        if checked:
            self.update_x_range()
    def update_x_range(self):
        if not self.btn_followX.isChecked():
            return

        x_width = self.spin_x_width.value()
        x_end = max(self.max_current_idx, x_width)
        x_start = x_end - x_width
        self.plot.setXRange(x_start, x_end, padding=0)
    # ----- Cursor
    def cursor_toggle(self, checked):
        if checked:     self.cursor_show()
        else:           self.cursor_hide()
    def cursor_show(self):
        self.vLine.show()
        self.hLine.show()
        self.label.show()
        if self.mouse_proxy is None:        # 連結 mouseMoved() 事件
            self.mouse_proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=30, slot=self.mouseMoved)
    def cursor_hide(self):
        self.vLine.hide()
        self.hLine.hide()
        self.label.hide()
        if self.mouse_proxy is not None:
            self.mouse_proxy.disconnect()   # 斷開訊號
            self.mouse_proxy = None         # 清空物件，停止監聽
    # ----- Auto Y
    def auto_y(self):
        y_range = self._get_data_y_range()
        if y_range is None:
            return            
        self.plot.setYRange(y_range[0], y_range[1], padding=0.05)

    def _get_data_y_range(self):
        if not self.curves_data:
            return None

        y_min = None
        y_max = None
        for info in self.curves_data.values():
            idx = min(info["idx"], MAX_POINTS)
            if idx <= 0:
                continue

            values = info["buf"][:idx]
            values = values[np.isfinite(values)]
            if not values.size:
                continue

            curve_min = float(np.min(values))
            curve_max = float(np.max(values))
            y_min = curve_min if y_min is None else min(y_min, curve_min)
            y_max = curve_max if y_max is None else max(y_max, curve_max)

        if y_min is None or y_max is None:
            return None

        if y_min == y_max:
            margin = max(abs(y_min) * 0.05, 1.0)
            return y_min - margin, y_max + margin

        return y_min, y_max
    # ----- Clear
    def clear_data(self):
        self.max_current_idx = 0
        # Clear parser residual as well as visible curve buffers.
        self.rx_controller.reset_plot_parser()

        # 將已建立的線段進行重設
        for name, info in self.curves_data.items():
            info["buf"].fill(np.nan)
            info["idx"] = 0
            info["curve"].setData(info["buf"])

        self.update_x_range()
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
