import os
import tempfile
import unittest

from src import config
from src.ops import selftest
from src.ops.lifecycle import startup_checks, generate_launchd_plist
from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.reconciliation import Reconciler


class TestSelfTest(unittest.TestCase):
    def test_all_checks_pass_on_valid_config(self):
        report = selftest.run(config.load())
        self.assertTrue(report.all_passed, report.summary())

    def test_category_filter(self):
        report = selftest.run(config.load(), category="pretrade")
        self.assertTrue(all(r.category == "pretrade" for r in report.results))
        self.assertGreater(len(report.results), 0)

    def test_no_lookahead_check_passes(self):
        report = selftest.run(config.load(), category="nightly")
        names = {r.name: r.passed for r in report.results}
        self.assertTrue(names.get("no_lookahead"))

    def test_summary_string(self):
        self.assertIn("self-tests passed", selftest.run(config.load()).summary())


class TestStartup(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.tmp = tempfile.mkdtemp()

    def _reconciler(self, positions):
        return Reconciler(RobinhoodMCPClient(MockTransport(
            {"get_positions": {"positions": positions}})))

    def test_clean_startup_can_trade(self):
        r = startup_checks(project_dir=self.tmp, cfg=self.cfg,
                           reconciler=self._reconciler([]), internal_positions={})
        self.assertTrue(r.can_trade, r.blockers)

    def test_halt_flag_blocks_startup(self):
        open(os.path.join(self.tmp, "HALT.flag"), "w").close()
        r = startup_checks(project_dir=self.tmp, cfg=self.cfg, run_selftests=False)
        self.assertFalse(r.can_trade)
        self.assertTrue(any("HALT.flag" in b for b in r.blockers))

    def test_reconciliation_desync_blocks(self):
        recon = self._reconciler([{"ticker": "TSLA", "shares": 5, "avg_price": 200}])
        r = startup_checks(project_dir=self.tmp, cfg=self.cfg, reconciler=recon,
                           internal_positions={}, run_selftests=False)
        self.assertFalse(r.can_trade)
        self.assertTrue(any("desync" in b for b in r.blockers))

    def test_launchd_plist_well_formed(self):
        plist = generate_launchd_plist("alarkpatel", hour=7, minute=15)
        self.assertIn("com.hooddabang.controller", plist)
        self.assertIn("<integer>7</integer>", plist)
        self.assertIn("/.venv/bin/python", plist)


if __name__ == "__main__":
    unittest.main()
