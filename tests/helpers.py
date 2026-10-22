"""Shared fixture builders for the test suite."""
from tracing.model import Span, Trace


def make_trace(trace_id="t1", user_id="u1", version="1.0", status="success",
               started_at=1000.0, session_id="s1", agent_name="support-agent",
               outcome="done"):
    return Trace(trace_id=trace_id, session_id=session_id, user_id=user_id,
                 agent_name=agent_name, agent_version=version,
                 started_at=started_at, status=status, outcome=outcome)


def make_span(span_id="sp1", trace_id="t1", kind="llm", name="call", cost=0.0,
              duration_ms=100.0, started_at=1000.0, parent_span_id=None,
              model="", prompt_tokens=0, completion_tokens=0, status="ok",
              error="", input_summary="", output_summary=""):
    return Span(span_id=span_id, trace_id=trace_id, kind=kind, name=name,
                started_at=started_at, parent_span_id=parent_span_id,
                duration_ms=duration_ms, input_summary=input_summary,
                output_summary=output_summary, prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens, cost_usd=cost,
                status=status, error=error, model=model)


def analytics_fixture():
    """Hand-computed fixture.

    trace A (u1, v1.0, success): llm m1 $0.30 + tool get_order $0.10
    trace B (u1, v1.0, failure): llm m1 $0.20
    trace C (u2, v2.0, success): llm m2 $0.50 + tool get_order $0.00

    total $1.10 | per request $0.366667 | per success $0.55
    by model {m1: 0.50, m2: 0.50} | by user {u1: 0.60, u2: 0.50}
    by version {1.0: 0.60, 2.0: 0.50} | tokens 300 prompt / 150 completion
    """
    traces = [
        make_trace("A", user_id="u1", version="1.0", status="success"),
        make_trace("B", user_id="u1", version="1.0", status="failure",
                   outcome="boom"),
        make_trace("C", user_id="u2", version="2.0", status="success"),
    ]
    spans = [
        make_span("A1", "A", kind="llm", name="plan", cost=0.30, model="m1",
                  prompt_tokens=100, completion_tokens=50),
        make_span("A2", "A", kind="tool", name="get_order", cost=0.10),
        make_span("B1", "B", kind="llm", name="plan", cost=0.20, model="m1"),
        make_span("C1", "C", kind="llm", name="plan", cost=0.50, model="m2",
                  prompt_tokens=200, completion_tokens=100),
        make_span("C2", "C", kind="tool", name="get_order", cost=0.0),
    ]
    return traces, spans
