import unittest

from src import config
from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.execution import ExecutionHandler, OrderRequest


def make_handler(place_resp=None, stop_resp=None, clock=None):
    """Build a handler over a MockTransport with configurable fill/stop behavior."""
    place_resp = place_resp or {"order_id": "O1", "status": "filled",
                                "filled_shares": 10, "avg_fill_price": 100.0}
    stop_resp = stop_resp or {"order_id": "S1", "status": "accepted",
                              "filled_shares": 0, "avg_fill_price": 0.0}
    responses = {
        "place_order": lambda p: (place_resp if not p["client_order_id"].endswith("-flat")
                                  else {"order_id": "F1", "status": "filled",
                                        "filled_shares": p["shares"], "avg_fill_price": 100.0}),
        "place_stop_order": stop_resp,
        "cancel_order": {},
        "get_order_status": place_resp,
    }
    client = RobinhoodMCPClient(MockTransport(responses))
    cfg = config.load()
    kw = {"clock": clock} if clock else {}
    return ExecutionHandler(client, cfg, **kw), client


def good_req(**kw):
    d = dict(ticker="AAPL", side="buy", shares=10, limit_price=100.05,
             stop_price=99.0, client_order_id="c1", conviction_score=78.0,
             thesis_id="t1", has_thesis=True)
    d.update(kw)
    return OrderRequest(**d)


class TestExecution(unittest.TestCase):
    def test_happy_path_filled_and_protected(self):
        h, _ = make_handler()
        r = h.submit(good_req())
        self.assertTrue(r.accepted)
        self.assertEqual(r.filled_shares, 10)
        self.assertEqual(r.stop_order_id, "S1")
        self.assertFalse(r.flattened)

    def test_idempotent_no_double_fire(self):
        h, client = make_handler()
        req = good_req()
        r1 = h.submit(req)
        n_after_first = len(client.t.calls)
        r2 = h.submit(req)  # same client_order_id
        self.assertIs(r1, r2)
        self.assertEqual(len(client.t.calls), n_after_first)  # no new broker calls

    def test_conviction_below_floor_blocked(self):
        h, client = make_handler()
        r = h.submit(good_req(conviction_score=70.0))  # floor 72
        self.assertFalse(r.accepted)
        self.assertEqual(r.kill, "conviction_bypass")
        self.assertEqual(len(client.t.calls), 0)  # never touched the broker

    def test_missing_conviction_blocked(self):
        h, _ = make_handler()
        r = h.submit(good_req(conviction_score=None))
        self.assertEqual(r.kill, "conviction_bypass")

    def test_thesis_less_blocked(self):
        h, client = make_handler()
        r = h.submit(good_req(has_thesis=False, thesis_id=None))
        self.assertFalse(r.accepted)
        self.assertEqual(r.kill, "thesis_less_trade")
        self.assertEqual(len(client.t.calls), 0)

    def test_stop_rejected_flattens(self):
        h, _ = make_handler(stop_resp={"order_id": "S1", "status": "rejected",
                                       "filled_shares": 0, "avg_fill_price": 0.0})
        r = h.submit(good_req())
        self.assertFalse(r.accepted)
        self.assertTrue(r.flattened)
        self.assertEqual(r.kill, "unhedged_position")

    def test_stop_deadline_exceeded_flattens(self):
        # clock jumps 5s between order and stop confirm (> 2s deadline)
        ticks = iter([0.0, 5.0, 5.0, 5.0])
        h, _ = make_handler(clock=lambda: next(ticks))
        r = h.submit(good_req())
        self.assertTrue(r.flattened)
        self.assertEqual(r.kill, "unhedged_position")

    def test_partial_fill_stop_sized_to_fill(self):
        h, client = make_handler(place_resp={"order_id": "O1", "status": "partial",
                                             "filled_shares": 4, "avg_fill_price": 100.0})
        r = h.submit(good_req(shares=10))
        self.assertTrue(r.accepted)
        self.assertEqual(r.filled_shares, 4)
        # the stop order was sized to the 4 filled shares, not 10
        stop_calls = [c for c in client.t.calls if c["tool"] == "place_stop_order"]
        self.assertEqual(stop_calls[0]["params"]["shares"], 4)

    def test_unfilled_cancelled_no_stop(self):
        h, client = make_handler(place_resp={"order_id": "O1", "status": "accepted",
                                            "filled_shares": 0, "avg_fill_price": 0.0})
        r = h.submit(good_req())
        self.assertFalse(r.accepted)
        self.assertIn("unfilled", r.reason)
        stop_calls = [c for c in client.t.calls if c["tool"] == "place_stop_order"]
        self.assertEqual(len(stop_calls), 0)


if __name__ == "__main__":
    unittest.main()
