"""Append-only trace storage.

Two backends with the same API:

- :class:`InMemoryStore` — lists in RAM; used by tests and the demo.
- :class:`JsonlStore` — one JSON object per line in a single file, lines
  tagged ``{"record": "trace", ...}`` or ``{"record": "span", ...}``.
  Append-only: existing lines are never rewritten, so a crash mid-write can
  at worst lose the last record, never corrupt earlier ones.

Queries filter traces by session, user, agent, version, status and time
range; span lookup is by trace id.
"""
from __future__ import annotations

import json
import os

from .model import Span, Trace


class InMemoryStore:
    def __init__(self):
        self.traces: list = []
        self.spans: list = []

    def add_trace(self, trace: Trace) -> None:
        self.traces.append(trace)

    def add_span(self, span: Span) -> None:
        self.spans.append(span)

    def load_traces(self) -> list:
        return list(self.traces)

    def load_spans(self) -> list:
        return list(self.spans)


class JsonlStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _append(self, record: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def add_trace(self, trace: Trace) -> None:
        self._append({"record": "trace", **trace.to_dict()})

    def add_span(self, span: Span) -> None:
        self._append({"record": "span", **span.to_dict()})

    def _load(self, kind: str, cls) -> list:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("record") == kind:
                    record.pop("record")
                    out.append(cls.from_dict(record))
        return out

    def load_traces(self) -> list:
        return self._load("trace", Trace)

    def load_spans(self) -> list:
        return self._load("span", Span)


def query_traces(traces: list, session_id: str = None, user_id: str = None,
                 agent_name: str = None, agent_version: str = None,
                 status: str = None, since: float = None,
                 until: float = None) -> list:
    """Filter traces; every supplied criterion must match. ``since``/``until``
    are epoch seconds on ``Trace.started_at`` (inclusive/exclusive)."""
    out = []
    for t in traces:
        if session_id is not None and t.session_id != session_id:
            continue
        if user_id is not None and t.user_id != user_id:
            continue
        if agent_name is not None and t.agent_name != agent_name:
            continue
        if agent_version is not None and t.agent_version != agent_version:
            continue
        if status is not None and t.status != status:
            continue
        if since is not None and t.started_at < since:
            continue
        if until is not None and t.started_at >= until:
            continue
        out.append(t)
    return out


def spans_for_trace(spans: list, trace_id: str) -> list:
    """All spans belonging to one trace, in stored order."""
    return [s for s in spans if s.trace_id == trace_id]


def group_spans_by_trace(spans: list) -> dict:
    grouped: dict = {}
    for span in spans:
        grouped.setdefault(span.trace_id, []).append(span)
    return grouped
