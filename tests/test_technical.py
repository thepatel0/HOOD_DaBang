import unittest

import numpy as np

from src.analysts_local.technical import (
    ema, rsi, atr, vwap, macd, bb_width_percentile, opening_range, rvol_proxy,
    TechnicalAnalyst,
)
from src.strategies.base import Bar
from src.strategies.intraday.orb import OpeningRangeBreakout


class TestIndicators(unittest.TestCase):
    def test_ema_of_constant_is_constant(self):
        self.assertAlmostEqual(ema(np.array([5.0] * 50), 9), 5.0, places=6)

    def test_rsi_monotonic_up_is_100(self):
        self.assertEqual(rsi(np.arange(1.0, 40.0), 14), 100.0)

    def test_rsi_in_range(self):
        rng = np.random.default_rng(0)
        vals = 100 + np.cumsum(rng.normal(0, 1, 200))
        r = rsi(vals, 14)
        self.assertTrue(0 <= r <= 100)

    def test_atr_constant_range(self):
        n = 30
        high = np.full(n, 101.0)
        low = np.full(n, 100.0)
        close = np.full(n, 100.5)
        # TR each bar = max(1, |101-100.5|, |100-100.5|) = 1.0
        self.assertAlmostEqual(atr(high, low, close, 14), 1.0, places=6)

    def test_vwap_weighted(self):
        h = np.array([10.0, 10.0]); l = np.array([10.0, 10.0])
        c = np.array([10.0, 20.0]); v = np.array([1.0, 3.0])
        # typical = [(10+10+10)/3, (10+10+20)/3] = [10, 13.333]
        # vwap = (10*1 + 13.333*3)/4 = 50/4 = 12.5
        self.assertAlmostEqual(vwap(h, l, c, v), 12.5, places=4)

    def test_macd_present_on_long_series(self):
        closes = np.linspace(100, 120, 60)
        m, s, hist = macd(closes)
        self.assertIsNotNone(m)

    def test_bb_width_percentile_bounds(self):
        rng = np.random.default_rng(1)
        closes = 100 + np.cumsum(rng.normal(0, 0.5, 150))
        p = bb_width_percentile(closes)
        self.assertTrue(0.0 <= p <= 1.0)

    def test_opening_range_first_five_min(self):
        bars = [Bar(f"2026-06-15T09:3{i}:00-04:00", 100, 100 + i*0.1, 99.5, 100, 1000)
                for i in range(8)]
        orr = opening_range(bars, 5)
        self.assertIsNotNone(orr)
        hi, lo = orr
        # only bars 09:30-09:34 count; highest high among those
        self.assertAlmostEqual(hi, 100 + 4*0.1, places=6)

    def test_rvol_proxy(self):
        v = np.array([100.0] * 20 + [300.0])
        self.assertAlmostEqual(rvol_proxy(v), 3.0, places=6)


class TestTechnicalIntegration(unittest.TestCase):
    def _orb_bars(self):
        bars = []
        # opening range 09:30-09:34: high ~101, low ~100
        for i in range(5):
            bars.append(Bar(f"2026-06-15T09:3{i}:00-04:00", 100.2, 101.0, 100.0, 100.5, 2000))
        # drift 09:35-09:41 inside range
        for i in range(5, 12):
            ts = f"2026-06-15T09:{30+i:02d}:00-04:00"
            bars.append(Bar(ts, 100.5, 100.9, 100.3, 100.6, 1500))
        # breakout bar at 09:42 above OR-high with big volume
        bars.append(Bar("2026-06-15T09:42:00-04:00", 100.7, 101.6, 100.6, 101.45, 9000))
        return bars

    def test_compute_populates_marketstate(self):
        ta = TechnicalAnalyst()
        bars = self._orb_bars()
        ms = ta.compute("AAPL", "2026-06-15T09:42:00-04:00", 101.45,
                        {"1m": bars}, bid=101.44, ask=101.46,
                        prior_close=100.0, regime="bull_trend_low_vol",
                        has_catalyst=True, catalyst_age_min=5, catalyst_sources=2,
                        adv_shares=5_000_000)
        self.assertIsNotNone(ms.opening_range_high)
        self.assertAlmostEqual(ms.opening_range_high, 101.0, places=2)
        self.assertIsNotNone(ms.vwap)
        self.assertIsNotNone(ms.atr_1m)
        self.assertGreater(ms.rvol, 1.5)        # breakout bar volume spike
        self.assertGreater(ms.gap_pct, 0)        # opened above prior close

    def test_tier0_to_orb_produces_setup(self):
        ta = TechnicalAnalyst()
        ms = ta.compute("AAPL", "2026-06-15T09:42:00-04:00", 101.45,
                        {"1m": self._orb_bars()}, bid=101.44, ask=101.46,
                        prior_close=100.0, regime="bull_trend_low_vol",
                        has_catalyst=True, catalyst_age_min=5, catalyst_sources=2,
                        adv_shares=5_000_000)
        setups = OpeningRangeBreakout().scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")
        self.assertGreater(setups[0].entry_price, setups[0].stop_price)


if __name__ == "__main__":
    unittest.main()
