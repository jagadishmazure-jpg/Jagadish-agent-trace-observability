"""Trace/span model: serialisation, tree building, validation."""
from tests.helpers import make_span, make_trace
from tracing.model import build_tree, validate_spans


def test_trace_defaults():
    t = make_trace(status="running", outcome="")
    assert t.status == "running"
    assert t.outcome == ""


def test_span_defaults():
    s = make_span()
    assert s.parent_span_id is None
    assert s.cost_usd == 0.0
    assert s.status == "ok"
    assert s.error == ""


def test_trace_dict_round_trip():
    from tracing.model import Trace
    t = make_trace("t9", user_id="u7", version="2.0", status="failure",
                   outcome="boom")
    assert Trace.from_dict(t.to_dict()) == t


def test_span_dict_round_trip():
    from tracing.model import Span
    s = make_span("sp9", cost=0.25, prompt_tokens=10, completion_tokens=5,
                  model="m1")
    assert Span.from_dict(s.to_dict()) == s


def test_build_tree_nesting():
    spans = [
        make_span("root", started_at=1000.0),
        make_span("child1", started_at=1000.1, parent_span_id="root"),
        make_span("child2", started_at=1000.2, parent_span_id="root"),
        make_span("grand", started_at=1000.15, parent_span_id="child1"),
    ]
    tree = build_tree(spans)
    assert tree.ok
    assert len(tree.roots) == 1
    root = tree.roots[0]
    assert [c.span.span_id for c in root.children] == ["child1", "child2"]
    assert root.children[0].children[0].span.span_id == "grand"
    assert root.depth() == 3
    assert len(list(root.walk())) == 4


def test_build_tree_multiple_roots_sorted():
    spans = [
        make_span("b", started_at=1001.0),
        make_span("a", started_at=1000.0),
    ]
    tree = build_tree(spans)
    assert [n.span.span_id for n in tree.roots] == ["a", "b"]


def test_build_tree_orphan_reported_not_dropped():
    spans = [
        make_span("root", started_at=1000.0),
        make_span("lost", started_at=1000.1, parent_span_id="missing"),
    ]
    tree = build_tree(spans)
    assert not tree.ok
    assert [s.span_id for s in tree.orphans] == ["lost"]
    assert len(tree.roots) == 1
    # the orphan is not silently attached anywhere in the tree
    assert all(n.span.span_id != "lost" for n in tree.roots[0].walk())


def test_build_tree_empty():
    tree = build_tree([])
    assert tree.roots == [] and tree.orphans == [] and tree.ok


def test_validate_clean_spans():
    spans = [make_span("a"), make_span("b", parent_span_id="a")]
    assert validate_spans(spans) == []


def test_validate_duplicate_id():
    spans = [make_span("a"), make_span("a")]
    problems = validate_spans(spans)
    assert any("duplicate" in p for p in problems)


def test_validate_orphan_flagged():
    spans = [make_span("a", parent_span_id="ghost")]
    problems = validate_spans(spans)
    assert any("orphan" in p for p in problems)


def test_validate_unknown_kind_and_negative_duration():
    spans = [make_span("a", kind="weird", duration_ms=-5.0)]
    problems = validate_spans(spans)
    assert any("unknown kind" in p for p in problems)
    assert any("negative duration" in p for p in problems)


def test_validate_mixed_traces():
    spans = [make_span("a", trace_id="t1"), make_span("b", trace_id="t2")]
    problems = validate_spans(spans)
    assert any("multiple traces" in p for p in problems)
