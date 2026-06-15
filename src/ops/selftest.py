"""
HOOD DaBang — self-test suite (Brief §15).

Runtime invariant checks the system runs ON ITSELF: nightly (all), pre-market
(safety subset), and pre-trade (per-order, the fastest). Each check is a callable
returning (passed, detail). Any failure -> halt + notify (killswitch #15).

These are live assertions, not the pytest suite — they verify the *running*
config and code behave safely with synthetic inputs, every session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from .. import config as cfgmod
from ..risk import RiskGate, OrderProposal, AccountState
from ..killswitch import KillswitchState, most_severe, HaltScope
from ..conviction.gate import ConvictionGate
from ..conviction.scorecard import Signal


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    category: str = "nightly"


@dataclass
class SelfTestReport:
    results: List[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> List[CheckResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        return (f"{sum(r.passed for r in self.results)}/{len(self.results)} self-tests "
                f"passed" + ("" if self.all_passed else
                f"; FAILED: {[r.name for r in self.failures]}"))


# --------------------------------------------------------------------------- #
# Individual checks (return (passed, detail))                                  #
# --------------------------------------------------------------------------- #
def _check_risk_caps(cfg) -> Tuple[bool, str]:
    gate = RiskGate(cfg)
    acct = AccountState(1500, 1500, 1500, 0, 0, 0, 1)
    # an order risking 5% must be rejected
    o = OrderProposal("AAPL", "long", 100, 95, 30, 0.001, "orb",
                      has_thesis=True, conviction_score=80)
    v = gate.check(o, acct)
    return ((not v.approved and "per_trade_risk_exceeds_cap" in v.violations),
            "5% risk order correctly rejected")


def _check_killswitch_loss_limit(cfg) -> Tuple[bool, str]:
    s = KillswitchState(day_pnl=-80, session_start_equity=1500,
                        daily_loss_limit_pct=0.05)
    h = most_severe(s)
    return (h is not None and h.name == "daily_loss_limit", "loss limit fires halt")


def _check_conviction_floor(cfg) -> Tuple[bool, str]:
    gate = ConvictionGate(cfg)
    weak = Signal("X", "orb", "long", {k: 30 for k in [
        "setup_quality", "regime_fit", "multi_timeframe_confluence",
        "volume_confirmation", "catalyst_freshness", "liquidity_spread",
        "risk_reward_geometry", "strategy_recent_expectancy"]})
    res = gate.stage1([weak])
    return (len(res.advancing) == 0, "below-floor signal does not advance")


def _check_conviction_hard_floor(cfg) -> Tuple[bool, str]:
    gate = ConvictionGate(cfg)
    strong = {k: 90 for k in [
        "setup_quality", "regime_fit", "multi_timeframe_confluence",
        "volume_confirmation", "catalyst_freshness", "liquidity_spread",
        "risk_reward_geometry", "strategy_recent_expectancy"]}
    sig = Signal("X", "orb", "long", strong, spread_pct=0.01)  # spread too wide
    res = gate.stage1([sig])
    return (len(res.advancing) == 0, "hard floor overrides a high score")


def _check_no_lookahead(cfg) -> Tuple[bool, str]:
    from ..backtest.engine import BacktestEngine
    from ..strategies.intraday.orb import OpeningRangeBreakout
    from ..strategies.base import Bar
    # minimal trap: corrupting far-future bars must not change a completed trade
    def ts(i): return f"2026-06-15T{9 + (30 + i)//60:02d}:{(30 + i)%60:02d}:00-04:00"
    bars = [Bar(ts(i), 100.4, 101.0, 100.0, 100.5, 2000) for i in range(5)]
    bars += [Bar(ts(i), 100.5, 100.9, 100.2, 100.6, 1500) for i in range(5, 12)]
    bars.append(Bar(ts(12), 100.7, 101.6, 100.6, 101.5, 12000))
    bars.append(Bar(ts(13), 101.5, 110.0, 101.4, 108.0, 15000))
    bars += [Bar(ts(i), 100.5, 100.8, 100.3, 100.5, 1200) for i in range(14, 40)]
    eng = BacktestEngine(cfg, warmup=10, det_floor=60)
    clean = eng.run(OpeningRangeBreakout(), bars, regime="bull_trend_low_vol",
                    prior_close=100.0)
    corrupt = list(bars)
    for i in range(20, len(corrupt)):
        corrupt[i] = Bar(corrupt[i].ts, 500, 9999, 1, 0.01, 99)
    dirty = eng.run(OpeningRangeBreakout(), corrupt, regime="bull_trend_low_vol",
                    prior_close=100.0)
    ok = (clean.trades and dirty.trades
          and clean.trades[0].r_multiple == dirty.trades[0].r_multiple)
    return (bool(ok), "future-data trap: completed trade unchanged")


def _check_config_valid(cfg) -> Tuple[bool, str]:
    try:
        cfgmod.validate(cfg)
        return True, "config validates"
    except Exception as e:
        return False, str(e)


# name -> (callable, category)
CHECKS: Dict[str, Tuple[Callable, str]] = {
    "risk_caps": (_check_risk_caps, "pretrade"),
    "killswitch_loss_limit": (_check_killswitch_loss_limit, "premarket"),
    "conviction_floor": (_check_conviction_floor, "premarket"),
    "conviction_hard_floor": (_check_conviction_floor, "pretrade"),
    "no_lookahead": (_check_no_lookahead, "nightly"),
    "config_valid": (_check_config_valid, "premarket"),
}


def run(cfg=None, category: str = None) -> SelfTestReport:
    """Run all checks (or only those in `category`)."""
    cfg = cfg or cfgmod.load()
    report = SelfTestReport()
    for name, (fn, cat) in CHECKS.items():
        if category and cat != category:
            continue
        try:
            passed, detail = fn(cfg)
        except Exception as e:               # a crashing check is a failure
            passed, detail = False, f"exception: {type(e).__name__}: {e}"
        report.results.append(CheckResult(name, passed, detail, cat))
    return report
