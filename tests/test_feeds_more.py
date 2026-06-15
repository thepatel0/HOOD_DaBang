import unittest

from src.data_feeds.news_rss import NewsFeed, url_hash
from src.data_feeds.sec_edgar import (SecEdgarFeed, FredFeed, EarningsCalendar,
                                      EarningsEvent)


class TestNewsFeed(unittest.TestCase):
    def _entries(self, n=3):
        return [{"title": f"headline {i}", "link": f"http://x/{i}", "published": "t"}
                for i in range(n)]

    def test_fetch_and_dedup(self):
        feed = NewsFeed(fetcher=lambda url: self._entries(3), ttl_s=0)
        r1 = feed.fetch("AAPL", only_new=True)
        self.assertEqual(len(r1.headlines), 3)
        # second fetch: same articles already seen -> none new
        r2 = feed.fetch("AAPL", only_new=True)
        self.assertEqual(len(r2.headlines), 0)

    def test_cache_within_ttl(self):
        calls = {"n": 0}
        def fetcher(url):
            calls["n"] += 1
            return self._entries(2)
        clock = {"t": 100.0}
        feed = NewsFeed(fetcher=fetcher, ttl_s=300, clock=lambda: clock["t"])
        feed.fetch("AAPL")
        feed.fetch("AAPL")          # within TTL
        self.assertEqual(calls["n"], 1)

    def test_degrades_on_error(self):
        feed = NewsFeed(fetcher=lambda url: self._entries(2), ttl_s=0)
        feed.fetch("AAPL", only_new=False)
        feed.fetcher = lambda url: (_ for _ in ()).throw(ConnectionError("down"))
        r = feed.fetch("AAPL", only_new=False)
        self.assertTrue(r.degraded)

    def test_url_hash_stable(self):
        self.assertEqual(url_hash("http://a"), url_hash("http://a"))


class TestSecEdgar(unittest.TestCase):
    def test_parses_form4(self):
        raw = [{"insider": "ceo", "role": "CEO", "side": "buy", "dollars": 600000,
                "days_ago": 3, "accession": "a1"}]
        feed = SecEdgarFeed(fetcher=lambda cik: raw)
        txns = feed.fetch_form4("320193")
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].role, "CEO")

    def test_dedup_by_accession(self):
        raw = [{"insider": "x", "role": "Dir", "side": "buy", "dollars": 1,
                "accession": "dup"}]
        feed = SecEdgarFeed(fetcher=lambda cik: raw, ttl_s=0)
        feed.fetch_form4("1")
        second = feed.fetch_form4("1")   # same accession -> filtered
        self.assertEqual(len(second), 0)

    def test_degrades_to_empty(self):
        feed = SecEdgarFeed(fetcher=lambda cik: (_ for _ in ()).throw(IOError()))
        self.assertEqual(feed.fetch_form4("1"), [])


class TestFred(unittest.TestCase):
    def test_get_and_cache(self):
        calls = {"n": 0}
        def f(s):
            calls["n"] += 1
            return 4.25
        clock = {"t": 0.0}
        fred = FredFeed(fetcher=f, ttl_s=3600, clock=lambda: clock["t"])
        self.assertEqual(fred.get("DGS10"), 4.25)
        fred.get("DGS10")
        self.assertEqual(calls["n"], 1)

    def test_degrades_to_none(self):
        fred = FredFeed(fetcher=None)
        self.assertIsNone(fred.get("DGS10"))


class TestEarnings(unittest.TestCase):
    def test_events_and_days_since(self):
        cal = EarningsCalendar(fetcher=lambda d: [{"ticker": "AAPL", "date": d,
                                                   "timing": "AMC"}])
        evs = cal.events("2026-06-15")
        self.assertEqual(evs[0].ticker, "AAPL")
        self.assertEqual(cal.days_since_earnings("AAPL", evs, "2026-06-15"), 0)
        self.assertIsNone(cal.days_since_earnings("MSFT", evs, "2026-06-15"))


if __name__ == "__main__":
    unittest.main()
