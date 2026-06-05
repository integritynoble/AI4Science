import pytest
from ai4science.harness.events import ToolCall, Done
from ai4science.harness.paper_load import PaperDoc
from ai4science.harness import paper_review
from ai4science.harness.paper_review import run_panel, structured_subrun, PanelError
from ai4science.harness.paper_bundle import ReviewerReview


class StubPanelAdapter:
    """Emits one queued tool-call per sub-run (fresh history), then stops."""
    def __init__(self, queue):
        self._queue = list(queue)   # list of (tool_name, args_dict)

    def stream(self, history, specs, *, model, reasoning):
        has_result = any(getattr(m, "role", None) == "tool" for m in history)
        if not has_result and self._queue:
            name, args = self._queue.pop(0)
            yield ToolCall(id="c0", name=name, arguments=args)
        yield Done()


def _doc():
    return PaperDoc(title="T", text="paper body", source_path="T.md", fmt="md")


def _review_args(rating):
    return {"summary": "s", "strengths": ["a"], "weaknesses": ["b"],
            "questions": ["q"], "scores": {"soundness": 3, "contribution": 3,
            "presentation": 3}, "rating": rating, "confidence": 4}


def _meta_args(decision):
    return {"summary": "ms", "key_points": ["k"], "decision": decision,
            "justification": "j"}


def test_structured_subrun_captures_args(tmp_path):
    adapter = StubPanelAdapter([("submit_review", _review_args(7))])
    out = structured_subrun(adapter=adapter, model="m", system="sys",
                            user_content="rev this", capture_tool="submit_review",
                            schema={"type": "object", "properties": {}},
                            workspace=tmp_path)
    assert out["rating"] == 7


def test_structured_subrun_raises_when_no_submit(tmp_path):
    adapter = StubPanelAdapter([])  # emits nothing
    with pytest.raises(paper_review.SubrunError):
        structured_subrun(adapter=adapter, model="m", system="s", user_content="u",
                          capture_tool="submit_review",
                          schema={"type": "object", "properties": {}},
                          workspace=tmp_path)


def test_run_panel_deep(tmp_path):
    adapter = StubPanelAdapter([
        ("submit_review", _review_args(8)),
        ("submit_review", _review_args(6)),
        ("submit_review", _review_args(4)),
        ("submit_meta_review", _meta_args("borderline")),
    ])
    bundle = run_panel(doc=_doc(), depth="deep", adapter=adapter, model="m",
                       backend="gemini", workspace=tmp_path)
    assert len(bundle.reviews) == 3
    assert bundle.meta_review is not None
    assert bundle.decision == "borderline"
    assert bundle.aggregate["mean_rating"] == 6.0


def test_run_panel_shallow_derives_decision(tmp_path):
    adapter = StubPanelAdapter([("submit_review", _review_args(8))])
    bundle = run_panel(doc=_doc(), depth="shallow", adapter=adapter, model="m",
                       backend="gemini", workspace=tmp_path)
    assert len(bundle.reviews) == 1
    assert bundle.meta_review is None
    assert bundle.decision == "accept"


def test_run_panel_marks_errored_reviewer(tmp_path, monkeypatch):
    calls = {"n": 0}
    real = paper_review.structured_subrun
    def flaky(**kw):
        if kw["capture_tool"] == "submit_review":
            calls["n"] += 1
            if calls["n"] == 2:
                raise paper_review.SubrunError("boom")
        return real(**kw)
    adapter = StubPanelAdapter([
        ("submit_review", _review_args(7)),
        ("submit_review", _review_args(7)),
        ("submit_meta_review", _meta_args("accept")),
    ])
    monkeypatch.setattr(paper_review, "structured_subrun", flaky)
    bundle = run_panel(doc=_doc(), depth="deep", adapter=adapter, model="m",
                       backend="gemini", workspace=tmp_path)
    errored = [r for r in bundle.reviews if r.error]
    assert len(errored) == 1


def test_run_panel_all_fail_raises(tmp_path, monkeypatch):
    def always_fail(**kw):
        raise paper_review.SubrunError("nope")
    monkeypatch.setattr(paper_review, "structured_subrun", always_fail)
    with pytest.raises(PanelError):
        run_panel(doc=_doc(), depth="shallow", adapter=StubPanelAdapter([]),
                  model="m", backend="gemini", workspace=tmp_path)
