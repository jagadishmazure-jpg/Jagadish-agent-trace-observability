"""Regression tests for bugs found in the portfolio-standard review."""
import pytest

from tracing.budgets import BudgetChecker, BudgetPolicy
from tracing.instrument import Tracer
from tracing.redact import redact_text
from tracing.store import InMemoryStore


def _fail(message):
    raise ValueError(message)


def _checker():
    return BudgetChecker(BudgetPolicy(user_daily_usd=1.0, global_daily_usd=5.0))


@pytest.mark.parametrize("bad", [-100.0, float("nan"), float("inf")])
def test_budget_rejects_negative_or_nan_estimate(bad):
    # A negative estimate used to pass the cap check; NaN compares False
    # against every cap, so it was always allowed too.
    with pytest.raises(ValueError):
        _checker().check("u1", bad, at=0.0)


def test_budget_rejects_negative_recorded_spend():
    c = _checker()
    c.record_spend("u1", 0.9, at=0.0)
    with pytest.raises(ValueError):
        c.record_spend("u1", -0.9, at=0.0)  # would have erased the spend
    assert not c.check("u1", 0.2, at=0.0).allowed


def test_exception_text_is_redacted_in_span_error_and_trace_outcome():
    store = InMemoryStore()
    tracer = Tracer(store=store)
    with pytest.raises(ValueError):
        with tracer.trace("s1", "u1", "agent", "1.0") as run:
            with run.span("tool", "charge"):
                _fail("card 4111 1111 1111 1111 declined, call 555-123-4567")
    trace = store.load_traces()[0]
    span = store.load_spans()[0]
    for text in (trace.outcome, span.error):
        assert "4111" not in text and "555-123-4567" not in text
        assert "[REDACTED]" in text


def test_record_llm_error_is_redacted():
    tracer = Tracer(store=InMemoryStore())
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        span = run.record_llm("llm", "m", 1, 1, 0.0, error="bad input 123-45-6789")
    assert "123-45-6789" not in span.error


def test_fifteen_digit_card_layout_is_redacted():
    assert "822463" not in redact_text("amex 3782 822463 10005 on file")
