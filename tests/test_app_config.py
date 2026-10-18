import os
import unittest
from dataclasses import replace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app_config import AppConfig
from plot_config import LINE_MODES, SEP_MODES, VALUE_MODES
from rx_terminal_config import RxTerminalDisplayMode
from SerialChart import SerialPlot
from plot_config import PlotConfig
from plot_settings_dialog import PlotSettingsDialog
from pyqtgraph.Qt import QtCore, QtWidgets


class AppConfigTests(unittest.TestCase):
    def test_defaults_are_independent(self):
        first, second = AppConfig(), AppConfig()
        first.tx.line_endings["Custom"] = "!"
        first.comm = replace(first.comm, port="COM8")
        self.assertNotIn("Custom", second.tx.line_endings)
        self.assertEqual(second.comm.port, "COM6")

    def test_default_parser_and_replacement(self):
        window = SerialPlot.__new__(SerialPlot)
        window.config = AppConfig()
        parser = window.create_rx_plot_parser()
        self.assertEqual(parser.feed(b"speed = 12\n"),
                         ({"mode": "multi_ascii", "series": {"speed": [12]}}, 1))
        window.config.plot = replace(
            window.config.plot, line_mode=LINE_MODES.SINGLE_LINE,
            sep_mode=SEP_MODES.LENGTH, value_mode=VALUE_MODES.BIN_I16_LE,
            packet_length=2,
        )
        parser = window.create_rx_plot_parser()
        self.assertEqual(parser.feed(b"\xfe\xff"),
                         ({"mode": "single", "values": [-2]}, 1))


class MainWindowConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = SerialPlot(AppConfig())

    @classmethod
    def tearDownClass(cls):
        cls.window.main_win.close()
        cls.window.plot_window.close()

    def test_existing_settings_update_app_config(self):
        window = self.window
        comm = replace(window.config.comm, baudrate=57600)
        self.assertTrue(window.apply_comm_config(comm))
        self.assertIs(window.config.comm, comm)
        self.assertEqual(window.ser.baudrate, 57600)
        tx = replace(window.config.tx, prefix_enabled=False)
        window.apply_tx_config(tx)
        self.assertIs(window.tx_controller.config, window.config.tx)
        window.set_rx_display_mode(RxTerminalDisplayMode.HEX)
        terminal = replace(window.config.terminal, idle_timeout_ms=250)
        window.apply_rx_terminal_config(terminal)
        self.assertIs(window.config.terminal, terminal)
        self.assertEqual(window.format_rx_terminal_line(b"A"), "HEX: 41\n")

    def test_application_icon_is_inherited_by_windows(self):
        icon = self.window.app.windowIcon()
        self.assertFalse(icon.isNull())
        self.assertFalse(icon.pixmap(32, 32).isNull())
        self.assertEqual(self.window.main_win.windowIcon().cacheKey(), icon.cacheKey())
        self.assertEqual(self.window.plot_window.windowIcon().cacheKey(), icon.cacheKey())

    def test_reconnect_uses_latest_config(self):
        window = SerialPlot.__new__(SerialPlot)
        window.config = AppConfig()
        window.ser = Mock(is_open=False)
        window.plot_window = Mock()
        window.timer = Mock()
        window.rx_controller = Mock()
        window.rx_controller.thread = None
        window.set_connected_ui = Mock()
        for baudrate, separator in ((19200, b"!"), (38400, b";")):
            window.config.comm = replace(window.config.comm, baudrate=baudrate)
            window.config.plot = replace(window.config.plot, separator=separator)
            window.connect_serial()
            parser = window.rx_controller.start.call_args.args[1]
            self.assertEqual(parser.sep, separator)
            self.assertEqual(window.ser.baudrate, baudrate)
            window.set_connected_ui.assert_called_with(True)
            window.disconnect_serial()

    def test_plot_settings_guard_and_worker_cleanup(self):
        window = self.window
        original_ser = window.ser
        window.ser = Mock(is_open=True)
        config = replace(window.config.plot, max_lines=11)
        before = window.config.plot
        try:
            window.update_plot_settings_enabled()
            self.assertFalse(window.plot_window.btn_settings.isEnabled())
            self.assertFalse(window.apply_plot_config(config))
            window.ser.is_open = False
            window.rx_controller.thread = Mock()
            window.update_plot_settings_enabled()
            self.assertFalse(window.apply_plot_config(config))
            self.assertIs(window.config.plot, before)
            window.rx_controller.clear_worker()
            self.assertTrue(window.plot_window.btn_settings.isEnabled())
        finally:
            window.ser = original_ser
            window.rx_controller.thread = None

    def test_plot_apply_preserves_curves_and_terminal(self):
        window = self.window
        window.apply_plot_config(PlotConfig())
        plot = window.plot_window
        plot.update_plot_batch({"mode": "multi_ascii", "series": {"speed": [1, 2]}})
        speed_curve = plot.curves_data["speed"]["curve"]
        window.rx_terminal.setPlainText("keep terminal")
        config = replace(window.config.plot, line_mode=LINE_MODES.SINGLE_LINE,
                         max_points=100, x_follow_width=50)
        plot.set_plot_running(True)
        self.assertTrue(window.apply_plot_config(config))
        self.assertFalse(plot.is_plot_running())
        self.assertEqual(list(plot.curves_data), ["speed", "default"])
        self.assertIs(plot.curves_data["speed"]["curve"], speed_curve)
        self.assertEqual(plot.curves_data["speed"]["buf"][:2].tolist(), [1, 2])
        self.assertEqual(len(plot.curves_data["default"]["buf"]), 100)
        self.assertEqual(plot.spin_x_width.maximum(), 100)
        self.assertEqual(plot.spin_x_width.value(), 100)
        self.assertTrue(plot.plot.legend.isVisible())
        self.assertEqual(window.rx_terminal.toPlainText(), "keep terminal")
        plot.update_plot_batch({"mode": "single", "values": [4, 5]})
        default_curve = plot.curves_data["default"]["curve"]
        self.assertTrue(window.apply_plot_config(config))
        self.assertEqual(plot.curves_data["default"]["idx"], 2)
        window.handle_plot_batch({"mode": "single", "values": [99]})
        self.assertEqual(plot.curves_data["default"]["idx"], 2)
        window.apply_plot_config(PlotConfig())
        self.assertIs(plot.curves_data["default"]["curve"], default_curve)
        self.assertEqual(plot.curves_data["default"]["buf"][:2].tolist(), [4, 5])
        self.assertTrue(plot.plot.legend.isVisible())
        plot.update_plot_batch({"mode": "multi_ascii", "series": {"new": [6]}})
        self.assertEqual(len(plot.plot.legend.items), 3)
        window.apply_plot_config(replace(PlotConfig(), separator=b"!"))
        buffer_before = plot.curves_data["speed"]["buf"]
        window.apply_plot_config(replace(window.config.plot, separator=b";"))
        self.assertIs(plot.curves_data["speed"]["buf"], buffer_before)
        # Shrinking capacity drops only oldest points, never the curve itself.
        window.apply_plot_config(replace(window.config.plot, max_points=1, x_follow_width=1, max_lines=1))
        self.assertIs(plot.curves_data["speed"]["curve"], speed_curve)
        self.assertEqual(plot.curves_data["speed"]["buf"].tolist(), [2])
        plot.update_plot_batch({"mode": "multi_ascii", "series": {"speed": [7], "ignored": [8]}})
        self.assertEqual(plot.curves_data["speed"]["buf"].tolist(), [7])
        self.assertNotIn("ignored", plot.curves_data)
        window.apply_plot_config(replace(window.config.plot, line_mode=LINE_MODES.SINGLE_LINE))
        self.assertIs(plot.curves_data["default"]["curve"], default_curve)
        plot.update_plot_batch({"mode": "single", "values": [9, 10]})
        self.assertEqual(plot.curves_data["default"]["buf"].tolist(), [10])
        window.apply_plot_config(PlotConfig())

    def test_plot_dialog_selection_validation_and_cancel(self):
        config = PlotConfig()
        dialog = PlotSettingsDialog(config)
        self.assertEqual(dialog.get_config(), config)
        self.assertEqual(dialog.ending_box.currentText(), "LF (0x0A)")
        self.assertFalse(dialog.offset_spin.isEnabled())
        binary_index = dialog.value_box.findData(VALUE_MODES.BIN_I16_LE)
        self.assertFalse(dialog.value_box.model().item(binary_index).isEnabled())
        dialog.line_box.setCurrentIndex(dialog.line_box.findData(LINE_MODES.SINGLE_LINE))
        dialog.value_box.setCurrentIndex(binary_index)
        dialog.length_radio.setChecked(True)
        dialog.length_spin.setValue(1)
        dialog.accept()
        self.assertEqual(dialog.result(), QtWidgets.QDialog.Rejected)
        self.assertIn("shorter", dialog.error_label.text())
        dialog.length_spin.setValue(2)
        dialog.accept()
        self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)
        self.assertEqual(dialog.get_config().value_mode, VALUE_MODES.BIN_I16_LE)
        dialog.reject()
        self.assertEqual(config, PlotConfig())

    def test_custom_ending_and_settings_button(self):
        dialog = PlotSettingsDialog(replace(PlotConfig(), separator=b"\x00\xff"))
        self.assertEqual(dialog.get_config().separator, b"\x00\xff")
        dialog.custom_ending.setText("0")
        with self.assertRaises(ValueError):
            dialog.get_config()
        dialog.custom_ending.setText("")
        with self.assertRaises(ValueError):
            dialog.get_config()
        dialog.custom_ending.setText("0D 0A")
        self.assertEqual(dialog.get_config().separator, b"\r\n")
        dialog.points_spin.setValue(100)
        self.assertEqual(dialog.get_config().x_follow_width, 100)
        dialog.reject()
        # Exercise the actual button -> signal -> dialog path and cancel it.
        QtCore.QTimer.singleShot(0, lambda: QtWidgets.QApplication.activeModalWidget().reject())
        before = self.window.config.plot
        self.window.plot_window.btn_settings.click()
        self.assertIs(self.window.config.plot, before)

    def test_plot_preview_updates_without_applying_settings(self):
        config = PlotConfig()
        dialog = PlotSettingsDialog(config)
        self.assertIn("speed", dialog.preview.toPlainText())
        dialog.line_box.setCurrentIndex(dialog.line_box.findData(LINE_MODES.SINGLE_LINE))
        dialog.value_box.setCurrentIndex(dialog.value_box.findData(VALUE_MODES.BIN_I16_LE))
        self.assertIn("4660", dialog.preview.toPlainText())
        dialog.value_box.setCurrentIndex(dialog.value_box.findData(VALUE_MODES.BIN_I16_BE))
        self.assertIn("13330", dialog.preview.toPlainText())
        dialog.ending_box.setCurrentIndex(3)
        dialog.custom_ending.setText("0")
        self.assertIn("complete HEX pairs", dialog.preview.toPlainText())
        dialog.custom_ending.setText("0D 0A")
        self.assertIn("13330", dialog.preview.toPlainText())
        dialog.length_radio.setChecked(True)
        dialog.length_spin.setValue(2147483647)
        self.assertIn("Preview unavailable", dialog.preview.toPlainText())
        self.assertEqual(dialog.get_config().packet_length, 2147483647)
        self.assertIs(dialog._base_config, config)
        dialog.reject()

    def test_plot_settings_presentation(self):
        dialog = PlotSettingsDialog(PlotConfig())
        self.assertFalse(hasattr(dialog, "width_spin"))
        self.assertTrue(dialog.preview.font().fixedPitch())
        self.assertEqual(dialog.preview.font().family(), "Consolas")
        self.assertTrue(dialog.ending_ascii.isReadOnly())
        self.assertEqual(dialog.ending_ascii.text(), "[LF]")
        dialog.ending_box.setCurrentIndex(2)
        self.assertEqual(dialog.custom_ending.text(), "0D 0A")
        self.assertEqual(dialog.ending_ascii.text(), "[CR][LF]")
        dialog.ending_box.setCurrentIndex(3)
        dialog.custom_ending.setText("41 42 00 0A")
        self.assertEqual(dialog.ending_ascii.text(), "AB[NUL][LF]")
        dialog.ending_box.setCurrentIndex(0)
        dialog.ending_box.setCurrentIndex(3)
        self.assertEqual(dialog.custom_ending.text(), "41 42 00 0A")
        dialog.custom_ending.setText("4")
        self.assertEqual(dialog.ending_ascii.text(), "Invalid HEX")
        for mode, symbol in ((VALUE_MODES.ASCII_INT, "int()"),
                             (VALUE_MODES.ASCII_FLOAT, "float()"),
                             (VALUE_MODES.BIN_I16_LE, "<h"),
                             (VALUE_MODES.BIN_U16_BE, ">H")):
            self.assertIn(symbol, dialog.value_box.itemText(dialog.value_box.findData(mode)))
        plot = self.window.plot_window
        self.assertEqual(plot.btn_settings.height(), plot.btn_clear.height())
        plot.spin_x_width.setValue(37)
        self.window.apply_plot_config(replace(self.window.config.plot, separator=b"!"))
        self.assertEqual(plot.spin_x_width.value(), 37)
        dialog.reject()


if __name__ == "__main__":
    unittest.main()
