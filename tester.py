import argparse
import random
import time
import serial

PORT = "COM7"
BAUD = 115200
MIN_INTERVAL_MS = 0.05
MAX_INTERVAL_MS = 0.2
LINE_ENDING = "\n"
CHANNELS = ("a", "b", "c")
RANDOM_MIN = -2000
RANDOM_MAX = 2000
MODE_ASCII_SINGLE = "ASCII_SINGLE"
MODE_ASCII_MULTI = "ASCII_MULTI"
MODE_HEX = "HEX"
MODES = (MODE_ASCII_SINGLE, MODE_ASCII_MULTI, MODE_HEX)
ENDIANS = ("little", "big")


def parse_args():
    parser = argparse.ArgumentParser(description="Send random ASCII serial data for SerialChart testing.")
    parser.add_argument("--port", default=PORT, help=f"Serial port, default: {PORT}")
    parser.add_argument("--baud", type=int, default=BAUD, help=f"Baud rate, default: {BAUD}")
    parser.add_argument("--min-ms", type=float, default=MIN_INTERVAL_MS, help="Minimum send interval in ms")
    parser.add_argument("--max-ms", type=float, default=MAX_INTERVAL_MS, help="Maximum send interval in ms")
    parser.add_argument("--mode", choices=MODES, default=MODE_ASCII_MULTI, help=f"Output mode, default: {MODE_ASCII_MULTI}")
    return parser.parse_args()


def make_packet(mode):
    if mode == MODE_ASCII_SINGLE:
        return f"{random.randint(RANDOM_MIN, RANDOM_MAX)}{LINE_ENDING}"

    if mode == MODE_ASCII_MULTI:
        channel = random.choice(CHANNELS)
        value = random.randint(RANDOM_MIN, RANDOM_MAX)
        return f"{channel} = {value}{LINE_ENDING}"

    if mode == MODE_HEX:
        # HEX mode sends a fixed-width signed integer so binary RX modes can be tested.
        HEX_LEN = 4
        HEX_ENDIAN = "little"
        return make_hex_packet(HEX_LEN, HEX_ENDIAN)

    raise ValueError(f"Unsupported mode: {mode}")


def make_hex_packet(hex_len, endian):
    value = random.randint(RANDOM_MIN, RANDOM_MAX)
    min_value = -(1 << (hex_len * 8 - 1))
    max_value = (1 << (hex_len * 8 - 1)) - 1

    # If the random value cannot fit in the configured signed width, skip this send.
    if value < min_value or value > max_value:
        return None

    return value.to_bytes(hex_len, byteorder=endian, signed=True)


def encode_packet(packet):
    if isinstance(packet, bytes):
        return packet
    return packet.encode("ascii")


def main():
    args = parse_args()
    if args.min_ms < 0 or args.max_ms < args.min_ms:
        raise ValueError("--max-ms must be greater than or equal to --min-ms, and both must be non-negative")
    
    print("Tester started with " + args.port)
    with serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=0) as ser:
        print(f"Sending random {args.mode} data to {args.port} at {args.baud} baud. Press Ctrl+C to stop.")
        try:
            while True:
                packet = make_packet(args.mode)
                if packet is not None:
                    ser.write(encode_packet(packet))
                # print(packet, end="")
                interval = random.uniform(args.min_ms, args.max_ms) / 1000.0
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
