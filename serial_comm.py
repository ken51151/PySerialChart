from dataclasses import dataclass

import serial


# ========================================================
@dataclass(frozen=True)
class SerialCommConfig:
    port: str
    baudrate: int
    timeout: float = 0.1
    write_timeout: float = 0
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False


# ========================================================
def create_serial_port(config):
    # Do not pass port into serial.Serial(); keeping it closed lets the UI own open/close.
    ser = serial.Serial(
        baudrate=config.baudrate,
        bytesize=config.bytesize,
        parity=config.parity,
        stopbits=config.stopbits,
        timeout=config.timeout,
        write_timeout=config.write_timeout,
        xonxoff=config.xonxoff,
        rtscts=config.rtscts,
        dsrdtr=config.dsrdtr,
    )
    ser.port = config.port
    return ser


# ========================================================
def apply_serial_config(ser, config):
    # pyserial can change some fields while open, but reconnect-only keeps RX/TX threads predictable.
    if ser.is_open:
        raise serial.SerialException("Cannot apply serial config while COM is open")

    ser.port = config.port
    ser.baudrate = config.baudrate
    ser.bytesize = config.bytesize
    ser.parity = config.parity
    ser.stopbits = config.stopbits
    ser.timeout = config.timeout
    ser.write_timeout = config.write_timeout
    ser.xonxoff = config.xonxoff
    ser.rtscts = config.rtscts
    ser.dsrdtr = config.dsrdtr
