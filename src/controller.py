"""
HOOD DaBang — controller / orchestrator (Brief §4.4, §16).

Wires the decision pipeline into a runnable loop. Per tick:
  1. evaluate killswitches (halt if any fires) — safety first, every tick
  2. manage open positions (stop / target / strategy.manage exits)
  3. scan registered strategies (wake routing) -> Setups
  4. Conviction Gate Stage-1 (deterministic) -> top 1-3 survivors
  5. Insight Engine -> falsifiable thesis (mandatory; no thesis => no trade)
  6. Conviction verdict (rules mode = deterministic; full mode adds LLM debate)
  7. Adaptive sizing -> Risk gate (hard caps) -> atomic Execution
  8. Journal everything; update equity

mode="rules": no LLM; deterministic score IS the conviction, and only the
deterministic+thesis path runs (degrade-don't-die / backtest parity).
mode="full": adds the LLM debate/trader/PM stages (hooks; built in Phase 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .strategies.base import MarketState, Setup, Position, ActionType
from .strategies.registry import StrategyRegistry
from .conviction.gate import ConvictionGate
from .conviction.scorecard import Signal
from .insight.engine import InsightEngine
from .decision.adaptive_risk import AdaptiveRiskGovernor, RiskContext
from .sizing.sizers import StrategyStats
from .risk import RiskGate, OrderProposal, AccountState
from .execution import ExecutionHandler, OrderRequest
from .journal import Journal
from . import killswitch as ks


@dataclass
class ControllerState:
    equity: float
    session_start_equity: float
    ath: float
    effective_capital: float
    day_pnl: float = 0.0
    day_number: int = 1
    consecutive_losses: int = 0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str = ""


@dataclass
class OpenTrade:
    pos: Position
    trade_id: int
    thesis_id: str
    target: Optional[float]
    risk_per_share: float


class Controller:
    def __init__(self, cfg: dict, registry: StrategyRegistry, gate: ConvictionGate,
                 insight: InsightEngine, governor: AdaptiveRiskGovernor,
                 risk_gate: RiskGate, execution: ExecutionHandler, journal: Journal,
                 *, mode: str = "rules", llm_client=None, execution_mode: str = "execute",
                 env_name: str = "production", knowledge_base=None,
                 strategy_stats: Optional[Dict[str, StrategyStats]] = None):
        self.cfg = cfg
        self.registry = registry
        self.gate = gate
        self.insight = insight
        self.governor = governor
        self.risk_gate = risk_gate
        self.execution = execution
        self.journal = journal
        self.mode = mode
        # execution_mode: "execute" (place orders — paper or live, via the wired
        # handler/env) or "recommend" (research only — write recommendation, no order)
        self.execution_mode = execution_mode
        self.env_name = env_name
        # shared KnowledgeBase: validated paper patterns tilt conviction (bounded);
        # None => bedrock scorecard only (paper/prod isolation otherwise intact)
        self.knowledge_base = knowledge_base
        self.llm = llm_client          # required for mode="full"; None => rules only
        self.strategy_stats = strategy_stats or {}
        self.open: Dict[str, OpenTrade] = {}
        self.recommendations_today = 0
        self._oid = 0

    # ----- killswitch ---------------------------------------------------- #
    def _killswitch_state(self) -> ks.KillswitchState:
        r = self.cfg["risk"]
        return ks.KillswitchState(
            day_pnl=self.state.day_pnl, session_start_equity=self.state.session_start_equity,
            equity=self.state.equity, ath_equity=self.state.ath,
            catastrophic_floor=r["catastrophic_halt_equity_usd"],
            consecutive_losses=self.state.consecutive_losses,
            daily_loss_limit_pct=r["daily_loss_limit_pct"],
            drawdown_halt_pct=r["drawdown_halt_pct_from_ath"],
            consecutive_loss_cooldown=r["consecutive_loss_cooldown"],
            consecutive_loss_halt_day=r["consecutive_loss_halt_day"])

    HALTING = {ks.HaltScope.HALT_SESSION, ks.HaltScope.HALT_UNTIL_RESUME,
               ks.HaltScope.HALT_INDEFINITE}

    def start_session(self, equity: float, ath: float = None, day_number: int = 1,
                      effective_capital: float = None) -> None:
        self.state = ControllerState(
            equity=equity, session_start_equity=equity, ath=ath or equity,
            effective_capital=effective_capital or equity, day_number=day_number)

    # ----- main tick ----------------------------------------------------- #
    def process_tick(self, states: Dict[str, MarketState], now_et: str) -> None:
        # 1) killswitches
        fired = ks.most_severe(self._killswitch_state())
        if fired and fired.scope in self.HALTING:
            self.state.halted = True
            self.state.halt_reason = f"#{fired.number} {fired.name}: {fired.reason}"
            self._flatten_all(states, now_et, reason="killswitch")
            return
        cooling = fired is not None and fired.scope == ks.HaltScope.PAUSE_NEW_ORDERS

        # 2) manage open positions
        for ticker in list(self.open.keys()):
            ms = states.get(ticker)
            if ms is not None:
                self._manage(ticker, ms, now_et)

        # 3-7) entries (unless cooling off / halted)
        if cooling or self.state.halted:
            self._mark_equity(now_et)
            return
        self._scan_and_enter(states, now_et)
        self._mark_equity(now_et)

    # ----- position management ------------------------------------------ #
    def _manage(self, ticker: str, ms: MarketState, now_et: str) -> None:
        ot = self.open[ticker]
        pos = ot.pos
        pos.bars_held += 1
        price = ms.quote

        # intrabar stop / target
        if pos.side == "long":
            if price <= pos.stop_price:
                return self._close(ticker, pos.stop_price, now_et, "stop")
            if ot.target and price >= ot.target:
                return self._close(ticker, ot.target, now_et, "target")
        else:
            if price >= pos.stop_price:
                return self._close(ticker, pos.stop_price, now_et, "stop")
            if ot.target and price <= ot.target:
                return self._close(ticker, ot.target, now_et, "target")

        strat = self.registry.get(pos.strategy).strategy
        action = strat.manage(pos, ms)
        if action.type == ActionType.EXIT:
            self._close(ticker, price, now_et, action.reason)
        elif action.type in (ActionType.MOVE_STOP, ActionType.SCALE_OUT) and action.new_stop:
            pos.stop_price = action.new_stop

    def _close(self, ticker: str, exit_price: float, now_et: str, reason: str) -> None:
        ot = self.open.pop(ticker)
        pos = ot.pos
        if pos.side == "long":
            pnl = (exit_price - pos.entry_price) * pos.shares
        else:
            pnl = (pos.entry_price - exit_price) * pos.shares
        r = (pnl / (ot.risk_per_share * pos.shares)) if ot.risk_per_share > 0 else 0.0

        self.state.equity += pnl
        self.state.day_pnl += pnl
        self.state.ath = max(self.state.ath, self.state.equity)
        if pnl <= 0:
            self.state.consecutive_losses += 1
            self.gate.set_floor_bump(self.cfg["conviction"]["loss_cooldown_floor_bump"])
        else:
            self.state.consecutive_losses = 0
            self.gate.set_floor_bump(0)

        self.journal.close_trade(ot.trade_id, exit_ts=now_et, exit_price=round(exit_price, 4),
                                 exit_reason=reason, pnl_dollars=round(pnl, 2),
                                 pnl_r=round(r, 4))
        self.journal.close_position(ticker)

    def _flatten_all(self, states, now_et, reason):
        for ticker in list(self.open.keys()):
            ms = states.get(ticker)
            px = ms.quote if ms else self.open[ticker].pos.entry_price
            self._close(ticker, px, now_et, reason)

    # ----- entry pipeline ------------------------------------------------ #
    def _scan_and_enter(self, states: Dict[str, MarketState], now_et: str) -> None:
        # collect setups across all names (Stage-1 gate ranks across the book)
        all_setups: List[tuple] = []  # (Setup, MarketState)
        for ticker, ms in states.items():
            if ticker in self.open:
                continue  # one position per name
            for s in self.registry.tradeable():
                if s.regime_weight(ms.regime) <= 0:
                    continue
                for setup in s.scan(ms):
                    all_setups.append((setup, ms))

        if not all_setups:
            return

        signals = [self._signal(setup, ms) for setup, ms in all_setups]
        result = self.gate.stage1(signals)
        # log every decision
        for d in result.decisions:
            self.journal.log_conviction(now_et, d.ticker, d.strategy,
                                        d.deterministic_score, None, d.advanced,
                                        False, d.reason)

        advancing_keys = {(s.ticker, s.strategy) for s in result.advancing}
        for setup, ms in all_setups:
            if (setup.ticker, setup.strategy) not in advancing_keys:
                continue
            if self._at_concurrency_cap():
                break
            self._evaluate_survivor(setup, ms, now_et)

    def _at_concurrency_cap(self) -> bool:
        cap = (self.cfg["risk"]["max_concurrent_positions_days_1_30"]
               if self.state.day_number <= self.cfg["operation"]["intraday_only_days"]
               else self.cfg["risk"]["max_concurrent_positions_after"])
        return len(self.open) >= cap

    def _evaluate_survivor(self, setup: Setup, ms: MarketState, now_et: str) -> None:
        # 5) thesis (mandatory)
        thesis = self.insight.build(setup, ms, use_llm=(self.mode == "full"))
        if thesis is None:
            return

        # 6) conviction verdict
        det = self._signal(setup, ms)
        from .conviction.scorecard import score
        det_score = score(det, self.gate.weights)
        if self.mode == "full" and self.llm is not None:
            # §4.4 LLM pipeline: debate -> Stage-2 verdict -> Trader -> PM
            from .agents.debate import run_debate
            from .agents.trader import synthesize, pm_decide
            ctx = {"ticker": setup.ticker, "strategy": setup.strategy,
                   "side": setup.side, "entry": setup.entry_price,
                   "stop": setup.stop_price, "factors": setup.factors,
                   "thesis": thesis.claim, "mechanism": thesis.mechanism,
                   "regime": ms.regime, "base_rate": thesis.base_rate}
            debate = run_debate(self.llm, ctx)
            verdict = self.gate.stage2_verdict(
                det_score, debate.bull_confidence, debate.bear_confidence,
                min(1.0, thesis.confidence), 0.7)
            conviction = verdict["final_conviction"]
            passes = verdict["passes"]
            if passes:
                plan = synthesize(self.llm, {**ctx, "conviction": conviction,
                                             "debate_margin": debate.margin})
                if plan.decision != "trade":
                    return
                pm = pm_decide(self.llm, {**ctx, "plan": plan.decision,
                                          "open_positions": len(self.open),
                                          "day_pnl": self.state.day_pnl})
                if not pm.approves:
                    return
        elif self.mode == "full":
            verdict = self.gate.stage2_verdict(det_score, thesis.confidence, 0.3,
                                               min(1.0, thesis.confidence), 0.7)
            conviction = verdict["final_conviction"]
            passes = verdict["passes"]
        else:
            # rules mode: deterministic score is the conviction; overconfidence penalty
            gap = thesis.confidence_base_rate_gap or 0.0
            penalty = max(0.0, gap - 0.2) * 20
            conviction = det_score - penalty
            passes = conviction >= self.gate.effective_execution_floor

        # validated-knowledge tilt (bounded ±5): the only paper->prod signal
        if self.knowledge_base is not None:
            conviction = max(0.0, min(100.0, conviction +
                             self.knowledge_base.conviction_tilt(setup.strategy, ms.regime)))

        if not passes:
            return

        # 7) sizing -> risk gate -> execution
        stats = self.strategy_stats.get(setup.strategy,
                                        StrategyStats(0, 0.5, 1.0, 1.0))
        dd = (self.state.ath - self.state.equity) / self.state.ath if self.state.ath else 0.0
        decision = self.governor.decide(RiskContext(
            stats=stats, drawdown_from_ath=dd, realized_vol_20d=0.0,
            n_proven_trades=stats.n_trades))
        risk_dollars = decision.fraction * self.state.effective_capital
        rps = setup.per_share_risk
        if rps <= 0:
            return
        shares = int(risk_dollars / rps)
        if shares <= 0:
            return

        proposal = OrderProposal(
            ticker=setup.ticker, side=setup.side, entry_price=setup.entry_price,
            stop_price=setup.stop_price, shares=shares, spread_pct=ms.spread_pct,
            strategy=setup.strategy, quote_age_ms=ms.quote_age_ms,
            last_bar_age_s=ms.last_bar_age_s, has_thesis=True,
            conviction_score=conviction, authorized_risk_pct=decision.fraction)
        acct = AccountState(
            equity=self.state.equity, effective_capital=self.state.effective_capital,
            session_start_equity=self.state.session_start_equity,
            day_pnl=self.state.day_pnl, open_positions=len(self.open),
            gross_exposure=self._gross_exposure(), day_number=self.state.day_number)
        verdict = self.risk_gate.check(proposal, acct)
        if not verdict.approved:
            return

        # RESEARCH (recommend-only) mode: write the recommendation to the journal +
        # memory instead of placing any order. No execution, no position.
        if self.execution_mode == "recommend":
            tid = self.journal.record_thesis(thesis, now_et)
            self.journal.record_recommendation(
                ts=now_et, ticker=setup.ticker, side=setup.side,
                strategy=setup.strategy, entry=setup.entry_price,
                stop=setup.stop_price,
                target=setup.targets[0][0] if setup.targets else None,
                shares=shares, conviction=conviction, thesis_id=tid,
                regime=ms.regime, mechanism=thesis.mechanism,
                invalidation="; ".join(thesis.invalidation), env=self.env_name)
            self.journal.log_conviction(now_et, setup.ticker, setup.strategy,
                                        det_score, conviction, True, False,
                                        "recommended_not_traded")
            self.recommendations_today += 1
            return

        self._oid += 1
        coid = f"{setup.ticker}-{self._oid}-{now_et[:16]}"
        req = OrderRequest(
            ticker=setup.ticker, side=("buy" if setup.side == "long" else "sell"),
            shares=shares, limit_price=setup.entry_price, stop_price=setup.stop_price,
            client_order_id=coid, conviction_score=conviction,
            thesis_id=thesis.id(), has_thesis=True)
        res = self.execution.submit(req)
        if not res.accepted:
            return

        # 8) journal + track
        tid = self.journal.record_thesis(thesis, now_et)
        trade_id = self.journal.record_trade(
            ticker=setup.ticker, strategy=setup.strategy, strategy_version=setup.version,
            side=setup.side, entry_ts=now_et, entry_price=res.avg_fill_price,
            entry_shares=res.filled_shares, stop_price=setup.stop_price,
            conviction_score=conviction, thesis_id=tid, market_regime=ms.regime,
            order_id=res.order_id,
            target_price=setup.targets[0][0] if setup.targets else None)
        self.journal.open_position(setup.ticker, res.filled_shares, res.avg_fill_price,
                                   res.stop_order_id or "", setup.strategy, tid, now_et)
        pos = Position(ticker=setup.ticker, side=setup.side, shares=res.filled_shares,
                       entry_price=res.avg_fill_price, stop_price=setup.stop_price,
                       targets=setup.targets, strategy=setup.strategy, opened_ts=now_et)
        self.open[setup.ticker] = OpenTrade(
            pos=pos, trade_id=trade_id, thesis_id=tid,
            target=setup.targets[0][0] if setup.targets else None, risk_per_share=rps)
        self.state.trades_today += 1

    # ----- helpers ------------------------------------------------------- #
    def _signal(self, setup: Setup, ms: MarketState) -> Signal:
        return Signal(
            ticker=setup.ticker, strategy=setup.strategy, side=setup.side,
            factors=dict(setup.factors), spread_pct=ms.spread_pct,
            shares_at_risk_cap=1, requires_catalyst=setup.requires_catalyst,
            has_catalyst=ms.has_catalyst, catalyst_age_min=ms.catalyst_age_min,
            catalyst_sources=ms.catalyst_sources,
            is_large_move=(ms.gap_pct or 0) > 0.03, regime=ms.regime)

    def _gross_exposure(self) -> float:
        return sum(ot.pos.entry_price * ot.pos.shares for ot in self.open.values())

    def _mark_equity(self, now_et: str) -> None:
        dd = (self.state.ath - self.state.equity) / self.state.ath if self.state.ath else 0.0
        self.journal.update_equity(now_et, round(self.state.equity, 2),
                                   round(self.state.day_pnl, 2), round(dd, 4),
                                   round(self.state.ath, 2), self.state.effective_capital)
