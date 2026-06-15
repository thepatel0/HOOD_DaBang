import unittest

from src.strategies.base import MarketState, Bar
from src.strategies.intraday.short_squeeze import ShortSqueeze
from src.strategies.intraday.earnings_reaction import EarningsReaction
from src.strategies.intraday.sector_rotation import SectorRotation
from src.strategies.swing.pead import PostEarningsDrift
from src.strategies.swing.momentum_swing import MomentumSwing
from src.strategies.swing.earnings_beat_followthrough import EarningsBeatFollowThrough
from src.strategies.swing.quality_mean_reversion import QualityMeanReversion
from src.strategies.swing.sector_momentum_rotation import SectorMomentumRotation
from src.strategies.stat_arb.pairs import (PairsStatArb, rolling_zscore, hedge_ratio)


def ms(**kw):
    m = MarketState(ticker="X", now_et="2026-06-15T11:00:00-04:00", quote=100.0)
    m.atr_14 = 1.0
    m.spread_pct = 0.0005
    m.rvol = 2.0
    m.regime = "bull_trend_low_vol"
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class TestDataDependentIntraday(unittest.TestCase):
    def test_short_squeeze_fires(self):
        m = ms(short_interest_pct=0.25, rvol=4.0, quote=101.0, regime="bull_trend_high_vol")
        m.bars["5m"] = [Bar(f"t{i}", 100, 100.3, 99.8, 100, 5000) for i in range(6)]
        setups = ShortSqueeze().scan(m)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_short_squeeze_abstains_without_si(self):
        m = ms(short_interest_pct=None, rvol=4.0)
        self.assertEqual(ShortSqueeze().scan(m), [])

    def test_short_squeeze_needs_high_si(self):
        m = ms(short_interest_pct=0.10, rvol=4.0, quote=101.0)
        m.bars["5m"] = [Bar(f"t{i}", 100, 100.3, 99.8, 100, 5000) for i in range(6)]
        self.assertEqual(ShortSqueeze().scan(m), [])

    def test_earnings_reaction_continuation(self):
        m = ms(days_since_earnings=0, gap_pct=0.07, quote=107.0, vwap=107.0,
               now_et="2026-06-15T10:00:00-04:00")
        m.bars["5m"] = [Bar("t0", 106.0, 108, 105, 107, 9000)]
        setups = EarningsReaction().scan(m)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_earnings_reaction_abstains_outside_window(self):
        m = ms(days_since_earnings=5, gap_pct=0.07, vwap=107.0)
        self.assertEqual(EarningsReaction().scan(m), [])

    def test_sector_rotation_fires_for_leader(self):
        m = ms(sector_is_leader=True, sector="XLK", ema9=100.2, ema20=99.8,
               quote=100.3, rvol=2.0)
        setups = SectorRotation().scan(m)
        self.assertEqual(len(setups), 1)

    def test_sector_rotation_abstains_non_leader(self):
        m = ms(sector_is_leader=False, ema9=100.2, ema20=99.8, quote=100.3)
        self.assertEqual(SectorRotation().scan(m), [])


class TestSwing(unittest.TestCase):
    def test_pead_day2_beat(self):
        m = ms(days_since_earnings=2, sue=1.5, rs_rank_pct=0.8, quote=100)
        setups = PostEarningsDrift().scan(m)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_pead_abstains_weak_beat(self):
        m = ms(days_since_earnings=2, sue=0.5, rs_rank_pct=0.8)
        self.assertEqual(PostEarningsDrift().scan(m), [])

    def test_momentum_swing_fires(self):
        m = ms(mom_20d=0.15, high_20d=99.5, sma50=98.0, quote=100.0, rvol=2.0)
        setups = MomentumSwing().scan(m)
        self.assertEqual(len(setups), 1)

    def test_momentum_swing_needs_high_break(self):
        m = ms(mom_20d=0.15, high_20d=101.0, sma50=98.0, quote=100.0, rvol=2.0)
        self.assertEqual(MomentumSwing().scan(m), [])

    def test_earnings_beat_ft_fires(self):
        m = ms(days_since_earnings=1, sue=2.0, guidance_raised=True, quote=100)
        m.bars["1D"] = [Bar("d1", 98, 101, 97.5, 100, 1_000_000)]  # close>open
        setups = EarningsBeatFollowThrough().scan(m)
        self.assertEqual(len(setups), 1)

    def test_earnings_beat_ft_needs_guidance(self):
        m = ms(days_since_earnings=1, sue=2.0, guidance_raised=False)
        m.bars["1D"] = [Bar("d1", 98, 101, 97.5, 100, 1_000_000)]
        self.assertEqual(EarningsBeatFollowThrough().scan(m), [])

    def test_quality_mean_reversion_fires(self):
        m = ms(rsi2=3.0, sma200=99.0, sma50=102.0, quote=100.0, has_catalyst=False)
        setups = QualityMeanReversion().scan(m)
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].side, "long")

    def test_quality_mr_needs_oversold(self):
        m = ms(rsi2=20.0, sma200=99.0, quote=100.0)
        self.assertEqual(QualityMeanReversion().scan(m), [])

    def test_sector_momentum_rotation_fires(self):
        m = ms(sector_is_leader=True, sector="XLE", rs_rank_pct=0.85, sma50=98.0,
               quote=100.0)
        setups = SectorMomentumRotation().scan(m)
        self.assertEqual(len(setups), 1)


class TestPairs(unittest.TestCase):
    def test_zscore(self):
        spread = [0.0] * 19 + [3.0]   # last value far from mean 0.15
        z = rolling_zscore(spread)
        self.assertIsNotNone(z)
        self.assertGreater(z, 2.0)

    def test_zscore_insufficient(self):
        self.assertIsNone(rolling_zscore([1, 2, 3]))

    def test_hedge_ratio(self):
        # a = 2*b exactly -> ratio 2.0
        b = [1.0, 2.0, 3.0, 4.0]
        a = [2.0, 4.0, 6.0, 8.0]
        self.assertAlmostEqual(hedge_ratio(a, b), 2.0, places=6)

    def test_scan_pair_produces_two_legs(self):
        # a diverges high -> short a, long b
        prices_b = [100.0] * 25
        prices_a = [100.0] * 24 + [110.0]   # a spikes
        legs = PairsStatArb().scan_pair("MA", 110.0, "V", 100.0, prices_a, prices_b)
        self.assertEqual(len(legs), 2)
        sides = {l.ticker: l.setup.side for l in legs}
        self.assertEqual(sides["MA"], "short")
        self.assertEqual(sides["V"], "long")

    def test_no_legs_when_z_small(self):
        prices = [100.0 + (i % 2) for i in range(25)]
        legs = PairsStatArb().scan_pair("MA", 100.0, "V", 100.0, prices, prices)
        self.assertEqual(legs, [])

    def test_exit_signals(self):
        s = PairsStatArb()
        self.assertEqual(s.should_exit_pair(0.05), "spread_reverted")
        self.assertEqual(s.should_exit_pair(3.5), "spread_stop_3sigma")
        self.assertIsNone(s.should_exit_pair(1.5))


if __name__ == "__main__":
    unittest.main()
