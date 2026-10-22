# Security policy

## Scope

This is a portfolio learning project. It runs fully offline on fictional
data: there are no live services, no credentials, and no real customer
data anywhere in the repo.

## Safety properties (tested, not just documented)

- Span input/output summaries are redacted before storage: phone numbers
  (including `(555) 123-4567` and `+1 (555) 123-4567` formats), SSNs and
  card-like digit runs are removed; dates are preserved.
- The budget checker denies *before* spend happens; a denied run is
  recorded as `budget_blocked` rather than executed anyway.
- Orphan spans (a parent instrumentation failed to emit) are reported by
  validation instead of being silently dropped or mis-attributed.

## Reporting a vulnerability

If you find a security issue in this demo code, please open a GitHub
issue. Do not include any real personal data in the report.
