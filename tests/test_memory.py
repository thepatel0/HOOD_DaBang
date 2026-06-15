import unittest

from src.memory.store import MemoryStore, hashing_embed, cosine


class TestEmbedder(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(hashing_embed("RVOL spike above VWAP"),
                         hashing_embed("RVOL spike above VWAP"))

    def test_similar_texts_more_similar(self):
        a = hashing_embed("ORB breakout long on high volume")
        b = hashing_embed("ORB breakout long with strong volume")
        c = hashing_embed("pairs trade mean reversion crisis regime")
        self.assertGreater(cosine(a, b), cosine(a, c))


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.clock = {"t": 1_000_000.0}
        self.m = MemoryStore(clock=lambda: self.clock["t"], half_life_days=30)

    def test_add_and_retrieve_relevant(self):
        self.m.add("RVOL>3 + news + above VWAP -> ORB long expectancy 0.42R",
                   importance=5)
        self.m.add("FOMC days: entries before 14:30 underperform", importance=5)
        self.m.add("pairs spread z>2 mean reverts in crisis", importance=3)
        hits = self.m.retrieve("ORB long high relative volume above VWAP", k=1)
        self.assertIn("ORB long", hits[0].content)

    def test_importance_boosts_score(self):
        self.m.add("routine note about AAPL", importance=1)
        self.m.add("LESSON: never chase a gap without volume", importance=5)
        hits = self.m.retrieve("lesson chase gap volume", k=1)
        self.assertIn("LESSON", hits[0].content)

    def test_recency_decay(self):
        old = self.m.add("old pattern", importance=3)
        self.clock["t"] += 60 * 86400          # 60 days later (2 half-lives)
        new = self.m.add("old pattern", importance=3)
        # same content/importance; the newer item should rank higher
        hits = self.m.retrieve("old pattern", k=2)
        self.assertEqual(hits[0].id, new.id)

    def test_consolidation_graduates_confirmed(self):
        item = self.m.add("RVOL>3 ORB long works", layer="medium", importance=3)
        self.m.confirm(item); self.m.confirm(item)   # now confirmation_count=3
        out = self.m.consolidate()
        self.assertEqual(out["graduated"], 1)
        self.assertEqual(item.layer, "long")

    def test_consolidation_demotes_contradicted(self):
        item = self.m.add("pattern X", layer="long", importance=3)
        self.m.contradict(item); self.m.contradict(item)
        out = self.m.consolidate()
        self.assertEqual(out["demoted"], 1)
        self.assertEqual(item.layer, "medium")

    def test_layer_filter(self):
        self.m.add("a", layer="working")
        self.m.add("b", layer="long")
        self.assertEqual(len(self.m.all("long")), 1)


if __name__ == "__main__":
    unittest.main()
