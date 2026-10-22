"""Failure mining: turn production traces into eval cases.

Offline eval sets are written from imagination; production traces are what
actually happened. This module selects the traces worth learning from —
failures, budget-blocked runs, and slow/expensive outliers — clusters them
by error signature so the *patterns* are visible instead of 200 anecdotes,
and exports them as eval cases a team can drop into a regression set.

This is deliberately different from user-feedback mining (see
Jagadish-agent-feedback-loop): no human has to complain first. The signal
here is the execution itself — the spans, the errors, the cost.
"""
from __future__ import annotations

import json
import re

from .analytics import total_cost, trace_duration_ms
from .model import TRACE_BUDGET_BLOCKED, TRACE_FAILURE
from .store import group_spans_by_trace

_DIGITS_RE = re.compile(r"\d+")


def error_signature(trace, trace_spans: list) -> str:
    """Stable cluster key for a trace's failure.

    Built from the *innermost* error span's name and error text — the error
    span that started last, since wrapper spans (e.g. a request root) inherit
    the same exception as it unwinds — with digit runs normalised to ``#``,
    so "timeout after 3000 ms" and "timeout after 5000 ms" from the same
    tool cluster together instead of forming one cluster per incident.
    Traces with no error span fall back to their status + outcome.
    """
    error_spans = [s for s in trace_spans if s.status == "error"]
    if error_spans:
        span = max(error_spans, key=lambda s: s.started_at)
        normalised = _DIGITS_RE.sub("#", span.error or span.name)
        return "%s: %s" % (span.name, normalised.strip())
    return "%s: %s" % (trace.status, _DIGITS_RE.sub("#", trace.outcome or ""))


def select_traces(traces: list, spans: list, include_failures: bool = True,
                  include_budget_blocked: bool = True,
                  slow_ms: float = None, expensive_usd: float = None) -> list:
    """Pick traces worth mining. Returns dicts: trace_id, reasons (list).

    A trace can be selected for several reasons at once (e.g. failed AND
    expensive); all of them are listed.
    """
    grouped = group_spans_by_trace(spans)
    selected = []
    for trace in traces:
        trace_spans = grouped.get(trace.trace_id, [])
        reasons = []
        if include_failures and trace.status == TRACE_FAILURE:
            reasons.append("failure")
        if include_budget_blocked and trace.status == TRACE_BUDGET_BLOCKED:
            reasons.append("budget_blocked")
        if slow_ms is not None and trace_duration_ms(trace_spans) > slow_ms:
            reasons.append("slow")
        if expensive_usd is not None and total_cost(trace_spans) > expensive_usd:
            reasons.append("expensive")
        if reasons:
            selected.append({"trace_id": trace.trace_id, "reasons": reasons})
    return selected


def cluster_failures(traces: list, spans: list) -> dict:
    """Group failed / budget-blocked traces by error signature.

    Returns signature -> {count, trace_ids, example_trace_id}, sorted keys.
    """
    grouped = group_spans_by_trace(spans)
    clusters: dict = {}
    for trace in traces:
        if trace.status not in (TRACE_FAILURE, TRACE_BUDGET_BLOCKED):
            continue
        sig = error_signature(trace, grouped.get(trace.trace_id, []))
        bucket = clusters.setdefault(sig, {
            "count": 0, "trace_ids": [], "example_trace_id": trace.trace_id,
        })
        bucket["count"] += 1
        bucket["trace_ids"].append(trace.trace_id)
    return {k: clusters[k] for k in sorted(clusters)}


def export_eval_cases(traces: list, spans: list, selected_ids) -> list:
    """Build eval-case dicts for the selected traces.

    Format (JSONL-friendly, one dict per case)::

        {
          "case_id": "trace-<id>",
          "source_trace_id": ..., "agent_name": ..., "agent_version": ...,
          "user_id": ..., "session_id": ...,
          "input": <root span input summary, or "">,
          "observed_outcome": <what actually happened>,
          "observed_status": "failure" | "budget_blocked" | ...,
          "expected_status": "success",   # the regression expectation
          "error_signature": ...,
          "spans": [{"kind":..., "name":..., "status":...}, ...]
        }

    The expectation is always "this should succeed": the case exists because
    production showed it currently does not.
    """
    wanted = set(selected_ids)
    grouped = group_spans_by_trace(spans)
    cases = []
    for trace in traces:
        if trace.trace_id not in wanted:
            continue
        trace_spans = sorted(grouped.get(trace.trace_id, []),
                              key=lambda s: s.started_at)
        root_input = ""
        for span in trace_spans:
            if span.parent_span_id is None and span.input_summary:
                root_input = span.input_summary
                break
        cases.append({
            "case_id": "trace-%s" % trace.trace_id,
            "source_trace_id": trace.trace_id,
            "agent_name": trace.agent_name,
            "agent_version": trace.agent_version,
            "user_id": trace.user_id,
            "session_id": trace.session_id,
            "input": root_input,
            "observed_outcome": trace.outcome,
            "observed_status": trace.status,
            "expected_status": "success",
            "error_signature": error_signature(trace, trace_spans),
            "spans": [
                {"kind": s.kind, "name": s.name, "status": s.status}
                for s in trace_spans
            ],
        })
    return cases


def write_eval_cases(cases: list, path: str) -> int:
    """Write cases as JSONL; returns the number written."""
    with open(path, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, sort_keys=True) + "\n")
    return len(cases)
