# SerialChart

SerialChart is a lightweight Python tool for real-time serial data plotting. It reads numeric data from a COM port and displays it as live curves for quick signal monitoring and debugging.

## Features

- Real-time COM port data plotting
- Single-line and multi-line ASCII data support
- Configurable packet separation by custom ending or fixed length
- ASCII and binary value conversion modes
- Up to 10 dynamic curves in multi-line ASCII mode
- Cursor mode for inspecting X/Y values
- Manual Y-axis auto-scaling
- Optional X-axis follow mode with configurable display width
- Text transmit input with command history, Tab completion, line endings, and HEX TX support
- Non-blocking TX worker thread to keep the UI responsive while sending
- Sine-wave validation function for plot testing

## Requirements

```bash
pip install PyQt5 pyqtgraph pyserial numpy
```

## Configuration

Most settings are defined near the top of `SerialChart.py`.

```python
PORT = "COM6"
BAUD = 115200
MAX_POINTS = 50000
UPDATE_INTERVAL = 30
X_FOLLOW_WIDTH_DEFAULT = 2000
```

Data parsing can be adjusted with:

```python
SEP_MODE
LINE_MODE
VALUE_MODE
CUSTOM_END
LEN_END
VAL_OFFSET
```

## Data Format

### Single-Line Mode

Each received packet is converted into one numeric value and plotted as a single curve.

### Multi-Line ASCII Mode

Expected format:

```text
name = value
```

Example:

```text
temperature = 25
pressure = 1013
speed = 120
```

Each unique name creates or updates its own curve.

## Validation

A sine-wave validation function is available for checking plot behavior without external serial data.

In `update()`:

```python
self.update_validation_sin()
```

Comment this line out when validation is not needed.

## Controls

- `Running`: start or stop serial reading
- `Cursor`: show or hide the X/Y cursor
- `RectMode`: switch the mouse interaction mode
- `AutoY`: fit the Y-axis to the current data range
- `FollowX`: keep the plot following the newest data
- `X Width`: set the visible X-axis width while `FollowX` is enabled
- `Clear`: reset all curve data
- `TX`: type text and press Enter to send it through the COM port
- `TX history`: press Up/Down to browse previous TX commands, or choose from the drop-down list
- `TX completion`: press Tab to complete from TX history
- `HEX TX`: type `hex: 01 02 0A FF` to send raw bytes without appending a line ending
- `Line ending`: choose the text terminator for normal text TX data: `None`, `LF`, `CR`, or `CRLF`

## Usage

Run the script:

```bash
python SerialChart.py
```

Click `Running` to start reading and plotting data. Use `AutoY` to fit the Y-axis to the current data range.

## Changelog

### 0.3 (2026/05/28)

- Added editable TX command history with Up/Down navigation and mouse-selectable history.
- Added Tab completion for TX history commands.
- Added raw HEX transmit mode using the `hex:` prefix, such as `hex: 01 02 0A FF`.
- Prevented empty TX input from sending only a line ending.
- Moved TX handling into `serial_tx.py`, including TX input widgets, HEX parsing, and TX worker/controller logic.
- Added non-blocking TX thread/controller so serial writes do not freeze the UI.
- Added TX timeout/error reporting with the original TX string.
- Added a status bar with COM state and TX status messages.
- Updated UI sizing, font family, TX row layout, and plot minimum height.
- Added `.gitignore` for Python cache and local environment files.

### 0.2 (2026/05/27)

- Added version constants and versioned window title.
- Added configurable X-axis follow mode.
- Added text transmit input with selectable line ending.
- Optimized multi-line ASCII updates by batching new values per curve before updating buffers.
- Changed Y-axis auto-scaling to apply once instead of continuously auto-ranging.
- Added README documentation.

### 0.1

- Initial serial plotting tool.
- Added COM port reading, packet parsing, single-line mode, multi-line ASCII mode, cursor inspection, and basic plot controls.
