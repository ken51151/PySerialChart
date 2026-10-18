from dataclasses import dataclass, field

from plot_config import PlotConfig
from rx_terminal_config import RxTerminalConfig
from serial_comm import SerialCommConfig
from serial_tx import DEFAULT_TX_CONFIG, TX_WRITE_TIMEOUT, TxConfig


def _default_comm_config():
    return SerialCommConfig(port="COM6", baudrate=115200, write_timeout=TX_WRITE_TIMEOUT)


def _default_tx_config():
    # Each application owns its mutable line-ending mapping.
    return TxConfig(
        line_endings=dict(DEFAULT_TX_CONFIG.line_endings),
        prefix_enabled=DEFAULT_TX_CONFIG.prefix_enabled,
    )


@dataclass
class AppConfig:
    """Application-owned settings; replace snapshots through the UI apply methods."""

    comm: SerialCommConfig = field(default_factory=_default_comm_config)
    tx: TxConfig = field(default_factory=_default_tx_config)
    terminal: RxTerminalConfig = field(default_factory=RxTerminalConfig)
    plot: PlotConfig = field(default_factory=PlotConfig)
    rx_interval_ms: int = 30
