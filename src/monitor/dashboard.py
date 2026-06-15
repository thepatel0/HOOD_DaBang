"""
HOOD DaBang — terminal dashboard (Brief §20).

Renders the operator's at-a-glance view with `rich`: equity/P&L, the Conviction
Gate panel (signals seen/cleared/traded + highest-not-taken — making "quality
over quantity" visible), active theses, LLM costs, positions, and system health.

`render(snapshot) -> str` produces the panel text so it is testable headless and
usable in `--quiet` mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PositionView:
    ticker: str
    side: str
    shares: int
    entry: float
    last: float
    stop: float
    strategy: str
    thesis_claim: str = ""


@dataclass
class Snapshot:
    now_et: str
    regime: str
    equity: float
    session_start_equity: float
    day_pnl: float
    ath: float
    trades_today: int
    conviction_floor: float
    signals_seen: int = 0
    signals_cleared: int = 0
    signals_traded: int = 0
    highest_not_taken: str = ""
    llm_today: float = 0.0
    llm_budget: float = 5.0
    llm_month: float = 0.0
    cache_hit_rate: float = 0.0
    positions: List[PositionView] = field(default_factory=list)
    killswitch_armed: bool = True
    halted: bool = False
    halt_reason: str = ""

    @property
    def dd_from_ath(self) -> float:
        return (self.ath - self.equity) / self.ath if self.ath else 0.0

    @property
    def day_pnl_pct(self) -> float:
        return self.day_pnl / self.session_start_equity if self.session_start_equity else 0.0


def render(s: Snapshot) -> str:
    """Render to a string (rich if available, else plain)."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich import box
    except ImportError:
        return _render_plain(s)

    console = Console(record=True, width=82)
    pnl_color = "green" if s.day_pnl >= 0 else "red"
    header = (f"[bold]HOOD DaBang[/]  {s.now_et[:16]}  REGIME: [cyan]{s.regime}[/]  "
              f"{'[red]HALTED[/]' if s.halted else '[green]ARMED[/]'}")

    summary = Table.grid(padding=(0, 2))
    summary.add_row(
        f"Equity: [bold]${s.equity:,.2f}[/]",
        f"Day P&L: [{pnl_color}]${s.day_pnl:+,.2f} ({s.day_pnl_pct:+.2%})[/]",
        f"ATH: ${s.ath:,.2f}")
    summary.add_row(
        f"Trades: {s.trades_today} (target 1-10)",
        f"DD from peak: {s.dd_from_ath:.2%}",
        f"Conviction floor: {s.conviction_floor:.0f}")

    conv = Table.grid(padding=(0, 2))
    conv.add_row(f"Signals seen: {s.signals_seen}",
                 f"Cleared floor: {s.signals_cleared}",
                 f"Traded: {s.signals_traded}")
    if s.highest_not_taken:
        conv.add_row(f"[yellow]Highest not taken: {s.highest_not_taken}[/]")

    cost = Table.grid(padding=(0, 2))
    pct = (s.llm_today / s.llm_budget) if s.llm_budget else 0
    cost.add_row(f"LLM today: ${s.llm_today:.2f}/${s.llm_budget:.2f} ({pct:.0%})",
                 f"Month: ${s.llm_month:.2f}",
                 f"Cache hit: {s.cache_hit_rate:.0%}")

    pos = Table(box=box.SIMPLE, expand=True)
    for col in ("Ticker", "Side", "Shares", "Entry", "Last", "Stop", "Strategy"):
        pos.add_column(col)
    for p in s.positions:
        pos.add_row(p.ticker, p.side, str(p.shares), f"{p.entry:.2f}", f"{p.last:.2f}",
                    f"{p.stop:.2f}", p.strategy)
    if not s.positions:
        pos.add_row("—", "", "", "", "", "", "(flat)")

    console.print(Panel(summary, title=header, box=box.ROUNDED))
    console.print(Panel(conv, title="CONVICTION GATE", box=box.ROUNDED))
    console.print(Panel(cost, title="COSTS", box=box.ROUNDED))
    console.print(Panel(pos, title=f"POSITIONS ({len(s.positions)})", box=box.ROUNDED))
    if s.halted:
        console.print(Panel(f"[bold red]{s.halt_reason}[/]", title="HALT", box=box.HEAVY))
    return console.export_text()


def _render_plain(s: Snapshot) -> str:
    lines = [
        f"HOOD DaBang  {s.now_et[:16]}  REGIME: {s.regime}  "
        f"{'HALTED' if s.halted else 'ARMED'}",
        f"Equity ${s.equity:,.2f}  Day P&L ${s.day_pnl:+,.2f} ({s.day_pnl_pct:+.2%})  "
        f"ATH ${s.ath:,.2f}",
        f"Trades {s.trades_today}  DD {s.dd_from_ath:.2%}  Floor {s.conviction_floor:.0f}",
        f"Gate: seen {s.signals_seen} cleared {s.signals_cleared} traded {s.signals_traded}",
        f"LLM ${s.llm_today:.2f}/${s.llm_budget:.2f}  month ${s.llm_month:.2f}  "
        f"cache {s.cache_hit_rate:.0%}",
        f"Positions ({len(s.positions)}):",
    ]
    for p in s.positions:
        lines.append(f"  {p.ticker} {p.side} {p.shares}@{p.entry:.2f} stop {p.stop:.2f} "
                     f"{p.strategy}")
    if not s.positions:
        lines.append("  (flat)")
    if s.halted:
        lines.append(f"HALT: {s.halt_reason}")
    return "\n".join(lines)


def snapshot_from_controller(ctrl, *, regime: str = "range_low_vol",
                             gate_stats: dict = None, llm_today: float = 0.0,
                             llm_month: float = 0.0, cache_hit: float = 0.0,
                             last_prices: dict = None) -> Snapshot:
    """Build a Snapshot from live controller state."""
    gate_stats = gate_stats or {}
    last_prices = last_prices or {}
    positions = [
        PositionView(t, ot.pos.side, ot.pos.shares, ot.pos.entry_price,
                     last_prices.get(t, ot.pos.entry_price), ot.pos.stop_price,
                     ot.pos.strategy)
        for t, ot in ctrl.open.items()]
    st = ctrl.state
    return Snapshot(
        now_et="", regime=regime, equity=st.equity,
        session_start_equity=st.session_start_equity, day_pnl=st.day_pnl,
        ath=st.ath, trades_today=st.trades_today,
        conviction_floor=ctrl.gate.effective_execution_floor,
        signals_seen=gate_stats.get("seen", 0),
        signals_cleared=gate_stats.get("cleared", 0),
        signals_traded=st.trades_today,
        highest_not_taken=gate_stats.get("highest_not_taken", ""),
        llm_today=llm_today, llm_budget=ctrl.cfg["llm"]["daily_budget_usd"],
        llm_month=llm_month, cache_hit_rate=cache_hit, positions=positions,
        halted=st.halted, halt_reason=st.halt_reason)
