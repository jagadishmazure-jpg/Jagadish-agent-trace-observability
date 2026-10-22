"""Trace and span data model.

A *trace* is one end-to-end agent request (one user asking for one thing).
A *span* is one unit of work inside that trace: an LLM call, a tool call, a
guard check, or anything else worth timing and costing. Spans form a tree via
``parent_span_id``; the root span has ``parent_span_id is None``.

Everything here is plain dataclasses with dict (JSON) round-tripping so the
store can persist them as JSONL without any third-party serialiser.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

# Trace statuses. "running" is transient; the rest are terminal.
TRACE_RUNNING = "running"
TRACE_SUCCESS = "success"
TRACE_FAILURE = "failure"
TRACE_BUDGET_BLOCKED = "budget_blocked"

SPAN_KINDS = ("llm", "tool", "guard", "other")
SPAN_OK = "ok"
SPAN_ERROR = "error"


@dataclass
class Span:
    span_id: str
    trace_id: str
    kind: str  # one of SPAN_KINDS
    name: str
    started_at: float  # epoch seconds
    parent_span_id: Optional[str] = None
    duration_ms: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    status: str = SPAN_OK  # "ok" | "error"
    error: str = ""
    model: str = ""  # set on llm spans; "" otherwise

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Span":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Trace:
    trace_id: str
    session_id: str
    user_id: str
    agent_name: str
    agent_version: str
    started_at: float  # epoch seconds
    status: str = TRACE_RUNNING
    outcome: str = ""  # short human-readable final outcome

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Trace":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class SpanNode:
    """A span plus its resolved children, produced by build_tree."""

    span: Span
    children: list = field(default_factory=list)  # list[SpanNode]

    def walk(self):
        """Yield this node and all descendants, depth-first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def depth(self) -> int:
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children)


@dataclass
class TreeResult:
    roots: list  # list[SpanNode] — spans whose parent_span_id is None
    orphans: list  # list[Span] — parent_span_id points at a missing span

    @property
    def ok(self) -> bool:
        return not self.orphans


def build_tree(spans: list) -> TreeResult:
    """Reconstruct the span tree for one trace.

    Spans whose ``parent_span_id`` references a span that is not present are
    reported as orphans instead of being silently dropped or attached to the
    wrong parent — a missing parent usually means instrumentation lost a span,
    which is exactly the kind of gap observability exists to catch.
    """
    by_id = {s.span_id: s for s in spans}
    nodes = {s.span_id: SpanNode(span=s) for s in spans}
    roots: list = []
    orphans: list = []
    for span in spans:
        node = nodes[span.span_id]
        if span.parent_span_id is None:
            roots.append(node)
        elif span.parent_span_id in by_id:
            nodes[span.parent_span_id].children.append(node)
        else:
            orphans.append(span)
    # Deterministic ordering: by start time, then id.
    roots.sort(key=lambda n: (n.span.started_at, n.span.span_id))
    for node in nodes.values():
        node.children.sort(key=lambda n: (n.span.started_at, n.span.span_id))
    orphans.sort(key=lambda s: (s.started_at, s.span_id))
    return TreeResult(roots=roots, orphans=orphans)


def validate_spans(spans: list) -> list:
    """Return a list of human-readable problems found in a span list.

    Checks: duplicate span ids, spans from a different trace mixed in,
    unknown kinds, negative durations, and orphan parents (via build_tree).
    An empty list means the span set is well-formed.
    """
    problems: list = []
    seen: set = set()
    trace_ids: set = set()
    for span in spans:
        if span.span_id in seen:
            problems.append("duplicate span id: %s" % span.span_id)
        seen.add(span.span_id)
        trace_ids.add(span.trace_id)
        if span.kind not in SPAN_KINDS:
            problems.append("span %s has unknown kind %r" % (span.span_id, span.kind))
        if span.duration_ms < 0:
            problems.append("span %s has negative duration" % span.span_id)
    if len(trace_ids) > 1:
        problems.append("spans span multiple traces: %s" % sorted(trace_ids))
    tree = build_tree(spans)
    for orphan in tree.orphans:
        problems.append(
            "orphan span %s: parent %s not found" % (orphan.span_id, orphan.parent_span_id)
        )
    return problems
