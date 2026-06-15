"""
HOOD DaBang — event-driven backtest engine (Brief §4.1, §9, §26.8).

Walks 1-min bars chronologically. At bar i it builds a MarketState from ONLY
bars[:i+1] (strict no-look-ahead), runs the SAME strategy.scan / strategy.manage
and the SAME Conviction Gate Stage-1 code used live (parity principle), and fills
at bar i+1's open plus modeled slippage. Stops/targets are checked intrabar
against the bar's high/low.

The Conviction Gate's LLM stages don't exist in backtest, so the deterministic
Stage-1 score acts as the gate (with a configurable backtest floor) — which is
honest: we never claim a backtest reflects the LLM debate, only the rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..strategies.base import Bar, MarketState, Position, Setup, ActionType
from ..analysts_local.technical import TechnicalAnalyst
from ..conviction.gate import ConvictionGate
from ..conviction.scorecard import Signal
from .stats import compute_stats, Stats


@dataclass
class BTTrade:
    entry_ts: str
    entry: float
    exit_ts: str
    exit: float
    shares: int
    side: str
    r_multiple: float
    pnl: float
    reason: str


@dataclass
class BacktestResult:
    trades: List[BTTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)
    r_series: List[float] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, cfg: dict, slippage_pct: float = None,
                 warmup: int = 30, det_floor: float = None):
        self.cfg = cfg
        self.slip = slippage_pct if slippage_pct is not None else cfg["risk"]["slippage_budget_pct"]
        self.warmup = warmup
        self.gate = ConvictionGate(cfg)
        self.det_floor = det_floor if det_floor is not None else cfg["conviction"]["stage1_hard_floor"]
        self.ta = TechnicalAnalyst()

    def _signal_from_setup(self, s: Setup, ms: MarketState) -> Signal:
        return Signal(
            ticker=s.ticker, strategy=s.strategy, side=s.side, factors=dict(s.factors),
            spread_pct=ms.spread_pct, shares_at_risk_cap=1,
            requires_catalyst=s.requires_catalyst, has_catalyst=ms.has_catalyst,
            catalyst_age_min=ms.catalyst_age_min, catalyst_sources=ms.catalyst_sources,
            is_large_move=(ms.gap_pct or 0) > 0.03, regime=ms.regime,
            holding_window_spans_earnings=False, in_blackout_window=False,
            open_positions_at_cap=False, daily_halt_active=False,
        )

    def run(self, strategy, bars_1m: List[Bar], *, ticker: str = "TEST",
            regime: str = "bull_trend_low_vol", prior_close: float = None,
            has_catalyst: bool = True, catalyst_age_min: float = 5,
            catalyst_sources: int = 2, risk_per_trade_dollars: float = 15.0,
            start_equity: float = 1500.0) -> BacktestResult:
        res = BacktestResult()
        equity = start_equity
        res.equity_curve.append(equity)
        pos: Optional[Position] = None
        pos_target: Optional[float] = None
        risk_per_share = 0.0

        n = len(bars_1m)
        for i in range(self.warmup, n - 1):
            window = bars_1m[:i + 1]          # NO future data
            cur = bars_1m[i]
            nxt = bars_1m[i + 1]
            ms = self.ta.compute(
                ticker, cur.ts, cur.c, {"1m": window}, prior_close=prior_close,
                regime=regime, has_catalyst=has_catalyst,
                catalyst_age_min=catalyst_age_min, catalyst_sources=catalyst_sources)

            # ----- manage an open position ------------------------------- #
            if pos is not None:
                pos.bars_held += 1
                # intrabar stop / target checks on THIS bar
                if pos.side == "long":
                    if cur.l <= pos.stop_price:
                        equity, t = self._close(res, pos, pos.stop_price, cur.ts,
                                                 risk_per_share, equity, "stop")
                        pos = None
                    elif pos_target and cur.h >= pos_target:
                        equity, t = self._close(res, pos, pos_target, cur.ts,
                                                 risk_per_share, equity, "target")
                        pos = None
                else:  # short
                    if cur.h >= pos.stop_price:
                        equity, t = self._close(res, pos, pos.stop_price, cur.ts,
                                                 risk_per_share, equity, "stop")
                        pos = None
                    elif pos_target and cur.l <= pos_target:
                        equity, t = self._close(res, pos, pos_target, cur.ts,
                                                 risk_per_share, equity, "target")
                        pos = None

                if pos is not None:
                    action = strategy.manage(pos, ms)
                    if action.type == ActionType.EXIT:
                        equity, t = self._close(res, pos, cur.c, cur.ts,
                                                 risk_per_share, equity, action.reason)
                        pos = None
                    elif action.type == ActionType.MOVE_STOP and action.new_stop:
                        pos.stop_price = action.new_stop
                    elif action.type == ActionType.SCALE_OUT and action.new_stop:
                        pos.stop_price = action.new_stop  # move to break-even; keep runner

            # ----- look for a new entry ---------------------------------- #
            elif strategy.activation_status != "paused":
                setups = strategy.scan(ms)
                if setups:
                    s = setups[0]
                    sig = self._signal_from_setup(s, ms)
                    g = self.gate.stage1([sig])
                    if g.advancing and sig.det_score >= self.det_floor:
                        rps = s.per_share_risk
                        if rps > 0:
                            shares = int(risk_per_trade_dollars / rps)
                            if shares > 0:
                                # fill at NEXT bar open + slippage (no look-ahead)
                                fill = nxt.o * (1 + self.slip) if s.side == "long" \
                                    else nxt.o * (1 - self.slip)
                                pos = Position(
                                    ticker=ticker, side=s.side, shares=shares,
                                    entry_price=fill, stop_price=s.stop_price,
                                    targets=s.targets, strategy=s.strategy,
                                    opened_ts=nxt.ts)
                                pos_target = s.targets[0][0] if s.targets else None
                                risk_per_share = rps

            res.equity_curve.append(equity)

        # close any residual position at the last bar
        if pos is not None:
            last = bars_1m[-1]
            equity, _ = self._close(res, pos, last.c, last.ts, risk_per_share,
                                    equity, "eod_close")
            res.equity_curve.append(equity)

        res.r_series = [t.r_multiple for t in res.trades]
        res.stats = compute_stats(res.r_series, res.equity_curve)
        return res

    def _close(self, res, pos, raw_exit, ts, risk_per_share, equity, reason):
        # exit slippage works against us
        exit_px = raw_exit * (1 - self.slip) if pos.side == "long" \
            else raw_exit * (1 + self.slip)
        if pos.side == "long":
            pnl = (exit_px - pos.entry_price) * pos.shares
        else:
            pnl = (pos.entry_price - exit_px) * pos.shares
        r = (pnl / (risk_per_share * pos.shares)) if risk_per_share > 0 else 0.0
        res.trades.append(BTTrade(
            entry_ts=pos.opened_ts, entry=round(pos.entry_price, 4), exit_ts=ts,
            exit=round(exit_px, 4), shares=pos.shares, side=pos.side,
            r_multiple=round(r, 4), pnl=round(pnl, 2), reason=reason))
        return equity + pnl, res.trades[-1]
