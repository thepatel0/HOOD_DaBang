"""
HOOD DaBang — Regime Analyst (Tier 0, Brief §5.1, §26.3).

A Gaussian HMM (unsupervised) AND a RandomForest (supervised) both vote on the
market regime. Agreement -> a high-confidence label; disagreement -> 'transitional'
(the allocator then gets conservative). Tracks its own prediction residuals and
flags when a retrain is warranted (DreamerV3 principle).

8 labels: bull_trend_low_vol, bull_trend_high_vol, range_low_vol, range_high_vol,
bear_trend_low_vol, bear_trend_high_vol, crisis, transitional.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

import numpy as np

LABELS = [
    "bull_trend_low_vol", "bull_trend_high_vol",
    "range_low_vol", "range_high_vol",
    "bear_trend_low_vol", "bear_trend_high_vol",
    "crisis", "transitional",
]

# Feature order used throughout: [trend_50, trend_200, realized_vol, vix, breadth]
FEATURES = ["trend_50", "trend_200", "realized_vol", "vix", "breadth"]


def deterministic_regime(trend_50: float, trend_200: float, realized_vol: float,
                         vix: float, breadth: float) -> str:
    """Rule-based label — the supervised 'ground truth' the RF learns, and the
    fail-safe fallback when models are untrained."""
    if realized_vol > 0.40 or vix > 35:
        return "crisis"
    if trend_50 > 0.02 and trend_200 > 0:
        direction = "bull"
    elif trend_50 < -0.02 and trend_200 < 0:
        direction = "bear"
    else:
        direction = "range"
    vol_regime = "low_vol" if realized_vol < 0.15 else "high_vol"
    if direction == "range":
        return f"range_{vol_regime}"
    return f"{direction}_trend_{vol_regime}"


@dataclass
class RegimeResult:
    label: str
    confidence: float
    hmm_label: str
    rf_label: str
    agree: bool


class RegimeClassifier:
    def __init__(self, n_states: int = 4, seed: int = 42):
        self.n_states = n_states
        self.seed = seed
        self._hmm = None
        self._rf = None
        self._state_to_label: Dict[int, str] = {}
        self._residuals: Deque[int] = deque(maxlen=60)  # 1 if model != realized
        self._fitted = False

    # ----- training ------------------------------------------------------ #
    def fit(self, X: np.ndarray) -> "RegimeClassifier":
        """X: (n_samples, 5) feature matrix. Fits the HMM (unsupervised) and the
        RF (supervised on deterministic labels)."""
        from hmmlearn.hmm import GaussianHMM
        from sklearn.ensemble import RandomForestClassifier

        X = np.asarray(X, dtype=float)
        y = np.array([deterministic_regime(*row) for row in X])

        # HMM on standardized features
        self._mu = X.mean(axis=0)
        self._sd = X.std(axis=0) + 1e-9
        Xs = (X - self._mu) / self._sd
        self._hmm = GaussianHMM(n_components=self.n_states, covariance_type="diag",
                                n_iter=50, random_state=self.seed)
        self._hmm.fit(Xs)
        states = self._hmm.predict(Xs)
        # map each hidden state to the majority deterministic label within it
        for s in range(self.n_states):
            members = y[states == s]
            if len(members):
                self._state_to_label[s] = Counter(members).most_common(1)[0][0]
            else:
                self._state_to_label[s] = "transitional"

        # RF generalizes the deterministic rule (robust to noise)
        self._rf = RandomForestClassifier(n_estimators=60, random_state=self.seed,
                                          max_depth=6)
        self._rf.fit(X, y)
        self._fitted = True
        return self

    # ----- inference ----------------------------------------------------- #
    def classify(self, features: List[float]) -> RegimeResult:
        x = np.asarray(features, dtype=float).reshape(1, -1)
        # fallback to the deterministic rule if not fitted
        if not self._fitted:
            lbl = deterministic_regime(*features)
            return RegimeResult(lbl, 0.5, lbl, lbl, True)

        xs = (x - self._mu) / self._sd
        hmm_state = int(self._hmm.predict(xs)[0])
        hmm_label = self._state_to_label.get(hmm_state, "transitional")
        rf_label = str(self._rf.predict(x)[0])
        rf_conf = float(self._rf.predict_proba(x).max())

        agree = (hmm_label == rf_label)
        if agree:
            label = rf_label
            confidence = min(0.95, 0.7 + 0.25 * rf_conf)
        else:
            label = "transitional"
            confidence = 0.4
        return RegimeResult(label, round(confidence, 3), hmm_label, rf_label, agree)

    # ----- self-monitoring (residuals -> retrain trigger) ---------------- #
    def record_outcome(self, predicted: str, realized: str) -> None:
        self._residuals.append(0 if predicted == realized else 1)

    def residual_rate(self) -> float:
        return sum(self._residuals) / len(self._residuals) if self._residuals else 0.0

    def should_retrain(self, threshold: float = 0.40) -> bool:
        """True if recent residuals exceed threshold (regime model drifting)."""
        return len(self._residuals) >= 20 and self.residual_rate() > threshold
