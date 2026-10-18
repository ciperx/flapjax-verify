"""Unit tests for flapjax_verify — pure logic only, no network."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flapjax_verify as fv  # noqa: E402


class TestAbi(unittest.TestCase):
    def test_pad_is_32_bytes(self):
        p = fv.pad("0x7C34E9e21eE28A49Ff0b84B61774119E6633359f")
        self.assertEqual(len(p), 64)
        self.assertTrue(p.startswith("000000000000000000000000"))
        self.assertTrue(p.endswith("7c34e9e21ee28a49ff0b84b61774119e6633359f"))

    def test_pad_lowercases(self):
        self.assertEqual(fv.pad("0xABCDEF"), fv.pad("0xabcdef"))

    def test_word_to_int(self):
        self.assertEqual(fv.word_to_int("0x" + "0" * 64), 0)
        self.assertEqual(fv.word_to_int("0x" + "0" * 63 + "1"), 1)
        self.assertEqual(fv.word_to_int("0x" + "0" * 60 + "1f40"), 8000)

    def test_uint_empty(self):
        self.assertEqual(fv.uint(""), 0)
        self.assertEqual(fv.uint("0x1"), 1)


class TestDecodeTransfer(unittest.TestCase):
    def _log(self, frm, to, value):
        return {
            "blockNumber": hex(128267486),
            "transactionHash": "0x" + "ab" * 32,
            "topics": [
                fv.TRANSFER_TOPIC,
                "0x" + fv.pad(frm),
                "0x" + fv.pad(to),
            ],
            "data": hex(value),
        }

    def test_decode_amount_and_parties(self):
        d = fv.decode_transfer(self._log(fv.TREASURY, "0x226ea74D26E2aA98973Dc35ffE7E66fa2e3B2588", 100_000 * 10**18))
        self.assertEqual(d["block"], 128267486)
        self.assertAlmostEqual(d["value"], 100_000.0, delta=1e-6)
        self.assertEqual(d["from"].lower(), fv.TREASURY.lower())
        self.assertEqual(d["to"].lower(), "0x226ea74d26e2aa98973dc35ffe7e66fa2e3b2588")

    def test_zero_value_transfer(self):
        d = fv.decode_transfer(self._log(fv.TREASURY, fv.TREASURY, 0))
        self.assertEqual(d["value"], 0.0)


class TestPriceMaths(unittest.TestCase):
    def test_sqrt_price_to_ratio(self):
        # sqrtPriceX96 == Q96 means price exactly 1.0
        sqrt_price = fv.Q96
        wbnb_per_fj = (sqrt_price / fv.Q96) ** 2
        self.assertAlmostEqual(wbnb_per_fj, 1.0)
        self.assertAlmostEqual(1 / wbnb_per_fj, 1.0)

    def test_real_tick_price_is_sane(self):
        # observed on 2026-10-18: sqrtPriceX96 = 1624719868057956652043500
        sqrt_price = 1624719868057956652043500
        wbnb_per_fj = (sqrt_price / fv.Q96) ** 2
        fj_per_wbnb = 1 / wbnb_per_fj
        # ~2.38e9 FLAPJAX per WBNB
        self.assertGreater(fj_per_wbnb, 2.0e9)
        self.assertLess(fj_per_wbnb, 2.8e9)

    def test_usd_price(self):
        fj_per_wbnb = 2_377_947_077.0
        wbnb_per_fj = 1 / fj_per_wbnb
        self.assertAlmostEqual(wbnb_per_fj * 720, 3.028e-7, delta=1e-10)


class TestChunking(unittest.TestCase):
    def test_chunk_windows_are_max_1000_and_contiguous(self):
        start, end = 128_260_000, 128_292_000
        windows, cur = [], start
        while cur <= end:
            to = min(cur + fv.MAX_CHUNK - 1, end)
            windows.append((cur, to))
            cur = to + 1
        self.assertTrue(all(b - a + 1 <= 1000 for a, b in windows))
        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[-1][1], end)
        for (_, prev_to), (nxt_from, _) in zip(windows, windows[1:]):
            self.assertEqual(nxt_from, prev_to + 1)

    def test_single_block_range(self):
        start = end = 128_267_486
        windows, cur = [], start
        while cur <= end:
            to = min(cur + fv.MAX_CHUNK - 1, end)
            windows.append((cur, to))
            cur = to + 1
        self.assertEqual(windows, [(start, end)])


class TestFormatting(unittest.TestCase):
    def test_fmt_18_decimals(self):
        self.assertEqual(fv.fmt(100_000 * 10**18), "100,000.000000")

    def test_fmt_supply(self):
        self.assertEqual(fv.fmt(44_444_444_444 * 10**18, places=0), "44,444,444,444")


class TestCli(unittest.TestCase):
    def test_bad_range_returns_usage_error(self):
        self.assertEqual(fv.main(["transfers", "200", "100"]), 2)

    def test_no_command_raises_systemexit(self):
        with self.assertRaises(SystemExit):
            fv.main([])


if __name__ == "__main__":
    unittest.main()
