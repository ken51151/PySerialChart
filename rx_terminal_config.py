from dataclasses import dataclass
from enum import IntEnum


class RxTerminalDisplayMode(IntEnum):
    ASCII = 0
    ASCII_HEX = 1
    HEX = 2


class RxTerminalFrameMode(IntEnum):
    TERMINATOR = 0
    FIXED_LENGTH = 1


RX_TERMINAL_TERMINATORS = {
    "LF": b"\n",
    "CR": b"\r",
    "CRLF": b"\r\n",
}


@dataclass(frozen=True)
class RxTerminalConfig:
    display_mode: RxTerminalDisplayMode = RxTerminalDisplayMode.ASCII
    frame_mode: RxTerminalFrameMode = RxTerminalFrameMode.TERMINATOR
    terminator_name: str = "LF"
    fixed_length: int = 16
    idle_timeout_ms: int = 120
    pending_limit: int = 4096

    @property
    def terminator(self):
        return RX_TERMINAL_TERMINATORS[self.terminator_name]
