"""Bounded sample data and presentation for the plot settings dialog only."""

from dataclasses import asdict
from html import escape
import struct

from serial_rx import RxPlotParser


PREVIEW_PACKET_LIMIT = 256
PREVIEW_ENDING_LIMIT = 32


def make_sample_data(config):
    fixed = config.sep_mode == "length"
    if config.offset > PREVIEW_PACKET_LIMIT - 16 or (fixed and config.len_end > PREVIEW_PACKET_LIMIT):
        raise ValueError("Preview unavailable: sample packets are limited to 256 bytes. Settings can still be applied.")
    if not fixed and len(config.sep) > PREVIEW_ENDING_LIMIT:
        raise ValueError("Preview unavailable: sample endings are limited to 32 bytes. Settings can still be applied.")

    packets = []
    for index in range(2):
        if config.value_type == "BIN":
            if config.value_fmt[-1] in "fd":
                value = struct.pack(config.value_fmt, (1.25, -2.5)[index])
            else:
                # Same bytes for signed/unsigned and LE/BE, so their differences stay visible.
                value = (b"\x34\x12\x03\x04\x05\x06\x07\x08" if index == 0 else b"\xfe" + b"\xff" * 7)[:config.value_size]
            prefix = (b"\xaa\xbb" * ((config.offset + 1) // 2))[:config.offset]
            packet = prefix + value
            padding = b"\x00"
        else:
            value = ((b"123", b"-45") if config.value_fmt is int else (b"1.25", b"-2.5"))[index]
            name = (b"speed=", b"temp=")[index] if config.line_mode == "multi_ascii" else b""
            prefix = b"~" * config.offset
            if fixed:
                available = config.len_end - len(name) - len(prefix)
                if available < len(value) and name:
                    name = (b"x=", b"y=")[index]
                    available = config.len_end - len(name) - len(prefix)
                if available < len(value):
                    value = (b"1", b"2")[index]
            packet = name + prefix + value
            padding = b" "
        if fixed:
            # Very short multi-line frames may be invalid; show what the real parser ignores.
            packets.append(packet[:config.len_end].ljust(config.len_end, padding))
        else:
            packets.append(packet + config.sep)
    return b"".join(packets)


def format_bytes(data, binary):
    if binary:
        return data.hex(" ").upper()
    names = {0: "[NUL]", 9: "[TAB]", 10: "[LF]", 13: "[CR]", 32: "[SP]"}
    return "".join(names.get(byte, chr(byte) if 33 <= byte <= 126 else f"[{byte:02X}]") for byte in data)


def _value_range(packet, config):
    start, end = 0, len(packet)
    if config.line_mode == "multi_ascii":
        eq = packet.find(b"=")
        if eq < 0:
            return 0, 0
        value = packet[eq + 1:]
        start = eq + 1 + len(value) - len(value.lstrip())
        end = eq + 1 + len(value.rstrip())
    start = min(start + config.offset, end)
    if config.value_type == "BIN" or config.offset:
        end = min(start + config.value_size, end)
    return start, end


def build_preview_html(plot_config):
    plot_config.validate()
    config = plot_config.to_parser_config()
    raw = make_sample_data(config)
    parser = RxPlotParser(**asdict(config))
    # Use the same bound split/parse functions as feed(), without changing the RX parser.
    packets = parser.split_packets(raw)
    binary = config.value_type == "BIN"

    def shown(data):
        return escape(format_bytes(data, binary))

    raw_html = shown(raw)
    if config.sep_mode == "custom_end":
        ending = f'<span style="color:#76501B;background-color:#FFF0CC">&nbsp;{shown(config.sep)}&nbsp;</span>'
        raw_html = ending.join(shown(part) for part in raw.split(config.sep))
        framing = f"Ending: {shown(config.sep)} (removed)"
    else:
        raw_html = " <b>|</b> ".join(shown(packet) for packet in packets)
        framing = f"Fixed length: {config.len_end} bytes"

    rows = []
    for index, packet in enumerate(packets, 1):
        start, end = _value_range(packet, config)
        batch, _ = parser.parse_packets([packet])
        if batch is None:
            result = '<span style="color:#B3261E">Ignored: invalid value or missing name=value</span>'
        elif batch["mode"] == "single":
            result = escape(str(batch["values"][0]))
        else:
            result = "<br>".join(f"{escape(name)} &rarr; {escape(str(values[0]))}" for name, values in batch["series"].items())
        parts = [
            f'<span style="color:#687078">{shown(packet[:start])}</span>',
            f'<span style="color:#14532D;background-color:#BBF7D0"><b>{shown(packet[start:end])}</b></span>',
            f'<span style="color:#687078">{shown(packet[end:])}</span>',
        ]
        packet_html = (" " if binary else "").join(part for part, data in zip(parts, (packet[:start], packet[start:end], packet[end:])) if data)
        rows.append(f"<tr><td>{index}</td><td>{packet_html}</td><td>{result}</td></tr>")

    residual = f"<p>Pending: {shown(parser.residual)}</p>" if parser.residual else ""
    return (
        '<html><body>'
        f'<p><b>Sample stream ({"HEX bytes" if binary else "ASCII"})</b><br>{raw_html}</p>'
        f'<p>{framing} &nbsp; Offset: {config.offset} bytes</p>'
        '<table cellspacing="4" cellpadding="3">'
        '<tr><th align="left">#</th><th align="left">Packet / extracted value</th>'
        '<th align="left">Result</th></tr>'
        + "".join(rows) + '</table>' + residual +
        '<p><span style="color:#14532D;background-color:#BBF7D0">Value</span> &nbsp; '
        '<span style="color:#687078">Prefix / name / unused bytes</span></p></body></html>'
    )
