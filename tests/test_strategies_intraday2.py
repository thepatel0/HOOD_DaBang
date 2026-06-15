import unittest

from src.strategies.base import MarketState, Bar, Position, ActionType
from src.strategies.intraday.ibb import InitialBalanceBreakout
from src.strategies.intraday.catalyst_scalp import CatalystScalp
from src.strategies.intraday.engulfing import MultiTimeframeEngulfing
from src.strategies.intraday.hourly_sweep import HourlySweep


def ms_with(**kw):
    m = MarketState(ticker="SPY", now_et="2026-06-15T11:00:00-04:00", quote=100.0)
    m.atr_1m = 0.3
    m.atr_14 = 0.5
    m.spread_pct = 0.0005
    m.rvol = 2.0
    m.regime = "bull_trend_low_vol"
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class TestIBB(unittest.TestCase):
    def test_break_above_ib_long(self):
        bars = [Bar(f"2026-06-15T{9 + (30+i)//60:02d}:{(30+i)%60:02d}:00-04:00",
                    100, 100.5, 99.5, 100, 3000) for i in range(60)]
        ms = ms_with(quote=101.0, regime="bull_trend_low_vol", ema20=100.2)
        ms.bars["1m"] = bars
        setups = InitialBalanceBreakout().scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_inside_ib_no_setup(self):
        bars = [Bar(f"2026-06-15T{9 + (30+i)//60:02d}:{(30+i)%60:02d}:00-04:00",
                    100, 100.5, 99.5, 100, 3000) for i in range(60)]
        ms = ms_with(quote=100.0)
        ms.bars["1m"] = bars
        self.assertEqual(InitialBalanceBreakout().scan(ms), [])


class TestCatalystScalp(unittest.TestCase):
    def test_fires_on_fresh_multisource_catalyst(self):
        ms = ms_with(has_catalyst=True, catalyst_age_min=3, catalyst_sources=2)
        ms.bars["1m"] = [Bar("t0", 100, 100.2, 99.9, 100.0, 5000),
                         Bar("t1", 100.0, 100.5, 100.0, 100.4, 9000)]
        setups = CatalystScalp().scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")
        # ~0.5% tight stop
        self.assertLess(abs(setups[0].entry_price - setups[0].stop_price),
                        0.01 * setups[0].entry_price + 0.2)

    def test_no_fire_stale_catalyst(self):
        ms = ms_with(has_catalyst=True, catalyst_age_min=30, catalyst_sources=2)
        ms.bars["1m"] = [Bar("t0", 100, 100.2, 99.9, 100, 5000),
                         Bar("t1", 100, 100.5, 100, 100.4, 9000)]
        self.assertEqual(CatalystScalp().scan(ms), [])

    def test_no_fire_single_source(self):
        ms = ms_with(has_catalyst=True, catalyst_age_min=3, catalyst_sources=1)
        ms.bars["1m"] = [Bar("t0", 100, 100.2, 99.9, 100, 5000),
                         Bar("t1", 100, 100.5, 100, 100.4, 9000)]
        self.assertEqual(CatalystScalp().scan(ms), [])

    def test_relaxed_gating(self):
        self.assertFalse(CatalystScalp().requires_llm_gating)


class TestEngulfing(unittest.TestCase):
    def test_bullish_engulf_at_support(self):
        # b0 bearish, b1 bullish engulfing; price near sma50 support
        b0 = Bar("2026-06-15T10:00:00-04:00", 100.5, 100.6, 100.0, 100.1, 3000)
        b1 = Bar("2026-06-15T10:15:00-04:00", 100.0, 101.0, 99.9, 100.9, 8000)
        ms = ms_with(quote=100.9, sma50=100.8, regime="range_low_vol", rvol=2.0)
        ms.bars["15m"] = [b0, b1]
        setups = MultiTimeframeEngulfing().scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_no_engulf_low_volume(self):
        b0 = Bar("t0", 100.5, 100.6, 100.0, 100.1, 3000)
        b1 = Bar("t1", 100.0, 101.0, 99.9, 100.9, 8000)
        ms = ms_with(quote=100.9, sma50=100.8, rvol=1.0)
        ms.bars["15m"] = [b0, b1]
        self.assertEqual(MultiTimeframeEngulfing().scan(ms), [])


class TestHourlySweep(unittest.TestCase):
    def _bars(self):
        bars = []
        # prior hour 10:00-10:59 range ~99.5-100.5
        for i in range(60):
            bars.append(Bar(f"2026-06-15T10:{i:02d}:00-04:00", 100, 100.5, 99.5, 100, 2000))
        # current hour opens at 100 (inside), sweeps below 99.5 then reclaims
        bars.append(Bar("2026-06-15T11:00:00-04:00", 100.0, 100.1, 100.0, 100.0, 2000))
        bars.append(Bar("2026-06-15T11:01:00-04:00", 100.0, 100.0, 99.2, 99.3, 5000))  # sweep low
        bars.append(Bar("2026-06-15T11:02:00-04:00", 99.3, 99.9, 99.3, 99.8, 4000))   # reclaim
        return bars

    def test_sweep_low_reclaim_long(self):
        ms = ms_with(now_et="2026-06-15T11:02:00-04:00", quote=99.8, regime="range_low_vol")
        ms.bars["1m"] = self._bars()
        setups = HourlySweep().scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")
        self.assertAlmostEqual(setups[0].targets[0][0], 100.0)  # return to hour open


if __name__ == "__main__":
    unittest.main()
