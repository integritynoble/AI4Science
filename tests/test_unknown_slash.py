"""`/<name>` switches to whatever that name is — spec, roster agent, or task.

Typing `/sarsi-worker` in a live session did not switch anything and did not say
so. It fell through to the LLM as ordinary text, the agent treated it as an
instruction and went off reading that worker's task folder, and the user
believed they had switched. The old behaviour was deliberate:

    if not handled:
        # Unknown slash — fall through to the LLM as literal text.
        pass

Two things were wrong underneath it.

**A slash addresses the harness.** Forwarding one silently turns a typo into a
paid turn whose output reads like an answer to a question nobody asked.

**And `sarsi-worker` was genuinely unreachable from the REPL.** `/do` and
`/tasks` look up their sarsi worker BY THE CHAT AGENT'S NAME, and there is no
chat spec called `sarsi-worker` — so no sequence of existing commands could aim
them at it. `/agent sarsi-worker` fails too. The name had nowhere to go.

**Two agents are called `work`, and telling them apart is the point.** One is a
chat spec — the original in-process ai4science agent, which answers in your
session: ask it for a GAP-TV implementation and it writes one, there and then.
The other is a sarsi roster agent, which holds tasks and drives Claude Code
sessions. `/work` has to say which it did.
"""
import pytest

from ai4science.harness import repl


# ── what counts as an attempt at all ──────────────────────────────────

@pytest.mark.parametrize("line", ["/sarsi-worker", "/agents", "/Model",
                                  "/tsk_849fc52a90", "/do_the_thing"])
def test_a_bare_word_after_the_slash_is_an_attempt(line):
    assert repl.looks_like_command(line) is True


@pytest.mark.parametrize("line", [
    "/home/grace/x is missing",
    "/etc/passwd contains root",
    "/tmp/live-social/post1.md",
])
def test_but_a_path_is_a_sentence(line):
    """The line this must not cross. A user quoting a path should not have to
    escape it, and refusing these would be worse than the bug being fixed."""
    assert repl.looks_like_command(line) is False


@pytest.mark.parametrize("line", ["/", "/ how are you", "/2 of the cases"])
def test_and_a_lone_slash_or_a_number_is_not(line):
    assert repl.looks_like_command(line) is False


# ── what a name resolves to ───────────────────────────────────────────

def test_a_chat_spec_resolves_to_the_chat_agent():
    kind, _ = repl.resolve_name("research")
    assert kind == "spec"


def test_a_roster_agent_with_no_spec_resolves_to_the_roster():
    """The one that had nowhere to go. `sarsi-worker` holds tasks and drives
    sessions; there is no chat spec of that name."""
    kind, _ = repl.resolve_name("sarsi-worker")
    assert kind == "roster"


def test_a_task_id_resolves_to_a_task():
    kind, _ = repl.resolve_name("tsk_849fc52a90")
    assert kind == "task"


def test_a_name_that_is_both_says_so_rather_than_choosing(monkeypatch):
    """`work` is a chat spec AND a sarsi roster agent. Picking one silently is
    how the confusion started; naming both is the fix.

    The roster is INJECTED. My first version read this machine's registry and
    asserted `work` was in it — true on the account I had been testing, false
    on this one, which has a different roster entirely. A test that passes
    because of whose registry is on the box is testing the box.
    """
    monkeypatch.setattr(repl, "_roster_agents", lambda: {"work", "sarsi-worker"})
    kind, detail = repl.resolve_name("work")
    assert kind == "both"
    assert "chat" in detail.lower() and "roster" in detail.lower()


def test_a_command_wins_over_everything():
    """`/agent` is a command, whatever else might share the word."""
    kind, _ = repl.resolve_name("agent")
    assert kind == "command"


def test_and_a_name_nobody_knows_is_unknown():
    kind, _ = repl.resolve_name("xyzzy")
    assert kind == "unknown"


# ── what it says ──────────────────────────────────────────────────────

def test_an_unknown_name_is_named_and_nothing_is_sent():
    msg = repl.slash_answer("/xyzzy")
    assert "/xyzzy" in msg
    assert "not sent" in msg.lower()


def test_a_near_miss_is_offered_the_real_command():
    assert "/agent" in repl.slash_answer("/agnet")


def test_the_roster_answer_tells_you_what_you_just_switched_to():
    msg = repl.slash_answer("/sarsi-worker")
    assert "sarsi-worker" in msg
    assert "/do" in msg or "task" in msg.lower()


def test_the_ambiguous_answer_separates_the_two_works(monkeypatch):
    """It must distinguish the agent that ANSWERS from the agent that
    DELEGATES, because that is the whole difference."""
    monkeypatch.setattr(repl, "_roster_agents", lambda: {"work", "sarsi-worker"})
    msg = repl.slash_answer("/work").lower()
    assert "chat" in msg and "roster" in msg
    assert "/agent work" in msg


def test_nothing_here_raises_on_a_machine_with_no_registry(monkeypatch):
    """The REPL must survive a box that never ran `sarsi init`. Every failure
    in this path is a returned string; raising would drop the session the owner
    is standing in."""
    from ai4science.harness.agents.sarsi import registry as reg

    def _boom(*a, **k):
        raise reg.ConfigError("no registry")
    monkeypatch.setattr(reg, "load", _boom)
    assert repl.resolve_name("sarsi-worker")[0] in ("roster", "unknown")
    assert repl.slash_answer("/sarsi-worker")


# ── and the route it names actually exists ────────────────────────────

def test_the_verb_the_message_suggests_is_really_wired():
    """The message says `/<roster> do <goal>`. Suggesting a command that does
    not exist would be its own defect — a help string that sends the reader
    somewhere the code does not go."""
    handled, msg = repl._dispatch_slash("/sarsi-worker tasks", {"agent": "research"})
    assert handled is True
    assert "sarsi-worker" in msg


def test_a_roster_name_with_no_verb_explains_itself():
    handled, msg = repl._dispatch_slash("/sarsi-worker", {"agent": "research"})
    assert handled is True
    assert "/sarsi-worker do" in msg


def test_an_unknown_name_is_still_not_handled_here():
    """It belongs to the loop, which prints the refusal and stops. The
    dispatcher saying "handled" would swallow it silently."""
    handled, _ = repl._dispatch_slash("/xyzzy", {"agent": "research"})
    assert handled is False


# ── /task lists everything; /tsk_… goes in guided ─────────────────────

def test_task_singular_lists_across_every_agent():
    """`/tasks` is one agent's board — the chat agent's. `/task` is the whole
    machine, which is what an owner who has just been handed a task id wants."""
    handled, msg = repl._dispatch_slash("/task", {"agent": "research"})
    assert handled is True
    assert isinstance(msg, str) and msg


def test_a_task_id_opens_it_in_guided_mode():
    """Guided is the mode where the owner's word goes in AHEAD of the worker's.
    Entering by id is how you get there from a task name you were just given."""
    handled, msg = repl._dispatch_slash("/tsk_nosuch", {"agent": "research"})
    assert handled is True
    assert "tsk_nosuch" in msg


def test_and_names_the_way_into_the_real_session():
    """Guided steers from outside; interact is the tmux session itself. A task
    view that does not say how to get into the session leaves the owner at the
    edge of the thing they asked to enter."""
    from ai4science.harness.agents.sarsi import registry as reg
    try:
        config = reg.load()
    except Exception:
        import pytest as _p
        _p.skip("no registry on this machine")
    for a in config.agents.values():
        for t in _tasks_of(config, a):
            msg = repl.task_view(config, a, t)
            assert "tmux attach" in msg or "no session" in msg.lower()
            return


def _tasks_of(config, agent):
    from ai4science.harness.agents.sarsi import task as tsk
    try:
        return tsk.all_of(config, agent)
    except Exception:
        return []
