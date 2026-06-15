import unittest

from src.strategies.base import MarketState, Bar, Position, ActionType
from src.strategies.registry import StrategyRegistry, PromotionError, FIVE_GATES
from src.strategies.intraday.orb import OpeningRangeBreakout


def ms_breakout(side="long", **kw):
    """A clean ORB long: OR 100-101, last 1m closes at 101.4 above OR-high."""
    d = dict(
        ticker="AAPL", now_et="2026-06-15T09:42:00-04:00", quote=101.4,
        bid=101.39, ask=101.41, spread_pct=0.0002,
        opening_range_high=101.0, opening_range_low=100.0,
        atr_1m=0.20, atr_14=0.5, rvol=2.0, ema9=101.1, ema20=100.8, vwap=100.9,
        regime="bull_trend_low_vol", has_catalyst=True, catalyst_age_min=5,
        catalyst_sources=2, adv_shares=5_000_000,
    )
    d.update(kw)
    ms = MarketState(**{k: v for k, v in d.items() if k != "last_close"})
    close = d.get("last_close", 101.4 if side == "long" else 99.6)
    ms.bars["1m"] = [Bar(d["now_et"], 101.0, 101.5, 100.9, close, 50000)]
    return ms


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = StrategyRegistry(regime_allocations={
            "bull_trend_low_vol": {"orb": 0.15}, "range_low_vol": {"orb": 0.05}})
        self.reg.register(OpeningRangeBreakout())

    def test_cannot_go_live_without_five_gates(self):
        with self.assertRaises(PromotionError):
            self.reg.promote("orb", "live")

    def test_can_go_live_with_all_gates(self):
        for g in FIVE_GATES:
            self.reg.set_gate("orb", g, True)
        self.reg.promote("orb", "live")
        self.assertEqual(self.reg.get("orb").strategy.activation_status, "live")

    def test_missing_one_gate_still_blocked(self):
        for g in FIVE_GATES[:-1]:
            self.reg.set_gate("orb", g, True)
        with self.assertRaises(PromotionError):
            self.reg.promote("orb", "live")
        self.assertIn("paper", self.reg.get("orb").validation.missing())

    def test_unknown_gate_rejected(self):
        with self.assertRaises(ValueError):
            self.reg.set_gate("orb", "made_up_gate", True)

    def test_allocation_lookup(self):
        self.assertEqual(self.reg.allocation("bull_trend_low_vol", "orb"), 0.15)
        self.assertEqual(self.reg.allocation("crisis", "orb"), 0.0)

    def test_wake_routing_respects_regime_and_window(self):
        self.reg.promote("orb", "paper")  # tradeable
        ms = ms_breakout()
        woke = self.reg.wake_strategies(ms, "1m")
        self.assertEqual([s.name for s in woke], ["orb"])
        # crisis regime -> 0 weight -> not woken
        ms.regime = "crisis"
        self.assertEqual(self.reg.wake_strategies(ms, "1m"), [])
        # outside the session window -> not woken
        ms2 = ms_breakout(now_et="2026-06-15T11:00:00-04:00")
        self.assertEqual(self.reg.wake_strategies(ms2, "1m"), [])
        # wrong timeframe -> not woken
        self.assertEqual(self.reg.wake_strategies(ms_breakout(), "5m"), [])


class TestORB(unittest.TestCase):
    def setUp(self):
        self.orb = OpeningRangeBreakout()

    def test_long_breakout_produces_setup(self):
        setups = self.orb.scan(ms_breakout("long"))
        self.assertEqual(len(setups), 1)
        s = setups[0]
        self.assertEqual(s.side, "long")
        self.assertGreater(s.entry_price, s.stop_price)   # long stop below entry
        self.assertEqual(len(s.factors), 8)
        self.assertGreater(s.reward_risk, 1.0)            # >= 1.5R target

    def test_short_breakdown_produces_setup(self):
        ms = ms_breakout("short", quote=99.6, last_close=99.6, ema9=99.9, ema20=100.2,
                         vwap=100.1)
        setups = self.orb.scan(ms)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "short")
        self.assertLess(setups[0].entry_price, setups[0].stop_price)

    def test_no_precondition_no_setup(self):
        # no catalyst and low rvol -> nothing
        ms = ms_breakout(has_catalyst=False, rvol=1.0)
        self.assertEqual(self.orb.scan(ms), [])

    def test_inside_range_no_setup(self):
        ms = ms_breakout(last_close=100.5)  # inside OR
        self.assertEqual(self.orb.scan(ms), [])

    def test_factors_in_range(self):
        s = self.orb.scan(ms_breakout("long"))[0]
        for k, val in s.factors.items():
            self.assertGreaterEqual(val, 0.0, k)
            self.assertLessEqual(val, 100.0, k)

    def test_manage_time_stop(self):
        pos = Position("AAPL", "long", 10, 101.4, 100.0, [(103.0, 0.5)], "orb",
                       "2026-06-15T09:42:00-04:00")
        ms = ms_breakout("long", now_et="2026-06-15T15:31:00-04:00")
        a = self.orb.manage(pos, ms)
        self.assertEqual(a.type, ActionType.EXIT)
        self.assertIn("time_stop", a.reason)

    def test_manage_lost_vwap_exits(self):
        pos = Position("AAPL", "long", 10, 101.4, 100.0, [(103.0, 0.5)], "orb",
                       "2026-06-15T09:42:00-04:00")
        ms = ms_breakout("long", quote=100.5, vwap=100.9)  # below vwap
        a = self.orb.manage(pos, ms)
        self.assertEqual(a.type, ActionType.EXIT)
        self.assertEqual(a.reason, "lost_vwap")

    def test_manage_scale_out_at_t1(self):
        pos = Position("AAPL", "long", 10, 101.0, 100.0, [(102.0, 0.5)], "orb",
                       "2026-06-15T09:42:00-04:00")
        ms = ms_breakout("long", quote=102.1, vwap=100.5)  # above t1, above vwap
        a = self.orb.manage(pos, ms)
        self.assertEqual(a.type, ActionType.SCALE_OUT)
        self.assertEqual(a.new_stop, pos.entry_price)  # stop to break-even


if __name__ == "__main__":
    unittest.main()
