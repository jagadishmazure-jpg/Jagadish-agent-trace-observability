"""Tracer instrumentation: context managers, decorator, redaction, fakes."""
import pytest

from tracing.instrument import FakeClock, SequentialIds, Tracer
from tracing.store import InMemoryStore


def make_tracer():
    store = InMemoryStore()
    clock = FakeClock(start=1000.0, step=0.05)
    tracer = Tracer(store=store, clock=clock, ids=SequentialIds())
    return tracer, store, clock


def test_trace_and_span_recorded():
    tracer, store, _ = make_tracer()
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        with run.span("tool", "get_order") as span:
            span.input_summary = "order_id=CP-1"
            span.output_summary = "shipped"
    traces, spans = store.load_traces(), store.load_spans()
    assert len(traces) == 1
    assert traces[0].status == "success"
    assert traces[0].outcome == "completed"
    assert len(spans) == 1
    assert spans[0].kind == "tool" and spans[0].name == "get_order"
    assert spans[0].parent_span_id is None
    assert spans[0].input_summary == "order_id=CP-1"


def test_sequential_ids_are_deterministic():
    tracer, store, _ = make_tracer()
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        with run.span("tool", "a"):
            pass
        with run.span("tool", "b"):
            pass
    assert store.load_traces()[0].trace_id == "trace-1"
    assert [s.span_id for s in store.load_spans()] == ["span-1", "span-2"]


def test_fake_clock_duration_is_one_step():
    tracer, store, _ = make_tracer()
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        with run.span("tool", "timed"):
            pass
    assert store.load_spans()[0].duration_ms == 50.0  # step 0.05s


def test_nested_spans_link_to_parent():
    tracer, store, _ = make_tracer()
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        with run.span("other", "root"):
            with run.span("tool", "inner"):
                pass
    spans = {s.name: s for s in store.load_spans()}
    assert spans["inner"].parent_span_id == spans["root"].span_id
    assert spans["root"].parent_span_id is None


def test_exception_marks_span_and_trace_failure():
    tracer, store, _ = make_tracer()
    with pytest.raises(ValueError):
        with tracer.trace("s1", "u1", "agent", "1.0") as run:
            with run.span("tool", "explode"):
                raise ValueError("kaboom")
    trace = store.load_traces()[0]
    span = store.load_spans()[0]
    assert trace.status == "failure"
    assert "ValueError" in trace.outcome and "kaboom" in trace.outcome
    assert span.status == "error"
    assert "kaboom" in span.error


def test_decorator_records_tool_span():
    tracer, store, _ = make_tracer()

    @tracer.tool("add")
    def add(a, b):
        return a + b

    with tracer.trace("s1", "u1", "agent", "1.0"):
        assert add(2, 3) == 5
    spans = store.load_spans()
    assert len(spans) == 1
    assert spans[0].kind == "tool" and spans[0].name == "add"
    assert "2" in spans[0].input_summary and "3" in spans[0].input_summary
    assert spans[0].output_summary == "5"
    assert spans[0].status == "ok"


def test_decorator_outside_trace_raises():
    tracer, _, _ = make_tracer()

    @tracer.tool("add")
    def add(a, b):
        return a + b

    with pytest.raises(RuntimeError):
        add(1, 2)


def test_decorator_error_propagates_and_marks_span():
    tracer, store, _ = make_tracer()

    @tracer.tool("failer")
    def failer():
        raise KeyError("missing")

    with pytest.raises(KeyError):
        with tracer.trace("s1", "u1", "agent", "1.0"):
            failer()
    assert store.load_spans()[0].status == "error"
    assert store.load_traces()[0].status == "failure"


def test_span_summaries_are_redacted_before_storage():
    tracer, store, _ = make_tracer()
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        with run.span("tool", "call_customer") as span:
            span.input_summary = "phone (555) 123-4567"
            span.output_summary = "left voicemail"
    stored = store.load_spans()[0]
    assert "555" not in stored.input_summary
    assert "[REDACTED]" in stored.input_summary


def test_record_llm_stores_tokens_cost_and_parent():
    tracer, store, _ = make_tracer()
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        with run.span("other", "root"):
            span = run.record_llm("plan", "m1", 100, 40, 0.0123,
                                  input_summary="q", output_summary="a",
                                  duration_ms=88.0)
    assert span.prompt_tokens == 100 and span.completion_tokens == 40
    assert span.cost_usd == 0.0123 and span.model == "m1"
    root = [s for s in store.load_spans() if s.name == "root"][0]
    assert span.parent_span_id == root.span_id


def test_tracer_without_store_still_collects_spans():
    tracer = Tracer(store=None, clock=FakeClock(), ids=SequentialIds())
    with tracer.trace("s1", "u1", "agent", "1.0") as run:
        with run.span("tool", "x"):
            pass
    assert len(run.spans) == 1
    assert run.trace.status == "success"
