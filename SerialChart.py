# pip install PyQt5 pyqtgraph pyserial

import sys
import serial
import struct
import math
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
from enum import IntEnum

DEBUG_LINE_ENABLE = False       # Add debug line(sin wave) while running
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
X_FOLLOW_WIDTH_DEFAULT = 2000   # default X width while following latest data

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

# @@@@@ 通用設定
VAL_OFFSET = 0              # 數值分段後的固定位移, 除了MULTI_LINE_ASCII以外的所有模式都會受影響, 不會檢查是否溢出
SEP = CUSTOM_END.encode()   # 預先計算分隔符避免即時運算的花費
TX_ENCODING = 'utf-8'
TX_LINE_ENDINGS = {
    'None': '',
    'LF': '\n',
    'CR': '\r',
    'CRLF': '\r\n',
}
TX_HISTORY_LIMIT = 50

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
class TxLineEdit(QtWidgets.QLineEdit):
    def __init__(self, history_combo):
        super().__init__()
        self.history_combo = history_combo

    def event(self, event):
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Tab:
            self.history_combo.complete_from_history()
            return True
        return super().event(event)

    def focusNextPrevChild(self, next):
        if next:
            self.history_combo.complete_from_history()
            return True
        return super().focusNextPrevChild(next)

# ========================================================
class TxHistoryComboBox(QtWidgets.QComboBox):
    def __init__(self):
        super().__init__()
        self.setEditable(True)
        self.setLineEdit(TxLineEdit(self))
        self.setCompleter(None)
        self.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.setMaxCount(TX_HISTORY_LIMIT)
        self.setPlaceholderText("Type text and press Enter to send")
        self.history_index = -1
        self.lineEdit().installEventFilter(self)
        self.lineEdit().textEdited.connect(self.reset_history_browse)

    def reset_history_browse(self):
        self.history_index = -1

    def eventFilter(self, watched, event):
        if watched == self.lineEdit() and event.type() == QtCore.QEvent.KeyPress:
            return self.handle_tx_key(event)
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if self.handle_tx_key(event):
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next):
        if next and self.lineEdit().hasFocus():
            self.complete_from_history()
            return True
        return super().focusNextPrevChild(next)

    def handle_tx_key(self, event):
        if event.key() == QtCore.Qt.Key_Up:
            self.select_history(1)
            return True
        if event.key() == QtCore.Qt.Key_Down:
            self.select_history(-1)
            return True
        if event.key() == QtCore.Qt.Key_Tab:
            self.complete_from_history()
            return True
        return False

    def complete_from_history(self):
        text = self.currentText()
        if not text:
            if self.count() > 0:
                self.showPopup()
            return

        matches = [
            self.itemText(i)
            for i in range(self.count())
            if self.itemText(i).startswith(text)
        ]

        if not matches:
            return

        if len(matches) == 1:
            completion = matches[0]
        else:
            completion = self.common_prefix(matches)
            self.showPopup()

        if len(completion) > len(text):
            self.setEditText(completion)
            self.lineEdit().setSelection(len(text), len(completion) - len(text))
        self.reset_history_browse()

    def common_prefix(self, texts):
        prefix = texts[0]
        for text in texts[1:]:
            while not text.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        return prefix

    def select_history(self, step):
        if self.count() == 0:
            return

        if step > 0:
            self.history_index = min(self.history_index + 1, self.count() - 1)
            self.setCurrentIndex(self.history_index)
        else:
            self.history_index -= 1
            if self.history_index < 0:
                self.history_index = -1
                self.setCurrentIndex(-1)
                self.setEditText("")
            else:
                self.setCurrentIndex(self.history_index)

        self.lineEdit().selectAll()

    def remember(self, text):
        if not text:
            return

        index = self.findText(text)
        if index >= 0:
            self.removeItem(index)

        self.insertItem(0, text)
        self.setCurrentIndex(-1)
        self.setEditText("")
        self.reset_history_browse()

# ========================================================
class SerialPlot:
    def __init__(self):
        # 初始化 Qt Window
        self.app = QtWidgets.QApplication(sys.argv)
        self.main_win = QtWidgets.QMainWindow()
        self.main_win.setWindowTitle(f"SerialChart v{VERSION}")
        self.main_win.resize(800, 600)
        self.central_widget = QtWidgets.QWidget()
        self.main_win.setCentralWidget(self.central_widget)
        self.layout = QtWidgets.QVBoxLayout(self.central_widget)

        # 頂部控制區
        self.controls_layout = QtWidgets.QHBoxLayout()
        self.btn_cursor = QtWidgets.QCheckBox("&Cursor")
        self.btn_cursor.toggled.connect(self.cursor_toggle)
        self.btn_rectMode = QtWidgets.QCheckBox("&RectMode")
        self.btn_rectMode.toggled.connect(self.rect_mode_toggle)
        self.btn_connect = QtWidgets.QPushButton("")
        self.btn_connect.setCheckable(True)
        self.btn_connect.toggled.connect(self.conncet_toggle)
        self.btn_autoY = QtWidgets.QPushButton("Auto&Y")
        self.btn_autoY.clicked.connect(self.auto_y)
        self.btn_followX = QtWidgets.QCheckBox("Follow&X")
        self.btn_followX.setChecked(True)
        self.btn_followX.toggled.connect(self.follow_x_toggle)
        self.spin_x_width = QtWidgets.QSpinBox()
        self.spin_x_width.setRange(1, MAX_POINTS)
        self.spin_x_width.setValue(X_FOLLOW_WIDTH_DEFAULT)
        self.spin_x_width.setSuffix(" pts")
        self.spin_x_width.setFixedWidth(100)
        self.spin_x_width.setSingleStep(100)
        self.spin_x_width.valueChanged.connect(self.update_x_range)
        self.btn_clear = QtWidgets.QPushButton("Clear🧹")
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
        self.tx_label = QtWidgets.QLabel("TX:")
        self.tx_input = TxHistoryComboBox()
        self.tx_input.setFixedWidth(260)
        self.tx_input.lineEdit().returnPressed.connect(self.send_tx_input)
        self.combo_tx_line_end = QtWidgets.QComboBox()
        self.combo_tx_line_end.addItems(TX_LINE_ENDINGS.keys())
        self.combo_tx_line_end.setCurrentText('LF')
        self.combo_tx_line_end.setFixedWidth(70)
        self.btn_send = QtWidgets.QPushButton("&Send")
        self.btn_send.setFixedWidth(45)
        self.btn_send.clicked.connect(self.send_tx_input)
        self.tx_status = QtWidgets.QLabel("")
        self.tx_layout.addWidget(self.tx_label)
        self.tx_layout.addWidget(self.tx_input)
        self.tx_layout.addWidget(self.combo_tx_line_end)
        self.tx_layout.addWidget(self.btn_send)
        self.tx_layout.addWidget(self.tx_status)
        self.tx_layout.addStretch()

        # 曲線圖
        self.residual = b""                     # 儲存末端的不完整資料
        self.win = pg.GraphicsLayoutWidget()
        self.plot = self.win.addPlot()
        self.plot.showGrid(x=True, y=True)
        self.plot.setYRange(-2000, 2000, padding=0.05)
        self.plot.setXRange(0, X_FOLLOW_WIDTH_DEFAULT, padding=0)

        # 將元件加入layout
        self.layout.addLayout(self.controls_layout)
        self.layout.addLayout(self.tx_layout)
        self.layout.addWidget(self.win)

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
        info = ""
        offset = VAL_OFFSET
        self.ser = serial.Serial(baudrate=BAUD, timeout=0.1)
        self.ser.port = PORT
        if   SEP_MODE == SEP_MODES.CUSTOM_END:          self.rxHandle = self.rxHandle_split     ; info += "特定資料分段模式"
        elif SEP_MODE == SEP_MODES.LENGTH:              self.rxHandle = self.rxHandle_length    ; info += "固定長度分段模式"
        else:                                           print('ERROR, invalid SEP_MODE!!!')     ; info += "!!! 模式錯誤 !!!"

        self.max_current_idx = 0
        self.curves_data = {}   # 字典管理多條線段： { "name": {"buf": array, "idx": 0, "curve": pg_object} }
        if   LINE_MODE == LINE_MODES.SINGLE_LINE:
            info += ", 單線段模式"
            buf = np.full(MAX_POINTS, np.nan)  # curve 原始資料
            curve = self.plot.plot(pen=colors[0])
            curve.setData(buf, connect="finite")
            self.curves_data["default"] = {"buf": buf, "idx": 0, "curve": curve}
            self.update_packets = self.update_line_single
        elif LINE_MODE == LINE_MODES.MULTI_LINE_ASCII:
            info += ", 多線段ASCII模式"
            # 多線段會動態新增線段
            self.plot.addLegend()   # 多線段模式建議開啟圖例
            self.update_packets = self.update_line_ascii
        else:
            info += "!!! 線段設定錯誤 !!!"  
            print('ERROR, invalid LINE_MODE!!!')
        
        if VALUE_MODE in VALUE_CONFIG_TABLE:
            type, fmt, size = VALUE_CONFIG_TABLE[VALUE_MODE]
            if type == 'ASCII':
                if offset == 0:                         self.convert_func = fmt
                else:                                   self.convert_func = lambda pak, f=fmt, s=size: f(pak[offset:offset + s])
                info += " + {}, size={}, offset={}, SEP=[{}]".format(type, size, offset, SEP.hex(' ').upper())
            else:
                if offset == 0:                         self.convert_func = lambda pak, f=fmt, s=size: struct.unpack(f, pak[:s])[0]
                else:                                   self.convert_func = lambda pak, f=fmt, s=size: struct.unpack(f, pak[offset : offset + s])[0]
                info += " + {}, size={}, offset={}, Length={}".format(type, size, offset, LEN_END)
        else:
            print('ERROR, invalid VALUE_MODE!!!')
            self.convert_func = lambda x: x # 預防性 fallback，避免執行時報錯
        print(info)

        # update timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.conncet_toggle(False)

        self.validation_sin_phase = 0.0     # only for validation function: update_validation_sin()
# ========================================================
    def send(self, data):
        if self.ser.is_open:
            self.ser.write(data)
# ========================================================
    def send_tx_input(self):
        text = self.tx_input.currentText()
        line_end = TX_LINE_ENDINGS[self.combo_tx_line_end.currentText()]
        data = (text + line_end).encode(TX_ENCODING)

        if not self.ser.is_open:
            self.tx_status.setText("COM closed")
            return

        # try:
        #     self.send(data)
        # except serial.SerialException as e:
        #     self.tx_status.setText("TX failed")
        #     print(f"Serial TX error: {e}")
        #     return

        self.tx_status.setText(f"Sent {len(data)} bytes")
        self.tx_input.remember(text)
# ========================================================
    def rxHandle_split(self, new_rx):
        packets = (self.residual + new_rx).split(SEP)   # 補回不完整的資料再切割
        self.residual = packets.pop()                   # 取出最後一項不完整資料, 剩下的都是完整的封包

        if not packets:
            return

        packets = filter(None, packets)                 # 過濾空封包
        self.update_packets(packets)
# ========================================================
    def rxHandle_length(self, new_rx):
        N = LEN_END
        data = self.residual + new_rx
        num_packets = len(data) // N
        packets = [data[i*N : (i+1)*N] for i in range(num_packets)]
        self.residual = data[num_packets * N:]

        if not packets:
            return
        
        self.update_packets(packets)
# ========================================================
    def update_line_single(self, packets):
        # 單線模式直接對應到 "default" 線段
        curve_info = self.curves_data.get("default")

        try:
            new_values = [self.convert_func(pak) for pak in packets]
            num_new = len(new_values)

            if num_new == 0: 
                return
            
            buf = curve_info["buf"]
            idx = curve_info["idx"]

            # --- 更新 NumPy Buffer ---
            if idx + num_new <= MAX_POINTS:    # Buffer 還沒填滿，從左往右填充
                buf[idx : idx + num_new] = new_values
                curve_info["idx"] += num_new
                self.max_current_idx = idx + num_new
            else:                              # 剛好填滿或已經溢出, 切換到滾動模式
                buf[:-num_new] = buf[num_new:]    # 將舊資料左移
                buf[-num_new:] = new_values       # 新資料填入最末端
                curve_info["idx"] = MAX_POINTS
                self.max_current_idx = MAX_POINTS
            v_len = self.max_current_idx        # 有效資料點數量 (僅傳有效資料給curve)
            curve_info["curve"].setData(buf[:v_len], connect="finite")
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
    def update_line_ascii(self, packets):
        # 多線段 ASCII 模式解析: "<name> = <value>"
        try:
            pending_values = {}
            for pak in packets:
                if b'=' not in pak:     continue        # 辨識是否有 '='
                
                parts = pak.split(b'=')
                if len(parts) != 2:     continue        # 拆分左值與右值失敗
                
                name = parts[0].strip().decode('ascii', errors='ignore')
                val_str = parts[1].strip()
                
                try:
                    val = self.convert_func(val_str)
                except:                 continue        # 轉換失敗

                # print("{}={}".format(name, val))
                
                pending_values.setdefault(name, []).append(val)

            # 同一批資料依線段分組後再批次更新Buffer，避免滿Buffer時逐筆搬移
            for name, values in pending_values.items():
                curve_info = self._get_or_create_curve(name)
                if not curve_info:      continue        # 取得線條資料失敗
                self._append_curve_values(curve_info, values)

            # 尋找資料最長的線段
            if self.curves_data:
                self.max_current_idx = max(info["idx"] for info in self.curves_data.values())

            # 更新繪圖與自動調整畫面
            for name in pending_values:
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
    def handleRxData(self):
        try:
            new_rx = self.ser.read_all()        # 讀取目前所有可用 bytes
        except:
            self.conncet_toggle(False)          # read_all失敗, turn off COM
            return
        
        if not new_rx:
            return
        self.rxHandle(new_rx)
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
        self.handleRxData()                     # 讀取serial資料並處理
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
            self.btn_connect.setText("🟢Running")
            self.clear_data()
            self.timer.start(UPDATE_INTERVAL)
            self.ser.open()
            self.ser.reset_input_buffer()
            self.tx_input.setEnabled(True)
            self.combo_tx_line_end.setEnabled(True)
            self.btn_send.setEnabled(True)
            self.tx_status.setText("")
        else:
            self.timer.stop()
            self.btn_connect.setStyleSheet("background-color : lightpink")
            self.btn_connect.setText("🔴Stop")
            if self.ser.is_open:
                self.ser.close()
            self.tx_input.setEnabled(False)
            self.combo_tx_line_end.setEnabled(False)
            self.btn_send.setEnabled(False)
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
        self.residual = b""
        self.max_current_idx = 0

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
