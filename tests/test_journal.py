import unittest

from src import db
from src.journal import Journal
from src.insight.thesis import Thesis, Driver


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.conn = db.init_db(":memory:")
        self.j = Journal(self.conn)

    def test_thesis_roundtrip(self):
        t = Thesis("AAPL", "long", "to 103", "real mechanism", ["loses 100"],
                   drivers=[Driver("rvol=2.5", 0.9)], confidence=0.7, base_rate=0.5)
        tid = self.j.record_thesis(t, "2026-06-15T09:42:00-04:00")
        got = self.j.get_thesis(tid)
        self.assertEqual(got["mechanism"], "real mechanism")
        self.assertEqual(got["confidence"], 0.7)

    def test_conviction_log(self):
        self.j.log_conviction("2026-06-15T09:42:00", "AAPL", "orb", 74.0, 78.0,
                              True, True, "advanced_to_llm")
        rows = self.conn.execute("SELECT advanced, traded FROM conviction_log").fetchall()
        self.assertEqual(rows[0], (1, 1))

    def test_position_mirror_and_open_positions(self):
        self.j.open_position("AAPL", 10, 101.5, "S1", "orb", "tid1",
                             "2026-06-15T09:43:00")
        self.assertEqual(self.j.open_positions(), {"AAPL": 10})
        self.j.close_position("AAPL")
        self.assertEqual(self.j.open_positions(), {})

    def test_trade_lifecycle(self):
        tid = self.j.record_trade(
            ticker="AAPL", strategy="orb", strategy_version="1.0.0", side="long",
            entry_ts="2026-06-15T09:43:00", entry_price=101.5, entry_shares=10,
            stop_price=99.9, conviction_score=78.0, thesis_id="tid1",
            market_regime="bull_trend_low_vol", order_id="O1", target_price=103.9)
        self.j.close_trade(tid, exit_ts="2026-06-15T09:50:00", exit_price=103.9,
                           exit_reason="target", pnl_dollars=24.0, pnl_r=1.5)
        closed = self.j.closed_trades()
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["pnl_r"], 1.5)
        self.assertEqual(closed[0]["exit_reason"], "target")

    def test_order_id_unique(self):
        import sqlite3
        self.j.record_trade(ticker="AAPL", strategy="orb", strategy_version="1.0.0",
                            side="long", entry_ts="t", entry_price=1, entry_shares=1,
                            stop_price=0.5, conviction_score=78, thesis_id="x",
                            market_regime="r", order_id="DUP")
        with self.assertRaises(sqlite3.IntegrityError):
            self.j.record_trade(ticker="AAPL", strategy="orb", strategy_version="1.0.0",
                                side="long", entry_ts="t", entry_price=1, entry_shares=1,
                                stop_price=0.5, conviction_score=78, thesis_id="x",
                                market_regime="r", order_id="DUP")  # same order_id

    def test_equity_curve(self):
        self.j.update_equity("2026-06-15T16:00:00", 1567.2, 67.2, 0.02, 1600, 300)
        row = self.conn.execute("SELECT equity, effective_capital FROM equity_curve").fetchone()
        self.assertEqual(row, (1567.2, 300))


if __name__ == "__main__":
    unittest.main()
