from ai4science.harness import repl as repl_mod
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done


def test_repl_expands_mentions_on_turn(tmp_path, monkeypatch):
    (tmp_path / "note.md").write_text("SECRET-CONTENT")
    captured = {}
    real = repl_mod.AgentSession

    def _cap(**kwargs):
        s = real(**kwargs)
        orig = s.run_turn

        def _wrapped(text, images=None):
            captured["text"] = text
            captured["images"] = images
            return orig(text, images=images)
        s.run_turn = _wrapped
        captured["session"] = s
        return s

    monkeypatch.setattr(repl_mod, "AgentSession", _cap)
    monkeypatch.setattr(repl_mod, "adapter_for",
                        lambda b: StubAdapter([[TextDelta("ok"), Done("end")]]))
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr("ai4science.harness.persistence.save", lambda *a, **k: None)
    inputs = iter(["summarize @note.md", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    repl_mod.run_common_repl(tmp_path, backend="anthropic", model="stub")
    assert "SECRET-CONTENT" in captured["text"]
