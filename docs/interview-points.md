# Interview talking points

**The 60-second story.** "Agents in production are a black box unless you
trace them. I built a stdlib-only observability layer: every request is a
trace, every model/tool call a span with inputs, outputs, latency, tokens
and cost. On top of the traces sit three things most dashboards miss: cost
per *successful* request, pre-flight budget caps, and failure mining that
turns production failures into eval cases."

**Why cost per success?** "Cost per call spreads the spend from failed,
retried and looping runs over every request. Per-success pricing puts the
waste in the numerator. In my simulated workload it runs ~21% higher than
per-call — that gap is real money a normal dashboard hides. It also stops
the classic mistake of swapping in a cheap model that fails three times
as often and calling it a saving."

**Why check budgets before the call?** "A budget report after the money
is gone is accounting. The checker holds a daily per-user and global
ledger and answers allow/deny with a reason *before* the run; denied runs
are recorded as `budget_blocked` traces so blocked demand stays visible.
I test it with the prove-it-trips pattern: set the cap artificially low
and show the denial."

**How do you find runaway agents?** "Two loop signals: traces with an
abnormal span count, and the same tool called repeatedly with identical
arguments — the classic agent loop. The demo's looping trace succeeds,
which is the point: success rate alone would never surface it, but loop
detection plus its cost does."

**Traces vs feedback vs evals?** "Three different signals. Feedback
mining (my agent-feedback-loop repo) needs a user to complain. Offline
evals (llm-evals-observability) score curated cases before deploy. Trace
mining reads the execution itself: failures, outliers and clusters,
exported as new eval cases. Production feeds the eval set, the eval set
gates the next deploy."

**Design choices worth defending.**
- *Append-only JSONL store* — a crash loses at most the last record;
  analytics are pure functions over loaded data, so every dashboard
  number is reproducible in a unit test.
- *Orphan spans reported, not dropped* — a missing parent means
  instrumentation lost data; hiding it makes the tree lie.
- *Redaction before storage, specific patterns first* — phone patterns
  run before generic digit runs so numbers are fully removed, and dates
  survive because their digit runs are short.
- *Deterministic fakes* — an injectable clock and id factory make the
  whole pipeline testable offline with hand-computed fixtures.

**Honest limitations.** "The workload is simulated and the pricing is
illustrative; there is no live vendor integration. The exporter seam is
the store interface — a Langfuse/OTel adapter implements the same
add_trace/add_span contract. Latency percentiles are nearest-rank over
stored spans, fine at this scale, not a streaming sketch."
