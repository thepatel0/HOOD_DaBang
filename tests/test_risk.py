import unittest

from src import config
from src.risk import RiskGate, OrderProposal, AccountState


def base_acct(**kw):
    d = dict(equity=1500, effective_capital=1500, session_start_equity=1500,
             day_pnl=0.0, open_positions=0, gross_exposure=0.0, day_number=1,
             manual_override=False)
    d.update(kw)
    return AccountState(**d)


def base_order(**kw):
    # risk = |100-99|*15 = $15 = 1.0% of 1500 -> within 1.5% cap; notional $1500
    d = dict(ticker="AAPL", side="long", entry_price=100.0, stop_price=99.0,
             shares=15, spread_pct=0.001, strategy="orb", quote_age_ms=500,
             last_bar_age_s=2, has_thesis=True, conviction_score=80.0)
    d.update(kw)
    return OrderProposal(**d)


class TestRiskGate(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.gate = RiskGate(self.cfg)

    def test_compliant_order_passes(self):
        # notional $1500 == 100% — too big; shrink to 4 shares (notional $400)
        o = base_order(shares=4)  # risk $4, notional $400 (<30% of 1500=$450)
        v = self.gate.check(o, base_acct())
        self.assertTrue(v.approved, v.violations)

    def test_per_trade_risk_cap_rejects(self):
        # risk = $1 * 30 = $30 = 2% of 1500 > 1.5% cap
        o = base_order(shares=30)
        v = self.gate.check(o, base_acct())
        self.assertIn("per_trade_risk_exceeds_cap", v.violations)

    def test_position_30pct_cap_rejects(self):
        # entry 100, stop 99.9 -> tiny risk, but notional huge
        o = base_order(entry_price=100, stop_price=99.9, shares=10)  # notional $1000 > $450
        v = self.gate.check(o, base_acct())
        self.assertIn("position_exceeds_30pct", v.violations)

    def test_spread_rejects(self):
        o = base_order(shares=4, spread_pct=0.01)  # 1% > 0.3%
        v = self.gate.check(o, base_acct())
        self.assertIn("spread_too_wide", v.violations)

    def test_thesis_less_rejected(self):
        o = base_order(shares=4, has_thesis=False)
        v = self.gate.check(o, base_acct())
        self.assertFalse(v.approved)
        self.assertIn("thesis_less_trade_forbidden", v.violations)

    def test_missing_conviction_rejected(self):
        o = base_order(shares=4, conviction_score=None)
        v = self.gate.check(o, base_acct())
        self.assertIn("missing_conviction_verdict", v.violations)

    def test_below_execution_floor_rejected(self):
        o = base_order(shares=4, conviction_score=70.0)  # floor is 72
        v = self.gate.check(o, base_acct())
        self.assertIn("below_execution_floor", v.violations)

    def test_concurrency_cap(self):
        o = base_order(shares=4)
        v = self.gate.check(o, base_acct(open_positions=3))  # cap is 3 in days 1-30
        self.assertIn("concurrency_cap_reached", v.violations)

    def test_daily_loss_limit(self):
        o = base_order(shares=4)
        v = self.gate.check(o, base_acct(day_pnl=-80))  # -5% of 1500 = -75
        self.assertIn("daily_loss_limit_hit", v.violations)

    def test_long_stop_must_be_below_entry(self):
        o = base_order(side="long", entry_price=100, stop_price=101, shares=4)
        v = self.gate.check(o, base_acct())
        self.assertIn("long_stop_not_below_entry", v.violations)

    def test_freshness_rejects_stale_quote(self):
        o = base_order(shares=4, quote_age_ms=5000)
        tol = {"quote_age_ms": 1500, "last_bar_age_s": 5}
        v = self.gate.check(o, base_acct(), freshness_tol=tol)
        self.assertIn("stale_quote", v.violations)

    def test_override_relaxes_soft_but_not_hard_caps(self):
        # over-size order with override: per_trade cap is soft (relaxed), but a
        # thesis-less trade must STILL be rejected even with override.
        o = base_order(shares=30, has_thesis=False)
        v = self.gate.check(o, base_acct(manual_override=True))
        self.assertNotIn("per_trade_risk_exceeds_cap", v.violations)
        self.assertIn("thesis_less_trade_forbidden", v.violations)

    def test_authorized_risk_allows_above_1_5pct(self):
        # governor authorizes 2.5%; an order risking ~2% must pass (not capped at 1.5%)
        # risk = $1 * 30 = $30 = 2% of 1500; notional small enough via cheap stock
        o = base_order(entry_price=20, stop_price=19, shares=30, authorized_risk_pct=0.025)
        # notional 30*20=600 > 30% of 1500=450 -> would fail position cap; use 15 shares
        o = base_order(entry_price=10, stop_price=9, shares=22, authorized_risk_pct=0.025)
        # risk = 1*22 = $22 = 1.47%; notional 220 < 450 ok
        v = self.gate.check(o, base_acct())
        self.assertTrue(v.approved, v.violations)

    def test_authorized_risk_cannot_exceed_absolute_ceiling(self):
        o = base_order(shares=4, authorized_risk_pct=0.05)  # 5% > 2.5% immutable
        v = self.gate.check(o, base_acct())
        self.assertIn("authorized_risk_exceeds_absolute_ceiling", v.violations)

    def test_absolute_ceiling_not_overridable(self):
        o = base_order(shares=4, authorized_risk_pct=0.05)
        v = self.gate.check(o, base_acct(manual_override=True))
        self.assertIn("authorized_risk_exceeds_absolute_ceiling", v.violations)

    def test_shares_for_risk_floors(self):
        self.assertEqual(RiskGate.shares_for_risk(100, 99, 15), 15)
        self.assertEqual(RiskGate.shares_for_risk(100, 99.5, 15), 30)
        self.assertEqual(RiskGate.shares_for_risk(100, 100, 15), 0)


if __name__ == "__main__":
    unittest.main()
