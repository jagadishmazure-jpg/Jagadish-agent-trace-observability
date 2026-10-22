# Implementation guide

For engineers adopting this pattern in a real agent system.

## 1. Instrument the agent

Wrap one request in a trace; wrap each unit of work in a span:

```python
from tracing import Tracer, JsonlStore

tracer = Tracer(store=JsonlStore("traces.jsonl"))

with tracer.trace(session_id="s-1", user_id="u-9",
                  agent_name="support-agent", agent_version="2.0") as run:
    with run.span("tool", "get_order") as span:
        span.input_summary = "order_id=CP-1042"
        order = get_order("CP-1042")
        span.output_summary = "status: %s" % order.status
    run.record_llm("respond", model="your-model", prompt_tokens=500,
                   completion_tokens=120, cost_usd=0.000392,
                   duration_ms=340.0)
```

Or decorate tool functions — `@tracer.tool("get_order")` records a span
per call with argument/return summaries and error capture.

Rules of thumb:

- One trace per user request, never per process. Long-lived agents should
  start a new trace per turn or per task.
- Put token counts and cost on the LLM span at record time (from the
  provider response). Reconstructing cost later from logs is where
  observability projects go to die.
- Summaries, not payloads. Span inputs/outputs are for humans debugging;
  store a truncated summary and keep raw payloads in your system of
  record. The tracer redacts summaries before storage by default.

## 2. Check the budget before the run

```python
from tracing.budgets import BudgetChecker, BudgetPolicy

checker = BudgetChecker(BudgetPolicy(user_daily_usd=2.00,
                                     global_daily_usd=500.00))
decision = checker.check(user_id, estimated_cost_usd=0.01, at=now)
if not decision.allowed:
    # record a budget_blocked trace with a guard span; do not run the agent
    ...
checker.record_spend(user_id, actual_cost, at=now)  # after the run
```

Estimate honestly (last-run cost for the same request type is a good
default) and always record *actual* spend afterwards — the ledger is the
enforcement, the estimate is only the pre-flight test.

## 3. Analyse

Load the store and use the pure analytics functions: cost per request vs
per success, breakdowns by model/tool/user/version, latency percentiles,
loop detection (`detect_loops` flags both span-count blowups and repeated
identical tool calls), and success rate by version for deploy decisions.

## 4. Close the loop

Run mining on a schedule (nightly is fine): select failures, blocked runs
and outliers; review the clusters (new signatures are the interesting
output); export cases into your offline eval set so a fixed production
failure becomes a permanent regression test.

## 5. Plugging in a real backend

The span model carries the fields Langfuse / OpenTelemetry expect (trace
and span ids, parent links, start times, durations, token usage, cost).
An exporter is a store-shaped adapter: implement `add_trace`/`add_span`
(or a batch flush on trace end) that forwards spans to OTLP or the
vendor SDK, and keep the JSONL store as a local fallback. Nothing in the
analytics layer changes — it reads traces and spans, not the transport.

## Operational notes

- **Sampling:** at high volume, keep 100% of failures and blocked runs,
  sample successes. Mining depends on failures being complete.
- **Clock skew:** span trees assume one process's clock. For distributed
  agents, pass server timestamps into span records and validate with
  `validate_spans` on ingest.
- **Retention:** traces contain behavioural data even after redaction.
  Set a retention window and aggregate old traces into daily rollups.
