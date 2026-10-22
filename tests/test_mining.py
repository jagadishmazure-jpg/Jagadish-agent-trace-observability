"""Failure mining: signatures, clustering, selection, eval export."""
import json

from tests.helpers import make_span, make_trace
from tracing.mining import (cluster_failures, error_signature,
                            export_eval_cases, select_traces,
                            write_eval_cases)


def _timeout_trace(tid, ms, start=1000.0):
    trace = make_trace(tid, status="failure",
                       outcome="ToolTimeout: order service timeout")
    spans = [
        make_span(tid + "-root", tid, kind="other", name="handle_request",
                  started_at=start, status="error",
                  error="ToolTimeout: order service timeout after %d ms" % ms),
        make_span(tid + "-tool", tid, kind="tool", name="get_order",
                  started_at=start + 0.1, parent_span_id=tid + "-root",
                  status="error",
                  error="ToolTimeout: order service timeout after %d ms" % ms),
    ]
    return trace, spans


def test_signature_normalises_digits():
    _, spans_a = _timeout_trace("a", 3000)
    _, spans_b = _timeout_trace("b", 5000)
    trace_a, _ = _timeout_trace("a", 3000)
    assert error_signature(trace_a, spans_a) == \
        error_signature(trace_a, spans_b)


def test_signature_uses_innermost_error_span():
    trace, spans = _timeout_trace("a", 3000)
    sig = error_signature(trace, spans)
    assert sig.startswith("get_order:")
    assert "handle_request" not in sig


def test_signature_fallback_without_error_spans():
    trace = make_trace("x", status="budget_blocked",
                       outcome="blocked: cap 123 exceeded")
    sig = error_signature(trace, [])
    assert sig.startswith("budget_blocked:")
    assert "123" not in sig  # digits normalised


def test_cluster_failures_groups_by_signature():
    traces, spans = [], []
    for tid, ms in [("a", 3000), ("b", 5000), ("c", 3000)]:
        t, s = _timeout_trace(tid, ms)
        traces.append(t)
        spans += s
    ok = make_trace("ok", status="success")
    traces.append(ok)
    clusters = cluster_failures(traces, spans)
    assert len(clusters) == 1
    bucket = list(clusters.values())[0]
    assert bucket["count"] == 3
    assert sorted(bucket["trace_ids"]) == ["a", "b", "c"]
    assert bucket["example_trace_id"] == "a"


def test_cluster_failures_separates_different_errors():
    traces, spans = [], []
    t, s = _timeout_trace("a", 3000)
    traces.append(t)
    spans += s
    other = make_trace("p", status="failure", outcome="PaymentError: no")
    spans += [make_span("p1", "p", kind="tool", name="issue_refund",
                        status="error",
                        error="PaymentError: refund rail rejected")]
    traces.append(other)
    clusters = cluster_failures(traces, spans)
    assert len(clusters) == 2


def test_select_failures_and_blocked_by_default():
    traces = [make_trace("f", status="failure", outcome="x"),
              make_trace("b", status="budget_blocked", outcome="x"),
              make_trace("s", status="success")]
    selected = select_traces(traces, [])
    assert {x["trace_id"] for x in selected} == {"f", "b"}
    reasons = {x["trace_id"]: x["reasons"] for x in selected}
    assert reasons["f"] == ["failure"]
    assert reasons["b"] == ["budget_blocked"]


def test_select_can_exclude_blocked():
    traces = [make_trace("b", status="budget_blocked", outcome="x")]
    assert select_traces(traces, [], include_budget_blocked=False) == []


def test_select_slow_and_expensive_outliers():
    traces = [make_trace("slow-ok", status="success"),
              make_trace("fast-ok", status="success")]
    spans = [
        make_span("s1", "slow-ok", duration_ms=3000.0, cost=0.001),
        make_span("s2", "fast-ok", duration_ms=100.0, cost=0.001),
    ]
    selected = select_traces(traces, spans, slow_ms=2000.0)
    assert [x["trace_id"] for x in selected] == ["slow-ok"]
    assert selected[0]["reasons"] == ["slow"]
    selected = select_traces(traces, spans, expensive_usd=0.0005)
    assert {x["trace_id"] for x in selected} == {"slow-ok", "fast-ok"}


def test_export_eval_case_format():
    trace, spans = _timeout_trace("a", 3000)
    spans[0].input_summary = "refund request for order CP-3090"
    cases = export_eval_cases([trace], spans, ["a"])
    assert len(cases) == 1
    case = cases[0]
    assert case["case_id"] == "trace-a"
    assert case["source_trace_id"] == "a"
    assert case["input"] == "refund request for order CP-3090"
    assert case["observed_status"] == "failure"
    assert case["expected_status"] == "success"
    assert case["error_signature"].startswith("get_order:")
    assert case["spans"][1] == {"kind": "tool", "name": "get_order",
                                "status": "error"}
    json.dumps(case)  # must be JSON-serialisable


def test_export_skips_unselected_traces():
    trace, spans = _timeout_trace("a", 3000)
    other = make_trace("z", status="failure", outcome="x")
    assert export_eval_cases([trace, other], spans, ["a"])[0][
        "source_trace_id"] == "a"
    assert export_eval_cases([trace, other], spans, []) == []


def test_write_eval_cases_jsonl(tmp_path):
    trace, spans = _timeout_trace("a", 3000)
    cases = export_eval_cases([trace], spans, ["a"])
    path = str(tmp_path / "cases.jsonl")
    assert write_eval_cases(cases, path) == 1
    with open(path, encoding="utf-8") as f:
        loaded = [json.loads(line) for line in f if line.strip()]
    assert loaded == cases
