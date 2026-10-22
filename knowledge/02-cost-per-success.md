# 02 — Cost per successful request

Most agent dashboards report **cost per call**: total spend divided by the
number of requests. It is the wrong denominator.

Failed requests still burn tokens. Retried requests burn them twice.
Looping requests burn them eight times. None of that spend produced a
successful outcome, but cost-per-call spreads it evenly over every request
and makes the unit economics look better than they are.

**Cost per successful request** = total spend ÷ *successful* requests.
All the waste lands in the numerator, where it belongs.

## The demo numbers (simulated workload, 40 requests)

| Metric | Value |
|---|---|
| Total cost | $0.110800 |
| Cost per request | $0.002770 |
| Cost per successful request | $0.003358 |

The per-success figure is ~21% higher. That gap is the money spent on the
6 failed runs, the budget-blocked attempt's predecessors, and the looping
trace — invisible in the per-call number.

## Why version comparisons need it

| Version | Requests | Success rate | Cost | Cost / success |
|---|---|---|---|---|
| 1.0 | 18 | 77.8% | $0.008944 | $0.000639 |
| 2.0 | 22 | 86.4% | $0.101856 | $0.005361 |

Read this table carefully, because it teaches the second lesson: v2's cost
per success is higher *not* because v2 is worse — its success rate is
better — but because v2's traffic mix includes 11 deep-dive research
requests at $0.0088 each from one power user, while v1 only handled cheap
standard requests. Cost per success is only comparable across **the same
traffic mix**. Segment by request type (or user, or tool) before drawing
conclusions — which is why the analytics module breaks cost down by model,
tool, user and version instead of offering one global number.

## The failure mode this catches

The classic production surprise: a cheaper model is swapped in, cost per
call drops 40%, and the change is declared a win — while its failure rate
tripled and cost per *success* actually rose. Per-call metrics reward
models that fail cheaply and often. Per-success metrics price the outcome
the business actually wanted.
