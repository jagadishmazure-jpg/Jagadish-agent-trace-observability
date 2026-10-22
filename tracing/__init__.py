"""Tracing: production trace observability and cost analytics for agents."""
from .model import Span, Trace, SpanNode, build_tree, validate_spans
from .instrument import Tracer, TraceRun, FakeClock, SequentialIds
from .redact import redact_text
from .store import InMemoryStore, JsonlStore, query_traces, spans_for_trace
from .budgets import BudgetChecker, BudgetPolicy, Decision

__all__ = [
    "Span", "Trace", "SpanNode", "build_tree", "validate_spans",
    "Tracer", "TraceRun", "FakeClock", "SequentialIds",
    "redact_text",
    "InMemoryStore", "JsonlStore", "query_traces", "spans_for_trace",
    "BudgetChecker", "BudgetPolicy", "Decision",
]
