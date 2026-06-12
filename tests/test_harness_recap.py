"""End-of-turn LLM recap — Claude Code parity.

After a substantial turn (several tools or long crunch), Claude Code prints a
one-sentence recap of what was asked and found. The native harness mirrors
that with a cheap low-reasoning LLM call. AI4SCIENCE_RECAP tunes it:
0/off = never, always = every turn, unset = only substantial turns.
"""
from __future__ import annotations

from ai4science.harness import recap
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done


# ── policy ───────────────────────────────────────────────────────────────────

def test_should_recap_substantial_turns_only(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_RECAP", raising=False)
    assert recap.should_recap(seconds=5, tools=3)        # many tools
    assert recap.should_recap(seconds=25, tools=0)       # long crunch
    assert not recap.should_recap(seconds=3, tools=1)    # quick turn


def test_should_recap_env_off(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_RECAP", "0")
    assert not recap.should_recap(seconds=99, tools=9)


def test_should_recap_env_always(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_RECAP", "always")
    assert recap.should_recap(seconds=0, tools=0)


# ── generation ───────────────────────────────────────────────────────────────

def test_generate_recap_returns_text():
    stub = StubAdapter([[TextDelta("You asked for X; I found Y."), Done("end")]])
    out = recap.generate_recap(stub, "stub-model",
                               user_text="find my files",
                               final_text="here are your files: a, b")
    assert out == "You asked for X; I found Y."


def test_generate_recap_empty_stream_returns_none():
    stub = StubAdapter([[Done("end")]])
    assert recap.generate_recap(stub, "m", user_text="q", final_text="a") is None


def test_generate_recap_meters_usage():
    from ai4science.harness.events import Usage
    stub = StubAdapter([[TextDelta("r"), Usage(input=10, output=5, total=15),
                         Done("end")]])
    seen = []
    recap.generate_recap(stub, "m", user_text="q", final_text="a",
                         meter=lambda u: seen.append(u.total))
    assert seen == [15]


# ── REPL wiring ──────────────────────────────────────────────────────────────

def test_repl_prints_recap_line(tmp_path, monkeypatch, capsys):
    from ai4science.llm import routing
    import ai4science.harness.repl as repl_mod

    stub = StubAdapter([
        [TextDelta("the answer"), Done("end")],          # the turn
        [TextDelta("Recap sentence here."), Done("end")],  # the recap call
    ])
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: stub)
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: b == "anthropic")
    monkeypatch.setenv("AI4SCIENCE_RECAP", "always")

    inputs = iter(["do something", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl_mod.run_common_repl(tmp_path, read_only=True, auto_yes=False,
                             backend="anthropic", model="stub")

    out = capsys.readouterr().out
    assert "recap: Recap sentence here." in out


def test_repl_skips_recap_on_quick_turns(tmp_path, monkeypatch, capsys):
    from ai4science.llm import routing
    import ai4science.harness.repl as repl_mod

    stub = StubAdapter([[TextDelta("fast answer"), Done("end")]])
    monkeypatch.setattr(repl_mod, "adapter_for", lambda b: stub)
    monkeypatch.setattr(repl_mod, "make_meter", lambda **kw: lambda u: None)
    monkeypatch.setattr(routing, "backend_available", lambda b: b == "anthropic")
    monkeypatch.delenv("AI4SCIENCE_RECAP", raising=False)

    inputs = iter(["quick q", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl_mod.run_common_repl(tmp_path, read_only=True, auto_yes=False,
                             backend="anthropic", model="stub")

    assert "recap:" not in capsys.readouterr().out
