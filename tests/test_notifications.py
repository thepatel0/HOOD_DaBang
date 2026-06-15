import unittest

from src.monitor.notifications import Notifier


class TestNotifications(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.n = Notifier(runner=lambda argv: self.calls.append(argv))

    def test_loud_event_has_sound(self):
        n = self.n.notify("stop_hit", "Stop", "AAPL stopped out")
        self.assertTrue(n.loud)
        self.assertEqual(n.sound, "Glass")
        self.assertIn("sound name", self.calls[0][2])

    def test_quiet_event_no_sound(self):
        n = self.n.notify("brief_ready", "Brief", "Watchlist ready")
        self.assertFalse(n.loud)
        self.assertNotIn("sound name", self.calls[0][2])

    def test_escapes_quotes(self):
        self.n.notify("info", 'Say "hi"', 'a "quoted" message')
        self.assertIn('\\"', self.calls[0][2])

    def test_disabled_runner_not_called(self):
        n = Notifier(runner=lambda argv: self.calls.append(argv), enabled=False)
        n.notify("info", "t", "m")
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(len(n.sent), 1)   # still recorded

    def test_uses_osascript(self):
        self.n.notify("info", "t", "m")
        self.assertEqual(self.calls[0][0], "osascript")


if __name__ == "__main__":
    unittest.main()
