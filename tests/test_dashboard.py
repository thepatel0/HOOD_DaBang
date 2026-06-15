import unittest

from src.monitor.dashboard import Snapshot, PositionView, render, _render_plain


def snap(**kw):
    d = dict(now_et="2026-06-15T14:32:00-04:00", regime="bull_trend_low_vol",
             equity=1567.20, session_start_equity=1500.0, day_pnl=67.20, ath=1600.0,
             trades_today=2, conviction_floor=72, signals_seen=41,
             signals_cleared=6, signals_traded=2,
             highest_not_taken="AMD ORB 69 (below 72)",
             llm_today=1.12, llm_budget=5.0, llm_month=34.1, cache_hit_rate=0.83)
    d.update(kw)
    return Snapshot(**d)


class TestDashboard(unittest.TestCase):
    def test_derived_metrics(self):
        s = snap()
        self.assertAlmostEqual(s.day_pnl_pct, 67.2 / 1500)
        self.assertAlmostEqual(s.dd_from_ath, (1600 - 1567.2) / 1600)

    def test_render_contains_key_fields(self):
        out = render(snap())
        self.assertIn("HOOD DaBang", out)
        self.assertIn("1,567", out)
        self.assertIn("CONVICTION GATE", out)
        self.assertIn("41", out)                 # signals seen
        self.assertIn("AMD ORB 69", out)         # highest not taken

    def test_render_positions(self):
        s = snap(positions=[PositionView("AAPL", "long", 50, 189.43, 191.10, 188.90,
                                         "orb")])
        out = render(s)
        self.assertIn("AAPL", out)
        self.assertIn("orb", out)

    def test_render_flat(self):
        out = render(snap(positions=[]))
        self.assertIn("flat", out)

    def test_render_halt(self):
        out = render(snap(halted=True, halt_reason="#1 daily_loss_limit"))
        self.assertIn("daily_loss_limit", out)

    def test_plain_fallback(self):
        out = _render_plain(snap())
        self.assertIn("HOOD DaBang", out)
        self.assertIn("Gate:", out)


if __name__ == "__main__":
    unittest.main()
