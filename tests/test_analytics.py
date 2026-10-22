"""Analytics against hand-computed fixtures (see tests/helpers.py)."""
import pytest

from tests.helpers import analytics_fixture, make_span, make_trace
from tracing import analytics


def test_total_cost():
    _, spans = analytics_fixture()
    assert analytics.total_cost(spans) == pytest.approx(1.10)


def test_cost_per_request():
    traces, spans = analytics_fixture()
    assert analytics.cost_per_request(traces, spans) == pytest.approx(0.366667)


def test_cost_per_success_counts_failed_spend():
    traces, spans = analytics_fixture()
    # $1.10 total / 2 successes = $0.55 — higher than per-request because
    # the failed trace's $0.20 is real spend with no success to show for it.
    assert analytics.cost_per_success(traces, spans) == pytest.approx(0.55)
    assert analytics.cost_per_success(traces, spans) > \
        analytics.cost_per_request(traces, spans)


def test_cost_per_success_with_no_successes_is_zero():
    traces = [make_trace("x", status="failure", outcome="boom")]
    spans = [make_span("s", "x", cost=0.50)]
    assert analytics.cost_per_success(traces, spans) == 0.0


def test_cost_per_request_with_no_traces_is_zero():
    assert analytics.cost_per_request([], []) == 0.0


def test_cost_by_model():
    _, spans = analytics_fixture()
    assert analytics.cost_by_model(spans) == {"m1": 0.50, "m2": 0.50}


def test_cost_by_model_skips_spans_without_model():
    spans = [make_span("a", kind="tool", name="t", cost=0.30)]
    assert analytics.cost_by_model(spans) == {}


def test_cost_by_tool():
    _, spans = analytics_fixture()
    assert analytics.cost_by_tool(spans) == {"get_order": 0.10}


def test_cost_by_user():
    traces, spans = analytics_fixture()
    assert analytics.cost_by_user(traces, spans) == {"u1": 0.60, "u2": 0.50}


def test_cost_by_version():
    traces, spans = analytics_fixture()
    assert analytics.cost_by_version(traces, spans) == {"1.0": 0.60, "2.0": 0.50}


def test_token_totals():
    _, spans = analytics_fixture()
    assert analytics.token_totals(spans) == {"prompt": 300, "completion": 150}


def test_percentile_nearest_rank():
    values = [10.0, 20.0, 30.0, 40.0]
    assert analytics.percentile(values, 50) == 20.0
    assert analytics.percentile(values, 95) == 40.0
    assert analytics.percentile(values, 99) == 40.0
    assert analytics.percentile(values, 25) == 10.0


def test_percentile_edges():
    assert analytics.percentile([], 95) == 0.0
    assert analytics.percentile([7.0], 50) == 7.0
    assert analytics.percentile([7.0], 99) == 7.0


def test_latency_by_kind_and_tool():
    spans = [
        make_span("a", kind="llm", name="plan", duration_ms=100.0),
        make_span("b", kind="llm", name="plan", duration_ms=300.0),
        make_span("c", kind="tool", name="get_order", duration_ms=50.0),
    ]
    by_kind = analytics.latency_by_kind(spans)
    assert by_kind["llm"] == {"count": 2, "p50": 100.0, "p95": 300.0,
                              "p99": 300.0}
    by_tool = analytics.latency_by_tool(spans)
    assert list(by_tool) == ["get_order"]
    assert by_tool["get_order"]["count"] == 1


def test_trace_duration_ms():
    spans = [
        make_span("a", started_at=1000.0, duration_ms=200.0),
        make_span("b", started_at=1000.1, duration_ms=500.0),
    ]
    # last end = 1000.1 + 0.5 = 1000.6; first start 1000.0 -> 600 ms
    assert analytics.trace_duration_ms(spans) == pytest.approx(600.0)
    assert analytics.trace_duration_ms([]) == 0.0


def test_success_rate_by_version():
    traces, _ = analytics_fixture()
    rates = analytics.success_rate_by_version(traces)
    assert rates["1.0"]["total"] == 2
    assert rates["1.0"]["success"] == 1
    assert rates["1.0"]["failure"] == 1
    assert rates["1.0"]["success_rate"] == 0.5
    assert rates["2.0"]["success_rate"] == 1.0


def test_detect_loops_repeated_identical_tool_call():
    traces = [make_trace("L")]
    spans = [make_span("r", "L", kind="other", name="root")]
    spans += [make_span("s%d" % i, "L", kind="tool", name="check_inventory",
                        input_summary="sku=BOOT-220", started_at=1000.0 + i)
              for i in range(5)]
    flags = analytics.detect_loops(traces, spans)
    assert len(flags) == 1
    assert flags[0]["reason"] == "repeated_tool_call"
    assert flags[0]["trace_id"] == "L"


def test_detect_loops_same_tool_different_inputs_not_flagged():
    traces = [make_trace("L")]
    spans = [make_span("s%d" % i, "L", kind="tool", name="get_order",
                       input_summary="order=%d" % i, started_at=1000.0 + i)
             for i in range(5)]
    assert analytics.detect_loops(traces, spans) == []


def test_detect_loops_too_many_spans():
    traces = [make_trace("L")]
    spans = [make_span("s%d" % i, "L", kind="other", name="step%d" % i,
                       started_at=1000.0 + i) for i in range(26)]
    flags = analytics.detect_loops(traces, spans, max_spans=25)
    assert len(flags) == 1
    assert flags[0]["reason"] == "too_many_spans"


def test_detect_loops_clean_trace_not_flagged():
    traces, spans = analytics_fixture()
    assert analytics.detect_loops(traces, spans) == []
