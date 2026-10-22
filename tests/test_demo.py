"""End-to-end demo workload: the simulated day, its dashboard, its exports.

Expected numbers below come from an actual run of demos/demo_run.py and are
asserted here so the README figures cannot drift from the code.
"""
import pytest

from demos.demo_run import build_workload
from demos.report import build_summary, render_html, render_markdown
from tracing.mining import export_eval_cases, select_traces
from tracing.store import InMemoryStore


@pytest.fixture(scope="module")
def workload():
    return build_workload(InMemoryStore())


@pytest.fixture(scope="module")
def summary(workload):
    traces, spans = workload
    return build_summary(traces, spans)


def test_workload_has_40_traces_with_expected_outcomes(workload):
    traces, _ = workload
    assert len(traces) == 40
    statuses = [t.status for t in traces]
    assert statuses.count("success") == 33
    assert statuses.count("failure") == 6
    assert statuses.count("budget_blocked") == 1


def test_workload_is_deterministic(workload):
    traces2, spans2 = build_workload(InMemoryStore())
    traces1, spans1 = workload
    assert [t.to_dict() for t in traces1] == [t.to_dict() for t in traces2]
    assert [s.to_dict() for s in spans1] == [s.to_dict() for s in spans2]


def test_headline_cost_numbers(summary):
    assert summary["total_cost"] == pytest.approx(0.1108, abs=1e-4)
    assert summary["cost_per_request"] == pytest.approx(0.002770, abs=1e-6)
    assert summary["cost_per_success"] == pytest.approx(0.003358, abs=1e-6)
    # the point of the metric: per-success costs more than per-request
    assert summary["cost_per_success"] > summary["cost_per_request"]


def test_version_comparison(summary):
    v1 = summary["by_version"]["1.0"]
    v2 = summary["by_version"]["2.0"]
    assert v1["total"] == 18 and v1["success_rate"] == pytest.approx(0.7778)
    assert v2["total"] == 22 and v2["success_rate"] == pytest.approx(0.8636)
    assert v2["budget_blocked"] == 1


def test_loop_trace_is_flagged(summary):
    assert len(summary["loop_flags"]) == 1
    flag = summary["loop_flags"][0]
    assert flag["reason"] == "repeated_tool_call"
    assert "check_inventory" in flag["detail"]


def test_failure_clusters(summary):
    clusters = summary["clusters"]
    assert len(clusters) == 4
    timeout = [b for sig, b in clusters.items() if "ToolTimeout" in sig]
    assert len(timeout) == 1 and timeout[0]["count"] == 4  # 3000ms + 5000ms


def test_eval_export_from_demo_selection(workload):
    traces, spans = workload
    selected = select_traces(traces, spans, slow_ms=1500.0,
                             expensive_usd=0.005)
    cases = export_eval_cases(traces, spans,
                              [s["trace_id"] for s in selected])
    assert len(cases) == 19  # 11 expensive + 6 failures + 1 slow + 1 blocked
    assert all(c["expected_status"] == "success" for c in cases)


def test_dashboard_markdown_contains_headline_numbers(summary):
    md = render_markdown(summary)
    assert "Cost per successful request" in md
    assert "$0.003358" in md
    assert "trace" in md.lower()


def test_dashboard_html_renders_tables(summary):
    page = render_html(summary)
    assert page.startswith("<!DOCTYPE html>")
    assert "<table>" in page
    assert "Cinder Peak Outfitters" in page
