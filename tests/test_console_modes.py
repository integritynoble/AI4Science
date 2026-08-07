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
