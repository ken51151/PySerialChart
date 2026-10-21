from dataclasses import dataclass
from enum import IntEnum

from serial_rx import RxParserConfig

# ===== 圖表/接收模式設定 =====
MAX_POINTS = 50000              # curve ring buffer size
MAX_LINES = 10                  # max curve (only multi line mode)

# @@@@@ 資料分段方式, 特定資料 or 固定長度
class SEP_MODES(IntEnum):
    CUSTOM_END = 1          # 特定資料分段, 常用在ASCII格式, 可搭配binary使用，但注意數值可能跟結尾符相撞
    LENGTH = 2              # 固定長度分段, 常用在binary格式
SEP_MODE = SEP_MODES.CUSTOM_END

# @@@@@ 線段模式
class LINE_MODES(IntEnum):
    SINGLE_LINE = 1         # 單線段模式, 通常無冗餘資料, 效率上最高
    MULTI_LINE_ASCII = 2    # 多線段模式, 會將各封包再次分析在匹配到各線段, ASCII資料格式為 "<name> = <value>", 最多10條
LINE_MODE = LINE_MODES.MULTI_LINE_ASCII
colors = ['y', 'g', 'r', 'c', 'm', 'w', 'b', (255,165,0), (128,0,128), (0,255,127)]

# @@@@@ 數值處理方式, ASCII or binary
class VALUE_MODES(IntEnum):
    # ASCII
    ASCII_INT = 1           # ASCII interger
    ASCII_FLOAT = 2         # ASCII float
    # binary with Little-endian
    BIN_U8 = 10
    BIN_I8 = 11
    BIN_U16_LE = 12
    BIN_I16_LE = 13
    BIN_U32_LE = 14
    BIN_I32_LE = 15
    BIN_U64_LE = 16
    BIN_I64_LE = 17
    # binary with big-endian
    BIN_U16_BE = 20
    BIN_I16_BE = 21
    BIN_U32_BE = 22
    BIN_I32_BE = 23
    BIN_U64_BE = 24
    BIN_I64_BE = 25
    # binary float/double (IEEE 754)
    BIN_FLOAT  = 40
    BIN_DOUBLE = 41
VALUE_MODE = VALUE_MODES.ASCII_INT

# @@@@@ 特定資料分段設定
ASCII_CR = "\r"             # CR: 0x0D, Carriage Return
ASCII_LF = "\n"             # LF: 0x0A, Line Feed
ASCII_CRLR = "\r\n"         # CRLF: [0D,0A]
CUSTOM_END = ASCII_LF       # 僅在CUSTOM_END模式下有效, 特定資料進行分段

# @@@@@ 固定長度分段設定
LEN_END = 5                 # 僅在LENGTH模式下有效

# @@@@@ General Setting
VAL_OFFSET = 0              # 數值分段後的固定位移, 除了MULTI_LINE_ASCII以外的所有模式都會受影響, 不會檢查是否溢出
SEP = CUSTOM_END.encode()   # 預先計算分隔符避免即時運算的花費



# --------------------------------------------------------
# table for value mode
VALUE_CONFIG_TABLE = {
    VALUE_MODES.ASCII_INT:  ('ASCII', int,   4),    # ASCII mode
    VALUE_MODES.ASCII_FLOAT:('ASCII', float, 4),
	VALUE_MODES.BIN_U8:     ('BIN', '<B',  1),    # binary mode
    VALUE_MODES.BIN_I8:     ('BIN', '<b',  1),
    VALUE_MODES.BIN_U16_LE: ('BIN', '<H',  2),
    VALUE_MODES.BIN_I16_LE: ('BIN', '<h',  2),
    VALUE_MODES.BIN_U32_LE: ('BIN', '<I',  4),
    VALUE_MODES.BIN_I32_LE: ('BIN', '<i',  4),
    VALUE_MODES.BIN_U64_LE: ('BIN', '<Q',  8),
    VALUE_MODES.BIN_I64_LE: ('BIN', '<q',  8),
    VALUE_MODES.BIN_U16_BE: ('BIN', '>H',  2),
    VALUE_MODES.BIN_I16_BE: ('BIN', '>h',  2),
    VALUE_MODES.BIN_U32_BE: ('BIN', '>I',  4),
    VALUE_MODES.BIN_I32_BE: ('BIN', '>i',  4),
    VALUE_MODES.BIN_U64_BE: ('BIN', '>Q',  8),
    VALUE_MODES.BIN_I64_BE: ('BIN', '>q',  8),
    VALUE_MODES.BIN_FLOAT:  ('BIN', '<f',  4),
    VALUE_MODES.BIN_DOUBLE: ('BIN', '<d',  8),
}


@dataclass(frozen=True)
class PlotConfig:
    max_points: int = MAX_POINTS
    max_lines: int = MAX_LINES
    x_follow_width: int = 2000
    colors: tuple = tuple(colors)
    debug_line_enabled: bool = False
    sep_mode: SEP_MODES = SEP_MODE
    line_mode: LINE_MODES = LINE_MODE
    value_mode: VALUE_MODES = VALUE_MODE
    separator: bytes = SEP
    packet_length: int = LEN_END
    offset: int = VAL_OFFSET

    def validate(self):
        if self.sep_mode not in tuple(SEP_MODES) or self.line_mode not in tuple(LINE_MODES):
            raise ValueError("Invalid plot mode.")
        if self.value_mode not in VALUE_CONFIG_TABLE:
            raise ValueError("Invalid value format.")
        if self.max_points < 1 or self.max_lines < 1 or not self.colors:
            raise ValueError("Point and line limits must be positive; colors must not be empty.")
        if not 1 <= self.x_follow_width <= self.max_points:
            raise ValueError("X width must be between 1 and the point limit.")
        if self.packet_length < 1 or self.offset < 0:
            raise ValueError("Packet length must be positive and offset must not be negative.")
        if not isinstance(self.separator, bytes) or not self.separator:
            raise ValueError("Ending must contain at least one byte.")
        value_type, _, value_size = VALUE_CONFIG_TABLE[self.value_mode]
        if self.line_mode == LINE_MODES.MULTI_LINE_ASCII and value_type != "ASCII":
            raise ValueError("Multi-line ASCII requires an ASCII value format.")
        if self.sep_mode == SEP_MODES.LENGTH and self.line_mode == LINE_MODES.SINGLE_LINE:
            if value_type == "BIN" or self.offset:
                if self.packet_length < self.offset + value_size:
                    raise ValueError("Packet length is shorter than offset plus value size.")

    def to_parser_config(self):
        sep_modes = {SEP_MODES.CUSTOM_END: "custom_end", SEP_MODES.LENGTH: "length"}
        line_modes = {LINE_MODES.SINGLE_LINE: "single", LINE_MODES.MULTI_LINE_ASCII: "multi_ascii"}
        sep_mode = sep_modes.get(self.sep_mode)
        line_mode = line_modes.get(self.line_mode)
        if sep_mode is None:
            print("ERROR, invalid SEP_MODE!!!")
        if line_mode is None:
            print("ERROR, invalid LINE_MODE!!!")
        value_config = VALUE_CONFIG_TABLE.get(self.value_mode)
        if value_config is None:
            print("ERROR, invalid VALUE_MODE!!!")
            value_config = ("ASCII", int, 4)
        value_type, value_fmt, value_size = value_config
        # Translate settings only when constructing/applying a parser, not per packet.
        return RxParserConfig(
            sep_mode, line_mode, value_type, value_fmt, value_size,
            self.separator, self.packet_length, self.offset,
        )
