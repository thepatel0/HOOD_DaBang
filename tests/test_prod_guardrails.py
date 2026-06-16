import unittest
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None

from src import config
from src.ops import market_hours as mh
from src.operator.passcode import verify_passcode, DEFAULT_DEPLOYMENT_CAP_USD
from src.risk import RiskGate, OrderProposal, AccountState
from src.audit import AuditLog
from src.robinhood import RobinhoodAgenticAdapter
from src.mcp_client import MCPError


def et(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


class TestMarketHours(unittest.TestCase):
    def test_regular_session(self):
        s = mh.classify(et(2026, 6, 15, 10, 0))   # Monday 10:00 ET
        self.assertEqual(s.session, "regular")
        self.assertEqual(s.market_hours, "regular_hours")
        self.assertTrue(s.is_open)
        self.assertFalse(s.limit_only)

    def test_pre_market(self):
        s = mh.classify(et(2026, 6, 15, 8, 0))
        self.assertEqual(s.session, "pre_market")
        self.assertEqual(s.market_hours, "extended_hours")
        self.assertTrue(s.limit_only)

    def test_after_hours(self):
        s = mh.classify(et(2026, 6, 15, 17, 0))
        self.assertEqual(s.session, "after_hours")
        self.assertEqual(s.market_hours, "extended_hours")

    def test_overnight(self):
        s = mh.classify(et(2026, 6, 15, 22, 0))    # Mon night
        self.assertEqual(s.session, "overnight")
        self.assertEqual(s.market_hours, "all_day_hours")

    def test_weekend_closed(self):
        s = mh.classify(et(2026, 6, 13, 12, 0))    # Saturday
        self.assertEqual(s.session, "closed")
        self.assertFalse(s.is_open)

    def test_sunday_evening_overnight(self):
        self.assertEqual(mh.classify(et(2026, 6, 14, 21, 0)).session, "overnight")
        self.assertEqual(mh.classify(et(2026, 6, 14, 12, 0)).session, "closed")

    def test_holiday_closed(self):
        s = mh.classify(et(2026, 7, 3, 11, 0))     # July 3 holiday
        self.assertEqual(s.session, "closed")

    def test_market_hours_for_extended_requires_approval(self):
        # after-hours: only returns extended if the order is approved for it
        self.assertIsNone(mh.market_hours_for(False, et(2026, 6, 15, 17, 0)))
        self.assertEqual(mh.market_hours_for(True, et(2026, 6, 15, 17, 0)),
                         "extended_hours")
        # regular session always regular_hours regardless
        self.assertEqual(mh.market_hours_for(False, et(2026, 6, 15, 10, 0)),
                         "regular_hours")


class TestPasscode(unittest.TestCase):
    def test_correct(self):
        self.assertTrue(verify_passcode("pinappleexpress9"))

    def test_wrong(self):
        self.assertFalse(verify_passcode("pineappleexpress9"))
        self.assertFalse(verify_passcode(""))
        self.assertFalse(verify_passcode("PINAPPLEEXPRESS9"))

    def test_cap_value(self):
        self.assertEqual(DEFAULT_DEPLOYMENT_CAP_USD, 500.0)


def order(**kw):
    d = dict(ticker="AAPL", side="long", entry_price=100.0, stop_price=99.0,
             shares=4, spread_pct=0.001, strategy="orb", has_thesis=True,
             conviction_score=80.0)
    d.update(kw)
    return OrderProposal(**d)


def acct(**kw):
    # equity above the $1050 catastrophic floor so we isolate the deployment cap
    d = dict(equity=1500, effective_capital=1500, session_start_equity=1500,
             day_pnl=0.0, open_positions=0, gross_exposure=0.0, day_number=1)
    d.update(kw)
    return AccountState(**d)


class TestDeploymentCap(unittest.TestCase):
    def setUp(self):
        self.gate = RiskGate(config.load())

    def test_within_cap_passes(self):
        # 2 shares * $100 = $200 notional (< 30% position cap, < $500 deploy)
        v = self.gate.check(order(shares=2, stop_price=99.5), acct())
        self.assertTrue(v.approved, v.violations)

    def test_exceeds_cap_rejected(self):
        # existing $400 deployed + $200 new = $600 > $500 cap
        v = self.gate.check(order(shares=2, stop_price=99.5),
                            acct(gross_exposure=400.0))
        self.assertIn("deployment_cap_exceeded", v.violations)

    def test_passcode_override_allows(self):
        v = self.gate.check(order(shares=2, stop_price=99.5),
                            acct(gross_exposure=400.0, deployment_cap_override=True))
        self.assertNotIn("deployment_cap_exceeded", v.violations)

    def test_manual_override_does_not_lift_cap(self):
        # generic manual_override must NOT bypass the deployment cap (passcode only)
        v = self.gate.check(order(shares=2, stop_price=99.5),
                            acct(gross_exposure=400.0, manual_override=True))
        self.assertIn("deployment_cap_exceeded", v.violations)


class TestForBalance(unittest.TestCase):
    def test_recalibrates_for_1000(self):
        cfg = config.for_balance(1000)
        self.assertEqual(cfg["account"]["starting_capital_usd"], 1000)
        self.assertEqual(cfg["risk"]["catastrophic_halt_equity_usd"], 700.0)
        self.assertEqual(cfg["risk"]["deployment_cap_usd"], 500.0)
        self.assertEqual(cfg["capital_ramp"]["live_day_31_plus_usd"], 1000)

    def test_1000_account_not_auto_halted(self):
        # a $1000 account must NOT trip the catastrophic halt under for_balance
        cfg = config.for_balance(1000)
        gate = RiskGate(cfg)
        a = AccountState(equity=1000, effective_capital=1000, session_start_equity=1000,
                         day_pnl=0.0, open_positions=0, gross_exposure=0.0)
        v = gate.check(order(shares=2, stop_price=99.5), a)
        self.assertNotIn("catastrophic_halt", v.violations)


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self.log = AuditLog(":memory:")

    def test_records_and_reads(self):
        eid = self.log.record("PROPOSED", symbol="AAPL", side="buy", quantity=1,
                              price=100.0)
        self.assertTrue(eid)
        self.assertEqual(self.log.count(), 1)
        self.assertEqual(self.log.entries()[0]["symbol"], "AAPL")

    def test_rejects_unknown_event(self):
        with self.assertRaises(ValueError):
            self.log.record("NONSENSE")

    def test_immutable_no_update_delete_methods(self):
        self.assertFalse(hasattr(self.log, "update"))
        self.assertFalse(hasattr(self.log, "delete"))

    def test_filter_by_event(self):
        self.log.record("PLACED", symbol="AAPL")
        self.log.record("FILL", symbol="AAPL")
        self.assertEqual(len(self.log.entries(event_type="PLACED")), 1)


# ---- fake transport that mimics the REAL Robinhood tool surface ---------- #
class FakeRH:
    def __init__(self, agentic=True, acct_type="cash", review_alert=None,
                 place_state="filled"):
        self.agentic = agentic
        self.acct_type = acct_type
        self.review_alert = review_alert
        self.place_state = place_state
        self.calls = []

    def list_tools(self):
        from src.robinhood import REAL_TOOLS
        return list(REAL_TOOLS)

    def call(self, tool, params):
        self.calls.append((tool, params))
        if tool == "get_accounts":
            return {"data": {"accounts": [{"account_number": "581853207",
                    "agentic_allowed": self.agentic, "type": self.acct_type}]}}
        if tool == "get_portfolio":
            return {"data": {"total_value": "1000", "cash": "1000",
                    "equity_value": "0", "buying_power": {"buying_power": "1000.0"}}}
        if tool == "get_equity_positions":
            return {"data": {"positions": []}}
        if tool == "get_equity_quotes":
            return {"data": {"results": [{"quote": {"bid_price": "99.90",
                    "ask_price": "100.10", "last_trade_price": "100.00"}}]}}
        if tool == "review_equity_order":
            return {"data": {"order_checks": self.review_alert or {},
                    "quote_data": {"ask_price": "100.10"}}}
        if tool == "place_equity_order":
            return {"data": {"id": "ord-1", "state": self.place_state,
                    "cumulative_quantity": params.get("quantity", "1"),
                    "average_price": "100.00"}}
        if tool == "cancel_equity_order":
            return {"data": {}}
        if tool == "get_equity_orders":
            return {"data": {"orders": [{"id": "ord-1", "state": "filled",
                    "cumulative_quantity": "1", "average_price": "100.00"}]}}
        return {"data": {}}


class TestRobinhoodAdapter(unittest.TestCase):
    def _adapter(self, **kw):
        return RobinhoodAgenticAdapter(FakeRH(**kw), "581853207")

    def test_validate_tool_map_clean(self):
        self.assertEqual(self._adapter().validate_tool_map(), [])

    def test_agentic_guard_passes(self):
        self._adapter().assert_agentic_account()   # no raise

    def test_agentic_guard_blocks_non_agentic(self):
        with self.assertRaises(MCPError):
            self._adapter(agentic=False).assert_agentic_account()

    def test_agentic_guard_blocks_margin(self):
        with self.assertRaises(MCPError):
            self._adapter(acct_type="margin").assert_agentic_account()

    def test_get_account_uses_portfolio(self):
        a = self._adapter().get_account()
        self.assertEqual(a.buying_power, 1000.0)

    def test_get_quote(self):
        q = self._adapter().get_quote("AAPL")
        self.assertAlmostEqual(q.last, 100.0)

    def test_place_order_reviews_then_places(self):
        fake = FakeRH()
        adapter = RobinhoodAgenticAdapter(fake, "581853207")
        res = adapter.place_order("AAPL", "buy", 1, 100.10, "coid-1")
        self.assertEqual(res.status, "filled")
        tools = [c[0] for c in fake.calls]
        self.assertIn("review_equity_order", tools)   # mandatory preview ran
        self.assertIn("place_equity_order", tools)
        self.assertLess(tools.index("review_equity_order"),
                        tools.index("place_equity_order"))

    def test_place_order_blocked_by_review_alert(self):
        fake = FakeRH(review_alert={"insufficient_buying_power": True})
        adapter = RobinhoodAgenticAdapter(fake, "581853207")
        res = adapter.place_order("AAPL", "buy", 1, 100.10, "coid-2")
        self.assertEqual(res.status, "rejected")
        self.assertNotIn("place_equity_order", [c[0] for c in fake.calls])  # never placed

    def test_stop_order_uses_stop_market(self):
        fake = FakeRH()
        adapter = RobinhoodAgenticAdapter(fake, "581853207")
        adapter.place_stop_order("AAPL", "sell", 1, 98.0, "coid-3")
        place = [c for c in fake.calls if c[0] == "place_equity_order"][0]
        self.assertEqual(place[1]["type"], "stop_market")
        self.assertEqual(place[1]["side"], "sell")
        self.assertEqual(place[1]["ref_id"], "coid-3")

    def test_audit_hooks_fire(self):
        log = AuditLog(":memory:")
        adapter = RobinhoodAgenticAdapter(FakeRH(), "581853207", audit=log)
        adapter.place_order("AAPL", "buy", 1, 100.10, "coid-4")
        events = {e["event_type"] for e in log.entries()}
        self.assertIn("REVIEWED", events)
        self.assertIn("PLACED", events)


if __name__ == "__main__":
    unittest.main()
