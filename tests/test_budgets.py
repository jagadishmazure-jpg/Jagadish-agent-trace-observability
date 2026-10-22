"""Budget caps: allow/deny decisions and the prove-it-trips pattern."""
from tracing.budgets import BudgetChecker, BudgetPolicy

T0 = 1_700_000_000.0  # 2023-11-14 22:13 UTC
NEXT_DAY = T0 + 90_000.0  # >25h later: a different UTC day


def make_checker(user_cap=1.00, global_cap=5.00):
    return BudgetChecker(BudgetPolicy(user_daily_usd=user_cap,
                                      global_daily_usd=global_cap))


def test_allows_within_budget():
    checker = make_checker()
    checker.record_spend("u1", 0.60, T0)
    decision = checker.check("u1", 0.30, T0)
    assert decision.allowed
    assert decision.user_spent_today == 0.60
    assert "within budget" in decision.reason


def test_allows_exactly_at_cap():
    checker = make_checker()
    checker.record_spend("u1", 0.60, T0)
    assert checker.check("u1", 0.40, T0).allowed  # 0.60 + 0.40 == cap


def test_denies_over_user_cap():
    checker = make_checker()
    checker.record_spend("u1", 0.60, T0)
    decision = checker.check("u1", 0.50, T0)
    assert not decision.allowed
    assert "user daily cap" in decision.reason


def test_denies_over_global_cap_for_fresh_user():
    checker = make_checker()
    checker.record_spend("u-heavy", 4.95, T0)
    decision = checker.check("u-new", 0.10, T0)
    assert not decision.allowed
    assert "global daily cap" in decision.reason
    assert decision.global_spent_today == 4.95


def test_user_caps_are_independent():
    checker = make_checker()
    checker.record_spend("u1", 0.99, T0)
    assert not checker.check("u1", 0.02, T0).allowed
    assert checker.check("u2", 0.02, T0).allowed


def test_spend_accumulates_across_records():
    checker = make_checker()
    checker.record_spend("u1", 0.25, T0)
    checker.record_spend("u1", 0.35, T0)
    assert checker.user_spent("u1", T0) == 0.60
    assert checker.global_spent(T0) == 0.60


def test_new_day_resets_caps():
    checker = make_checker()
    checker.record_spend("u1", 0.99, T0)
    assert not checker.check("u1", 0.50, T0).allowed
    decision = checker.check("u1", 0.50, NEXT_DAY)
    assert decision.allowed
    assert decision.user_spent_today == 0.0


def test_trip_proof_with_artificially_low_cap():
    """The prove-it-trips pattern: set the cap absurdly low and show the
    checker denying a request it would otherwise allow."""
    normal = make_checker(user_cap=1.00)
    assert normal.check("u1", 0.02, T0).allowed
    tripped = make_checker(user_cap=0.01)
    decision = tripped.check("u1", 0.02, T0)
    assert not decision.allowed
    assert "user daily cap" in decision.reason


def test_zero_estimate_allowed_even_at_cap():
    checker = make_checker()
    checker.record_spend("u1", 1.00, T0)
    assert checker.check("u1", 0.0, T0).allowed
