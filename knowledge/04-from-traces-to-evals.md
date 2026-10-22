# 04 — From traces to evals

Offline eval sets are written from imagination: the cases a team *expects*
to matter. Production traces are the cases that *actually* happened. The
mining module bridges the two:

1. **Select** — failed traces, budget-blocked traces, and outliers (slow
   or expensive) are the ones worth learning from. Successful, cheap,
   fast traces teach nothing new.
2. **Cluster** — group failures by error signature. The signature uses the
   innermost error span and normalises digit runs, so "timeout after
   3000 ms" and "timeout after 5000 ms" from the same tool land in one
   cluster. In the demo, 4 timeout traces across two agent versions form
   a single cluster — one underlying problem, not four anecdotes.
3. **Export** — each selected trace becomes an eval case: the original
   input (from the root span), the observed outcome, the span summary,
   and the expectation `expected_status: success`. The case exists because
   production proved the agent currently fails it; once fixed, the case
   guards against regression.

In the demo run, mining selects 19 of 40 traces (6 failures, 1 blocked,
11 expensive deep-dives, 1 slow loop) and exports them as JSONL eval
cases.

## How this differs from neighbouring repos

- **Jagadish-agent-feedback-loop** mines *user feedback*: ratings,
  corrections, rephrases. It needs a human to notice and report a bad
  answer. Trace mining needs no human signal — a run that failed, looped
  or cost 15x the median is visible in the spans whether or not anyone
  complained.
- **Jagadish-llm-evals-observability** scores agents *offline* against
  curated cases (trajectory and behaviour metrics). This repo observes
  agents *in production* and manufactures new cases for exactly that kind
  of offline scoring. The two compose: traces → mined cases → offline
  evals → safer deploys → new traces.

The loop is the point. Evals written once, from imagination, decay as
traffic changes. Evals continuously fed by production failures track what
users actually do.
