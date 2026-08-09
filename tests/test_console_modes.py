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


def test_anything_else_never_creates_the_pending_goal():
    """The invariant this test was written for, unchanged: prose at a
    confirmation must NOT create the pending task. Creating it anyway would be
    the one outcome nobody asked for.

    What changed is what happens to the prose. It used to be discarded, and
    that cost the owner a whole typed goal, twice in one session — see
    `test_a_new_goal_at_a_confirmation_is_not_thrown_away`. So the prose is now
    routed as what it is, which for `actually never mind` means it is offered
    back as a goal.

    That is mildly silly and entirely recoverable: it is one `n` away, and the
    abandoned goal is named. Losing typed work is neither.
    """
    made = []
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, mode = console.route("actually never mind", m,
                              _deps(create=lambda a, g: made.append(g) or "x"))
    assert made == []
    assert mode.pending != "do the thing"
    assert "do the thing" in act.text


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


# ── `/agents` must list the workers, not only the chat specs ──────────

def test_the_agent_menu_lists_workers_first():
    """The owner opened `/agents`, saw sixteen chat specs, and could not find
    `sarsi-worker` — the agent the whole machine is built around.

    It was absent because `/agents` listed one registry (chat specs: what THIS
    repl runs) and workers live in another (the sarsi roster: who holds tasks).
    That distinction is real and it is not the owner's problem. One door.

    Workers come first because that is what the owner reaches for.
    """
    from ai4science.harness import console

    entries = console.agent_menu(
        core=[("unified-LLM", "General coding assistant")],
        specific=[("imaging", "CASSI reconstruction")],
        workers=[("sarsi-worker", "the general worker"),
                 ("jobs", "job search")],
        active="unified-LLM")

    assert [e.name for e in entries][:2] == ["sarsi-worker", "jobs"], \
        [e.name for e in entries]
    assert entries[0].kind == "worker"
    assert entries[0].name == "sarsi-worker"


def test_a_worker_entry_is_marked_as_one():
    """Selecting a worker ENTERS it; selecting a spec SWITCHES this repl. Two
    different acts in one list, so the list has to say which is which."""
    from ai4science.harness import console
    entries = console.agent_menu(core=[("unified-LLM", "d")], specific=[],
                                 workers=[("sarsi-worker", "w")],
                                 active="unified-LLM")
    worker = [e for e in entries if e.kind == "worker"][0]
    spec = [e for e in entries if e.kind == "spec"][0]
    assert "worker" in worker.label.lower()
    assert "← current" in spec.label


def test_the_current_spec_is_still_marked():
    from ai4science.harness import console
    entries = console.agent_menu(core=[("a", "d1"), ("b", "d2")], specific=[],
                                 workers=[], active="b")
    assert "← current" in [e for e in entries if e.name == "b"][0].label
    assert "← current" not in [e for e in entries if e.name == "a"][0].label


def test_no_workers_configured_is_not_an_error():
    """A machine with no sarsi registry still gets its spec list."""
    from ai4science.harness import console
    entries = console.agent_menu(core=[("a", "d")], specific=[], workers=[],
                                 active="a")
    assert [e.name for e in entries] == ["a"]


# ── A2 · a pending confirmation must not EAT the next line ────────────

def _deps_ok():
    return {"resolve": lambda n: ("unknown", ""), "session_of": lambda t: "",
            "find_task": lambda t: (None, None), "create": lambda a, g: "tsk_x",
            "guide": lambda t, x: "sent", "suggest": lambda t: "",
            "unknown": lambda l: "not a command"}


def test_a_new_goal_at_a_confirmation_is_not_thrown_away():
    """The owner lost the same sentence twice:

        ❯ can you plan at A2?
          create it? [Enter=yes / e=edit / n=no]
        ❯ please write a gap-tv algorithm for cassi based on python
        dropped — nothing was created

    The gap-TV line was read as the ANSWER, was not Enter/e/n, and was
    discarded. "Honoured or refused, never dropped" — that refuses AND drops.

    A line that is plainly not an answer cancels the pending goal and is then
    routed as what it is. Nothing typed disappears.
    """
    from ai4science.harness import console
    pending = console.Mode(kind="agent", name="sarsi-worker",
                           pending="can you plan at A2?")
    act, mode = console.route(
        "please write a gap-tv algorithm for cassi based on python",
        pending, _deps_ok())
    assert act.kind == "confirm", act
    assert act.goal == "write a gap-tv algorithm for cassi based on python"
    assert mode.pending == act.goal
    assert "can you plan at A2?" in act.text, (
        "the abandoned goal must be named, not silently forgotten")


def test_an_explicit_no_still_drops_it():
    from ai4science.harness import console
    pending = console.Mode(kind="agent", name="w", pending="build a thing")
    act, mode = console.route("n", pending, _deps_ok())
    assert act.kind == "say" and "build a thing" in act.text
    assert mode.pending is None


def test_enter_still_creates_and_e_still_edits():
    from ai4science.harness import console
    pending = console.Mode(kind="agent", name="w", pending="g")
    assert console.route("", pending, _deps_ok())[0].kind == "create"
    assert console.route("e", pending, _deps_ok())[0].kind == "say"


# ── A3 · not every line is a goal ─────────────────────────────────────

def test_a_greeting_is_answered_not_turned_into_a_task():
    """`hi` became a task goal. A greeting is not a directive."""
    from ai4science.harness import console
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, mode = console.route("hi", m, _deps_ok())
    assert act.kind == "answer", act
    assert mode.pending is None


def test_a_question_about_the_system_is_answered():
    """`can you plan at A2?` became a task goal. A question about what the
    worker can do is a question, and answering it is the whole of B1's first
    row — the owner is talking to the worker and getting a form."""
    from ai4science.harness import console
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, _ = console.route("can you plan at A2?", m, _deps_ok())
    assert act.kind == "answer"


def test_the_answer_says_how_to_make_it_a_task_anyway():
    """A directive phrased as a question must not become unreachable. Nothing
    is lost: the line is answered AND the way to task it is named."""
    from ai4science.harness import console
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, _ = console.route("could you write a gap-tv algorithm?", m, _deps_ok())
    assert act.kind == "answer"
    assert "/do" in act.text


def test_a_directive_still_becomes_a_goal():
    from ai4science.harness import console
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, mode = console.route("write a gap-tv algorithm for cassi", m, _deps_ok())
    assert act.kind == "confirm" and mode.pending
    assert act.goal == "write a gap-tv algorithm for cassi"


def test_the_framing_does_not_become_the_goal():
    """`the goal is please write X` used to file a task whose goal was
    "the goal is please write X"."""
    from ai4science.harness import console
    act, mode = console.route(
        "the goal is please write a GAP-TV solver for CASSI",
        console.Mode(kind="agent", name="sarsi-worker"), _deps_ok())
    assert act.kind == "confirm"
    assert act.goal == "write a GAP-TV solver for CASSI", act.goal
    assert mode.pending == act.goal


# ── A1 · /tasks and /do must read the mode you are standing in ────────

def test_the_sarsi_bridge_uses_the_mode_not_the_chat_spec():
    """The owner stood in `sarsi-worker ❯`, typed `/tasks`, and read:

        [harness] claude-code has no sarsi worker — it answers here instead

    `repl.py` passed `state["agent"]` — the CHAT SPEC — to the sarsi bridge and
    never looked at `state["mode"]`. So the mode was displayed and not
    consulted, which makes the prompt label a lie. `/sarsi-worker tasks` worked,
    because that path passes the name explicitly; bare `/tasks` in worker mode
    did not.
    """
    from ai4science.harness import repl, console
    assert repl._bridge_target({"agent": "claude-code",
                                "mode": console.Mode(kind="agent",
                                                     name="sarsi-worker")}) \
        == "sarsi-worker"


def test_at_the_top_it_still_uses_the_chat_spec():
    """Outside a worker there is no mode to read, and `/do` from a chat agent
    to its own counterpart is the original, correct behaviour."""
    from ai4science.harness import repl, console
    assert repl._bridge_target({"agent": "unified-LLM",
                                "mode": console.Mode()}) == "unified-LLM"


def test_task_mode_falls_back_to_the_chat_spec():
    """Standing in a TASK is not standing in a worker; there is no worker name
    to use, and guessing one would be worse than the message."""
    from ai4science.harness import repl, console
    assert repl._bridge_target({"agent": "unified-LLM",
                                "mode": console.Mode(kind="task",
                                                     name="tsk_1")}) == "unified-LLM"


def test_a_missing_mode_key_is_not_a_crash():
    from ai4science.harness import repl
    assert repl._bridge_target({"agent": "unified-LLM"}) == "unified-LLM"


# ── the worker answers questions about itself ─────────────────────────

def test_a_question_about_the_worker_is_answered_from_its_own_state():
    """`can you plan at A2?` became a task goal, because the worker had nothing
    to answer from. Now it does: `selfaware.describe` derives the answer from
    the registry, the trust ledger and the task store — each claim linked to
    the store it came from.
    """
    from ai4science.harness import console
    deps = dict(_deps_ok())
    deps["about_self"] = lambda name: "I am sarsi-worker, a worker on this machine."
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, mode = console.route("can you plan at A2?", m, deps)
    assert act.kind == "say", act
    assert "sarsi-worker" in act.text
    assert mode.pending is None, "a question must not become a pending goal"


def test_a_question_about_the_world_still_reaches_the_model():
    """A router that guesses is worse than one that is quiet. A canned page
    standing in for a real answer is the failure mode here."""
    from ai4science.harness import console
    deps = dict(_deps_ok())
    deps["about_self"] = lambda name: "SHOULD NOT BE USED"
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, _ = console.route("how does GAP-TV work?", m, deps)
    assert act.kind == "answer", act
    assert "SHOULD NOT" not in act.text


def test_an_agent_that_is_not_self_aware_falls_through():
    """`describe` returns "" when the flag is off; the line must then be
    answered as before rather than becoming an empty reply."""
    from ai4science.harness import console
    deps = dict(_deps_ok())
    deps["about_self"] = lambda name: ""
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, _ = console.route("what can you do?", m, deps)
    assert act.kind == "answer", act


# ── the confirmation offers the backend ───────────────────────────────
#
# backends.py's own charter: "what was missing is a name the owner can choose
# at the confirmation". The CLI got `--backend`; the confirmation never did —
# the one surface where every task is actually created.

def test_the_confirm_block_names_the_backend_and_the_switch():
    text = console.confirm_block("write a solver", "sarsi-worker")
    assert "sarsi-pwm" in text, "the default backend must be shown, not implied"
    assert "b=" in text, "and the block must say how to choose the other one"


def test_b_switches_the_backend_and_keeps_the_goal():
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, mode = console.route("b", m, _deps())
    assert act.kind == "confirm"
    assert "sarsi-claude" in act.text
    assert mode.pending == "do the thing", "switching must not drop the goal"
    assert mode.backend == "sarsi-claude"


def test_b_again_switches_back():
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing",
                     backend="sarsi-claude")
    act, mode = console.route("b", m, _deps())
    assert mode.backend == "sarsi-pwm"
    assert mode.pending == "do the thing"


def test_yes_carries_the_chosen_backend():
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing",
                     backend="sarsi-claude")
    act, mode = console.route("", m, _deps())
    assert act.kind == "create"
    assert act.backend == "sarsi-claude"
    assert mode.pending is None


def test_the_default_confirm_carries_no_backend():
    """An empty backend means task.create resolves the default in ONE place —
    the confirmation must not become a second author of the default."""
    m = console.Mode(kind="agent", name="sarsi-worker", pending="do the thing")
    act, _ = console.route("", m, _deps())
    assert act.kind == "create"
    assert act.backend == ""


def test_a_question_in_task_mode_is_answered_not_steered():
    """The owner asking ABOUT the task is not steering it. 'what is process
    now' went into a live session as steering and the owner read the silence
    as 'no reasoning ability' — the answer must come from the task's record,
    and say that nothing was sent."""
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, mode = console.route(
        "what is the process now", m,
        _deps(task_status=lambda t: f"{t} — running — status text"))
    assert act.kind == "say"
    assert "tsk_ab12cd34" in act.text
    assert mode == m, "asking does not change where you are standing"


def test_a_question_mark_in_task_mode_is_answered_not_steered():
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, _ = console.route("did it finish?", m,
                           _deps(task_status=lambda t: "state line"))
    assert act.kind == "say" and "state line" in act.text


def test_task_mode_without_a_status_dep_still_steers():
    """A console wired before task_status existed keeps its old behavior —
    a missing dep must not turn every question into a crash or a swallow."""
    m = console.Mode(kind="task", name="tsk_ab12cd34")
    act, _ = console.route("what is the process now", m, _deps())
    assert act.kind == "guide"
