"""The console decides; repl performs. Everything here is a pure function.

The failure this exists to prevent: a user shown eight workers with no route
to any of them, because /do resolves its worker by the CHAT agent's name and
no chat spec is called sarsi-worker.
"""
import pytest

from ai4science.harness import console


def test_the_top_prompt_is_the_bare_marker():
    assert console.prompt_label(console.Mode()) == "❯ "


def test_agent_mode_names_the_agent():
    m = console.Mode(kind="agent", name="sarsi-worker")
    assert console.prompt_label(m) == "sarsi-worker ❯ "


def test_task_mode_says_it_is_guided():
    """Guided is not a detail — it is what the words in this mode DO, and a
    prompt that hid it would make steering look like chatting."""
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    assert console.prompt_label(m) == "tsk_ab12cd34 (guided) ❯ "


def test_a_mode_is_frozen():
    """route() returns a NEW Mode rather than mutating one. A mode mutated in
    place cannot be compared before and after, which is how a test asserting
    'entering costs nothing' would silently pass."""
    m = console.Mode()
    with pytest.raises(Exception):
        m.kind = "agent"


def test_an_action_carries_only_what_its_kind_needs():
    a = console.Action("say", text="hello")
    assert a.kind == "say" and a.text == "hello"
    assert a.goal == "" and a.task is None


def _deps(**over):
    d = {
        "resolve": lambda n: {"sarsi-worker": ("roster", "sarsi-worker"),
                              "research": ("spec", "research"),
                              "work": ("both", "work is BOTH: a chat spec and a roster agent"),
                              "tsk_ab12cd34": ("task", "tsk_ab12cd34")}.get(n, ("unknown", n)),
        "find_task": lambda t: ("agent-obj", "task-obj") if t == "tsk_ab12cd34" else (None, None),
        "suggest": lambda t: "",
        "create": lambda a, g: "tsk_new00001",
        "guide": lambda t, x: "sent",
        "session_of": lambda t: "sarsi-worker-cd34",
    }
    d.update(over)
    return d


def test_entering_a_roster_agent_sets_the_mode():
    act, mode = console.route("/sarsi-worker", console.Mode(), _deps())
    assert act.kind == "enter"
    assert mode == console.Mode(kind="agent", name="sarsi-worker")


def test_entering_costs_nothing():
    """The invariant. Nothing may be created by arriving somewhere."""
    made = []
    act, mode = console.route("/sarsi-worker", console.Mode(),
                              _deps(create=lambda a, g: made.append(g) or "x"))
    assert made == []
    assert act.kind == "enter"


def test_entering_a_task_sets_task_mode():
    act, mode = console.route("/tsk_ab12cd34", console.Mode(), _deps())
    assert mode == console.Mode(kind="task", name="tsk_ab12cd34")


def test_back_pops_one_level():
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, mode = console.route("/back", m, _deps())
    assert act.kind == "leave"
    assert mode.kind == "top"


def test_back_at_the_top_is_harmless():
    act, mode = console.route("/back", console.Mode(), _deps())
    assert mode.kind == "top"
    assert act.kind in ("say", "noop")


def test_a_spec_switches_the_chat_agent_without_entering_a_mode():
    act, mode = console.route("/research", console.Mode(), _deps())
    assert act.kind == "say" or act.kind == "enter"
    assert mode.kind == "top", "a chat spec is not a mode — it is who answers"


def test_a_name_that_is_both_enters_the_worker_and_says_the_other_exists():
    """`work` is a chat spec AND a roster agent. Entering the worker is the
    useful default; saying nothing about the other is how the confusion
    started."""
    act, mode = console.route("/work", console.Mode(), _deps())
    assert mode == console.Mode(kind="agent", name="work")
    assert "/agent work" in act.text


def test_an_unknown_slash_is_refused_and_nothing_is_sent():
    act, mode = console.route("/xyzzy", console.Mode(), _deps())
    assert act.kind == "say"
    assert mode.kind == "top"


def test_a_sentence_beginning_with_a_path_is_still_a_sentence():
    """The line this must not cross: a user quoting a path should not have to
    escape it."""
    act, _ = console.route("/home/grace/x is missing", console.Mode(), _deps())
    assert act.kind == "answer"
