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

## Usage

Run the script:

```bash
python SerialChart.py
```

Click `Running` to start reading and plotting data. Use `AutoY` to fit the Y-axis to the current data range.
