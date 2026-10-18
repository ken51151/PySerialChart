import unittest
from dataclasses import asdict, replace

from plot_config import LINE_MODES, SEP_MODES, VALUE_MODES, PlotConfig
from plot_preview import _value_range, build_preview_html, format_bytes, make_sample_data
from serial_rx import RxPlotParser


class PlotPreviewTests(unittest.TestCase):
    def test_ascii_multi_and_float(self):
        html = build_preview_html(PlotConfig())
        self.assertIn("speed &rarr; 123", html)
        self.assertIn("temp &rarr; -45", html)
        self.assertIn("[LF]", html)
        self.assertIn("&nbsp;[LF]&nbsp;", html)
        self.assertNotIn("Array range", html)
        self.assertNotIn("startIndex", html)
        self.assertNotIn("[6, 9]", html)
        self.assertIn('background-color:#BBF7D0"><b>123</b>', html)
        self.assertIn("speed &rarr; 1.25", build_preview_html(replace(PlotConfig(), value_mode=VALUE_MODES.ASCII_FLOAT)))

    def test_binary_offset_and_endianness(self):
        config = replace(PlotConfig(), line_mode=LINE_MODES.SINGLE_LINE,
                         value_mode=VALUE_MODES.BIN_I16_LE, sep_mode=SEP_MODES.LENGTH,
                         packet_length=4, offset=2)
        little = make_sample_data(config.to_parser_config())
        big_config = replace(config, value_mode=VALUE_MODES.BIN_I16_BE)
        self.assertEqual(little, make_sample_data(big_config.to_parser_config()))
        self.assertEqual(little, bytes.fromhex("AA BB 34 12 AA BB FE FF"))
        html = build_preview_html(config)
        self.assertIn("<b>34 12</b>", html)
        self.assertIn("4660", html)
        self.assertIn(">-2<", html)
        self.assertIn("13330", build_preview_html(big_config))
        self.assertIn(">-257<", build_preview_html(big_config))

    def test_all_value_formats_use_real_parser(self):
        for mode in VALUE_MODES:
            with self.subTest(mode=mode):
                config = replace(PlotConfig(), line_mode=LINE_MODES.SINGLE_LINE,
                                 value_mode=mode, sep_mode=SEP_MODES.LENGTH, packet_length=16)
                parser_config = config.to_parser_config()
                batch, count = RxPlotParser(**asdict(parser_config)).feed(make_sample_data(parser_config))
                self.assertEqual(count, 2)
                html = build_preview_html(config)
                for value in batch["values"]:
                    self.assertIn(f">{value}<", html)

    def test_delimiter_collision_shows_actual_ignored_packets(self):
        config = replace(PlotConfig(), line_mode=LINE_MODES.SINGLE_LINE,
                         value_mode=VALUE_MODES.BIN_I16_LE, separator=b"\x34")
        self.assertIn("Ignored:", build_preview_html(config))

    def test_ascii_offset_matches_existing_slice_behavior(self):
        config = replace(PlotConfig(), line_mode=LINE_MODES.SINGLE_LINE, offset=2)
        html = build_preview_html(config)
        self.assertIn("~~", html)
        self.assertIn("<b>123</b>", html)
        self.assertIn(">123<", html)
        multi = replace(config, line_mode=LINE_MODES.MULTI_LINE_ASCII).to_parser_config()
        self.assertEqual(_value_range(b"speed= ~~123  ", multi), (9, 12))

    def test_short_fixed_multi_and_html_escaping(self):
        config = replace(PlotConfig(), sep_mode=SEP_MODES.LENGTH, packet_length=2)
        self.assertIn("Ignored:", build_preview_html(config))
        html = build_preview_html(replace(PlotConfig(), separator=b"<>&"))
        self.assertIn("&lt;&gt;&amp;", html)
        self.assertIn("speed &rarr; 123", html)
        self.assertEqual(format_bytes(b"\x00\t\r\n\xff", False), "[NUL][TAB][CR][LF][FF]")

    def test_large_preview_is_bounded_without_invalidating_settings(self):
        for config in (replace(PlotConfig(), offset=2147483647),
                       replace(PlotConfig(), sep_mode=SEP_MODES.LENGTH, packet_length=2147483647),
                       replace(PlotConfig(), separator=b"!" * 33)):
            config.validate()
            with self.assertRaisesRegex(ValueError, "Preview unavailable"):
                build_preview_html(config)


if __name__ == "__main__":
    unittest.main()
