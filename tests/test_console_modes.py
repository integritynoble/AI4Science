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


def test_entering_is_case_insensitive_and_stores_the_canonical_id():
    """resolve_name lower-cases; the Mode must carry what the registry keys on,
    not what the user's shift key produced. Every fixture used matching case,
    which is why this went unnoticed."""
    deps = _deps(resolve=lambda n: ("roster", n.lower()))
    act, mode = console.route("/Sarsi-Worker", console.Mode(), deps)
    assert mode.name == "sarsi-worker"


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
    """A chat spec is not a mode — it is who answers. The switch itself is
    NOT reimplemented here: `/agent <name>` is forwarded to the loop's real
    switcher (provider-lock, session rebuild, TUI-label sync all live there),
    so this returns an `answer` the old chain performs — not a `say` that
    only claims a switch happened."""
    act, mode = console.route("/research", console.Mode(), _deps())
    assert act.kind == "answer"
    assert act.text == "/agent research"
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


def test_plain_text_in_agent_mode_asks_before_creating():
    """A task starts a session and spends PWM. One keystroke of friction, and
    no sentence becomes a task by accident."""
    made = []
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, mode = console.route("write a GAP-TV algorithm for CASSI", m,
                              _deps(create=lambda a, g: made.append(g) or "x"))
    assert act.kind == "confirm"
    assert made == [], "nothing may be created before the confirmation"
    assert mode.pending == "write a GAP-TV algorithm for CASSI"


def test_the_confirm_block_names_the_goal_and_the_agent():
    text = console.confirm_block("write a GAP-TV algorithm", "sarsi-worker")
    assert "write a GAP-TV algorithm" in text
    assert "sarsi-worker" in text
    assert "Enter" in text


def test_empty_confirms_and_creates():
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, mode = console.route("", m, _deps())
    assert act.kind == "create"
    assert act.goal == "do the thing"
    assert mode.pending is None


def test_y_confirms_too():
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, _ = console.route("y", m, _deps())
    assert act.kind == "create"


def test_n_drops_it_and_creates_nothing():
    made = []
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, mode = console.route("n", m,
                              _deps(create=lambda a, g: made.append(g) or "x"))
    assert act.kind == "say"
    assert made == []
    assert mode.pending is None


def test_e_reopens_the_goal_for_editing():
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, mode = console.route("e", m, _deps())
    assert act.kind == "say"
    assert "do the thing" in act.text
    assert mode.pending is None, "editing clears it; the next line is the new goal"


def test_anything_else_drops_it_rather_than_guessing():
    """A pending goal answered with prose is a user who has moved on. Creating
    the task anyway would be the one outcome nobody asked for."""
    made = []
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, mode = console.route("actually never mind", m,
                              _deps(create=lambda a, g: made.append(g) or "x"))
    assert made == []
    assert mode.pending is None


def test_plain_text_at_the_top_is_answered_not_confirmed():
    act, mode = console.route("what is GAP-TV?", console.Mode(), _deps())
    assert act.kind == "answer"
    assert mode.pending is None


def test_plain_text_in_task_mode_steers_it():
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, mode = console.route("focus on the mask convention first", m, _deps())
    assert act.kind == "guide"
    assert act.task == "tsk_ab12cd34"
    assert act.text == "focus on the mask convention first"
    assert mode == m, "steering does not change where you are standing"


def test_interact_names_the_session_to_attach():
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, _ = console.route("/interact", m, _deps())
    assert act.kind == "attach"
    assert act.session == "sarsi-worker-cd34"
    assert act.task == "tsk_ab12cd34"


def test_interact_print_only_says_the_command():
    """The escape hatch. On any terminal where the hand-off misbehaves there
    must still be a way through."""
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, _ = console.route("/interact --print", m, _deps())
    assert act.kind == "say"
    assert "tmux attach -t sarsi-worker-cd34" in act.text


def test_interact_with_no_session_says_how_to_start_one():
    """Not-there and cannot-be-read are different facts, and the first is the
    one with an action attached."""
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, _ = console.route("/interact", m, _deps(session_of=lambda t: ""))
    assert act.kind == "say"
    assert "sarsi run" in act.text


def test_interact_outside_task_mode_says_which_task():
    act, _ = console.route("/interact", console.Mode(), _deps())
    assert act.kind == "say"
    assert "task" in act.text.lower()


def test_every_harness_command_reaches_the_old_slash_chain():
    """The defect this guards: `console.route` had no `command` branch, so every
    known slash — /help, /model, /do, /exit — fell to the unknown catch-all,
    printed "not a command", and was swallowed before the real chain ever saw it.

    It uses the REAL resolver deliberately. `_deps()` stubs `resolve` with a dict
    that never returns "command", which is exactly why no existing test caught
    this. A fixture that cannot produce the failing input cannot find the bug.
    """
    from ai4science.harness import repl
    deps = _deps(resolve=repl.resolve_name)
    for cmd in sorted(repl.known_commands()):
        act, mode = console.route(f"/{cmd}", console.Mode(), deps)
        assert act.kind == "answer", (cmd, act.kind, act.text)
        assert act.text == f"/{cmd}", (cmd, act.text)


def test_and_the_arguments_survive():
    """`/agent sarsi-worker` must forward whole, not just the command word."""
    from ai4science.harness import repl
    deps = _deps(resolve=repl.resolve_name)
    act, _ = console.route("/agent sarsi-worker", console.Mode(), deps)
    assert act.kind == "answer"
    assert act.text == "/agent sarsi-worker"
