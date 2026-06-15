import unittest

from src.strategies.base import MarketState, Position, ActionType
from src.strategies.intraday.vwap_reversion import VWAPReversion
from src.strategies.intraday.momentum import RelativeVolumeMomentum


def vwap_ms(**kw):
    d = dict(ticker="SPY", now_et="2026-06-15T11:00:00-04:00", quote=97.5,
             regime="range_low_vol", has_catalyst=False)
    d.update(kw)
    m = MarketState(**{k: v for k, v in d.items()
                       if k in MarketState.__dataclass_fields__})
    m.vwap = kw.get("vwap", 100.0)
    m.atr_14 = kw.get("atr_14", 1.0)
    m.rsi14 = kw.get("rsi14", 20.0)
    m.spread_pct = 0.0005
    m.rvol = kw.get("rvol", 1.5)
    return m


def mom_ms(**kw):
    d = dict(ticker="NVDA", now_et="2026-06-15T11:00:00-04:00", quote=101.2,
             regime="bull_trend_low_vol")
    d.update(kw)
    m = MarketState(**{k: v for k, v in d.items()
                       if k in MarketState.__dataclass_fields__})
    m.ema9 = kw.get("ema9", 101.0)
    m.ema20 = kw.get("ema20", 100.0)
    m.atr_14 = kw.get("atr_14", 1.0)
    m.rvol = kw.get("rvol", 2.0)
    m.spread_pct = 0.0005
    return m


class TestVWAPReversion(unittest.TestCase):
    def setUp(self):
        self.s = VWAPReversion()

    def test_long_fade_when_oversold_below_vwap(self):
        setups = self.s.scan(vwap_ms(quote=97.5, rsi14=20))
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_short_fade_when_overbought_above_vwap(self):
        setups = self.s.scan(vwap_ms(quote=102.5, rsi14=80))
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "short")

    def test_no_setup_when_not_extended(self):
        self.assertEqual(self.s.scan(vwap_ms(quote=100.5, rsi14=20)), [])

    def test_no_setup_with_fresh_catalyst(self):
        ms = vwap_ms(quote=97.5, rsi14=20, has_catalyst=True)
        ms.catalyst_age_min = 5
        self.assertEqual(self.s.scan(ms), [])

    def test_no_setup_when_rsi_not_confirming(self):
        self.assertEqual(self.s.scan(vwap_ms(quote=97.5, rsi14=45)), [])

    def test_manage_exits_on_vwap_touch(self):
        pos = Position("SPY", "long", 5, 97.5, 97.0, [(100.0, 1.0)], "vwap_reversion",
                       "2026-06-15T11:00:00-04:00")
        ms = vwap_ms(quote=100.1)
        a = self.s.manage(pos, ms)
        self.assertEqual(a.type, ActionType.EXIT)
        self.assertEqual(a.reason, "vwap_touched")


class TestMomentum(unittest.TestCase):
    def setUp(self):
        self.s = RelativeVolumeMomentum()

    def test_long_on_pullback_in_uptrend(self):
        setups = self.s.scan(mom_ms())
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")
        self.assertGreater(setups[0].entry_price, setups[0].stop_price)

    def test_no_setup_low_rvol(self):
        self.assertEqual(self.s.scan(mom_ms(rvol=1.0)), [])

    def test_no_setup_not_near_ema9(self):
        # price far above ema9 -> not a pullback
        self.assertEqual(self.s.scan(mom_ms(quote=105.0)), [])

    def test_short_in_downtrend(self):
        ms = mom_ms(quote=98.8, ema9=99.0, ema20=100.0)
        setups = self.s.scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "short")

    def test_manage_scales_at_t1(self):
        pos = Position("NVDA", "long", 5, 101.2, 99.9, [(103.0, 0.5)], "momentum",
                       "2026-06-15T11:00:00-04:00")
        ms = mom_ms(quote=103.1)
        a = self.s.manage(pos, ms)
        self.assertEqual(a.type, ActionType.SCALE_OUT)


if __name__ == "__main__":
    unittest.main()
