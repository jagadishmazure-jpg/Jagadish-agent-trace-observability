"""Stores: JSONL round-trip, append-only behaviour, queries."""
from tests.helpers import make_span, make_trace
from tracing.store import InMemoryStore, JsonlStore, group_spans_by_trace, query_traces, spans_for_trace


def test_jsonl_round_trip(tmp_path):
    path = str(tmp_path / "traces.jsonl")
    store = JsonlStore(path)
    t = make_trace("t1", status="failure", outcome="boom")
    s = make_span("sp1", "t1", cost=0.42, prompt_tokens=10)
    store.add_trace(t)
    store.add_span(s)
    fresh = JsonlStore(path)
    assert fresh.load_traces() == [t]
    assert fresh.load_spans() == [s]


def test_jsonl_is_append_only_across_instances(tmp_path):
    path = str(tmp_path / "traces.jsonl")
    JsonlStore(path).add_trace(make_trace("t1"))
    JsonlStore(path).add_trace(make_trace("t2"))
    loaded = JsonlStore(path).load_traces()
    assert [t.trace_id for t in loaded] == ["t1", "t2"]


def test_jsonl_missing_file_loads_empty(tmp_path):
    store = JsonlStore(str(tmp_path / "nope.jsonl"))
    assert store.load_traces() == []
    assert store.load_spans() == []


def test_in_memory_store():
    store = InMemoryStore()
    store.add_trace(make_trace("t1"))
    store.add_span(make_span("sp1"))
    assert len(store.load_traces()) == 1
    assert len(store.load_spans()) == 1
    # loads return copies, not the live lists
    store.load_traces().append(make_trace("tx"))
    assert len(store.load_traces()) == 1


def _query_fixture():
    return [
        make_trace("t1", user_id="u1", version="1.0", status="success",
                   started_at=100.0, session_id="s1"),
        make_trace("t2", user_id="u1", version="2.0", status="failure",
                   started_at=200.0, session_id="s2", outcome="boom"),
        make_trace("t3", user_id="u2", version="2.0", status="success",
                   started_at=300.0, session_id="s2"),
    ]


def test_query_by_user():
    out = query_traces(_query_fixture(), user_id="u1")
    assert [t.trace_id for t in out] == ["t1", "t2"]


def test_query_by_version_and_status():
    out = query_traces(_query_fixture(), agent_version="2.0",
                       status="success")
    assert [t.trace_id for t in out] == ["t3"]


def test_query_by_session():
    out = query_traces(_query_fixture(), session_id="s2")
    assert [t.trace_id for t in out] == ["t2", "t3"]


def test_query_by_agent_name():
    out = query_traces(_query_fixture(), agent_name="support-agent")
    assert len(out) == 3
    assert query_traces(_query_fixture(), agent_name="other") == []


def test_query_time_range():
    out = query_traces(_query_fixture(), since=150.0, until=300.0)
    assert [t.trace_id for t in out] == ["t2"]
    out = query_traces(_query_fixture(), since=100.0)
    assert len(out) == 3  # since is inclusive


def test_query_no_criteria_returns_all():
    assert len(query_traces(_query_fixture())) == 3


def test_spans_for_trace_and_grouping():
    spans = [make_span("a", "t1"), make_span("b", "t2"),
             make_span("c", "t1")]
    assert [s.span_id for s in spans_for_trace(spans, "t1")] == ["a", "c"]
    grouped = group_spans_by_trace(spans)
    assert [s.span_id for s in grouped["t2"]] == ["b"]
    assert grouped.get("nope") is None
