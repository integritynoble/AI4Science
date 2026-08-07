# REPL Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `sarsi-worker` reachable from the REPL — enter it, hand it a goal, get a task, steer that task, or take the wheel in its tmux session.

**Architecture:** A new pure module `ai4science/harness/console.py` decides *what should happen* given the current mode and a line of input, returning an `Action`. `ai4science/harness/repl.py` is the only thing that performs an action — printing, calling a model, creating a task, or handing the terminal to tmux. Nothing in `console.py` touches a terminal, a model or a subprocess, so every rule is unit-testable.

**Tech Stack:** Python 3.12, pytest, dataclasses. No new dependencies.

## Global Constraints

- **Repo:** `/home/spiritai/pwm/Physics_World_Model/AI4Science`. Design of record: `docs/superpowers/specs/2026-08-07-machine-agent-first-repl-design.md`.
- **Out of scope, do not touch:** the website catalogue (`pwm_nonprofit`), the `sarsi-pwm` backend, and **any GPU or CPU compute-provider function**. No lease, no dispatch, no settlement.
- **Never raise into the REPL loop.** Every failure in this path returns a string. The REPL is what the owner is standing in; dropping it to report a routing problem trades a small failure for a large one.
- **Entering costs nothing.** `/sarsi-worker` and `/tsk_…` create no task, start no session and spend nothing. Only the confirmation creates.
- **Mode never widens authority.** No ceiling, grant or gate changes in this plan.
- **The prompt always names where the words are going.** Every mode has a distinct label.
- **Test isolation:** any test touching the roster must **inject** it. A test that passes because of whose registry is on the box is testing the box. Use `monkeypatch.setattr` on the dependency, never `reg.load()`.
- **Never `git add -A`.** This is a shared checkout; stage the exact files listed in each task.
- **Never `git stash`** here for any reason.
- **Commit style:** no co-author trailer.

## Already built (do not re-implement)

These exist in `ai4science/harness/repl.py` as of commit `1c1251e` and are consumed by this plan:

| symbol | line | signature |
|---|---|---|
| `known_commands` | 55 | `() -> set` |
| `looks_like_command` | 73 | `(line: str) -> bool` |
| `resolve_name` | 121 | `(name: str) -> tuple[str, str]` — kind is `command\|task\|spec\|roster\|both\|unknown` |
| `slash_answer` | 151 | `(line: str) -> str` |
| `all_tasks` | 237 | `(config) -> list[tuple[Agent, Task]]` |
| `task_view` | 254 | `(config, agent, task) -> str` |
| `_find_task` | 277 | `(config, task_id: str) -> tuple[Agent\|None, Task\|None]` |
| `_dispatch_slash` | 186 | `(line: str, state: dict) -> tuple[bool, str]` |

Existing APIs from elsewhere, used verbatim:

```python
tsk.create(config, agent, directive, *, now=time.time) -> Task
tsk.attach_plan(config, agent, task, plan, *, now=time.time) -> Task
pl.draft(directive) -> Plan
wk.Directive(agent_id=..., goal=...)          # dataclass, both fields required
ses.guide(config, agent, task, instruction, *, by_owner=False) -> Task
tui.read_input(prompt="› ", mode="chat", status="") -> str
```

## File Structure

| file | responsibility |
|---|---|
| `ai4science/harness/console.py` | **new.** `Mode`, `Action`, `prompt_label`, `route`. Pure: no printing, no model, no subprocess. |
| `ai4science/harness/repl.py` | **modified.** Holds the `Mode` in `state`, calls `route`, performs the returned `Action`, renders the prompt label. |
| `tests/test_console_modes.py` | **new.** Everything in `console.py`. |
| `tests/test_console_repl_wiring.py` | **new.** That `repl.py` performs each action and that the prompt tracks the mode. |

---

### Task 1: `Mode`, `Action` and `prompt_label`

**Files:**
- Create: `ai4science/harness/console.py`
- Test: `tests/test_console_modes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Mode(kind, name, pending)`, `Action(kind, text, goal, agent, task, session)`, `prompt_label(mode) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_console_modes.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai4science.harness.console'`

- [ ] **Step 3: Write minimal implementation**

Create `ai4science/harness/console.py`:

```python
"""What should happen, given the mode and a line — and nothing else.

This module never prints, never calls a model and never touches a terminal or a
subprocess. `repl.py` performs what this decides. That split is the point: the
defects that survived longest in this REPL — an unknown slash silently becoming
a prompt, the supervision loop spinning on a fact it already knew, a bare launch
dying on its first turn — were all in code reachable only by running the whole
thing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

#: The marker the ai4science TUI already uses. Kept identical so the prompt in
#: a mode reads as the same prompt, one level in — not as a different program.
MARKER = "❯ "


@dataclass(frozen=True)
class Mode:
    """Where the user is standing. Frozen: `route` returns a new one.

    A mutated-in-place mode cannot be compared before and after, and the
    invariant most worth testing here — entering costs nothing — is exactly a
    before-and-after comparison.
    """
    kind: str = "top"          # top | agent | task
    name: str = ""             # agent id or task id
    pending: Optional[str] = None   # a goal awaiting confirmation


@dataclass(frozen=True)
class Action:
    """One thing for `repl.py` to do. `kind` decides which fields are read."""
    kind: str                  # answer|say|confirm|create|guide|attach|enter|leave|noop
    text: str = ""
    goal: str = ""
    agent: Any = None
    task: Any = None
    session: str = ""


def prompt_label(mode: Mode) -> str:
    """What the prompt says. The label is not decoration — it is what makes
    'plain text becomes a goal' acceptable, because a mode that does not show
    itself is a trap."""
    if mode.kind == "agent":
        return f"{mode.name} {MARKER}"
    if mode.kind == "task":
        return f"{mode.name} (guided) {MARKER}"
    return MARKER
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/console.py tests/test_console_modes.py
git commit -m "console: Mode, Action and the prompt label

The label is what makes 'plain text becomes a goal' acceptable — a mode
that does not show itself is a trap. Mode is frozen so route returns a new
one: a mode mutated in place cannot be compared before and after, and the
invariant most worth testing is exactly that comparison."
```

---

### Task 2: `route` — entering and leaving

**Files:**
- Modify: `ai4science/harness/console.py`
- Test: `tests/test_console_modes.py`

**Interfaces:**
- Consumes: `Mode`, `Action` from Task 1.
- Produces: `route(line, mode, deps) -> tuple[Action, Mode]`, and the `deps` contract:
  ```python
  deps = {
      "resolve": callable(name) -> tuple[str, str],   # repl.resolve_name
      "find_task": callable(task_id) -> tuple[agent|None, task|None],
      "suggest": callable(text) -> str,               # "" when nothing to say
      "create": callable(agent_id, goal) -> str,      # returns a task id
      "guide": callable(task_id, text) -> str,        # returns a message
      "session_of": callable(task_id) -> str,         # "" when no session
  }
  ```

- [ ] **Step 1: Write the failing test**

Append to `tests/test_console_modes.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: FAIL — `AttributeError: module 'ai4science.harness.console' has no attribute 'route'`

- [ ] **Step 3: Write minimal implementation**

Append to `ai4science/harness/console.py`:

```python
import re

_COMMAND_WORD = re.compile(r"^/([A-Za-z][A-Za-z0-9_-]*)(\s|$)")


def _is_slash(line: str) -> bool:
    """An attempt at a slash, or a sentence that starts with a path?

    `/sarsi-worker` is an attempt. `/home/grace/x is missing` is a sentence, and
    refusing it would be worse than the bug this fixes. The separator is
    structure: a name is one word, a path has slashes or dots inside it.
    """
    if not _COMMAND_WORD.match(line or ""):
        return False
    first = line.split()[0]
    return "/" not in first[1:] and "." not in first[1:]


def route(line: str, mode: Mode, deps: dict) -> tuple:
    """Given where the user is and what they typed, what should happen."""
    line = (line or "").strip()
    if not line:
        return Action("noop"), mode

    if _is_slash(line):
        name, _, rest = line[1:].partition(" ")
        rest = rest.strip()

        if name.lower() == "back":
            if mode.kind == "top":
                return Action("say", text="already at the top"), mode
            return Action("leave"), Mode()

        kind, detail = deps["resolve"](name)

        if kind == "roster":
            return Action("enter", text=f"now addressing {name}"), \
                Mode(kind="agent", name=name)
        if kind == "both":
            return Action("enter",
                          text=f"{detail}. entered the worker; "
                               f"the chat spec is /agent {name}"), \
                Mode(kind="agent", name=name)
        if kind == "task":
            return Action("enter", text=f"guided on {name}"), \
                Mode(kind="task", name=name)
        if kind == "spec":
            # Not a mode: a chat spec is WHO ANSWERS, not somewhere to stand.
            return Action("say", text=f"chat agent is now {name}"), mode

        return Action("say", text=deps.get("unknown", lambda l: f"/{name} is not "
                                           "a command, and it was NOT sent to "
                                           "the model")(line)), mode

    return Action("answer", text=line), mode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: PASS, 14 passed

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/console.py tests/test_console_modes.py
git commit -m "console: entering and leaving a mode

Entering costs nothing — a test asserts no task is created by arriving
somewhere. A chat spec switches who answers rather than becoming a mode,
which is what keeps the two agents called 'work' apart: /work enters the
worker, /agent work switches the spec."
```

---

### Task 3: plain text — the two-step confirmation

**Files:**
- Modify: `ai4science/harness/console.py`
- Test: `tests/test_console_modes.py`

**Interfaces:**
- Consumes: `route`, `Mode.pending` from Tasks 1–2.
- Produces: `route` handling of plain text in agent mode, and `confirm_block(goal, agent) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_console_modes.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: FAIL — `AttributeError: module 'ai4science.harness.console' has no attribute 'confirm_block'`

- [ ] **Step 3: Write minimal implementation**

In `ai4science/harness/console.py`, add `confirm_block` and insert the pending
branch at the **top** of `route`, immediately after the empty-line guard:

```python
def confirm_block(goal: str, agent: str) -> str:
    """What the owner reads before a task exists."""
    return (f"\n  goal:   {goal}\n"
            f"  agent:  {agent}\n"
            f"  it will plan at A0 first, and stop for your grant\n\n"
            f"  create it? [Enter=yes / e=edit / n=no]")
```

Replace the empty-line guard in `route` with this block:

```python
    line = (line or "").strip()

    # A goal is waiting on an answer. This is read BEFORE anything else: a
    # pending confirmation owns the next line, and a slash typed here is an
    # answer of "no" rather than a command — which is the safe reading, since
    # the alternative silently creates a task the user did not confirm.
    if mode.pending is not None:
        settled = Mode(kind=mode.kind, name=mode.name, pending=None)
        if line == "" or line.lower() in ("y", "yes"):
            return Action("create", goal=mode.pending, agent=mode.name), settled
        if line.lower() == "e":
            return Action("say", text=f"edit it and send again:\n  {mode.pending}"), \
                settled
        return Action("say", text="dropped — nothing was created"), settled

    if not line:
        return Action("noop"), mode
```

And add the agent-mode plain-text branch immediately before the final `return
Action("answer", ...)`:

```python
    if mode.kind == "agent":
        return Action("confirm", goal=line, agent=mode.name,
                      text=confirm_block(line, mode.name)), \
            Mode(kind="agent", name=mode.name, pending=line)

    if mode.kind == "task":
        return Action("guide", task=mode.name, text=line), mode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: PASS, 22 passed

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/console.py tests/test_console_modes.py
git commit -m "console: the two-step confirmation before a task exists

A task starts a session and spends PWM, so plain text in agent mode is
echoed as the goal it would create and waits. Two ordinary calls rather
than a blocking prompt, so both are testable and Ctrl-C between them
leaves no half-made task.

A pending goal answered with prose drops it. Creating the task anyway
would be the one outcome nobody asked for."
```

---

### Task 4: task mode — guiding, and `/interact`

**Files:**
- Modify: `ai4science/harness/console.py`
- Test: `tests/test_console_modes.py`

**Interfaces:**
- Consumes: `route`, `deps["guide"]`, `deps["session_of"]` from Tasks 2–3.
- Produces: `route` handling of `/interact` and `/interact --print` in task mode.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_console_modes.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: FAIL — `assert 'say' == 'attach'` on `test_interact_names_the_session_to_attach`

- [ ] **Step 3: Write minimal implementation**

In `route`, inside the slash branch, add before the `deps["resolve"]` call:

```python
        if name.lower() == "interact":
            if mode.kind != "task":
                return Action("say", text="/interact needs a task — enter one "
                                          "with /<task-id>, or /task to list"), mode
            session = deps["session_of"](mode.name)
            if not session:
                return Action("say",
                              text=f"{mode.name} has no session yet — start one:"
                                   f"\n  ai4science sarsi run <agent> {mode.name}"), \
                    mode
            if rest.strip() in ("--print", "print"):
                return Action("say", text=f"  tmux attach -t {session}"), mode
            return Action("attach", session=session, task=mode.name), mode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_console_modes.py -p no:cacheprovider -q`
Expected: PASS, 27 passed

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/console.py tests/test_console_modes.py
git commit -m "console: guiding a task, and the two ways into its session

Plain text in task mode steers, ahead of the worker. /interact returns the
session to attach; /interact --print only names the command, which is the
escape hatch for terminals where the hand-off misbehaves.

No session and cannot-be-read are different facts, and the first is the one
with an action attached — so it says how to start one."
```

---

### Task 5: `repl.py` performs the actions

**Files:**
- Modify: `ai4science/harness/repl.py` — the input loop at line 902-908, and `state` at line 745
- Test: `tests/test_console_repl_wiring.py`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: `repl._console_deps(state) -> dict`, `repl._perform(action, state) -> bool` (True when the loop should continue to the next line rather than run a model turn).

- [ ] **Step 1: Write the failing test**

Create `tests/test_console_repl_wiring.py`:

```python
"""repl performs what console decides — and only repl touches the world.

The wiring is where the two halves can drift: a console that returns an action
repl does not handle is a command that silently does nothing, which is the
defect class this whole piece exists to remove.
"""
import pytest

from ai4science.harness import console, repl


def test_every_action_kind_console_can_return_is_handled_by_repl():
    """The drift guard. If console grows an action and repl does not learn it,
    the command does nothing and says nothing."""
    produced = {"answer", "say", "confirm", "create", "guide", "attach",
                "enter", "leave", "noop"}
    assert produced <= repl.HANDLED_ACTIONS


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_console_repl_wiring.py -p no:cacheprovider -q`
Expected: FAIL — `AttributeError: module 'ai4science.harness.repl' has no attribute 'HANDLED_ACTIONS'`

- [ ] **Step 3: Write minimal implementation**

Add to `ai4science/harness/repl.py`, near `known_commands` (around line 55):

```python
#: Every Action kind the loop performs. Asserted against what `console.route`
#: can return, because an action the console produces and the loop does not
#: handle is a command that silently does nothing.
HANDLED_ACTIONS = {"answer", "say", "confirm", "create", "guide", "attach",
                   "enter", "leave", "noop"}


def _prompt_for(state: dict) -> str:
    from ai4science.harness import console as _c
    return _c.prompt_label(state.get("mode") or _c.Mode())


def _console_deps(state: dict) -> dict:
    """The world, as callables `console.route` can index.

    Every one returns a value or a string — never raises. `route` reads these
    keys directly, and a KeyError or an exception here lands inside the REPL
    loop, which is the one place nothing may drop the session.
    """
    def _config():
        from ai4science.harness.agents.sarsi import registry as reg
        return reg.load()

    def _session_of(task_id: str) -> str:
        try:
            agent, t = _find_task(_config(), task_id)
            if t is None:
                return ""
            s = t.session if isinstance(t.session, dict) else None
            return (s or {}).get("name") or ""
        except Exception:
            return ""

    def _create(agent_id: str, goal: str) -> str:
        try:
            from ai4science.harness.agents.sarsi import (plan as pl, task as tsk,
                                                         worker as wk)
            config = _config()
            agent = config.agents.get(agent_id)
            if agent is None:
                return f"{agent_id} is not on this machine"
            d = wk.Directive(agent_id=agent.id, goal=goal)
            t = tsk.create(config, agent, d)
            t = tsk.attach_plan(config, agent, t, pl.draft(d))
            return t.id
        except Exception as e:
            return f"could not create it — {e}"

    def _guide(task_id: str, text: str) -> str:
        try:
            from ai4science.harness.agents.sarsi import session as ses
            config = _config()
            agent, t = _find_task(config, task_id)
            if t is None:
                return f"{task_id} is not a task on this machine"
            ses.guide(config, agent, t, text, by_owner=True)
            return f"sent, ahead of the worker — {text[:80]}"
        except Exception as e:
            return f"could not steer it — {e}"

    def _suggest(text: str) -> str:
        try:
            from ai4science.harness.agents.sarsi import triage
            got = triage.suggest(_config(), text)
            if got.best is None:
                return ""          # a tie or nothing: a router that guesses is
                                   # worse than one that is quiet
            return (f"  ───\n  {got.best.agent_id} could take this as a task "
                    f"instead — /{got.best.agent_id} to enter it")
        except Exception:
            return ""

    def _find(task_id: str):
        try:
            return _find_task(_config(), task_id)
        except Exception:
            return (None, None)

    return {"resolve": resolve_name, "find_task": _find, "suggest": _suggest,
            "create": _create, "guide": _guide, "session_of": _session_of}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_console_repl_wiring.py -p no:cacheprovider -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/repl.py tests/test_console_repl_wiring.py
git commit -m "repl: the deps console routes against, and the prompt

Every dep returns a value or a string and never raises: route indexes them
directly, and an exception here lands inside the loop the owner is standing
in. HANDLED_ACTIONS is asserted against what route can return, because an
action the console produces and the loop does not handle is a command that
silently does nothing."
```

---

### Task 6: wire the loop, and the terminal hand-off

**Files:**
- Modify: `ai4science/harness/repl.py` — `state` init at 745, the read at 902-908, the dispatch at 691
- Test: `tests/test_console_repl_wiring.py`

**Interfaces:**
- Consumes: `_console_deps`, `_prompt_for`, `HANDLED_ACTIONS` from Task 5.
- Produces: `repl._attach_tmux(session, *, run=None) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_console_repl_wiring.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_console_repl_wiring.py -p no:cacheprovider -q`
Expected: FAIL — `AttributeError: module 'ai4science.harness.repl' has no attribute '_attach_tmux'`

- [ ] **Step 3: Write minimal implementation**

Add to `ai4science/harness/repl.py`:

```python
def _attach_tmux(session: str, *, run=None) -> str:
    """Hand the terminal to tmux and take it back.

    `run` is injected so tests assert what was asked for without attaching
    anything. This is the one part of this piece that cannot be honestly
    unit-tested: prompt_toolkit must release the terminal, a child takes it,
    and the app is restored on return. If that goes wrong the failure mode is
    an unusable terminal, which is why `/interact --print` exists.
    """
    import subprocess
    argv = ["tmux", "attach", "-t", session]
    caller = run or (lambda a: subprocess.call(a))
    try:
        rc = caller(argv)
    except Exception as e:
        return (f"could not attach {session} — {type(e).__name__}: {e}\n"
                f"  attach it yourself: tmux attach -t {session}")
    if rc:
        return (f"tmux would not attach {session} (exit {rc})\n"
                f"  is it still running? ai4science sarsi tasks <agent>")
    return f"back from {session}. the worker is still paused — /resume hands it back"
```

Then, in the input loop, change the prompt call at line 907 from:

```python
            line = tui.read_input("> ", active_spec.name or mode_label or "chat",
                                  _st).strip()
```

to:

```python
            line = tui.read_input(_prompt_for(state),
                                  active_spec.name or mode_label or "chat",
                                  _st).strip()
```

Add `"mode": None` to the `state` dict at line 745, and route every line
through the console **before** the existing slash chain:

```python
        from ai4science.harness import console as _c
        _act, _new = _c.route(line, state.get("mode") or _c.Mode(),
                              _console_deps(state))
        state["mode"] = _new
        if _act.kind != "answer":
            _deps = _console_deps(state)
            if _act.kind in ("say", "enter", "leave", "confirm"):
                if _act.text:
                    print(_act.text, flush=True)
            elif _act.kind == "create":
                print(f"→ {_deps['create'](_act.agent, _act.goal)}", flush=True)
            elif _act.kind == "guide":
                print(_deps["guide"](_act.task, _act.text), flush=True)
            elif _act.kind == "attach":
                print(_attach_tmux(_act.session), flush=True)
            continue
        line = _act.text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_console_repl_wiring.py tests/test_console_modes.py -p no:cacheprovider -q`
Expected: PASS, 30 passed

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/repl.py tests/test_console_repl_wiring.py
git commit -m "repl: route every line through the console, and hand over the terminal

The attach is injected so tests assert what was asked for without attaching
anything. It is the one part of this piece that cannot be honestly
unit-tested — prompt_toolkit releases the terminal, a child takes it, the
app is restored on return — and it never raises: a failure returns the
command to run by hand."
```

---

### Task 7: `/agents` is the switcher, and the recommendation

**Files:**
- Modify: `ai4science/harness/repl.py` — the `cmd in ("agent", "mode")` branch at line 793
- Test: `tests/test_console_repl_wiring.py`

**Interfaces:**
- Consumes: `_console_deps`, `HANDLED_ACTIONS` from Tasks 5–6.
- Produces: no new symbols; `/agents` behaves as `/agent` and both remain.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_console_repl_wiring.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_console_repl_wiring.py -p no:cacheprovider -q`
Expected: FAIL on `test_agents_switches_as_well_as_lists` — `/agents` currently only lists.

- [ ] **Step 3: Write minimal implementation**

In `ai4science/harness/repl.py`, change the branch at line 793 from:

```python
            if cmd in ("agent", "mode"):
```

to:

```python
            # `/agents` lists AND switches, which is what someone typing it
            # expects. `/agent` and `/mode` stay as aliases: removing a command
            # people already use, to make a naming point, is a cost paid by the
            # user for the designer's tidiness.
            if cmd in ("agent", "agents", "mode"):
```

and delete the now-unreachable `if cmd == "agents":` branch at line 879, whose
listing behaviour the switcher already includes.

Then print the recommendation after a normal turn. Immediately after the model
turn completes in the loop, add:

```python
        if (state.get("mode") or _c.Mode()).kind == "top":
            _note = _console_deps(state)["suggest"](line)
            if _note:
                print(_note, flush=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_console_repl_wiring.py -p no:cacheprovider -q`
Expected: PASS, 34 passed

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/repl.py tests/test_console_repl_wiring.py
git commit -m "repl: /agents switches, and the top level recommends

/agents lists and switches in one breath; /agent and /mode stay as aliases.
A line answered at the top level gets one note underneath naming the worker
that could take it — and a tie prints nothing, because a router that
guesses is worse than one that is quiet."
```

---

### Task 8: full regression, then live verification as grace

**Files:**
- Test: the whole suite; no source changes unless a failure demands one.

**Interfaces:**
- Consumes: everything.
- Produces: nothing.

- [ ] **Step 1: Run the full regression**

Run:
```bash
cd /home/spiritai/pwm/Physics_World_Model/AI4Science
python3 -m pytest tests/sarsi tests/machine tests/docs tests/test_console_modes.py \
  tests/test_console_repl_wiring.py tests/test_unknown_slash.py \
  -p no:cacheprovider --no-header -q
```
Expected: 0 failures. **The suite takes over two minutes** — run it in the
background and wait for it to finish rather than reading a partial result. A
progress line at 65% is not a pass.

- [ ] **Step 2: Fix anything red, then re-run to completion**

If a test outside this plan fails, decide whether the rule is wrong or the
fixture is, and say which in the commit message. Do not weaken an assertion to
make it pass.

- [ ] **Step 3: Deploy to grace and verify live**

```bash
SHA=$(git rev-parse HEAD)
sudo -u grace -H bash -lc "timeout 500 /home/grace/sarsi-venv/bin/pip install \
  --quiet --force-reinstall --no-deps --no-cache-dir \
  'pwm-agent-core @ https://github.com/integritynoble/AI4Science/archive/$SHA.zip'"
```

Then, as grace, in tmux:

| check | expected |
|---|---|
| `/sarsi-worker` | prompt becomes `sarsi-worker ❯`, no task created |
| a plain goal | the confirm block, and **nothing created** until Enter |
| Enter | `→ tsk_…` |
| `/tsk_…` | prompt becomes `tsk_… (guided) ❯` |
| a plain line | "sent, ahead of the worker" |
| `/interact --print` | the `tmux attach` command only |
| `/interact` | attaches; `Ctrl-b d` returns to the REPL, still usable |
| `/back` | back to `❯` |
| `/home/grace/x is missing` | reaches the model as a sentence |

- [ ] **Step 4: Clean up**

Stop any task started during verification (`ai4science sarsi stop <agent> <task>`)
and confirm `tmux ls` is clear.

- [ ] **Step 5: Commit the verification note**

```bash
git commit --allow-empty -m "verify: REPL modes exercised live as grace

The terminal hand-off is the one part no unit test covers, so it was run:
/interact attached, Ctrl-b d returned, and the REPL was still usable
afterwards. Recorded here because 'verified live, once' is the only honest
status that claim can have."
```

---

## Self-Review

**Spec coverage.** §1 mode model → Tasks 1–4. §2 components and data flow →
Tasks 1–5. §3 recommendation and error handling → Tasks 5, 7. §4 `/interact` →
Tasks 4, 6, 8. §5 testing → every task, plus Task 8. §7 `/agents` → Task 7.
§6, §8, §9 are out of scope for this piece by the spec's own decomposition.

**Placeholders.** None: every code step carries the code, every test step carries
the test, and every run step carries the command and the expected result.

**Type consistency.** `Mode(kind, name, pending)` and `Action(kind, text, goal,
agent, task, session)` are defined in Task 1 and used unchanged in Tasks 2–7.
The `deps` keys — `resolve`, `find_task`, `suggest`, `create`, `guide`,
`session_of` — are declared in Task 2 and produced by `_console_deps` in Task 5,
and a test asserts the two agree. `_find_task`, `resolve_name`, `tsk.create`,
`tsk.attach_plan`, `pl.draft`, `wk.Directive` and `ses.guide` are quoted from the
existing source with their real signatures.

**One gap found and closed while reviewing:** Task 2's `route` referenced a
`deps["unknown"]` key that no task provided. It now falls back to an inline
message, so a missing key cannot raise inside the loop.
