import json
import unittest
from datetime import datetime, timezone

from src import config, db
from src.llm_budget import LLMBudget
from src.llm_client import LLMClient
from src.agents.debate import run_debate
from src.agents.trader import synthesize, pm_decide
from src.agents.base import parse_json_lenient


class ScriptedTransport:
    """Returns role-appropriate JSON based on the system prompt."""
    def __init__(self, bull=0.8, bear=0.4, trader_decision="trade", pm="execute"):
        self.bull, self.bear = bull, bear
        self.trader_decision, self.pm = trader_decision, pm
        self.calls = []

    def complete(self, model, system, messages, max_tokens, cached_tokens):
        self.calls.append(system[:20])
        if system.startswith("You are the Bull"):
            text = json.dumps({"confidence": self.bull, "thesis": "bull case",
                               "risks": ["r1"]})
        elif system.startswith("You are the Bear"):
            text = json.dumps({"confidence": self.bear, "thesis": "bear case",
                               "risks": ["r2"]})
        elif system.startswith("You are the Trader"):
            text = json.dumps({"decision": self.trader_decision, "side": "long",
                               "confidence": 0.75, "thesis_summary": "go",
                               "invalidation": ["loses vwap"]})
        else:  # PM
            text = json.dumps({"decision": self.pm, "reason": "ok", "size_factor": 0.9})
        return {"text": text, "input_tokens": 3000, "output_tokens": 300,
                "cached_tokens": cached_tokens, "latency_ms": 0}


def client(transport):
    budget = LLMBudget(db.init_ledger(":memory:"), config.load(),
                       now=lambda: datetime(2026, 6, 15, tzinfo=timezone.utc))
    return LLMClient(config.load(), budget, transport)


CTX = {"ticker": "AAPL", "strategy": "orb", "side": "long", "entry": 101.5,
       "factors": {"setup_quality": 80}}


class TestDebate(unittest.TestCase):
    def test_debate_margin(self):
        d = run_debate(client(ScriptedTransport(bull=0.8, bear=0.4)), CTX)
        self.assertTrue(d.spent)
        self.assertAlmostEqual(d.bull_confidence, 0.8)
        self.assertAlmostEqual(d.bear_confidence, 0.4)
        self.assertAlmostEqual(d.margin, 0.4)

    def test_bear_wins_zero_margin(self):
        d = run_debate(client(ScriptedTransport(bull=0.3, bear=0.7)), CTX)
        self.assertEqual(d.margin, 0.0)   # margin floored at 0

    def test_degrades_to_neutral_when_budget_exhausted(self):
        c = client(ScriptedTransport())
        c.budget.record("trader", "opus-4.8", 2_000_000, 200_000)  # blow budget
        d = run_debate(c, CTX)
        self.assertFalse(d.spent)
        self.assertEqual(d.bull_confidence, 0.5)
        self.assertEqual(d.bear_confidence, 0.5)


class TestTrader(unittest.TestCase):
    def test_trade_plan_parsed(self):
        plan = synthesize(client(ScriptedTransport(trader_decision="trade")), CTX)
        self.assertEqual(plan.decision, "trade")
        self.assertEqual(plan.side, "long")
        self.assertGreater(plan.confidence, 0)

    def test_pass_decision(self):
        plan = synthesize(client(ScriptedTransport(trader_decision="pass")), CTX)
        self.assertEqual(plan.decision, "pass")

    def test_degrades_to_pass_when_not_spent(self):
        c = client(ScriptedTransport())
        c.budget.record("trader", "opus-4.8", 2_000_000, 200_000)
        plan = synthesize(c, CTX)
        self.assertEqual(plan.decision, "pass")
        self.assertFalse(plan.spent)


class TestPM(unittest.TestCase):
    def test_execute(self):
        d = pm_decide(client(ScriptedTransport(pm="execute")), CTX)
        self.assertTrue(d.approves)
        self.assertAlmostEqual(d.size_factor, 0.9)

    def test_reject(self):
        d = pm_decide(client(ScriptedTransport(pm="reject")), CTX)
        self.assertFalse(d.approves)

    def test_fail_closed_when_not_spent(self):
        c = client(ScriptedTransport())
        c.budget.record("trader", "opus-4.8", 2_000_000, 200_000)
        d = pm_decide(c, CTX)
        self.assertEqual(d.decision, "reject")    # fail-closed
        self.assertFalse(d.approves)


class TestParsing(unittest.TestCase):
    def test_lenient_json_with_prose(self):
        d = parse_json_lenient('Sure! {"confidence": 0.7} hope that helps')
        self.assertEqual(d["confidence"], 0.7)

    def test_lenient_returns_none_on_garbage(self):
        self.assertIsNone(parse_json_lenient("no json here"))


if __name__ == "__main__":
    unittest.main()
