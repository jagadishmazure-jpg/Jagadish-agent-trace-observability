"""Instrumentation: turn agent code into traces with minimal effort.

Two APIs:

- Context managers — ``with tracer.trace(...) as run:`` then
  ``with run.span("tool", "get_order"):`` inside it.
- A decorator — ``@tracer.tool("get_order")`` wraps a function and records a
  span for every call, capturing argument/output summaries and errors.

The tracer takes an injectable clock and id factory so tests (and the demo)
are fully deterministic: :class:`FakeClock` advances by a fixed step on every
read, and :class:`SequentialIds` mints ``trace-1``, ``span-1``, ...

Span input/output summaries pass through a redaction hook (default:
:func:`tracing.redact.redact_text`) before anything is stored.
"""
from __future__ import annotations

import contextvars
import functools
import itertools
import time

from .model import TRACE_FAILURE, TRACE_SUCCESS, Span, Trace
from .redact import redact_text

_SUMMARY_LIMIT = 240


class FakeClock:
    """Deterministic clock: each ``now()`` returns the current value and then
    advances by ``step`` seconds. A duration measured between two consecutive
    reads is therefore exactly one step."""

    def __init__(self, start: float = 1_700_000_000.0, step: float = 0.05):
        self._t = start
        self._step = step

    def now(self) -> float:
        t = self._t
        self._t += self._step
        return t

    def advance(self, seconds: float) -> None:
        """Move the clock forward without a read (simulates work taking time)."""
        self._t += seconds


class SequentialIds:
    """Deterministic id factory: ``<prefix>-1``, ``<prefix>-2``, ..."""

    def __init__(self):
        self._counters = {}

    def __call__(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return "%s-%d" % (prefix, n)


_default_counter = itertools.count(1)


def _default_ids(prefix: str) -> str:
    return "%s-%d" % (prefix, next(_default_counter))


def _summarise(value) -> str:
    text = value if isinstance(value, str) else repr(value)
    if len(text) > _SUMMARY_LIMIT:
        text = text[: _SUMMARY_LIMIT - 3] + "..."
    return text


class _SpanContext:
    def __init__(self, tracer: "Tracer", run: "TraceRun", kind: str, name: str,
                 model: str = ""):
        self._tracer = tracer
        self._run = run
        self._kind = kind
        self._name = name
        self._model = model
        self.span: Span | None = None
        self._token = None

    def __enter__(self) -> Span:
        tracer = self._tracer
        parent = tracer._current_span.get()
        self.span = Span(
            span_id=tracer._ids("span"),
            trace_id=self._run.trace.trace_id,
            kind=self._kind,
            name=self._name,
            started_at=tracer._clock(),
            parent_span_id=parent.span_id if parent else None,
            model=self._model,
        )
        self._token = tracer._current_span.set(self.span)
        return self.span

    def __exit__(self, exc_type, exc, tb):
        tracer = self._tracer
        end = tracer._clock()
        span = self.span
        assert span is not None
        span.duration_ms = round((end - span.started_at) * 1000.0, 3)
        if exc is not None:
            span.status = "error"
            # Exception text often echoes the input (card, phone); redact it.
            span.error = tracer._redact("%s: %s" % (exc_type.__name__, exc))
        span.input_summary = tracer._redact(span.input_summary)
        span.output_summary = tracer._redact(span.output_summary)
        self._run.spans.append(span)
        tracer._current_span.reset(self._token)
        return False  # never swallow exceptions


class TraceRun:
    """Handle for one in-flight trace; returned by ``Tracer.trace``."""

    def __init__(self, tracer: "Tracer", trace: Trace):
        self._tracer = tracer
        self.trace = trace
        self.spans: list = []

    def span(self, kind: str, name: str, model: str = "") -> _SpanContext:
        return _SpanContext(self._tracer, self, kind, name, model=model)

    def record_llm(self, name: str, model: str, prompt_tokens: int,
                   completion_tokens: int, cost_usd: float,
                   input_summary: str = "", output_summary: str = "",
                   duration_ms: float = 0.0, error: str = "") -> Span:
        """Record a completed LLM call directly — for adapters that already
        have token/cost numbers from the provider response."""
        tracer = self._tracer
        parent = tracer._current_span.get()
        span = Span(
            span_id=tracer._ids("span"),
            trace_id=self.trace.trace_id,
            kind="llm",
            name=name,
            started_at=tracer._clock(),
            parent_span_id=parent.span_id if parent else None,
            duration_ms=duration_ms,
            input_summary=tracer._redact(input_summary),
            output_summary=tracer._redact(output_summary),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            status="error" if error else "ok",
            error=tracer._redact(error),
            model=model,
        )
        self.spans.append(span)
        return span


class _TraceContext:
    def __init__(self, tracer: "Tracer", session_id: str, user_id: str,
                 agent_name: str, agent_version: str):
        self._tracer = tracer
        self._session_id = session_id
        self._user_id = user_id
        self._agent_name = agent_name
        self._agent_version = agent_version
        self.run: TraceRun | None = None
        self._run_token = None

    def __enter__(self) -> TraceRun:
        tracer = self._tracer
        trace = Trace(
            trace_id=tracer._ids("trace"),
            session_id=self._session_id,
            user_id=self._user_id,
            agent_name=self._agent_name,
            agent_version=self._agent_version,
            started_at=tracer._clock(),
        )
        self.run = TraceRun(tracer, trace)
        self._run_token = tracer._current_run.set(self.run)
        return self.run

    def __exit__(self, exc_type, exc, tb):
        tracer = self._tracer
        run = self.run
        assert run is not None
        trace = run.trace
        if exc is not None:
            trace.status = TRACE_FAILURE
            trace.outcome = tracer._redact("%s: %s" % (exc_type.__name__, exc))
        elif trace.status == "running":
            trace.status = TRACE_SUCCESS
            if not trace.outcome:
                trace.outcome = "completed"
        if tracer.store is not None:
            tracer.store.add_trace(trace)
            for span in run.spans:
                tracer.store.add_span(span)
        tracer._current_run.reset(self._run_token)
        return False


class Tracer:
    """Creates traces and spans. Pass ``clock``/``ids`` fakes for tests."""

    def __init__(self, store=None, clock=None, ids=None, redactor=None):
        self.store = store
        self._clock = clock.now if clock is not None else time.time
        self._ids = ids if ids is not None else _default_ids
        self._redact = redactor if redactor is not None else redact_text
        self._current_span: contextvars.ContextVar = contextvars.ContextVar(
            "tracer_current_span", default=None
        )
        self._current_run: contextvars.ContextVar = contextvars.ContextVar(
            "tracer_current_run", default=None
        )

    def trace(self, session_id: str, user_id: str, agent_name: str,
              agent_version: str) -> _TraceContext:
        return _TraceContext(self, session_id, user_id, agent_name, agent_version)

    def tool(self, name: str):
        """Decorator: record a ``tool`` span around every call of the wrapped
        function. Summaries come from the call arguments and return value;
        exceptions mark the span as an error and are re-raised."""

        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                run = self._current_run.get()
                if run is None:
                    raise RuntimeError(
                        "@tracer.tool used outside a tracer.trace(...) block"
                    )
                with run.span("tool", name) as span:
                    parts = [_summarise(a) for a in args]
                    parts += ["%s=%s" % (k, _summarise(v))
                              for k, v in kwargs.items()]
                    span.input_summary = ", ".join(parts)
                    result = fn(*args, **kwargs)
                    span.output_summary = _summarise(result)
                    return result

            return wrapper

        return decorator
