import unittest

from src.data_feeds.bars import CachedBarFeed, FeedResult
from src.strategies.base import Bar


def fake_bars(n=3, base=100.0):
    return [Bar(f"2026-06-1{i}T00:00:00", base+i, base+i+1, base+i-1, base+i+0.5, 1000)
            for i in range(n)]


class TestCachedBarFeed(unittest.TestCase):
    def test_fetches_and_caches(self):
        calls = {"n": 0}
        def fetcher(t, iv, lb):
            calls["n"] += 1
            return fake_bars()
        clock = {"t": 1000.0}
        feed = CachedBarFeed(fetcher=fetcher, ttl_s=300, clock=lambda: clock["t"])
        r1 = feed.get_bars("AAPL")
        self.assertFalse(r1.from_cache)
        self.assertEqual(len(r1.bars), 3)
        r2 = feed.get_bars("AAPL")          # within TTL -> cache, no new fetch
        self.assertTrue(r2.from_cache)
        self.assertEqual(calls["n"], 1)

    def test_refetch_after_ttl(self):
        calls = {"n": 0}
        def fetcher(t, iv, lb):
            calls["n"] += 1
            return fake_bars()
        clock = {"t": 1000.0}
        feed = CachedBarFeed(fetcher=fetcher, ttl_s=300, clock=lambda: clock["t"])
        feed.get_bars("AAPL")
        clock["t"] = 1000.0 + 301        # past TTL
        feed.get_bars("AAPL")
        self.assertEqual(calls["n"], 2)

    def test_fetch_error_serves_stale_cache(self):
        state = {"fail": False}
        def fetcher(t, iv, lb):
            if state["fail"]:
                raise ConnectionError("yahoo down")
            return fake_bars()
        clock = {"t": 1000.0}
        feed = CachedBarFeed(fetcher=fetcher, ttl_s=10, clock=lambda: clock["t"])
        feed.get_bars("AAPL")            # populate cache
        clock["t"] += 100               # expire
        state["fail"] = True
        r = feed.get_bars("AAPL")        # fetch fails -> serve stale, degraded
        self.assertTrue(r.degraded)
        self.assertTrue(r.from_cache)
        self.assertEqual(len(r.bars), 3)

    def test_fetch_error_no_cache_returns_empty_degraded(self):
        def fetcher(t, iv, lb):
            raise ConnectionError("down")
        feed = CachedBarFeed(fetcher=fetcher)
        r = feed.get_bars("AAPL")
        self.assertTrue(r.degraded)
        self.assertEqual(r.bars, [])

    def test_empty_fetch_serves_stale(self):
        state = {"empty": False}
        def fetcher(t, iv, lb):
            return [] if state["empty"] else fake_bars()
        clock = {"t": 1000.0}
        feed = CachedBarFeed(fetcher=fetcher, ttl_s=10, clock=lambda: clock["t"])
        feed.get_bars("AAPL")
        clock["t"] += 100
        state["empty"] = True
        r = feed.get_bars("AAPL")
        self.assertTrue(r.degraded)
        self.assertEqual(len(r.bars), 3)


if __name__ == "__main__":
    unittest.main()
