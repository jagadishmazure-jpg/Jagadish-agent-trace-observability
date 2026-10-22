# Knowledge

Distilled notes behind this repo's design:

1. [Why traces](01-why-traces.md) — the black-box problem, span trees,
   orphan reporting, redact-before-store.
2. [Cost per successful request](02-cost-per-success.md) — the metric
   per-call dashboards hide, with the demo's real numbers and the
   traffic-mix caveat.
3. [Architecture](03-architecture.md) — components, data flow, and the
   decisions behind them.
4. [From traces to evals](04-from-traces-to-evals.md) — failure mining,
   clustering, eval export, and how this differs from feedback mining and
   offline eval scoring.
