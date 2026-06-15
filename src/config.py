"""
HOOD DaBang — canonical configuration (Section 32 of the brief).

Design choice: Python is the *source of truth* for defaults so the deterministic
bedrock runs with zero third-party dependencies (no pyyaml needed to start).
At runtime, if `config.yaml` exists AND pyyaml is installed, its values override
these defaults (hot-reload). Either way we validate before returning — an invalid
config is rejected (fail-closed), never silently used.

This mirrors the brief's rule: "Validate against config.schema.json on every
load; reject invalid configs and halt."
"""
from __future__ import annotations

import copy
import os
from typing import Any, Dict

# --------------------------------------------------------------------------- #
# CANONICAL DEFAULTS  (Brief Section 32)                                        #
# --------------------------------------------------------------------------- #
DEFAULTS: Dict[str, Any] = {
    "account": {
        "starting_capital_usd": 1500,
        "asset_scope": "equities_only",
        "margin_enabled": False,
        "shorts_enabled": False,
    },
    "capital_ramp": {  # Section 30.2 — risk less while unproven
        "live_days_1_5_usd": 300,
        "live_days_6_15_usd": 750,
        "live_days_16_30_usd": 1125,
        "live_day_31_plus_usd": 1500,
        "operator_can_accelerate": True,
        "exceed_schedule_requires_override": True,
    },
    "risk": {  # Section 13 — IMMUTABLE without MANUAL_OVERRIDE.flag + 24h cooldown
        "per_trade_risk_pct": 0.015,
        "max_position_pct": 0.30,
        "daily_loss_limit_pct": 0.05,
        "daily_soft_profit_cap_pct": 0.20,
        "max_concurrent_positions_days_1_30": 3,
        "max_concurrent_positions_after": 5,
        "total_exposure_cap_pct": 0.80,
        "drawdown_halt_pct_from_ath": 0.20,
        "catastrophic_halt_equity_usd": 1050,
        "spread_reject_pct": 0.003,
        "slippage_budget_pct": 0.0005,
        "trade_frequency_cap": 25,
        "consecutive_loss_cooldown": 5,
        "consecutive_loss_halt_day": 8,
    },
    "conviction": {  # Section 6
        "stage1_hard_floor": 65,
        "execution_floor": 72,
        "floor_min": 65,
        "floor_max": 80,
        "max_candidates_to_llm": 3,
        "loss_cooldown_floor_bump": 5,
        "near_close_floor_bump": 3,
        "scorecard_weights": {
            "setup_quality": 0.20,
            "regime_fit": 0.15,
            "multi_timeframe_confluence": 0.15,
            "volume_confirmation": 0.12,
            "catalyst_freshness": 0.10,
            "liquidity_spread": 0.08,
            "risk_reward_geometry": 0.10,
            "strategy_recent_expectancy": 0.10,
        },
        "verdict_weights": {  # Stage 2
            "deterministic": 0.45,
            "debate_margin": 0.20,
            "thesis_quality": 0.20,
            "source_calibration": 0.15,
        },
    },
    "sizing": {  # Section 10
        "kelly_fraction": 0.5,
        "kelly_fraction_unproven": 0.25,
        "unproven_risk_pct": 0.005,
        "vol_target_annualized": 0.12,
        "vol_scalar_max": 1.5,
        "correlation_cap": 0.70,
        "conviction_size_floor_ratio": 0.6,
    },
    "adaptive_risk": {  # OPERATOR ADDITION — risk as an optimised, bounded variable
        "enabled": True,
        "floor_pct": 0.001,            # never risk less than 0.1% (still participate)
        "absolute_max_pct": 0.025,     # HARD ceiling; adaptive risk can never exceed
        "nominal_pct": 0.015,          # the brief's 1.5% baseline
        "dd_throttle_start_pct": 0.05,  # start scaling risk down at 5% drawdown
        "dd_throttle_full_pct": 0.20,   # risk -> floor by the 20% drawdown halt
        "ruin_tolerance": 0.01,        # MC ruin-prob ceiling used to cap sizing
        "scale_up_requires_trades": 30,  # only size above nominal once proven
    },
    "latency": {  # Section 30.6
        "intraday_signal_to_order_budget_s": 20,
        "swing_signal_to_order_budget_s": 120,
        "stop_confirm_deadline_s": 2,
        "decision_timeout_halt_pct": 0.25,
    },
    "freshness_tolerances_ms": {  # Section 30.4
        "vwap_reversion": {"quote_age_ms": 1500, "last_bar_age_s": 5},
        "orb": {"quote_age_ms": 2000, "last_bar_age_s": 5},
        "momentum": {"quote_age_ms": 2000, "last_bar_age_s": 5},
        "catalyst_scalp": {"quote_age_ms": 1000, "last_bar_age_s": 3},
        "pead_swing": {"quote_age_ms": 30000, "last_bar_age_s": 60},
        "default": {"quote_age_ms": 5000, "last_bar_age_s": 15},
    },
    "llm": {  # Section 3
        "daily_budget_usd": 5.00,
        "daily_target_usd": 1.80,
        "monthly_budget_usd": 60.00,
        "max_concurrent_pipelines_days_1_30": 1,
        "max_concurrent_pipelines_after": 2,
        "cache_min_hit_rate": 0.70,
        # Pricing reference (Brief 3.2), $/Mtok — used by the token ledger & decision engine
        "pricing": {
            "haiku-4.5": {"input": 1.00, "output": 5.00},
            "sonnet-4.6": {"input": 3.00, "output": 15.00},
            "opus-4.8": {"input": 5.00, "output": 25.00},
        },
        "tiers": {
            "news": "haiku-4.5",
            "sentiment": "haiku-4.5",
            "macro": "sonnet-4.6",
            "fundamentals": "sonnet-4.6",
            "insight_engine": "sonnet-4.6",
            "bull": "sonnet-4.6",
            "bear": "sonnet-4.6",
            "risk_conservative": "sonnet-4.6",
            "risk_aggressive": "sonnet-4.6",
            "reflector": "sonnet-4.6",
            "discoverer": "sonnet-4.6",
            "trader": "opus-4.8",
            "portfolio_manager": "opus-4.8",
            "meta_learner": "opus-4.8",
            "judge": "opus-4.8",
        },
    },
    "screener": {  # Section 17
        "universe_price_min": 5,
        "universe_price_max": 500,
        "universe_min_adv_shares": 1000000,
        "universe_min_atr_pct": 0.01,
        "premarket_gap_min_pct": 0.015,
        "intraday_rvol_min": 2.0,
        "watchlist_max_names": 50,
    },
    "schedule_et": {  # Section 16
        "wake": "07:30",
        "research_start": "08:00",
        "watchlist_build": "09:00",
        "brief_publish": "09:25",
        "no_trade_after_open_until": "09:35",
        "no_entries_before_after_830_print": "09:45",
        "session_close_flatten": "15:50",
        "near_close_bump_after": "15:00",
        "post_market_review": "16:30",
        "nightly_self_improvement": "21:00",
        "weekly_review_day": "SUN",
        "weekly_review_time": "18:00",
        "fomc_blackout": ["14:00", "14:30"],
    },
    "operation": {
        "intraday_only_days": 30,
        "overnight_holds_allowed_after_day": 30,
        "half_day_size_reduction_pct": 0.50,
    },
}


# --------------------------------------------------------------------------- #
# VALIDATION  (the "config.schema.json equivalent", fail-closed)               #
# --------------------------------------------------------------------------- #
class ConfigError(ValueError):
    """Raised when a config fails validation. The system must halt, not guess."""


def validate(cfg: Dict[str, Any]) -> None:
    """Fail-closed validation of the merged config. Raises ConfigError on any
    violation. These checks encode invariants the brief treats as load-bearing."""
    r = cfg["risk"]
    c = cfg["conviction"]

    # Scorecard + verdict weights must each sum to 1.0 (Brief 6.2 / 6.3).
    sw = c["scorecard_weights"]
    if abs(sum(sw.values()) - 1.0) > 1e-9:
        raise ConfigError(f"scorecard_weights must sum to 1.0, got {sum(sw.values())}")
    vw = c["verdict_weights"]
    if abs(sum(vw.values()) - 1.0) > 1e-9:
        raise ConfigError(f"verdict_weights must sum to 1.0, got {sum(vw.values())}")

    # Conviction floors must respect bounds 65-80 (Brief 12 / 22).
    if not (c["floor_min"] <= c["stage1_hard_floor"] <= c["floor_max"]):
        raise ConfigError("stage1_hard_floor outside [floor_min, floor_max]")
    if not (c["floor_min"] <= c["execution_floor"] <= c["floor_max"]):
        raise ConfigError("execution_floor outside [floor_min, floor_max]")
    if c["execution_floor"] < c["stage1_hard_floor"]:
        raise ConfigError("execution_floor must be >= stage1_hard_floor")

    # Risk caps must be sane, positive fractions (Brief 13).
    if not (0 < r["per_trade_risk_pct"] <= 0.05):
        raise ConfigError("per_trade_risk_pct must be in (0, 0.05]")
    if not (0 < r["max_position_pct"] <= 1.0):
        raise ConfigError("max_position_pct must be in (0, 1.0]")
    if not (0 < r["daily_loss_limit_pct"] <= 0.20):
        raise ConfigError("daily_loss_limit_pct must be in (0, 0.20]")
    if r["catastrophic_halt_equity_usd"] >= cfg["account"]["starting_capital_usd"]:
        raise ConfigError("catastrophic halt equity must be below starting capital")

    # LLM budgets ordered correctly (Brief 3.1).
    L = cfg["llm"]
    if not (L["daily_target_usd"] <= L["daily_budget_usd"] <= L["monthly_budget_usd"]):
        raise ConfigError("LLM budgets must satisfy target <= daily <= monthly")

    # Capital ramp must be monotonic non-decreasing (Brief 30.2).
    cr = cfg["capital_ramp"]
    ramp = [cr["live_days_1_5_usd"], cr["live_days_6_15_usd"],
            cr["live_days_16_30_usd"], cr["live_day_31_plus_usd"]]
    if ramp != sorted(ramp):
        raise ConfigError("capital_ramp must be monotonic non-decreasing")
    if ramp[-1] > cfg["account"]["starting_capital_usd"]:
        raise ConfigError("capital ramp cannot exceed starting capital")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str = None) -> Dict[str, Any]:
    """Return the validated config. Optionally overlay config.yaml if present
    and pyyaml is installed. Fail-closed: validation errors propagate."""
    cfg = copy.deepcopy(DEFAULTS)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    if os.path.exists(path):
        try:
            import yaml  # optional dependency
            with open(path, "r") as fh:
                overlay = yaml.safe_load(fh) or {}
            cfg = _deep_merge(cfg, overlay)
        except ImportError:
            # pyyaml not installed: bedrock still runs on canonical defaults.
            pass
    validate(cfg)
    return cfg
