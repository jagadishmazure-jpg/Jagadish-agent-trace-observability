# Threat model — agent trace observability

Scope: the tracer, redaction, stores, analytics, budget checker and failure
mining in this repo. Assets: user PII inside prompts and tool arguments,
spend (budget ledger), and the integrity of cost and success metrics.

## STRIDE

| Threat | Example | Control in this repo | Residual risk |
| --- | --- | --- | --- |
| Spoofing | A caller reports spend for another user id | Ledger keyed by the caller-supplied id; adopters must take the id from auth, not the request | Documented, not enforced here |
| Tampering | Negative or NaN spend lowers a ledger or passes a cap | `_require_cost` rejects non-finite / negative values (test) | None known |
| Repudiation | A failed run is dropped and looks like it never happened | Failed and budget-blocked traces are stored and counted in cost per success | — |
| Information disclosure | PII in summaries, exception text or exported eval cases | Redaction of summaries, span errors and trace outcomes before storage (tests) | Regex redaction misses free-text PII such as names and addresses |
| Denial of service | Runaway loops burn budget | Loop detection (span count, repeated identical tool calls) and pre-flight caps | Caps are per process; shared ledger is planned |
| Elevation of privilege | Trace store used as an instruction source | Traces are data only; nothing in this repo feeds them back into a prompt | Adopters must keep it that way |

## OWASP LLM Top 10 (relevant items)

- **LLM02 Sensitive information disclosure** — redaction before store, card,
  phone, SSN and long digit runs; tested ordering.
- **LLM10 Unbounded consumption** — per-user and global daily caps checked
  before a run, loop detection after.
- **LLM05 Improper output handling** — HTML dashboard escapes values.
