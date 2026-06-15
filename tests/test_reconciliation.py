import unittest

from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.reconciliation import Reconciler


def client_with_positions(positions):
    resp = {"get_positions": {"positions": positions}}
    return RobinhoodMCPClient(MockTransport(resp))


class TestReconciliation(unittest.TestCase):
    def test_in_sync(self):
        c = client_with_positions([{"ticker": "AAPL", "shares": 10, "avg_price": 100.0}])
        r = Reconciler(c).reconcile({"AAPL": 10})
        self.assertTrue(r.in_sync)
        self.assertFalse(r.should_halt)

    def test_share_mismatch_halts(self):
        c = client_with_positions([{"ticker": "AAPL", "shares": 7, "avg_price": 100.0}])
        r = Reconciler(c).reconcile({"AAPL": 10})
        self.assertTrue(r.should_halt)
        self.assertEqual(r.discrepancies[0].kind, "share_mismatch")

    def test_missing_at_broker(self):
        c = client_with_positions([])  # broker has nothing
        r = Reconciler(c).reconcile({"AAPL": 10})
        self.assertEqual(r.discrepancies[0].kind, "missing_at_broker")

    def test_unknown_at_broker(self):
        # broker holds a position we don't track -> serious (Knight-Capital-style)
        c = client_with_positions([{"ticker": "TSLA", "shares": 5, "avg_price": 200.0}])
        r = Reconciler(c).reconcile({})
        self.assertEqual(r.discrepancies[0].kind, "unknown_at_broker")

    def test_zero_internal_ignored(self):
        c = client_with_positions([])
        r = Reconciler(c).reconcile({"AAPL": 0})  # closed position, 0 shares
        self.assertTrue(r.in_sync)


if __name__ == "__main__":
    unittest.main()
