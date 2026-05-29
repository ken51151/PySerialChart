import serial
from dataclasses import dataclass
from pyqtgraph.Qt import QtWidgets, QtCore

# ========================================================
# Keep this at 0 for non-blocking writes. Non-zero values can make writes fail
# with SerialTimeoutException when the paired COM port is not opened by another app.
TX_WRITE_TIMEOUT = 0
TX_HISTORY_LIMIT = 50
TX_LINE_ENDINGS = {
    'None': '',
    'LF (\\n)': '\n',
    'CR (\\r)': '\r',
    'CRLF': '\r\n',
}
HEX_TX_PREFIX = 'hex:'

# ========================================================
@dataclass(frozen=True)
class TxConfig:
    line_endings: dict
    prefix_enabled: bool = True

# ========================================================
DEFAULT_TX_CONFIG = TxConfig(
    line_endings=TX_LINE_ENDINGS,
    prefix_enabled=True,
)

# ========================================================
def parse_tx_input(text, line_end, config=DEFAULT_TX_CONFIG):
    # Prefix mode means raw bytes; normal text keeps the selected line ending.
    if config.prefix_enabled and text.lower().startswith(HEX_TX_PREFIX):
        return parse_hex_tx(text)
    return (text + line_end).encode('ascii'), text, False       # encode with ASCII normally

# ========================================================
def parse_hex_tx(text):
    hex_text = text[len(HEX_TX_PREFIX):].strip()
    if not hex_text:
        raise ValueError("HEX empty")

    hex_text = hex_text.replace(",", " ")
    hex_text = "".join(hex_text.split())

    if len(hex_text) % 2 != 0:
        raise ValueError("HEX length must be even")

    try:
        data = bytes.fromhex(hex_text)
    except ValueError:
        raise ValueError("HEX invalid")

    return data, text, True

# ========================================================
# ========================================================
# ========================================================

class TxLineEdit(QtWidgets.QLineEdit):
    def __init__(self, history_combo):
        super().__init__()
        self.history_combo = history_combo

    def event(self, event):
        # Qt normally treats Tab as focus navigation before keyPressEvent sees it.
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
# ========================================================
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
# ========================================================
    def reset_history_browse(self):
        self.history_index = -1
# ========================================================
    def eventFilter(self, watched, event):
        if watched == self.lineEdit() and event.type() == QtCore.QEvent.KeyPress:
            return self.handle_tx_key(event)
        return super().eventFilter(watched, event)
# ========================================================
    def keyPressEvent(self, event):
        if self.handle_tx_key(event):
            return
        super().keyPressEvent(event)
# ========================================================
    def focusNextPrevChild(self, next):
        if next and self.lineEdit().hasFocus():
            self.complete_from_history()
            return True
        return super().focusNextPrevChild(next)
# ========================================================
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
# ========================================================
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
            # Multiple matches behave like a terminal: complete only the shared prefix.
            completion = self.common_prefix(matches)
            self.showPopup()

        if len(completion) > len(text):
            self.setEditText(completion)
            self.lineEdit().setSelection(len(text), len(completion) - len(text))
        self.reset_history_browse()
# ========================================================
    def common_prefix(self, texts):
        prefix = texts[0]
        for text in texts[1:]:
            while not text.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        return prefix
# ========================================================
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
# ========================================================
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
# ========================================================
# ========================================================

class SerialTxWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(int, int, str)
    failed = QtCore.pyqtSignal(str, str, str)
# ========================================================
    def __init__(self, ser, data, text):
        super().__init__()
        self.ser = ser
        self.data = data
        self.text = text
# ========================================================
    def run(self):
        try:
            bytes_sent = self.ser.write(self.data)
        except serial.SerialTimeoutException as e:
            self.failed.emit("TX Timeout", f"Serial TX timeout: {e}", self.text)
            return
        except (serial.SerialException, OSError) as e:
            self.failed.emit("TX failed", f"Serial TX error: {e}", self.text)
            return

        print('Sent:', self.data)
        self.finished.emit(bytes_sent, len(self.data), self.text)
# ========================================================


class TxController(QtCore.QObject):
    started = QtCore.pyqtSignal(bool)
    finished = QtCore.pyqtSignal(int, int, str)
    failed = QtCore.pyqtSignal(str, str, str)
    rejected = QtCore.pyqtSignal(str)

# ========================================================
    def __init__(self, config=DEFAULT_TX_CONFIG):
        super().__init__()
        self.config = config
        self.thread = None
        self.worker = None

# ========================================================
    def apply_config(self, config):
        self.config = config

# ========================================================
    def is_busy(self):
        return self.thread is not None and self.thread.isRunning()

# ========================================================
    def send(self, ser, text, line_end):
        if self.is_busy():
            self.rejected.emit("TX busy")
            return

        if not text:
            self.rejected.emit("TX empty")
            return

        try:
            data, tx_text, is_hex = parse_tx_input(text, line_end, self.config)
        except ValueError as e:
            self.rejected.emit(str(e))
            return

        if not ser.is_open:
            self.rejected.emit("COM closed")
            return

        # Serial writes run off the UI thread because some drivers can block inside write().
        self.thread = QtCore.QThread()
        self.worker = SerialTxWorker(ser, data, tx_text)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.finished)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_worker)
        self.started.emit(is_hex)
        self.thread.start()

# ========================================================
    def clear_worker(self):
        self.thread = None
        self.worker = None

# ========================================================
