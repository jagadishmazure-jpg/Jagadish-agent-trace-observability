# 01 — Why traces

An agent in production is a black box. A user asks a question; some time
later an answer (or a refund, or a tool side-effect) comes out. When the
answer is wrong — or the bill is surprising — "the model did it" is not a
diagnosis.

A **trace** opens the box. One trace = one end-to-end request. Inside it,
every unit of work is a **span**: an LLM call, a tool call, a guard check.
Each span records:

- what went in and what came out (summaries, redacted),
- when it started and how long it took,
- how many tokens it used and what it cost,
- whether it failed, and with what error.

With spans in a tree you can answer the questions that actually come up in
operations:

- *Why did this request cost 15x the average?* — the span list shows a
  tool called 8 times with identical arguments.
- *Did the new agent version help?* — compare success rate and cost per
  success between versions over the same traffic.
- *Where does latency come from?* — p95 by span kind and by tool, instead
  of one end-to-end number that blames everything equally.
- *What broke at 3pm?* — cluster failed traces by error signature; one
  cluster with 40 members is an outage, 40 clusters with one member each
  is noise.

Two design choices in this repo are worth noting:

1. **Orphans are reported, not dropped.** If a span's parent is missing,
   instrumentation lost data. Silently attaching it elsewhere would make
   the tree lie; `build_tree` surfaces orphans explicitly.
2. **Redaction happens before storage.** Traces get read by people who
   should not see raw customer PII. Summaries pass through the redactor in
   the tracer, so there is no code path that persists an unredacted span.

Traces are the raw material for everything else in this repo: analytics,
budgets and failure mining all read the same span data.
