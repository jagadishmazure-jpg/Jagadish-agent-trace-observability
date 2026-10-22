"""Simulated production workload for a fictional support agent.

"Cinder Peak Outfitters" is an invented outdoor-gear retailer. Its support
agent answers order questions, checks refund eligibility and issues refunds.
This script runs 40 scripted requests through the tracer — most succeed,
some fail on tool errors, one loops on a tool, and one is stopped by the
budget cap before it spends anything — then builds the analytics dashboard.

Everything is deterministic: a FakeClock, sequential ids, fixed token
counts. No network, no API keys. Run:

    python3 demos/demo_run.py [--out demos/output]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracing.analytics import total_cost  # noqa: E402
from tracing.budgets import BudgetChecker, BudgetPolicy  # noqa: E402
from tracing.instrument import FakeClock, SequentialIds, Tracer  # noqa: E402
from tracing.model import TRACE_BUDGET_BLOCKED  # noqa: E402
from tracing.store import JsonlStore  # noqa: E402

AGENT_NAME = "support-agent"
MODEL = "cpo-chat-mini"  # fictional model; prices below are illustrative
PRICE_IN_PER_TOKEN = 0.40 / 1_000_000
PRICE_OUT_PER_TOKEN = 1.60 / 1_000_000

USER_CAP_USD = 0.10
GLOBAL_CAP_USD = 1.00


def llm_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return round(prompt_tokens * PRICE_IN_PER_TOKEN
                 + completion_tokens * PRICE_OUT_PER_TOKEN, 6)


class ToolTimeout(Exception):
    pass


class PaymentError(Exception):
    pass


class InventoryError(Exception):
    pass


# Token profiles: (prompt, completion) for the plan and respond LLM calls.
PROFILES = {
    "standard": {"plan": (320, 40), "respond": (500, 120)},
    "deep_dive": {"plan": (4000, 600), "respond": (6000, 2400)},
}


def estimate_cost(profile: str) -> float:
    p = PROFILES[profile]
    return round(llm_cost(*p["plan"]) + llm_cost(*p["respond"]), 6)


def _tool(run, clock, name, input_summary, advance_s, output_summary="",
          error=None):
    with run.span("tool", name) as span:
        span.input_summary = input_summary
        clock.advance(advance_s)
        if error is not None:
            raise error
        span.output_summary = output_summary


def _llm(run, profile, which, duration_ms, input_summary, output_summary):
    prompt, completion = PROFILES[profile][which]
    run.record_llm(which, MODEL, prompt, completion,
                   llm_cost(prompt, completion),
                   input_summary=input_summary, output_summary=output_summary,
                   duration_ms=duration_ms)


def _execute(run, clock, kind, profile, version):
    """The scripted agent body. Tool errors raise, like a real adapter's."""
    with run.span("other", "handle_request") as root:
        root.input_summary = "%s request" % kind
        _llm(run, profile, "plan", 210.0,
             "plan the %s request" % kind, "tool plan ready")
        if kind == "order_status":
            _tool(run, clock, "get_order", "order_id=CP-1042", 0.12,
                  "status: shipped")
        elif kind == "refund":
            _tool(run, clock, "get_order", "order_id=CP-2077", 0.11,
                  "status: delivered")
            _tool(run, clock, "check_refund_policy", "order_id=CP-2077",
                  0.06, "eligible: within 30 days")
            _tool(run, clock, "issue_refund", "order_id=CP-2077",
                  0.18, "refund ticket RT-88 created")
        elif kind == "deep_dive":
            _tool(run, clock, "search_catalogue", "query=insulated boots",
                  0.42, "14 candidates")
            _tool(run, clock, "compare_prices", "skus=14", 0.35,
                  "comparison ready")
        elif kind == "loop":
            for _ in range(8):
                _tool(run, clock, "check_inventory",
                      "sku=BOOT-220, warehouse=west", 0.05, "in stock: 3")
        elif kind == "timeout":
            _tool(run, clock, "get_order", "order_id=CP-3090", 0.30,
                  error=ToolTimeout("order service timeout after %d ms"
                                    % (3000 if version == "1.0" else 5000)))
        elif kind == "payment_error":
            _tool(run, clock, "get_order", "order_id=CP-4111", 0.10,
                  "status: delivered")
            _tool(run, clock, "issue_refund", "order_id=CP-4111", 0.15,
                  error=PaymentError("refund rail rejected the request"))
        elif kind == "inventory_error":
            _tool(run, clock, "check_inventory", "sku=TENT-110, warehouse=east",
                  0.22, error=InventoryError("warehouse feed unavailable"))
        _llm(run, profile, "respond", 340.0,
             "draft the customer reply", "reply sent")
        root.output_summary = "request completed"


def run_request(tracer, clock, checker, *, session_id, user_id, version,
                kind, profile="standard"):
    """Run one scripted request. Returns the finished Trace."""
    estimate = estimate_cost(profile)
    decision = checker.check(user_id, estimate, clock.now())
    run = None
    try:
        with tracer.trace(session_id=session_id, user_id=user_id,
                          agent_name=AGENT_NAME,
                          agent_version=version) as run:
            if not decision.allowed:
                run.trace.status = TRACE_BUDGET_BLOCKED
                run.trace.outcome = ("blocked before execution: %s"
                                     % decision.reason)
                with run.span("guard", "budget_check") as span:
                    span.input_summary = "estimated cost $%.4f" % estimate
                    span.output_summary = decision.reason
                return run.trace
            _execute(run, clock, kind, profile, version)
    except (ToolTimeout, PaymentError, InventoryError):
        pass  # the trace context already recorded the failure and its outcome
    assert run is not None
    checker.record_spend(user_id, total_cost(run.spans), run.trace.started_at)
    return run.trace


def build_workload(store):
    """Run the full 40-request workload into ``store``; return (traces, spans)."""
    clock = FakeClock(start=1_700_000_000.0, step=0.05)
    tracer = Tracer(store=store, clock=clock, ids=SequentialIds())
    checker = BudgetChecker(BudgetPolicy(user_daily_usd=USER_CAP_USD,
                                         global_daily_usd=GLOBAL_CAP_USD))
    users = ["u-101", "u-102", "u-103", "u-104", "u-105"]
    n = [0]  # session counter

    def go(user, version, kind, profile="standard"):
        n[0] += 1
        return run_request(tracer, clock, checker,
                           session_id="sess-%02d" % n[0], user_id=user,
                           version=version, kind=kind, profile=profile)

    # --- agent v1.0: 18 requests (14 success, 4 failure) ---
    for i in range(10):
        go(users[i % len(users)], "1.0", "order_status")
    for i in range(3):
        go(users[(i + 2) % len(users)], "1.0", "refund")
    for _ in range(3):
        go("u-103", "1.0", "timeout")
    go("u-104", "1.0", "payment_error")
    go("u-105", "1.0", "loop")

    # --- agent v2.0: 22 requests (19 success, 2 failure, 1 budget-blocked) ---
    for i in range(5):
        go(users[i % len(users)], "2.0", "order_status")
    for i in range(3):
        go(users[(i + 1) % len(users)], "2.0", "refund")
    go("u-102", "2.0", "timeout")
    go("u-103", "2.0", "inventory_error")
    # A power user runs deep-dive research requests until the daily cap
    # stops one before it spends anything (11 succeed, the 12th is blocked).
    for _ in range(12):
        go("u-power", "2.0", "deep_dive", profile="deep_dive")

    return store.load_traces(), store.load_spans()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out_dir = "demos/output"
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    os.makedirs(out_dir, exist_ok=True)

    from demos.report import build_summary, render_html, render_markdown
    from tracing.mining import (export_eval_cases, select_traces,
                                write_eval_cases)

    jsonl_path = os.path.join(out_dir, "traces.jsonl")
    if os.path.exists(jsonl_path):
        os.remove(jsonl_path)
    store = JsonlStore(jsonl_path)
    build_workload(store)
    # Re-load from disk so the dashboard reflects what was persisted.
    traces, spans = store.load_traces(), store.load_spans()

    summary = build_summary(traces, spans)
    with open(os.path.join(out_dir, "dashboard.md"), "w", encoding="utf-8") as f:
        f.write(render_markdown(summary))
    with open(os.path.join(out_dir, "dashboard.html"), "w",
              encoding="utf-8") as f:
        f.write(render_html(summary))

    selected = select_traces(traces, spans, slow_ms=1500.0, expensive_usd=0.005)
    cases = export_eval_cases(traces, spans, [s["trace_id"] for s in selected])
    write_eval_cases(cases, os.path.join(out_dir, "eval_cases.jsonl"))

    print("traces: %d (success %d, failure %d, budget_blocked %d)"
          % (summary["total"], summary["success"], summary["failure"],
             summary["budget_blocked"]))
    print("total cost: $%.4f" % summary["total_cost"])
    print("cost per request: $%.6f" % summary["cost_per_request"])
    print("cost per successful request: $%.6f" % summary["cost_per_success"])
    print("loop flags: %d" % len(summary["loop_flags"]))
    print("failure clusters: %d" % len(summary["clusters"]))
    print("eval cases exported: %d" % len(cases))
    print("dashboard: %s" % os.path.join(out_dir, "dashboard.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
