import math
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets


ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


# ========================================================
class PlotWindow(QtWidgets.QMainWindow):
    hidden = QtCore.pyqtSignal()
    clear_requested = QtCore.pyqtSignal()
    plot_running_changed = QtCore.pyqtSignal(bool)

    def __init__(
        self,
        max_points,
        max_lines,
        x_follow_width_default,
        line_mode,
        colors,
        debug_line_enabled=False,
        parent=None,
    ):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_QuitOnClose, False)
        self.max_points = max_points
        self.max_lines = max_lines
        self.x_follow_width_default = x_follow_width_default
        self.line_mode = line_mode
        self.colors = colors
        self.debug_line_enabled = debug_line_enabled

        self.max_current_idx = 0
        self.curves_data = {}
        self.validation_sin_phase = 0.0
        self.icon_plot_start = QtGui.QIcon(str(ICON_DIR / "plot_start.svg"))
        self.icon_plot_pause = QtGui.QIcon(str(ICON_DIR / "plot_pause.svg"))

        self.setWindowTitle("SerialChart Plot")
        self.resize(800, 600)

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QtWidgets.QVBoxLayout(self.central_widget)

        self._build_controls()
        self._build_plot()
        self._init_curves()

    # ========================================================
    def _build_controls(self):
        self.controls_layout = QtWidgets.QHBoxLayout()
        self.btn_plot_run = QtWidgets.QToolButton()
        self.btn_plot_run.setCheckable(True)
        self.btn_plot_run.setChecked(False)
        self.btn_plot_run.setFixedSize(46, 38)
        self.btn_plot_run.setIconSize(QtCore.QSize(30, 30))
        self.btn_plot_run.setIcon(self.icon_plot_pause)
        self.btn_plot_run.setToolTip("Plot paused")
        self.btn_plot_run.setStyleSheet(
            "QToolButton { border: 1px solid #9AA0A6; border-radius: 4px; background: transparent; padding: 0px; margin: 0px; }"
            "QToolButton:checked { background: #DFF5E3; border: 1px solid #1FA64A; padding: 0px; margin: 0px; }"
            "QToolButton:pressed { padding: 0px; }"
        )
        self.btn_plot_run.toggled.connect(self.set_plot_running)

        self.btn_cursor = QtWidgets.QCheckBox("&Cursor")
        self.btn_cursor.toggled.connect(self.cursor_toggle)
        self.btn_rectMode = QtWidgets.QCheckBox("&RectMode")
        self.btn_rectMode.toggled.connect(self.rect_mode_toggle)
        self.btn_autoY = QtWidgets.QPushButton("Auto&Y")
        self.btn_autoY.setFixedSize(80, 30)
        self.btn_autoY.clicked.connect(self.auto_y)
        self.btn_followX = QtWidgets.QCheckBox("Follow&X")
        self.btn_followX.setChecked(True)
        self.btn_followX.toggled.connect(self.follow_x_toggle)
        self.spin_x_width = QtWidgets.QSpinBox()
        self.spin_x_width.setRange(1, self.max_points)
        self.spin_x_width.setValue(self.x_follow_width_default)
        self.spin_x_width.setSuffix(" pts")
        self.spin_x_width.setFixedSize(120, 30)
        self.spin_x_width.setSingleStep(100)
        self.spin_x_width.valueChanged.connect(self.update_x_range)
        self.btn_clear = QtWidgets.QPushButton("&Clear")
        self.btn_clear.setFixedSize(80, 30)
        self.btn_clear.clicked.connect(self.clear_data)

        self.controls_layout.addWidget(self.btn_plot_run)
        self.controls_layout.addWidget(self.btn_cursor)
        self.controls_layout.addWidget(self.btn_rectMode)
        self.controls_layout.addWidget(self.btn_autoY)
        self.controls_layout.addWidget(self.btn_followX)
        self.controls_layout.addWidget(self.spin_x_width)
        self.controls_layout.addWidget(self.btn_clear)
        self.controls_layout.addStretch()
        self.layout.addLayout(self.controls_layout)

    # ========================================================
    def _build_plot(self):
        self.win = pg.GraphicsLayoutWidget()
        self.win.setMinimumHeight(300)
        self.plot = self.win.addPlot()
        self.plot.showGrid(x=True, y=True)
        self.plot.setYRange(-2000, 2000, padding=0.05)
        self.plot.setXRange(0, self.x_follow_width_default, padding=0)
        self.layout.addWidget(self.win)

        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen='w')
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen='w')
        self.label = pg.TextItem(anchor=(1,1), color='y')
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)
        self.plot.addItem(self.label)
        self.mouse_proxy = None
        self.cursor_hide()

    # ========================================================
    def _init_curves(self):
        if self.line_mode == "single":
            buf = np.full(self.max_points, np.nan)
            curve = self.plot.plot(pen=self.colors[0])
            curve.setData(buf, connect="finite")
            self.curves_data["default"] = {"buf": buf, "idx": 0, "curve": curve}
        elif self.line_mode == "multi_ascii":
            self.plot.addLegend()

    # ========================================================
    def closeEvent(self, event):
        event.ignore()
        if self.is_plot_running():
            self.set_plot_running(False)
        self.hide()
        self.hidden.emit()

    # ========================================================
    def is_plot_running(self):
        return self.btn_plot_run.isChecked()

    def set_plot_running(self, running):
        if self.btn_plot_run.isChecked() != running:
            self.btn_plot_run.setChecked(running)
            return

        if running:
            self.btn_plot_run.setIcon(self.icon_plot_start)
            self.btn_plot_run.setToolTip("Plot running")
        else:
            self.btn_plot_run.setIcon(self.icon_plot_pause)
            self.btn_plot_run.setToolTip("Plot paused")
        self.plot_running_changed.emit(running)

    # ========================================================
    def update_line_single_values(self, values):
        curve_info = self.curves_data.get("default")

        try:
            if not values:
                return

            self._append_curve_values(curve_info, values)
            self.max_current_idx = curve_info["idx"]
            v_len = self.max_current_idx
            curve_info["curve"].setData(curve_info["buf"][:v_len], connect="finite")
            self.update_x_range()

        except ValueError as e:
            print(f"Data conversion error: {e}")

    # ========================================================
    def _get_or_create_curve(self, name):
        if name not in self.curves_data:
            if len(self.curves_data) >= self.max_lines:
                return None

            buf = np.full(self.max_points, np.nan)
            color = self.colors[len(self.curves_data) % len(self.colors)]

            curve = self.plot.plot(pen=color, name=name)
            self.curves_data[name] = {"buf": buf, "idx": 0, "curve": curve}

        return self.curves_data[name]

    # ========================================================
    def _append_curve_value(self, curve_info, value):
        buf = curve_info["buf"]
        idx = curve_info["idx"]
        if idx < self.max_points:
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

        if num_new >= self.max_points:
            buf[:] = values[-self.max_points:]
            curve_info["idx"] = self.max_points
        elif idx + num_new <= self.max_points:
            buf[idx : idx + num_new] = values
            curve_info["idx"] += num_new
        else:
            overflow = idx + num_new - self.max_points
            keep_len = idx - overflow
            buf[:keep_len] = buf[overflow:idx]
            buf[keep_len:] = values
            curve_info["idx"] = self.max_points

    # ========================================================
    def update_line_ascii_series(self, series):
        try:
            for name, values in series.items():
                curve_info = self._get_or_create_curve(name)
                if not curve_info:      continue
                self._append_curve_values(curve_info, values)

            if self.curves_data:
                self.max_current_idx = max(info["idx"] for info in self.curves_data.values())

            for name in series:
                if name not in self.curves_data:
                    continue
                info = self.curves_data[name]
                v_len = self.max_current_idx
                info["curve"].setData(info["buf"][:v_len], connect="finite")

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
    def update_validation_sin(self):
        valid_points = 5
        phase_step = 0.08
        amplitude = 24689
        offset = 7777

        if self.line_mode == "single":
            curve_info = self.curves_data.get("default")
        else:
            curve_info = self._get_or_create_curve("sin")

        if not curve_info:
            return

        for _ in range(valid_points):
            value = (math.sin(self.validation_sin_phase) * amplitude) + offset
            self._append_curve_value(curve_info, value)
            self.validation_sin_phase += phase_step

        self.max_current_idx = max(info["idx"] for info in self.curves_data.values())
        v_len = self.max_current_idx
        curve_info["curve"].setData(curve_info["buf"][:v_len], connect="finite")

        if self.max_current_idx > 0:
            self.update_x_range()

    # ========================================================
    def update_validation_data(self):
        if self.debug_line_enabled:
            self.update_validation_sin()

    # ========================================================
    def mouseMoved(self, evt):
        pos = evt[0]
        if self.plot.sceneBoundingRect().contains(pos):
            mousePoint = self.plot.vb.mapSceneToView(pos)
            self.vLine.setPos(mousePoint.x())
            self.hLine.setPos(mousePoint.y())
            self.label.setText(f"X: {mousePoint.x():.1f}\nY: {mousePoint.y():.2f}")
            self.label.setPos(mousePoint.x(), mousePoint.y())

    # ========================================================
    def rect_mode_toggle(self, checked):
        if checked:     self.plot.vb.setMouseMode(pg.ViewBox.RectMode)
        else:           self.plot.vb.setMouseMode(pg.ViewBox.PanMode)

    # ========================================================
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

    # ========================================================
    def cursor_toggle(self, checked):
        if checked:     self.cursor_show()
        else:           self.cursor_hide()

    def cursor_show(self):
        self.vLine.show()
        self.hLine.show()
        self.label.show()
        if self.mouse_proxy is None:
            self.mouse_proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=30, slot=self.mouseMoved)

    def cursor_hide(self):
        self.vLine.hide()
        self.hLine.hide()
        self.label.hide()
        if self.mouse_proxy is not None:
            self.mouse_proxy.disconnect()
            self.mouse_proxy = None

    # ========================================================
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
            idx = min(info["idx"], self.max_points)
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

    # ========================================================
    def clear_data(self):
        self.max_current_idx = 0
        self.clear_requested.emit()

        for name, info in self.curves_data.items():
            info["buf"].fill(np.nan)
            info["idx"] = 0
            info["curve"].setData(info["buf"])

        self.update_x_range()
