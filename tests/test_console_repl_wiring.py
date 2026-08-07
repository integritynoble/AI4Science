"""repl performs what console decides — and only repl touches the world.

The wiring is where the two halves can drift: a console that returns an action
repl does not handle is a command that silently does nothing, which is the
defect class this whole piece exists to remove.
"""
import pytest

from ai4science.harness import console, repl


def _kinds_console_can_return() -> set:
    """Every Action kind console.py actually constructs, read from its source.

    Derived, not retyped. The previous version of this guard listed the kinds
    as a literal and compared it to repl.HANDLED_ACTIONS — another literal — so
    it could only fail when two hand-maintained lists disagreed with each other,
    and never noticed console.py at all. `known_commands()` in repl.py already
    derives from source the same way; this follows it.
    """
    import re, pathlib
    from ai4science.harness import console
    src = pathlib.Path(console.__file__).read_text()
    return set(re.findall(r'Action\(\s*["\']([a-z-]+)["\']', src))


def test_the_derivation_finds_something():
    """The trap in the fix. A regex that matched nothing would return an empty
    set, and `set() <= anything` passes — a hollow guard replaced by a hollow
    guard. Pin the floor so the derivation cannot silently stop working."""
    kinds = _kinds_console_can_return()
    assert len(kinds) >= 9, kinds
    assert "answer" in kinds and "attach" in kinds


def test_every_action_kind_console_can_return_is_handled_by_repl():
    """If console grows a kind and repl does not learn it, the command does
    nothing and says nothing."""
    missing = _kinds_console_can_return() - repl.HANDLED_ACTIONS
    assert not missing, (
        "console.py constructs these Action kinds that repl does not handle: %s"
        % sorted(missing))


def test_deps_expose_every_key_route_reads():
    """route() indexes deps directly; a missing key is a KeyError inside the
    REPL loop, which is the one place nothing may raise."""
    d = repl._console_deps({})
    for key in ("resolve", "find_task", "suggest", "create", "guide",
                "session_of"):
        assert key in d, key
        assert callable(d[key])


def test_the_prompt_tracks_the_mode():
    state = {"mode": console.Mode(kind="agent", name="sarsi-worker")}
    assert repl._prompt_for(state) == "sarsi-worker ❯ "
    state["mode"] = console.Mode()
    assert repl._prompt_for(state) == "❯ "


def test_a_dep_that_raises_becomes_a_message_not_an_exception(monkeypatch):
    """Nothing in this path may drop the session the owner is standing in."""
    d = repl._console_deps({})
    monkeypatch.setattr(repl, "_find_task",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert isinstance(d["session_of"]("tsk_nope"), str)


def test_the_attach_is_injectable_and_pauses_before_attaching():
    """The order is the safety property: a worker still steering while the
    owner types into the same session is two hands on one wheel."""
    calls = []
    out = repl._attach_tmux("sarsi-worker-cd34",
                            run=lambda argv: calls.append(argv) or 0)
    assert calls == [["tmux", "attach", "-t", "sarsi-worker-cd34"]]
    assert "sarsi-worker-cd34" in out


def test_a_failed_attach_is_reported_not_raised():
    out = repl._attach_tmux("nope", run=lambda argv: 1)
    assert isinstance(out, str)
    assert "nope" in out


def test_the_attach_never_raises_even_when_tmux_is_absent():
    def _boom(argv):
        raise FileNotFoundError("tmux")
    out = repl._attach_tmux("x", run=_boom)
    assert isinstance(out, str) and out


def test_suggest_is_quiet_when_there_is_no_clear_winner(monkeypatch):
    """A tie prints nothing. The alternative is a router that guesses, which is
    worse than one that says nothing."""
    class _S:
        best = None
    monkeypatch.setattr("ai4science.harness.agents.sarsi.triage.suggest",
                        lambda *a, **k: _S())
    assert repl._console_deps({})["suggest"]("anything") == ""


def test_and_names_the_agent_when_there_is_one(monkeypatch):
    class _C:
        agent_id = "sarsi-worker"
    class _S:
        best = _C()
    monkeypatch.setattr("ai4science.harness.agents.sarsi.triage.suggest",
                        lambda *a, **k: _S())
    note = repl._console_deps({})["suggest"]("write a gap-tv algorithm")
    assert "sarsi-worker" in note


def test_agents_switches_as_well_as_lists():
    """It lists and switches in one breath, which is what someone typing it
    expects."""
    handled, _ = repl._dispatch_slash("/agents", {"agent": "research"})
    assert handled is True


def test_agent_and_mode_survive_as_aliases():
    """Removing a command people already use, to make a naming point, is a cost
    paid by the user for the designer's tidiness."""
    for c in ("/agent", "/mode"):
        handled, _ = repl._dispatch_slash(c, {"agent": "research"})
        assert handled is True, c


def test_the_subagent_listing_survived_agents_becoming_the_switcher():
    """`/agents` used to print the SUBAGENTS registry — nested delegation types,
    an unrelated thing to the chat agents — and it was the only slash that
    surfaced them. Making /agents the switcher would have deleted a
    user-reachable listing to free up a name. It moved to /subagents instead."""
    handled, msg = repl._dispatch_slash("/subagents", {"agent": "research"})
    assert handled is True
    assert "physics-reviewer" in msg or "schema-validator" in msg


def test_a_tie_prints_no_recommendation(monkeypatch):
    """A router that guesses is worse than one that is quiet."""
    class _S:
        best = None
    monkeypatch.setattr("ai4science.harness.agents.sarsi.triage.suggest",
                        lambda *a, **k: _S())
    assert repl._console_deps({})["suggest"]("anything") == ""


def test_a_clear_winner_prints_one_line(monkeypatch):
    class _C:
        agent_id = "sarsi-worker"
    class _S:
        best = _C()
    monkeypatch.setattr("ai4science.harness.agents.sarsi.triage.suggest",
                        lambda *a, **k: _S())
    note = repl._console_deps({})["suggest"]("write a gap-tv algorithm")
    assert "sarsi-worker" in note
    assert note.count("\n") <= 1, "a recommendation is one line, not a paragraph"
