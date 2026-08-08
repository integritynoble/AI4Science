"""What should happen, given the mode and a line — and nothing else.

This module never prints, never calls a model and never touches a terminal or a
subprocess. `repl.py` performs what this decides. That split is the point: the
defects that survived longest in this REPL — an unknown slash silently becoming
a prompt, the supervision loop spinning on a fact it already knew, a bare launch
dying on its first turn — were all in code reachable only by running the whole
thing.
"""
from __future__ import annotations

import re
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
    #: The backend the pending confirmation will create with. Empty means
    #: `task.create` resolves the default — the confirmation shows the choice
    #: but must not become a second author of what the default IS.
    backend: str = ""
    #: The last substantive thing the owner said here. Kept because a line the
    #: worker could not place is usually the goal the NEXT line points at:
    #: "please create the task for me according to this goal" refers to
    #: something already on screen, and having to ask for it again is the
    #: worker failing to read what it was just told.
    recent: str = ""


@dataclass(frozen=True)
class Action:
    """One thing for `repl.py` to do. `kind` decides which fields are read."""
    kind: str                  # answer|say|confirm|create|guide|attach|enter|leave|noop
    text: str = ""
    goal: str = ""
    agent: Any = None
    task: Any = None
    session: str = ""
    backend: str = ""          # read by "create": which engine runs the task


def prompt_label(mode: Mode) -> str:
    """What the prompt says. The label is not decoration — it is what makes
    'plain text becomes a goal' acceptable, because a mode that does not show
    itself is a trap."""
    if mode.kind == "agent":
        return f"{mode.name} {MARKER}"
    if mode.kind == "task":
        return f"{mode.name} (guided) {MARKER}"
    return MARKER


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


def confirm_block(goal: str, agent: str, backend: str = "") -> str:
    """What the owner reads before a task exists."""
    from ai4science.harness.agents.sarsi import backends as _bk
    chosen = _bk.resolve(backend)
    other = next(n for n in _bk.NAMES if n != chosen)
    return (f"\n  goal:    {goal}\n"
            f"  agent:   {agent}\n"
            f"  backend: {chosen}\n"
            f"  it will plan at A0 first, and stop for your grant\n\n"
            f"  create it? [Enter=yes / e=edit / p=plan / b={other} / n=no]")


def route(line: str, mode: Mode, deps: dict) -> tuple:
    """Given where the user is and what they typed, what should happen."""
    line = (line or "").strip()

    # A goal is waiting on an answer. This is read BEFORE anything else: a
    # pending confirmation owns the next line, including a slash, which is
    # read as "no" rather than as a command — because a stray /back
    # mid-confirmation should not quietly discard a goal by a path that never
    # tells you.
    if mode.pending is not None:
        settled = Mode(kind=mode.kind, name=mode.name, pending=None)
        if line == "" or line.lower() in ("y", "yes"):
            return Action("create", goal=mode.pending, agent=mode.name,
                          backend=mode.backend), settled
        if line.lower() == "b":
            # The owner chooses the engine at the one surface every task
            # passes through. A switch re-shows the block — the choice must
            # be READ back, not trusted to have landed — and keeps the goal:
            # changing the engine is not an answer about the goal.
            from ai4science.harness.agents.sarsi import backends as _bk
            chosen = _bk.resolve(mode.backend)
            other = next(n for n in _bk.NAMES if n != chosen)
            return Action("confirm", goal=mode.pending, agent=mode.name,
                          text=confirm_block(mode.pending, mode.name, other)), \
                Mode(kind=mode.kind, name=mode.name, pending=mode.pending,
                     recent=mode.recent, backend=other)
        if line.lower() == "e":
            return Action("say", text=f"edit it and send again:\n  {mode.pending}"), \
                settled
        if line.lower() == "p":
            # The owner writes the plan. `e` edits the GOAL, which is a
            # different thing and was the only thing on offer -- the design says
            # the owner may author the plan and no surface let them.
            return Action("say", text=(
                f"write the plan yourself, then point the task at it:\n"
                f"  1. create it:  the goal stays \"{mode.pending}\"\n"
                f"  2. write a markdown plan -- phases, a `Verified when:` "
                f"line each, and a `## Permissions needed` section\n"
                f"  3. ai4science sarsi plan {mode.name} <task-id> "
                f"--set-from <your-file>.md\n"
                f"it is agreed on arrival and no session may rewrite its "
                f"criteria. Its permissions still need granting.")), settled
        if line.lower() in ("n", "no"):
            # Named, so a dropped goal is a thing the owner can read back and
            # retype. "dropped — nothing was created" said neither what was
            # dropped nor what it said.
            return Action("say", text=f"dropped — nothing was created:\n"
                                      f"  {mode.pending}"), settled
        # Anything else was never an answer to `[Enter=yes / e=edit / n=no]`.
        # It used to be read as one, refused, and DISCARDED: the owner typed a
        # whole goal at a stale confirmation and watched it vanish, twice in one
        # session. Honoured or refused, never dropped — so the pending goal is
        # abandoned OUT LOUD and the new line is routed as whatever it actually
        # is, which is usually the next goal.
        import dataclasses
        act, after = route(line, settled, deps)
        note = f"not created: {mode.pending}"
        text = f"{note}\n{act.text}" if act.text else note
        return dataclasses.replace(act, text=text), after

    if not line:
        return Action("noop"), mode

    if _is_slash(line):
        name, _, rest = line[1:].partition(" ")
        rest = rest.strip()

        if name.lower() == "back":
            if mode.kind == "top":
                return Action("say", text="already at the top"), mode
            return Action("leave"), Mode()

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

        kind, detail = deps["resolve"](name)

        if kind == "roster":
            if rest:
                return Action("answer", text=line), mode   # the old chain owns `do`/`tasks`
            return Action("enter", text=f"now addressing {name}"), \
                Mode(kind="agent", name=detail)
        if kind == "both":
            if rest:
                return Action("answer", text=line), mode   # the old chain owns `do`/`tasks`
            return Action("enter",
                          text=f"{detail}. entered the worker; "
                               f"the chat spec is /agent {name}"), \
                Mode(kind="agent", name=name.lower())
        if kind == "task":
            if rest:
                return Action("guide", task=detail, text=rest), mode
            if deps["find_task"](detail)[1] is None:
                return Action("say", text=f"{detail} is not a task on this "
                                          "machine — /task lists them"), mode
            return Action("enter", text=f"guided on {name}"), \
                Mode(kind="task", name=detail)
        if kind == "spec":
            # Not a mode: a chat spec is WHO ANSWERS, not somewhere to stand.
            # Reuse the existing switcher (`/agent <name>`) rather than
            # reimplementing it here — it does the provider-lock, session
            # rebuild and TUI-label sync that a bare `say` never touched.
            return Action("answer", text=f"/agent {name}"), mode

        if kind == "command":
            # A command the harness already owns. The console has nothing to add,
            # so it forwards the line UNCHANGED and lets the existing slash chain
            # handle it exactly as before. Returning the whole `line`, not just
            # the command word, is what keeps `/agent sarsi-worker` working.
            return Action("answer", text=line), mode

        return Action("say", text=deps.get("unknown", lambda l: f"/{name} is not "
                                           "a command, and it was NOT sent to "
                                           "the model")(line)), mode

    if mode.kind == "agent":
        from ai4science.harness.agents.sarsi import intent as _intent
        got = _intent.classify(line)

        def _remember(text: str) -> Mode:
            """Carry forward what was said, so a later back-reference resolves.

            Greetings and questions are NOT remembered: `hi` must never become
            the goal a later "make a task for this" points at.
            """
            return Mode(kind=mode.kind, name=mode.name, pending=mode.pending,
                        recent=text or mode.recent)

        if got.kind == "question":
            about = deps.get("about_self")
            if about is not None:
                from ai4science.harness.agents.sarsi import selfaware as _sa
                if _sa.is_about_self(line):
                    text = about(mode.name) or ""
                    if text:
                        return Action("say", text=text), mode
            return Action("answer",
                          text=f"{line}\n\n(to make that a task instead: "
                               f"/do {line})"), mode

        if got.kind == "greeting":
            return Action("answer",
                          text=f"{line}\n\n(to make that a task instead: "
                               f"/do {line})"), mode

        # A request to MAKE a task is not a goal, and a line this cannot place
        # is not one either. Both ask, and both say what was unclear -- the row
        # of the design's table that was missing.
        if got.kind == "meta" and mode.recent:
            # It asked for a task and pointed at a goal it did not restate ---
            # and the goal is one line up. Offering it beats asking for a
            # sentence the owner has already typed. Said out loud, because
            # filing a goal they did not type on THIS line without saying where
            # it came from is the loop putting words in their mouth.
            goal = mode.recent
            return Action("confirm", goal=goal, agent=mode.name,
                          text=(f"using what you said earlier as the goal:\n"
                                f"  {goal}\n"
                                + confirm_block(goal, mode.name))), \
                Mode(kind="agent", name=mode.name, pending=goal,
                     recent=mode.recent)

        if got.kind in ("meta", "ambiguous"):
            # Nothing to point at, or nothing placeable. Ask, and say what was
            # unclear. An ambiguous line is still worth remembering: it is
            # usually the goal the next line refers to.
            return Action("say", text=got.why), _remember(
                line if got.kind == "ambiguous" else "")

        # `got.goal`, not `line`: the framing is not part of the goal.
        # "the goal is please write X" files as "write X", instead of reading
        # back as noise in every listing thereafter.
        return Action("confirm", goal=got.goal, agent=mode.name,
                      text=confirm_block(got.goal, mode.name)), \
            Mode(kind="agent", name=mode.name, pending=got.goal,
                 recent=got.goal)

    if mode.kind == "task":
        return Action("guide", task=mode.name, text=line), mode

    return Action("answer", text=line), mode


@dataclass(frozen=True)
class MenuEntry:
    """One row of the `/agents` picker."""
    name: str
    kind: str          # "worker" — entering it; "spec" — switching this repl
    label: str


def agent_menu(*, core, specific, workers, active: str):
    """Rows for `/agents`, workers first.

    Two registries meet here. Chat SPECS are what this repl runs; sarsi WORKERS
    hold tasks and drive sessions. The distinction is real and it is not the
    owner's problem — they opened `/agents`, read sixteen specs, and could not
    find `sarsi-worker`, the agent the machine is built around.

    So: one door. Workers first, because that is what the owner reaches for,
    and each row says which act it performs — selecting a worker ENTERS it,
    selecting a spec SWITCHES this repl. Same list, two verbs, said out loud.

    `core`, `specific` and `workers` are each `(name, description)` pairs, so
    this stays a pure function over two registries it does not import.
    """
    rows = []
    for name, desc in workers:
        rows.append(MenuEntry(name, "worker",
                              f"{name} — {desc}  [worker · enter it]"))
    for name, desc in core:
        rows.append(MenuEntry(name, "spec", f"{name} — {desc}"
                              + ("  ← current" if name == active else "")))
    for name, desc in specific:
        rows.append(MenuEntry(name, "spec", f"{name} — {desc}"
                              + ("  ← current" if name == active else "")
                              + "  [domain]"))
    return rows
