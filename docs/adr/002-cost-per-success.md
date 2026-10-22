# ADR 002 — Cost per successful request as the headline cost metric

**Status:** accepted (2026-10-22)

**Context.** Cost per request hides failures: a run that fails still spent
tokens.

**Decision.** Report total spend divided by successful traces, with failed
and budget-blocked traces in the numerator. Zero successes returns 0.0 and
is shown alongside the success rate, so an outage is visible.

**Consequences.** The metric rises when reliability falls, which is the
point. It is not comparable across agents with different task mixes.
