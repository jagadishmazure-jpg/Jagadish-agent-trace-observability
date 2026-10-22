"""Dashboard generation: turn traces into a Markdown + HTML report.

The summary dict is built purely from the analytics/mining modules, so every
number on the dashboard is reproducible from the stored traces — the same
functions are unit-tested against hand-computed fixtures.
"""
from __future__ import annotations

import html

from tracing import analytics
from tracing.mining import cluster_failures
from tracing.model import TRACE_BUDGET_BLOCKED, TRACE_FAILURE, TRACE_SUCCESS
from tracing.store import query_traces


def build_summary(traces: list, spans: list) -> dict:
    by_version = {}
    rates = analytics.success_rate_by_version(traces)
    spend_by_version = analytics.cost_by_version(traces, spans)
    for version, rate in sorted(rates.items()):
        v_traces = query_traces(traces, agent_version=version)
        v_ids = {t.trace_id for t in v_traces}
        v_spans = [s for s in spans if s.trace_id in v_ids]
        by_version[version] = {
            **rate,
            "cost": spend_by_version.get(version, 0.0),
            "cost_per_success": analytics.cost_per_success(v_traces, v_spans),
            "cost_per_request": analytics.cost_per_request(v_traces, v_spans),
        }
    return {
        "total": len(traces),
        "success": sum(1 for t in traces if t.status == TRACE_SUCCESS),
        "failure": sum(1 for t in traces if t.status == TRACE_FAILURE),
        "budget_blocked": sum(1 for t in traces
                              if t.status == TRACE_BUDGET_BLOCKED),
        "total_cost": analytics.total_cost(spans),
        "cost_per_request": analytics.cost_per_request(traces, spans),
        "cost_per_success": analytics.cost_per_success(traces, spans),
        "tokens": analytics.token_totals(spans),
        "by_version": by_version,
        "cost_by_model": analytics.cost_by_model(spans),
        "cost_by_tool": analytics.cost_by_tool(spans),
        "cost_by_user": analytics.cost_by_user(traces, spans),
        "latency_by_kind": analytics.latency_by_kind(spans),
        "latency_by_tool": analytics.latency_by_tool(spans),
        "loop_flags": analytics.detect_loops(traces, spans),
        "clusters": cluster_failures(traces, spans),
    }


def _money(x: float) -> str:
    return "$%.6f" % x


def render_markdown(s: dict) -> str:
    lines = []
    lines.append("# Agent trace dashboard — Cinder Peak Outfitters support agent")
    lines.append("")
    lines.append("Simulated workload: %d requests across agent versions %s."
                 % (s["total"], ", ".join(sorted(s["by_version"]))))
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append("| Requests | %d |" % s["total"])
    lines.append("| Succeeded | %d |" % s["success"])
    lines.append("| Failed | %d |" % s["failure"])
    lines.append("| Budget-blocked | %d |" % s["budget_blocked"])
    lines.append("| Total cost | %s |" % _money(s["total_cost"]))
    lines.append("| Cost per request | %s |" % _money(s["cost_per_request"]))
    lines.append("| **Cost per successful request** | **%s** |"
                 % _money(s["cost_per_success"]))
    lines.append("| Tokens (prompt / completion) | %d / %d |"
                 % (s["tokens"]["prompt"], s["tokens"]["completion"]))
    lines.append("")
    lines.append("Cost per successful request is higher than cost per request "
                 "because failed, looping and retried runs still burn tokens — "
                 "that gap is the money a per-call dashboard hides.")
    lines.append("")
    lines.append("## By agent version")
    lines.append("")
    lines.append("| Version | Requests | Success rate | Cost | Cost / success |")
    lines.append("|---|---|---|---|---|")
    for version, v in sorted(s["by_version"].items()):
        lines.append("| %s | %d | %.1f%% | %s | %s |"
                     % (version, v["total"], 100 * v["success_rate"],
                        _money(v["cost"]), _money(v["cost_per_success"])))
    lines.append("")
    lines.append("## Top failure clusters")
    lines.append("")
    if s["clusters"]:
        lines.append("| Signature | Count | Example trace |")
        lines.append("|---|---|---|")
        for sig, bucket in sorted(s["clusters"].items(),
                                  key=lambda kv: -kv[1]["count"]):
            lines.append("| %s | %d | %s |"
                         % (sig, bucket["count"], bucket["example_trace_id"]))
    else:
        lines.append("No failures recorded.")
    lines.append("")
    lines.append("## Flagged traces (loop detection)")
    lines.append("")
    if s["loop_flags"]:
        lines.append("| Trace | Reason | Detail |")
        lines.append("|---|---|---|")
        for flag in s["loop_flags"]:
            lines.append("| %s | %s | %s |"
                         % (flag["trace_id"], flag["reason"], flag["detail"]))
    else:
        lines.append("No loops detected.")
    lines.append("")
    lines.append("## Latency by span kind (ms)")
    lines.append("")
    lines.append("| Kind | Count | p50 | p95 | p99 |")
    lines.append("|---|---|---|---|---|")
    for kind, lat in sorted(s["latency_by_kind"].items()):
        lines.append("| %s | %d | %.1f | %.1f | %.1f |"
                     % (kind, lat["count"], lat["p50"], lat["p95"], lat["p99"]))
    lines.append("")
    return "\n".join(lines)


def _table(headers: list, rows: list) -> str:
    head = "".join("<th>%s</th>" % html.escape(h) for h in headers)
    body = ""
    for row in rows:
        body += "<tr>" + "".join("<td>%s</td>" % html.escape(str(c))
                                 for c in row) + "</tr>"
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (head, body)


def render_html(s: dict) -> str:
    headline = _table(
        ["Metric", "Value"],
        [["Requests", s["total"]], ["Succeeded", s["success"]],
         ["Failed", s["failure"]], ["Budget-blocked", s["budget_blocked"]],
         ["Total cost", _money(s["total_cost"])],
         ["Cost per request", _money(s["cost_per_request"])],
         ["Cost per successful request", _money(s["cost_per_success"])],
         ["Tokens (prompt / completion)",
          "%d / %d" % (s["tokens"]["prompt"], s["tokens"]["completion"])]],
    )
    versions = _table(
        ["Version", "Requests", "Success rate", "Cost", "Cost / success"],
        [[v, d["total"], "%.1f%%" % (100 * d["success_rate"]),
          _money(d["cost"]), _money(d["cost_per_success"])]
         for v, d in sorted(s["by_version"].items())],
    )
    clusters = _table(
        ["Signature", "Count", "Example trace"],
        [[sig, b["count"], b["example_trace_id"]]
         for sig, b in sorted(s["clusters"].items(),
                              key=lambda kv: -kv[1]["count"])],
    ) if s["clusters"] else "<p>No failures recorded.</p>"
    flags = _table(
        ["Trace", "Reason", "Detail"],
        [[f["trace_id"], f["reason"], f["detail"]] for f in s["loop_flags"]],
    ) if s["loop_flags"] else "<p>No loops detected.</p>"
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Agent trace dashboard</title>
<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:60rem}
table{border-collapse:collapse;margin:1rem 0}td,th{border:1px solid #ccc;
padding:.35rem .6rem;text-align:left}th{background:#f0f0f0}</style></head>
<body><h1>Agent trace dashboard — Cinder Peak Outfitters support agent</h1>
<p>Simulated workload: %d requests. Cost per successful request exceeds cost
per request because failed and looping runs still burn tokens.</p>
<h2>Headline numbers</h2>%s
<h2>By agent version</h2>%s
<h2>Top failure clusters</h2>%s
<h2>Flagged traces (loop detection)</h2>%s
</body></html>""" % (s["total"], headline, versions, clusters, flags)
