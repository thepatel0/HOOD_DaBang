import unittest

from src import config, db
from src.research.pipeline import ResearchPipeline, TickerContext
from src.screener.screener import Screener, Candidate
from src.learning import WeeklyReview
from src.journal import Journal
from src.strategies.base import Bar


class TestResearchPipeline(unittest.TestCase):
    def setUp(self):
        self.p = ResearchPipeline()

    def _bars(self):
        return [Bar(f"2026-06-15T09:{30+i:02d}:00-04:00", 100, 100.5, 99.5, 100, 2000)
                for i in range(40)]

    def test_builds_full_marketstate(self):
        ctx = TickerContext(prior_close=99.0, days_since_earnings=2, sue=1.5,
                            rs_rank_pct=0.8, short_interest_pct=0.25, sector="XLK")
        ms = self.p.build("AAPL", "2026-06-15T09:50:00-04:00", 100.0,
                          {"1m": self._bars()}, "bull_trend_low_vol", ctx=ctx)
        self.assertIsNotNone(ms.vwap)            # technical computed
        self.assertEqual(ms.days_since_earnings, 2)   # context merged
        self.assertEqual(ms.sue, 1.5)
        self.assertEqual(ms.short_interest_pct, 0.25)
        self.assertEqual(ms.sector, "XLK")

    def test_build_watchlist_skips_empty(self):
        data = {"AAPL": {"quote": 100.0, "bars_by_tf": {"1m": self._bars()}},
                "BAD": {"quote": 100.0, "bars_by_tf": {}}}
        out = self.p.build_watchlist(["AAPL", "BAD"], "2026-06-15T09:50:00-04:00",
                                     data, "range_low_vol")
        self.assertIn("AAPL", out)
        self.assertNotIn("BAD", out)


class TestScreener(unittest.TestCase):
    def setUp(self):
        self.s = Screener(config.load())

    def test_filters_penny_stocks(self):
        c = Candidate("PENNY", 2.0, 5_000_000, 0.03)
        self.assertFalse(self.s.passes_liquidity(c))

    def test_filters_illiquid(self):
        c = Candidate("THIN", 50.0, 100_000, 0.03)
        self.assertFalse(self.s.passes_liquidity(c))

    def test_passes_good_name(self):
        c = Candidate("AAPL", 190.0, 50_000_000, 0.02)
        self.assertTrue(self.s.passes_liquidity(c))

    def test_premarket_ranks_by_gap(self):
        cands = [Candidate("A", 50, 5_000_000, 0.03, gap_pct=0.05),
                 Candidate("B", 50, 5_000_000, 0.03, gap_pct=0.02),
                 Candidate("C", 50, 5_000_000, 0.03, gap_pct=0.005)]  # below gap_min
        wl = self.s.premarket_watchlist(cands)
        self.assertEqual([c.ticker for c in wl], ["A", "B"])

    def test_intraday_ranks_by_rvol(self):
        cands = [Candidate("A", 50, 5_000_000, 0.03, rvol=5.0),
                 Candidate("B", 50, 5_000_000, 0.03, rvol=2.5),
                 Candidate("C", 50, 5_000_000, 0.03, rvol=1.0)]  # below rvol_min
        wl = self.s.intraday_watchlist(cands)
        self.assertEqual([c.ticker for c in wl], ["A", "B"])

    def test_combined_dedups(self):
        cands = [Candidate("A", 50, 5_000_000, 0.03, gap_pct=0.05, rvol=5.0)]
        self.assertEqual(self.s.combined_watchlist(cands), ["A"])


class TestWeeklyReview(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.journal = Journal(db.init_db(":memory:"))

    def _seed_trades(self, strategy, regime, r, n):
        for i in range(n):
            tid = self.journal.record_trade(
                ticker="X", strategy=strategy, strategy_version="1.0.0", side="long",
                entry_ts="t", entry_price=100, entry_shares=1, stop_price=99,
                conviction_score=80, thesis_id="th", market_regime=regime,
                order_id=f"{strategy}-{regime}-{i}")
            self.journal.close_trade(tid, exit_ts="t", exit_price=101, exit_reason="target",
                                     pnl_dollars=r, pnl_r=r)

    def test_reallocation_favors_winners(self):
        self._seed_trades("orb", "bull_trend_low_vol", 0.5, 10)
        self._seed_trades("vwap_reversion", "range_low_vol", -0.3, 10)
        review = WeeklyReview(self.cfg, journal=self.journal)
        report = review.run()
        self.assertIn("orb", report.reallocation)
        self.assertNotIn("vwap_reversion", report.reallocation)  # negative -> no weight

    def test_floor_raises_on_poor_expectancy(self):
        self._seed_trades("orb", "range_low_vol", -0.3, 12)
        report = WeeklyReview(self.cfg, journal=self.journal).run()
        self.assertGreater(report.proposed_floor, self.cfg["conviction"]["execution_floor"] - 1)
        self.assertLessEqual(report.proposed_floor, self.cfg["conviction"]["floor_max"])

    def test_floor_stays_in_bounds(self):
        self._seed_trades("orb", "bull_trend_low_vol", 0.5, 12)
        report = WeeklyReview(self.cfg, journal=self.journal).run()
        c = self.cfg["conviction"]
        self.assertGreaterEqual(report.proposed_floor, c["floor_min"])
        self.assertLessEqual(report.proposed_floor, c["floor_max"])

    def test_generates_hypotheses(self):
        self._seed_trades("orb", "bull_trend_low_vol", 0.5, 10)
        report = WeeklyReview(self.cfg, journal=self.journal).run()
        self.assertTrue(report.hypotheses)


if __name__ == "__main__":
    unittest.main()
