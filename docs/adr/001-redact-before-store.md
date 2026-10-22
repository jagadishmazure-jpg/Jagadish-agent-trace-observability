# ADR 001 — Redact before store, including errors

**Status:** accepted (2026-10-22)

**Context.** Trace data is read by many people while debugging. Exception
messages frequently echo the input that caused them.

**Decision.** Every free-text field that reaches a store (input and output
summaries, span errors, trace outcomes) passes through the redactor at the
moment the span or trace closes. There is no unredacted path.

**Consequences.** Debugging loses the raw value; the shape of the error is
kept. Regex redaction is a floor, not a guarantee: free-text names and
addresses are not caught.
