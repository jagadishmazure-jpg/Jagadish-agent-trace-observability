"""Spend caps, checked BEFORE a call is made.

A budget that is only reported after the money is gone is an accounting
feature, not a control. :class:`BudgetChecker` keeps a deterministic daily
ledger of recorded spend and answers ``check(user_id, estimated_cost)`` with
an allow/deny decision and a reason, *before* the caller spends anything.

When the checker denies, the caller should not run the agent at all; it
records the trace with status ``budget_blocked`` (see the demo) so the
blocked demand stays visible in analytics instead of vanishing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class BudgetPolicy:
    user_daily_usd: float  # max spend per user per UTC day
    global_daily_usd: float  # max spend across all users per UTC day


@dataclass
class Decision:
    allowed: bool
    reason: str
    user_spent_today: float
    global_spent_today: float


def _require_cost(name: str, value: float) -> None:
    """A negative or NaN cost would let a caller lower its own spend or
    slip past the cap (NaN comparisons are always False)."""
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("%s must be a finite, non-negative number, got %r" % (name, value))


def _day_key(at: float) -> str:
    return datetime.fromtimestamp(at, tz=timezone.utc).strftime("%Y-%m-%d")


class BudgetChecker:
    """Deterministic daily spend ledger + pre-flight cap check.

    ``record_spend`` is called with the *actual* cost after a run completes;
    ``check`` is called with an *estimate* before a run starts. Spend is
    bucketed by UTC day, so a new day resets both caps automatically.
    """

    def __init__(self, policy: BudgetPolicy):
        self.policy = policy
        self._user_day: dict = {}  # (day, user_id) -> usd
        self._global_day: dict = {}  # day -> usd

    def record_spend(self, user_id: str, cost_usd: float, at: float) -> None:
        _require_cost("cost_usd", cost_usd)
        day = _day_key(at)
        key = (day, user_id)
        self._user_day[key] = round(self._user_day.get(key, 0.0) + cost_usd, 6)
        self._global_day[day] = round(self._global_day.get(day, 0.0) + cost_usd, 6)

    def user_spent(self, user_id: str, at: float) -> float:
        return self._user_day.get((_day_key(at), user_id), 0.0)

    def global_spent(self, at: float) -> float:
        return self._global_day.get(_day_key(at), 0.0)

    def check(self, user_id: str, estimated_cost_usd: float, at: float) -> Decision:
        _require_cost("estimated_cost_usd", estimated_cost_usd)
        user_spent = self.user_spent(user_id, at)
        global_spent = self.global_spent(at)
        if user_spent + estimated_cost_usd > self.policy.user_daily_usd:
            return Decision(
                allowed=False,
                reason="user daily cap exceeded: spent $%.4f + estimate $%.4f "
                       "> cap $%.4f" % (user_spent, estimated_cost_usd,
                                         self.policy.user_daily_usd),
                user_spent_today=user_spent,
                global_spent_today=global_spent,
            )
        if global_spent + estimated_cost_usd > self.policy.global_daily_usd:
            return Decision(
                allowed=False,
                reason="global daily cap exceeded: spent $%.4f + estimate $%.4f "
                       "> cap $%.4f" % (global_spent, estimated_cost_usd,
                                         self.policy.global_daily_usd),
                user_spent_today=user_spent,
                global_spent_today=global_spent,
            )
        return Decision(
            allowed=True,
            reason="within budget: user $%.4f/$%.4f, global $%.4f/$%.4f"
                   % (user_spent, self.policy.user_daily_usd,
                      global_spent, self.policy.global_daily_usd),
            user_spent_today=user_spent,
            global_spent_today=global_spent,
        )
