"""Cost and performance analytics over stored traces.

The headline metric is **cost per successful request**: total spend divided
by the number of traces that actually succeeded. The naive alternative —
cost per call — hides the money burned on failed, retried and looping runs.
A version that looks cheaper per call can be more expensive per success if
it fails more often; the demo shows exactly that inversion.

All functions are pure: they take loaded traces/spans and return numbers or
plain dicts, so every figure in a report can be reproduced in a unit test
from a hand-computed fixture.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .model import TRACE_BUDGET_BLOCKED, TRACE_FAILURE, TRACE_SUCCESS
from .store import group_spans_by_trace


# ---------------------------------------------------------------- cost

def total_cost(spans: list) -> float:
    return round(sum(s.cost_usd for s in spans), 6)


def cost_per_request(traces: list, spans: list) -> float:
    """Total spend / number of traces. 0.0 when there are no traces."""
    if not traces:
        return 0.0
    return round(total_cost(spans) / len(traces), 6)


def cost_per_success(traces: list, spans: list) -> float:
    """Total spend / number of *successful* traces.

    Failed and budget-blocked traces still consumed tokens before they
    failed, so their cost is in the numerator — that is the point of the
    metric. Returns 0.0 when nothing succeeded (division by zero would
    hide a total outage behind an exception).
    """
    successes = sum(1 for t in traces if t.status == TRACE_SUCCESS)
    if successes == 0:
        return 0.0
    return round(total_cost(spans) / successes, 6)


def _sum_by(key_fn, spans: list) -> dict:
    out: dict = defaultdict(float)
    for s in spans:
        key = key_fn(s)
        if key is None:
            continue
        out[key] += s.cost_usd
    return {k: round(v, 6) for k, v in sorted(out.items())}


def cost_by_model(spans: list) -> dict:
    """Spend per model (llm spans only; spans without a model are skipped)."""
    return _sum_by(lambda s: s.model or None, spans)


def cost_by_tool(spans: list) -> dict:
    """Spend attributed to tool spans, grouped by tool name.

    Tool spans usually carry no direct model cost, but adapters can attach
    downstream API costs to them; either way the grouping is by span name
    for kind == "tool"."""
    return _sum_by(lambda s: s.name if s.kind == "tool" else None, spans)


def cost_by_user(traces: list, spans: list) -> dict:
    owner = {t.trace_id: t.user_id for t in traces}
    return _sum_by(lambda s: owner.get(s.trace_id), spans)


def cost_by_version(traces: list, spans: list) -> dict:
    version = {t.trace_id: t.agent_version for t in traces}
    return _sum_by(lambda s: version.get(s.trace_id), spans)


def token_totals(spans: list) -> dict:
    return {
        "prompt": sum(s.prompt_tokens for s in spans),
        "completion": sum(s.completion_tokens for s in spans),
    }


# ---------------------------------------------------------------- latency

def percentile(values: list, p: float) -> float:
    """Nearest-rank percentile. ``p`` in (0, 100]. Empty input -> 0.0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil(p / 100.0 * len(ordered))
    idx = min(max(rank - 1, 0), len(ordered) - 1)
    return ordered[idx]


def _latency_summary(durations: list) -> dict:
    return {
        "count": len(durations),
        "p50": round(percentile(durations, 50), 3),
        "p95": round(percentile(durations, 95), 3),
        "p99": round(percentile(durations, 99), 3),
    }


def latency_by_kind(spans: list) -> dict:
    by_kind: dict = defaultdict(list)
    for s in spans:
        by_kind[s.kind].append(s.duration_ms)
    return {k: _latency_summary(v) for k, v in sorted(by_kind.items())}


def latency_by_tool(spans: list) -> dict:
    by_tool: dict = defaultdict(list)
    for s in spans:
        if s.kind == "tool":
            by_tool[s.name].append(s.duration_ms)
    return {k: _latency_summary(v) for k, v in sorted(by_tool.items())}


def trace_duration_ms(trace_spans: list) -> float:
    """Wall-clock span of one trace: last span end minus trace start."""
    if not trace_spans:
        return 0.0
    start = min(s.started_at for s in trace_spans)
    end = max(s.started_at + s.duration_ms / 1000.0 for s in trace_spans)
    return round((end - start) * 1000.0, 3)


# ---------------------------------------------------------------- outcomes

def success_rate_by_version(traces: list) -> dict:
    """version -> {total, success, failure, budget_blocked, success_rate}."""
    out: dict = {}
    for t in traces:
        bucket = out.setdefault(t.agent_version, {
            "total": 0, "success": 0, "failure": 0,
            "budget_blocked": 0, "success_rate": 0.0,
        })
        bucket["total"] += 1
        if t.status == TRACE_SUCCESS:
            bucket["success"] += 1
        elif t.status == TRACE_FAILURE:
            bucket["failure"] += 1
        elif t.status == TRACE_BUDGET_BLOCKED:
            bucket["budget_blocked"] += 1
    for bucket in out.values():
        if bucket["total"]:
            bucket["success_rate"] = round(bucket["success"] / bucket["total"], 4)
    return out


# ---------------------------------------------------------------- loops

def detect_loops(traces: list, spans: list, max_spans: int = 25,
                 repeat_threshold: int = 4) -> list:
    """Flag traces that look like runaway loops.

    Two signals, either is enough:
    - the trace has more than ``max_spans`` spans, or
    - the same tool span (same name AND same input summary) repeats at least
      ``repeat_threshold`` times — the classic "agent keeps calling the same
      tool with the same arguments" loop.

    Returns a list of dicts: trace_id, reason, detail.
    """
    grouped = group_spans_by_trace(spans)
    trace_ids = {t.trace_id for t in traces}
    flags = []
    for trace_id in sorted(grouped):
        if trace_ids and trace_id not in trace_ids:
            continue
        trace_spans = grouped[trace_id]
        if len(trace_spans) > max_spans:
            flags.append({
                "trace_id": trace_id,
                "reason": "too_many_spans",
                "detail": "%d spans (limit %d)" % (len(trace_spans), max_spans),
            })
        counts: dict = defaultdict(int)
        for s in trace_spans:
            if s.kind == "tool":
                counts[(s.name, s.input_summary)] += 1
        for (name, _summary), n in sorted(counts.items()):
            if n >= repeat_threshold:
                flags.append({
                    "trace_id": trace_id,
                    "reason": "repeated_tool_call",
                    "detail": "tool %r called %d times with identical input"
                              % (name, n),
                })
    return flags
