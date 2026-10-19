"""Packaging entry point; normal startup uses the existing application."""

import json
import os
from pathlib import Path
import sys
import traceback

os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"


def smoke_test(report_path):
    # This mode never opens a COM port and is only invoked by the build script.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    report = {"ok": False}
    window = None
    try:
        from SerialChart import SerialPlot, VERSION, ICON_DIR
        from about_dialog import AboutDialog
        from plot_settings_dialog import PlotSettingsDialog
        from port_settings_dialog import PortSettingsDialog
        from rx_terminal_settings_dialog import RxTerminalSettingsDialog
        from pyqtgraph.Qt import QtGui

        window = SerialPlot()
        if window.ser.is_open:
            raise RuntimeError("COM unexpectedly opened during smoke test")
        for path in ICON_DIR.iterdir():
            if QtGui.QIcon(str(path)).pixmap(32, 32).isNull():
                raise RuntimeError(f"Cannot render icon: {path.name}")
        settings = PlotSettingsDialog(window.config.plot, window.plot_window)
        if "Sample stream" not in settings.preview.toPlainText():
            raise RuntimeError("Plot preview failed")
        port = PortSettingsDialog(window.config.comm, window.main_win)
        terminal = RxTerminalSettingsDialog(window.config.terminal, parent=window.main_win)
        about = AboutDialog("SerialChart", VERSION, window.main_win)
        for index in range(about.license_selector.count()):
            about.license_selector.setCurrentIndex(index)
            if "Unable to read license document:" in about.license_text.toPlainText():
                raise RuntimeError(about.license_text.toPlainText())
        window.main_win.show()
        window.plot_window.show()
        window.plot_window.update_plot_batch({"mode": "multi_ascii", "series": {"smoke": [1, 2, 3]}})
        window.app.processEvents()
        if window.plot_window.grab().isNull():
            raise RuntimeError("Plot could not render")
        for dialog in (settings, port, terminal, about):
            dialog.show()
            window.app.processEvents()
            if dialog.grab().isNull():
                raise RuntimeError("Dialog could not render")
            dialog.close()
        report.update(ok=True, version=VERSION, license_documents=about.license_selector.count())
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if window is not None:
            window.plot_window.close()
            window.main_win.close()
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        sys.exit(smoke_test(sys.argv[2]))
    from SerialChart import SerialPlot
    SerialPlot().run()
