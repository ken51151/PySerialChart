# TODO

Current work and historical decisions for SerialChart. See [README](README.md) for usage and [Changelog](CHANGELOG.md) for version history.

## Features

- [ ] Add terminal timestamps.
- [ ] Support `h:` as an alias for `hex:` in TX input.
- [ ] Add a UI option to enable or disable TX prefix parsing.
- [ ] Add predefined TX commands loaded from an external file.
- [ ] Support TX command prefixes such as `c:` or `cmd:` to send predefined commands.
- [ ] Store selected settings in an external `.ini` file.
- [ ] Let the program choose an existing `.ini` in the current directory or create a new one on startup.
- [ ] Expand `tester.py` modes and options as binary RX testing needs grow; ASCII_SINGLE, ASCII_MULTI and HEX already exist.
- [ ] Add optional file-based error logging for troubleshooting releases without a console window; not required for packaging or the initial release.

## Performance and Known Issues

- [ ] Replace direct cross-thread RX parser control with a command queue if RX pipeline complexity grows.
- [ ] Benchmark RX parser performance against the previous timer-based `read_all()` path.
- [ ] Consider replacing parser `strip()` calls with index-based trim if ASCII parsing becomes a bottleneck.
- [ ] Consider using a circular buffer for plot data to avoid large NumPy array moves after buffers are full.
- [ ] Review pyqtgraph redraw performance, including downsampling and clip-to-view options, for high-rate data.
- [ ] Investigate X-axis behavior when a curve reaches its maximum point capacity. Original report: 線段超過最大值時，X軸不會跳動的詭異情況.

## Completed

- [x] Keep an editable TX/RX terminal in the main window; show TX commands with a `>>` prefix.
- [x] Add ASCII, ASCII + HEX and HEX terminal display modes.
- [x] Add terminal framing by ending or fixed length, idle timeout and pending-buffer information.
- [x] Split plot features into an independent window with its own pause/resume control.
- [x] Enable plot parsing through the running state; closing the plot window pauses it without deleting its curves.
- [x] Move plot parser settings into UI controls, with sample-data parsing previews.
- [x] Add an independent COM port settings window for port, baud rate, timeout and related serial options.
- [x] Redesign the main window top controls as a toolbar with actions and icons; add a menu bar.
- [x] Improve RX thread pipeline control for terminal and plot consumers.
- [x] Add a formal API for replacing or applying RX parser config from UI settings.
- [x] Centralize application settings in `AppConfig`.
- [x] Add About / Licenses, an application icon and automated tests.
- [x] Add an isolated Windows onedir build workflow with ZIP, checksums and frozen-EXE smoke tests.

## Historical Decisions

- The original independent-terminal-window proposal was replaced by a terminal that stays in the main window. Only Plot opens as an additional window.
- The original combined terminal-options task is split above: display modes and framing are complete; timestamps remain pending.
- Plot visibility alone does not enable parsing. Its running state controls parsing, and showing the window does not automatically resume it.
- COM and plot configuration changes are restricted to a closed COM connection; seamless live parser switching is not a current goal.

## Before Public Release

- [ ] Test the extracted Windows package on a clean machine with real COM TX/RX.
- [ ] Set the intended version and tag, then rebuild from the matching source.
- [ ] Complete the corresponding-source and bundled-license checklist in [SOURCE.md](SOURCE.md) before uploading release assets.
