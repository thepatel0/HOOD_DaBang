"""
HOOD DaBang — deployment-cap passcode (NEXT_STEPS Priority 3).

The deployment cap (total deployed <= $500, 50% of the $1,000 balance) is a hard
risk-gate rule. It can be overridden ONLY by the operator supplying the passcode.
This prevents the AI from auto-escalating the cap on a misread instruction —
only a human who knows the passcode can lift it, and only for the current
session (never persisted).

Constant-time comparison (hmac.compare_digest) avoids timing leaks.
"""
from __future__ import annotations

import hmac

# Operator-set passcode (as provided). The override is session-scoped and audited.
_DEPLOYMENT_PASSCODE = "pinappleexpress9"

DEFAULT_DEPLOYMENT_CAP_USD = 500.0   # 50% of the $1,000 funded balance


def verify_passcode(submitted: str) -> bool:
    """Constant-time check of the operator deployment-cap passcode."""
    if not isinstance(submitted, str) or not submitted:
        return False
    return hmac.compare_digest(submitted, _DEPLOYMENT_PASSCODE)
