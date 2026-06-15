import unittest

from src.monitor.health import (PnLVelocityMonitor, FeedHealthMonitor,
                                OrderRateMonitor)
from src.killswitch import KillswitchState, evaluate


class TestPnLVelocity(unittest.TestCase):
    def test_no_anomaly_on_smooth_pnl(self):
        clk = {"t": 0.0}
        m = PnLVelocityMonitor(clock=lambda: clk["t"])
        for i in range(20):
            clk["t"] += 1
            m.record(i * 1.0)            # smooth +1/s
        self.assertFalse(m.is_anomaly())

    def test_anomaly_on_sudden_jump(self):
        clk = {"t": 0.0}
        m = PnLVelocityMonitor(clock=lambda: clk["t"])
        for i in range(20):
            clk["t"] += 1
            m.record(i * 0.1)            # gentle drift
        clk["t"] += 1
        m.record(100.0)                  # sudden huge jump
        self.assertTrue(m.is_anomaly())

    def test_insufficient_data_no_anomaly(self):
        m = PnLVelocityMonitor()
        m.record(1.0)
        self.assertFalse(m.is_anomaly())


class TestFeedHealth(unittest.TestCase):
    def test_stale_detection(self):
        clk = {"t": 0.0}
        m = FeedHealthMonitor(clock=lambda: clk["t"])
        m.heartbeat("yfinance")
        clk["t"] = 40
        self.assertTrue(m.is_stale("yfinance", 30))
        self.assertFalse(m.is_stale("yfinance", 60))

    def test_unknown_feed_is_stale(self):
        self.assertTrue(FeedHealthMonitor().is_stale("never", 30))


class TestOrderRate(unittest.TestCase):
    def test_excessive(self):
        clk = {"t": 0.0}
        m = OrderRateMonitor(clock=lambda: clk["t"])
        for _ in range(12):
            m.record_order()
        self.assertTrue(m.is_excessive(hard_cap=10))

    def test_window_expiry(self):
        clk = {"t": 0.0}
        m = OrderRateMonitor(window_s=60, clock=lambda: clk["t"])
        m.record_order()
        clk["t"] = 120
        m.record_order()
        self.assertEqual(m.rate(), 1)


class TestLiveFeedKillswitches(unittest.TestCase):
    def fired(self, **kw):
        return {h.name for h in evaluate(KillswitchState(**kw))}

    def test_mcp_failure(self):
        self.assertIn("mcp_failure", self.fired(mcp_heartbeat_age_s=70))

    def test_stale_feed_only_with_position(self):
        self.assertNotIn("stale_feed_open_position",
                         self.fired(data_feed_stale_age_s=40, has_open_position=False))
        self.assertIn("stale_feed_open_position",
                      self.fired(data_feed_stale_age_s=40, has_open_position=True))

    def test_quote_spike(self):
        self.assertIn("unexplained_quote_spike",
                      self.fired(quote_spike_unexplained=True))

    def test_pnl_velocity(self):
        self.assertIn("pnl_velocity_anomaly", self.fired(pnl_velocity_anomaly=True))

    def test_order_rate(self):
        self.assertIn("order_rate_amplification", self.fired(order_rate_excessive=True))


if __name__ == "__main__":
    unittest.main()
