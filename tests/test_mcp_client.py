import unittest

from src.mcp_client import (
    RobinhoodMCPClient, MockTransport, MCPSchemaError, MCPError,
)


class TestMCPClient(unittest.TestCase):
    def test_get_account_parses(self):
        t = MockTransport({"get_account_info": {"cash": 1500.0, "equity": 1500.0,
                                                "buying_power": 1500.0}})
        c = RobinhoodMCPClient(t)
        acct = c.get_account()
        self.assertEqual(acct.equity, 1500.0)

    def test_missing_field_raises_schema_error(self):
        t = MockTransport({"get_account_info": {"cash": 1500.0}})  # missing equity
        c = RobinhoodMCPClient(t)
        with self.assertRaises(MCPSchemaError):
            c.get_account()

    def test_non_numeric_field_raises(self):
        t = MockTransport({"get_quote": {"bid": "oops", "ask": 10.0, "last": 9.9}})
        c = RobinhoodMCPClient(t)
        with self.assertRaises(MCPSchemaError):
            c.get_quote("AAPL")

    def test_quote_spread(self):
        t = MockTransport({"get_quote": {"bid": 99.9, "ask": 100.1, "last": 100.0}})
        q = RobinhoodMCPClient(t).get_quote("AAPL")
        self.assertAlmostEqual(q.mid, 100.0, places=3)
        self.assertAlmostEqual(q.spread_pct, 0.002, places=4)

    def test_place_order_validates_side(self):
        c = RobinhoodMCPClient(MockTransport())
        with self.assertRaises(MCPSchemaError):
            c.place_order("AAPL", "long", 10, 100.0, "id1")  # 'long' invalid; want buy/sell

    def test_place_order_validates_shares(self):
        c = RobinhoodMCPClient(MockTransport())
        with self.assertRaises(MCPSchemaError):
            c.place_order("AAPL", "buy", 0, 100.0, "id1")

    def test_validate_tool_map_detects_missing(self):
        # server only exposes a subset -> the rest are flagged (failure mode #6)
        t = MockTransport(tools=["get_account_info", "get_quote"])
        c = RobinhoodMCPClient(t)
        missing = c.validate_tool_map()
        self.assertIn("place_order", missing)
        self.assertNotIn("get_account", missing)

    def test_no_canned_response_raises(self):
        c = RobinhoodMCPClient(MockTransport())
        with self.assertRaises(MCPError):
            c.get_account()


if __name__ == "__main__":
    unittest.main()
