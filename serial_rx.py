import time
import serial
import struct
from dataclasses import dataclass
from pyqtgraph.Qt import QtCore

# ========================================================
RX_NAME_CACHE_LIMIT = 128

# ========================================================
@dataclass(frozen=True)
class RxParserConfig:
    sep_mode: str
    line_mode: str
    value_type: str
    value_fmt: object
    value_size: int
    sep: bytes
    len_end: int
    offset: int

# ========================================================
# ========================================================
# ========================================================
class RxPlotParser:
    def __init__(self, sep_mode, line_mode, value_type, value_fmt, value_size, sep, len_end, offset):
        config = RxParserConfig(sep_mode, line_mode, value_type, value_fmt, value_size, sep, len_end, offset)
        self.apply_config(config)

    def apply_config(self, config):
        self.sep_mode = config.sep_mode
        self.line_mode = config.line_mode
        self.value_type = config.value_type
        self.value_fmt = config.value_fmt
        self.value_size = config.value_size
        self.sep = config.sep
        self.len_end = config.len_end
        self.offset = config.offset
        self.value_struct = None
        self.name_cache = {}
        self.reset()
        self._bind_strategy_functions()

    def _bind_strategy_functions(self):
        # Bind parser strategy once so the RX hot path avoids repeated mode checks.
        self.split_packets = self._make_split_packets_func()
        self.parse_packets = self._make_parse_packets_func()
        self.convert_value = self._make_convert_value_func()

    def reset(self):
        # Residual belongs to the active parser config; clear it when config/data is reset.
        self.residual = b""

    def feed(self, data):
        packets = self.split_packets(data)
        if not packets:
            return None, 0
        return self.parse_packets(packets)

    def _parse_single_packets(self, packets):
        values = []
        for packet in packets:
            try:
                values.append(self.convert_value(packet))
            except (ValueError, struct.error):
                continue
        if not values:
            return None, 0
        return {"mode": "single", "values": values}, len(values)

    def _parse_multi_ascii_packets(self, packets):
        series = {}
        value_count = 0
        for packet in packets:
            eq = packet.find(b'=')
            if eq < 0:
                continue

            name_bytes = packet[:eq].strip()
            name = self._get_name(name_bytes)
            value_bytes = packet[eq + 1:].strip()

            try:
                value = self.convert_value(value_bytes)
            except (ValueError, struct.error):
                continue

            series.setdefault(name, []).append(value)
            value_count += 1

        if not series:
            return None, 0
        return {"mode": "multi_ascii", "series": series}, value_count

    def _get_name(self, name_bytes):
        # Line names usually repeat. Cache decoded names to reduce per-packet string creation.
        name = self.name_cache.get(name_bytes)
        if name is not None:
            return name

        name = name_bytes.decode('ascii', errors='ignore')
        if len(self.name_cache) < RX_NAME_CACHE_LIMIT:
            self.name_cache[name_bytes] = name
        return name

    def _parse_noop_packets(self, packets):
        return None, 0

    def _split_custom_end_packets(self, data):
        # Keep the final partial packet in residual until the next separator arrives.
        packets = (self.residual + data).split(self.sep)
        self.residual = packets.pop()
        return [packet for packet in packets if packet]

    def _split_length_packets(self, data):
        data = self.residual + data
        num_packets = len(data) // self.len_end
        packets = [data[i * self.len_end : (i + 1) * self.len_end] for i in range(num_packets)]
        self.residual = data[num_packets * self.len_end:]
        return packets

    def _split_noop_packets(self, data):
        return []

    def _make_split_packets_func(self):
        if self.sep_mode == "custom_end":
            return self._split_custom_end_packets

        if self.sep_mode == "length":
            return self._split_length_packets

        print(f"Invalid RX sep_mode: {self.sep_mode}")
        return self._split_noop_packets

    def _make_parse_packets_func(self):
        if self.line_mode == "single":
            return self._parse_single_packets

        if self.line_mode == "multi_ascii":
            return self._parse_multi_ascii_packets

        print(f"Invalid RX line_mode: {self.line_mode}")
        return self._parse_noop_packets

    def _make_convert_value_func(self):
        if self.value_type == "ASCII":
            if self.offset == 0:
                return self.value_fmt
            return lambda packet: self.value_fmt(packet[self.offset : self.offset + self.value_size])

        if self.value_type == "BIN":
            # Struct.unpack_from avoids slicing bytes for each binary packet.
            self.value_struct = struct.Struct(self.value_fmt)
            if self.offset == 0:
                return lambda packet: self.value_struct.unpack_from(packet, 0)[0]
            return lambda packet: self.value_struct.unpack_from(packet, self.offset)[0]

        print(f"Invalid RX value_type: {self.value_type}")
        return lambda packet: (_ for _ in ()).throw(ValueError(f"Invalid RX value_type: {self.value_type}"))

# ========================================================
# ========================================================
# ========================================================
class SerialRxWorker(QtCore.QObject):
    raw_received = QtCore.pyqtSignal(bytes)
    plot_batch_ready = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)
    stopped = QtCore.pyqtSignal()

    def __init__(self, ser, parser, interval_ms=30, max_values=5000):
        super().__init__()
        self.ser = ser
        self.parser = parser
        self.interval_sec = interval_ms / 1000.0
        self.max_values = max_values
        self.running = False
        self.terminal_enabled = False
        self.plot_enabled = False
        self.raw_pending = bytearray()
        self.plot_pending = None
        self.pending_value_count = 0
        self.handle_rx_data = self._handle_rx_noop

    @QtCore.pyqtSlot()
    def run(self):
        self.running = True
        last_emit = time.perf_counter()

        while self.running:
            try:
                # read(1) blocks up to serial timeout when idle; in_waiting drains bursts in one read.
                data = self.ser.read(self.ser.in_waiting or 1)
            except (serial.SerialException, OSError) as e:
                self.failed.emit(f"Serial RX error: {e}")
                break

            if data:
                self.handle_rx_data(data)

            now = time.perf_counter()
            if (
                now - last_emit >= self.interval_sec
                or self.pending_value_count >= self.max_values
                or len(self.raw_pending) >= self.max_values
            ):
                # Batch signals cap UI wakeups while still flushing immediately under heavy load.
                self._emit_pending()
                last_emit = now

        self._emit_pending()
        self.stopped.emit()

    @QtCore.pyqtSlot()
    def stop(self):
        self.running = False

    @QtCore.pyqtSlot(bool)
    def set_terminal_enabled(self, enabled):
        self.terminal_enabled = enabled
        self._bind_rx_data_handler()
        if not enabled:
            self.raw_pending.clear()

    @QtCore.pyqtSlot(bool)
    def set_plot_enabled(self, enabled):
        self.plot_enabled = enabled
        self._bind_rx_data_handler()
        if not enabled:
            self.plot_pending = None
            self.pending_value_count = 0
            self.parser.reset()

    def _bind_rx_data_handler(self):
        if self.terminal_enabled and self.plot_enabled:
            self.handle_rx_data = self._handle_rx_terminal_plot
        elif self.terminal_enabled:
            self.handle_rx_data = self._handle_rx_terminal_only
        elif self.plot_enabled:
            self.handle_rx_data = self._handle_rx_plot_only
        else:
            self.handle_rx_data = self._handle_rx_noop

    def _handle_rx_noop(self, data):
        pass

    def _handle_rx_terminal_only(self, data):
        self.raw_pending.extend(data)

    def _handle_rx_plot_only(self, data):
        batch, value_count = self.parser.feed(data)
        if batch:
            self._merge_plot_batch(batch)
            self.pending_value_count += value_count

    def _handle_rx_terminal_plot(self, data):
        self.raw_pending.extend(data)
        batch, value_count = self.parser.feed(data)
        if batch:
            self._merge_plot_batch(batch)
            self.pending_value_count += value_count

    @QtCore.pyqtSlot()
    def reset_plot_parser(self):
        self.plot_pending = None
        self.pending_value_count = 0
        self.parser.reset()

    def apply_plot_config(self, config):
        # Config changes must drop partial parser state so old and new packet rules never mix.
        self.plot_pending = None
        self.pending_value_count = 0
        self.parser.apply_config(config)

    def _merge_plot_batch(self, batch):
        if self.plot_pending is None or self.plot_pending.get("mode") != batch.get("mode"):
            self.plot_pending = {"mode": batch["mode"]}
            if batch["mode"] == "single":
                self.plot_pending["values"] = []
            else:
                self.plot_pending["series"] = {}

        if batch["mode"] == "single":
            self.plot_pending["values"].extend(batch["values"])
            return

        for name, values in batch["series"].items():
            self.plot_pending["series"].setdefault(name, []).extend(values)

    def _emit_pending(self):
        if self.raw_pending:
            self.raw_received.emit(bytes(self.raw_pending))
            self.raw_pending.clear()

        if self.plot_pending:
            self.plot_batch_ready.emit(self.plot_pending)
            self.plot_pending = None
            self.pending_value_count = 0

# ========================================================
# ========================================================
# ========================================================
class SerialRxController(QtCore.QObject):
    raw_received = QtCore.pyqtSignal(bytes)
    plot_batch_ready = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, interval_ms=30):
        super().__init__()
        self.interval_ms = interval_ms
        self.thread = None
        self.worker = None
        self.terminal_enabled = False
        self.plot_enabled = False

    def is_running(self):
        return self.thread is not None and self.thread.isRunning()

    def start(self, ser, parser):
        if self.is_running():
            return

        self.thread = QtCore.QThread()
        self.worker = SerialRxWorker(ser, parser, self.interval_ms)
        self.worker.terminal_enabled = self.terminal_enabled
        self.worker.plot_enabled = self.plot_enabled
        self.worker._bind_rx_data_handler()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.raw_received.connect(self.raw_received)
        self.worker.plot_batch_ready.connect(self.plot_batch_ready)
        self.worker.failed.connect(self.failed)
        self.worker.failed.connect(self.worker.stop)
        self.worker.stopped.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.clear_worker)
        self.thread.start()

    def stop(self):
        # The worker loop owns the blocking read; setting running=False lets it exit on read timeout.
        if self.worker is not None:
            self.worker.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(1000)

    def set_terminal_enabled(self, enabled):
        self.terminal_enabled = enabled
        if self.worker is not None:
            self.worker.set_terminal_enabled(enabled)

    def set_plot_enabled(self, enabled):
        self.plot_enabled = enabled
        if self.worker is not None:
            self.worker.set_plot_enabled(enabled)

    def reset_plot_parser(self):
        if self.worker is not None:
            self.worker.reset_plot_parser()

    def apply_plot_config(self, config):
        if self.worker is not None:
            self.worker.apply_plot_config(config)

    def clear_worker(self):
        self.thread = None
        self.worker = None
# ========================================================
