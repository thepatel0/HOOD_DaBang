import unittest

from src.strategies.base import MarketState, Bar, Position, ActionType
from src.strategies.intraday.gap_fill import GapFill
from src.strategies.intraday.gap_continuation import GapAndGo
from src.strategies.intraday.range_compression import RangeCompression


def base_ms(**kw):
    m = MarketState(ticker="AAPL", now_et="2026-06-15T09:50:00-04:00", quote=100.0,
                    regime="range_low_vol")
    m.atr_1m = 0.3
    m.atr_14 = 0.5
    m.spread_pct = 0.0005
    m.rvol = 1.5
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class TestGapFill(unittest.TestCase):
    def setUp(self):
        self.s = GapFill()

    def test_gap_up_fades_short(self):
        ms = base_ms(quote=102.0, gap_pct=0.02, prior_close=100.0,
                     premarket_high=102.5, has_catalyst=False)
        setups = self.s.scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "short")
        self.assertEqual(setups[0].targets[0][0], 100.0)   # target prior close

    def test_gap_down_fades_long(self):
        ms = base_ms(quote=98.0, gap_pct=-0.02, prior_close=100.0,
                     premarket_low=97.5, has_catalyst=False)
        setups = self.s.scan(ms)
        self.assertEqual(setups[0].side, "long")

    def test_no_fade_with_news(self):
        ms = base_ms(quote=102.0, gap_pct=0.02, prior_close=100.0,
                     premarket_high=102.5, has_catalyst=True, catalyst_age_min=5)
        self.assertEqual(self.s.scan(ms), [])

    def test_no_fade_large_gap(self):
        ms = base_ms(quote=105.0, gap_pct=0.05, prior_close=100.0,
                     premarket_high=105.5, has_catalyst=False)
        self.assertEqual(self.s.scan(ms), [])


class TestGapAndGo(unittest.TestCase):
    def setUp(self):
        self.s = GapAndGo()

    def _bars(self, base=104.0):
        return [Bar(f"2026-06-15T09:3{i}:00-04:00", base, base+0.2, base-0.2, base, 5000)
                for i in range(6)]

    def test_gap_up_breakout_long(self):
        ms = base_ms(quote=104.5, gap_pct=0.04, has_catalyst=True, catalyst_age_min=10,
                     catalyst_sources=2)
        ms.bars["1m"] = self._bars(104.0)         # consolidation ~103.8-104.2
        setups = self.s.scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_requires_catalyst(self):
        ms = base_ms(quote=104.5, gap_pct=0.04, has_catalyst=False)
        ms.bars["1m"] = self._bars(104.0)
        self.assertEqual(self.s.scan(ms), [])


class TestRangeCompression(unittest.TestCase):
    def setUp(self):
        self.s = RangeCompression()

    def _bars(self):
        # 5 tight consolidation bars then a breakout
        bars = [Bar(f"2026-06-15T10:0{i}:00-04:00", 100, 100.2, 99.8, 100, 3000)
                for i in range(5)]
        bars.append(Bar("2026-06-15T10:06:00-04:00", 100.2, 100.9, 100.1, 100.8, 9000))
        return bars

    def test_squeeze_breakout_long(self):
        ms = base_ms(quote=100.8, bb_width_pctile=0.1, rvol=2.0)
        ms.bars["5m"] = self._bars()
        setups = self.s.scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_no_setup_when_not_squeezed(self):
        ms = base_ms(quote=100.8, bb_width_pctile=0.5, rvol=2.0)
        ms.bars["5m"] = self._bars()
        self.assertEqual(self.s.scan(ms), [])

    def test_no_setup_low_volume(self):
        ms = base_ms(quote=100.8, bb_width_pctile=0.1, rvol=1.0)
        ms.bars["5m"] = self._bars()
        self.assertEqual(self.s.scan(ms), [])


if __name__ == "__main__":
    unittest.main()
