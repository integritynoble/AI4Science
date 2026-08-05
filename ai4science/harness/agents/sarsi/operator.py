"""The supervision pass — `V`, `AN`, `SP`, `EC`, `S`, in that order.

`AN` and `SP` came out of the first live run, which had to be nursed by hand:
Claude Code's folder-trust prompt swallowed the kickoff, and the kickoff then sat
typed-but-unsubmitted at the `❯`. Both were specified in the session loop and
neither was implemented.

One pass, and the order is load-bearing:

| | Check | Then |
|---|---|---|
| 1 | is there a session at all? | nothing to operate |
| 2 | is it already verified? | stand down |
| 3 | **does the owner have the wheel?** | do nothing — the operator *is* the worker |
| 4 | **is the goal already met?** | `V` — and this sits ABOVE both typing steps |
| 5 | **is a gate on screen?** | `AN` — answer it if recognised, else abstain |
| 6 | is it mid-turn? | leave it alone; queued input is normal, not stuck |
| 7 | **is it asking a question?** | answer it from the plan, or stop for the owner |
| 8 | **is a prompt stranded at the `❯`?** | `SP` — submit it, verbatim |
| 9 | otherwise | `S` — compose one instruction and type it |

Step 7 is why an unattended run is not a thing that pages you every few minutes.
An agent answers a session's question **only** from what it already holds — the
goal, the criteria, the scope, what you said — and escalates rather than guesses.
Owner facts, secrets and anything that would widen what the session may do are
never answered here.

Step 4's position is why it exists at all: in the console a session that kept
receiving typed prompts consumed every pass at the submit step, so verification
starved for **23 consecutive passes** while an already-finished session went on
being guided.

Two rules the code keeps rather than the prompt:

  * **`SP` submits verbatim.** It presses Enter. Nothing here retypes a stranded
    prompt — the composer writes a *new* instruction, it never edits one already
    typed, and merging the two would imply the agent may reword what was already
    committed to.
  * **`AN` answers from an allowlist, never a denylist.** A gate this loop does
    not recognise is left for the owner and reported. A guessed Yes is the one
    mistake here that nobody would notice until afterwards.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ai4science.harness.agents.sarsi import ledger, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Mid-turn, and nothing weaker. `esc to interrupt` is shown by Claude Code
#: only while a turn is actually running, which makes it the one reliable
#: signal. A bare `✻` is not: it also heads FINISHED status lines — abraham's
#: run sat at `✻ Brewed for 35s` and the loop reported `busy` forever at a
#: session that had already stopped. A glyph is not a state.
_BUSY = ("esc to interrupt",)

#: Gates this loop is allowed to answer, and the option to press. Recognised by
#: a phrase that only appears on that gate. Anything else waits for the owner.
_KNOWN_GATES = (
    (re.compile(r"Is this a project you created or one you trust", re.I), "1",
     "the folder-trust prompt, for a folder this worker created"),
)

#: The wider option — "and don't ask again" — is never pressed.
_STANDING_OPTION = re.compile(r"don'?t ask again|and stop asking", re.I)

_GATE_SHAPE = re.compile(r"^\s*❯?\s*1\.\s+\S", re.M)
# `[^\S\r\n]` is "whitespace that is not a line break": it must not swallow the
# newline (a bare `❯` would then "find" the next line and submit an empty
# prompt), and it must accept U+00A0 — Claude Code's TUI separates the `❯` from
# the text with a NON-BREAKING space, which a plain `[ \t]` misses. The first
# operator run reported `idle` at a visibly stranded screen for exactly that.
_PROMPT_LINE = re.compile(r"^❯[^\S\r\n]+(?P<text>\S.*)$", re.M)


@dataclass(frozen=True)
class Action:
    kind: str            # answered | submitted | abstained | busy | idle | …
    detail: str = ""


def tick(config: Config, agent: Agent, task: tsk.Task, *, pane: Any,
         acts=None, runtime: Optional[Any] = None,
         verifier: Optional[Callable[..., dict]] = None,
         model: Optional[Callable[[str], str]] = None,
         engine: Optional[str] = None, now=time.time) -> Action:
    """One supervision pass over one session, in this order:

    no session · already done · the owner has the wheel · **verify** · a gate ·
    mid-turn · a stranded prompt · steer.

    Verification sits **above** both typing steps, and that position is
    load-bearing: in the console a session that kept receiving typed prompts
    consumed every pass at the submit step, and verification starved for 23
    consecutive passes while an already-finished session went on being guided.
    """
    session = (task.session or {}).get("name")
    if not session:
        return Action("no-session")
    if task.state == tsk.VERIFIED:
        return Action("done", "the verifier has already passed this")
    if task.steering_paused:
        # Interact pauses the worker, and the operator IS the worker.
        return Action("paused", "the owner has the wheel")

    screen = pane.capture(session) or ""

    # While planning there are no criteria, and judging against none is not
    # judging. Everything ELSE in the pass still applies: a planning session
    # gets stuck on a gate or a stranded prompt exactly like any other, and a
    # session that cannot be unstuck cannot be planned. The live run for
    # abraham sat at the folder-trust prompt for six passes reporting
    # `planning`, because collection used to return before `AN` ever ran.
    planning = task.state == tsk.PLANNING

    # BEFORE anything is answered, submitted or steered: a budget enforced
    # after the next step has run is one step too late, every time.
    from ai4science.harness.agents.sarsi import budget as bdg
    spent = bdg.check(config, agent, task, acts=acts, now=now)
    if spent.over:
        # NOT `_Sender(pane)`: that can only type into a pane, and `ses.stop`
        # swallows the missing `stop` — so the task went `off` while its
        # terminal kept running, which `attention` then reported as a session
        # no task claims, holding whatever it was granted. Stopping a task must
        # take its session with it, whichever path stopped it.
        bdg.enforce(config, agent, task, acts=acts, runtime=runtime, now=now)
        return Action("over-budget", spent.why)

    # A screen this loop cannot read is a screen it must not type at. Blind
    # keystrokes are not a brief: they are input to whatever menu happens to be
    # showing, and on the ai4science TUI they walked the cursor onto "No, exit"
    # and killed the session the loop was supervising.
    from ai4science.harness.agents.sarsi import session as _ses
    if not _ses.drivable(agent.spec):
        return Action("attended",
                      f"{agent.id} runs the {agent.spec!r} interface, which "
                      f"this loop cannot read — take the wheel yourself: "
                      f"tmux attach -t {session}")

    # A task that has not been briefed yet cannot have done anything to judge.
    if task.kickoff_pending and not planning:
        from ai4science.harness.agents.sarsi import session as ses
        if not _busy(screen) and _gate(screen) is None:
            after = ses.deliver_kickoff(config, agent, task, runtime=_Sender(pane),
                                        screen=screen, now=now)
            if after.kickoff_pending:
                return Action("briefing", "waiting to see the brief land")

    if verifier is not None and not planning:
        from ai4science.harness.agents.sarsi import evidence as evd, session as ses
        # What the session LEFT BEHIND, not what its terminal was showing. A
        # live run failed here: the pane held a spinner and some narration, and
        # the verifier correctly reported it could see no evidence of the file
        # the session had in fact written.
        # Judge the phase the work is actually ON, not every criterion at
        # once. Judging all of them meant a two-phase task could never pass its
        # first phase: the evidence for phase 2 does not exist yet, so the
        # whole-task verdict was FAIL until the very last step, and each FAIL
        # was fed back as though phase 1 were wrong.
        here = tsk.earliest_incomplete(task)
        criteria = ([task.criteria[here]]
                    if here is not None and here < len(task.criteria or [])
                    else list(task.criteria or []))
        # The task's own folder unless the plan declared a working directory.
        # A live run wrote its artefacts to the declared folder and was recorded
        # UNVERIFIED because the gatherer was looking somewhere else.
        proof = evd.gather(tsk.evidence_roots(agent, task), criteria,
                           screen=screen)
        task = ses.verify(config, agent, task, verifier=verifier,
                          evidence=proof, engine=engine, runtime=_Sender(pane),
                          phase=here, now=now)
        if task.state == tsk.VERIFIED:
            return Action("verified", "the goal is met")

    # The declared working directory is what makes a delete answerable at all,
    # so a task without one never reaches the rule.
    deletes = None
    if task.work_root:
        deletes = (tsk.evidence_root(agent, task), list(task.grants or []))
    gate = _gate(screen, planning=planning, deletes=deletes)
    if gate is not None:
        answer, why = gate
        if answer is None:
            _report(config, agent, task, state="gate",
                    evidence=f"a gate this loop does not recognise: {why}", now=now)
            return Action("abstained", why)
        pane.send(session, answer)
        _report(config, agent, task, state="answered",
                evidence=f"pressed {answer} — {why}", now=now)
        return Action("answered", why)

    if _busy(screen):
        # A permission menu's cursor is not a prompt, and a live spinner means
        # queued input is normal rather than stuck.
        return Action("busy")

    # The session asked something. Answering what was asked beats typing an
    # unrelated next step over it — and beats waking the owner for a question
    # the plan already settles. A gate is checked first, above: an option menu
    # is authority, and authority is not a clarification.
    if model is not None and not planning:
        from ai4science.harness.agents.sarsi import answering as anq
        asked = anq.question_on(screen)
        if asked:
            out = anq.answer(config, agent, task, question=asked, model=model)
            if out.answer:
                pane.send(session, out.answer)
                return Action("answered-question", asked[:70])
            return Action("asks-owner", out.escalate)

    stranded = _stranded(screen)
    if stranded and stranded != task.last_submitted:
        # Submitting what is already typed beats writing something new over it.
        # Once only: text still there after Enter was never input, and pressing
        # Enter at it every pass is how a loop mistakes a suggestion for work.
        pane.key(session, "Enter")          # verbatim: nothing is retyped
        task.last_submitted = stranded
        task = tsk._touch(agent, task, now)
        _report(config, agent, task, state="submitted",
                evidence=stranded[:200], now=now)
        return Action("submitted", stranded[:80])

    if planning:
        from ai4science.harness.agents.sarsi import session as ses
        # The session is idle and can receive its first instruction now. It was
        # not given one at assign, because a session started moments earlier is
        # still booting and the text is simply lost.
        if task.kickoff_pending:
            after = ses.deliver_kickoff(config, agent, task, runtime=_Sender(pane),
                                        screen=screen, now=now)
            if after.kickoff_undelivered:
                return Action("undelivered",
                              "the session is not taking its brief — attach and "
                              "look: tmux attach -t " + session)
            if after.kickoff_pending:
                return Action("briefing", "waiting to see the brief land")
        after = ses.collect_plan(config, agent, task, runtime=_Sender(pane),
                                 now=now)
        if after.state != tsk.PLANNING:
            return Action("planned",
                          f"{len(after.criteria)} criterion(s); "
                          + (", ".join(after.awaiting) or "nothing to grant"))
        return Action("planning")

    if model is not None:
        from ai4science.harness.agents.sarsi import composer as cp
        out = cp.steer(config, agent, task, screen=screen, model=model, pane=pane)
        if out.instruction:
            _report(config, agent, task, state="steered",
                    evidence=out.instruction[:200], now=now)
            return Action("steered", out.instruction[:80])
        return Action("idle", out.note)

    return Action("idle")


class _Sender:
    """Lets `verify` feed a FAIL reason back through the same pane."""

    def __init__(self, pane: Any) -> None:
        self._pane = pane

    def send(self, name: str, text: str):
        return self._pane.send(name, text)


def run(config: Config, agent: Agent, task: tsk.Task, *, pane: Any,
        verifier: Optional[Callable[..., dict]] = None,
        model: Optional[Callable[[str], str]] = None,
        engine: Optional[str] = None,
        passes: int = 20, interval: float = 3.0, sleep=time.sleep) -> list:
    """Supervise until the goal is verified, the owner takes over, or the budget
    runs out. Stops on a verdict — it does not keep guiding a finished session."""
    seen = []
    for i in range(passes):
        action = tick(config, agent, task, pane=pane, verifier=verifier,
                      model=model, engine=engine)
        seen.append(action)
        if action.kind in ("no-session", "done", "paused", "verified"):
            break
        if i + 1 < passes:
            sleep(interval)
    return seen


# ── reading the screen ────────────────────────────────────────────────

#: The one extra gate A0 makes necessary: writing THIS task's own plan file,
#: while planning. Narrow on purpose — a blanket "allow writes while planning"
#: would make the A0 drop decorative, which is worse than not dropping it.
#: Claude Code's own first-run wizard. A fresh user account meets it before
#: anything else, and it blocks every session that user starts.
_ONBOARDING = re.compile(r"Choose the option that looks best|Syntax theme:|"
                         r"colorblind-friendly", re.I)

#: `overwrite` is not `\bwrite\b` — there is no word boundary inside it, so the
#: rule missed the wording Claude Code actually uses ("Do you want to overwrite
#: plan0.md?") and the loop abstained at the session writing the very file it
#: had been told to write. Observed live, and the same shape as the `Try "…"`
#: filter: a pattern written against assumed wording meeting the real one.
_PLAN_WRITE = re.compile(r"\b(create|write|overwrite|edit|update)\b[^\n]*"
                         r"\bplan0(_\d+)?\.md\b",
                         re.I)


def _gate(screen: str, *, planning: bool = False, deletes=None):
    """(answer, why) when a gate is on screen; (None, why) when unrecognised.

    `deletes` is `(root, granted)` when this task has a declared working
    directory — the one destructive gate that can be answered, and only under
    the conditions in `deletion.permitted`.
    """
    if not _GATE_SHAPE.search(screen):
        return None
    for pattern, answer, why in _KNOWN_GATES:
        if pattern.search(screen):
            return (answer, why)
    if deletes is not None:
        command = _gate_command(screen)
        if command and _looks_like_delete(command):
            from ai4science.harness.agents.sarsi import deletion as dl
            root, granted = deletes
            allowed, why = dl.permitted(command, root=root, granted=granted)
            # Either way this gate is now RECOGNISED: a refusal that names its
            # reason beats "an option menu this loop has no rule for", which
            # told the owner nothing about what was being asked.
            return (("1", f"a delete this task is allowed: {why}") if allowed
                    else (None, f"a delete this loop will not answer: {why}"))
    if planning and _PLAN_WRITE.search(screen):
        return ("1", "writing this task's own plan file, which is exactly what "
                     "it was asked to do")
    if planning:
        # A0 is "reads allowed, everything else asks", but the governance hook
        # gates EVERY bash — so six supervision passes in a row abstained at a
        # `find … | head` the ceiling already permits, and planning a drivable
        # task needed a human at each gate. That is the one thing an unattended
        # loop cannot supply.
        #
        # Answered only when the command is PROVABLY read-only, by the same
        # conservative classifier the harness already gates on: anything it
        # cannot prove — an unknown binary, a redirect, a command substitution —
        # falls through to the owner exactly as before.
        command = _gate_command(screen)
        if command:
            from ai4science.harness.permissions import is_read_only_bash
            if is_read_only_bash(command):
                return ("1", f"a read-only command, which A0 already allows: "
                             f"{command[:80]}")
    if _ONBOARDING.search(screen):
        # Recognised, and still not answered. Clicking through a setup wizard on
        # the owner's behalf is the guess the allowlist forbids — but a fresh
        # account meets this before it can do anything, so name it.
        return (None, "this account has not finished Claude Code's first-run "
                      "setup — run `claude` once as this user and complete it")
    return (None, "an option menu this loop has no rule for")


#: The header a Bash gate puts above the command it is asking about — Claude
#: Code writes `Bash command`, the ai4science TUI writes `$ <cmd>`.
_GATE_HEADER = re.compile(r"^(?P<indent>\s*)(Bash command|\$\s+\S.*)\s*$", re.M)

#: Prose, not shell: the one-line description a gate prints under the command.
#: Recognised by what it LACKS — no metacharacter, no path, no flag — so a
#: wrapped fragment of the real command (`f | head -50`, `f > out.txt`) is
#: never mistaken for it. Getting this wrong in the safe direction leaves the
#: description in and the gate unanswered; getting it wrong the other way would
#: judge a truncated command, so the test is deliberately strict.
_GATE_PROSE = re.compile(r"^[A-Za-z][A-Za-z0-9 ,.'\u2019]*$")


def _gate_command(screen: str) -> str:
    """The command this gate is about — and nothing else on the screen.

    This used to take every line indented two spaces above `Do you want to
    proceed`, which on a real pane is the whole conversation: the kickoff text,
    the tool output, the command, and its description, joined into one string.
    The A0 read-only rule could therefore never fire, and a live run abstained
    four times at a `find … | head` written to be answered.

    The block is found structurally instead: the gate's header, then the lines
    indented DEEPER than it, stopping where the indent returns.
    """
    head = screen.split("Do you want to proceed", 1)[0]
    matches = list(_GATE_HEADER.finditer(head))
    if not matches:
        return ""
    last = matches[-1]
    header_indent = len(last.group("indent"))
    inline = last.group(0).strip()
    lines = []
    if inline.startswith("$"):
        # the ai4science TUI puts the command on the header line itself
        lines.append(inline[1:].strip())
    for raw in head[last.end():].splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent <= header_indent:
            break                      # the block ended — `Hook …`, `A0 …`
        lines.append(raw.strip())
    if len(lines) > 1 and _GATE_PROSE.match(lines[-1]):
        lines.pop()                    # the human-readable description
    return " ".join(lines).strip()


def _looks_like_delete(command: str) -> bool:
    """Is this gate even about deleting? Cheap and deliberately loose — the
    real decision is `deletion.permitted`, which refuses by default."""
    first = command.split()[0] if command.split() else ""
    from pathlib import Path as _P
    return _P(first).name in ("rm", "unlink", "shred", "rmdir")


def _busy(screen: str) -> bool:
    low = screen.lower()
    return any(marker.lower() in low for marker in _BUSY)


#: Claude Code's own dimmed example at an EMPTY prompt — `Try "how does
#: <filepath> work?"`, `Try "fix typecheck errors"`. A captured pane renders it
#: identically to typed text, so the loop read it as a stranded prompt and
#: pressed Enter: `decisions` on the grace fleet showed two real sessions asked
#: "how does <filepath> work?" by their own supervisor.
#:
#: This first required the quote to END IN A QUESTION MARK, because the one
#: sample available when it was written was a question. The hints ROTATE and
#: most are not questions, so a later live run submitted `Try "fix typecheck
#: errors"`, and the session spent 21 steps on that instead of its goal and
#: tripped its own budget — a task ended `off` having never been told what it
#: was for. Calibrating a filter on a single observation is how that happens.
#:
#: Still matched on SHAPE and not on the word: the whole line must be `Try
#: "…"` and nothing else, so a real instruction opening with "try", or one that
#: merely contains a quote, is left alone. The residual cost is an owner who
#: types exactly `Try "…"` and leaves it stranded — they press Enter themselves,
#: which is a far smaller harm than the loop inventing a prompt.
_SUGGESTION = re.compile(r'^Try\s+"[^"]*"$', re.I)


def _stranded(screen: str) -> Optional[str]:
    """Text typed at the `❯` and left unsent.

    An empty prompt is not stranded, and neither is Claude Code's placeholder:
    submitting the tool's own hint is the loop typing into a session on nobody's
    behalf.
    """
    hits = _PROMPT_LINE.findall(screen)
    if not hits:
        return None
    text = hits[-1].strip()
    if not text or _SUGGESTION.match(text):
        return None
    return text


def _report(config: Config, agent: Agent, task: tsk.Task, *, state: str,
            evidence: str, now) -> None:
    # The rung the act was taken AT, from the live session record rather than
    # the registry — the registry says what the agent asks for, the session says
    # what it got. Without this the ledger held every autonomous act and not the
    # authority it was taken under, so "did it over-reach" was unanswerable.
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": state,
                   "ceiling": (task.session or {}).get("ceiling") or "unknown",
                   "evidence": [evidence]}, now=now)


# ── the real pane ─────────────────────────────────────────────────────

class TmuxPane:
    """The real one: read and type into a live tmux pane."""

    def capture(self, name: str):
        """The pane's text, or **None** when there is no such pane.

        Not `""`. "The pane is gone" and "the pane is empty" were the same
        string, so a session whose terminal had died read as a quiet one and
        `attention` reported nothing waiting about it.
        """
        import subprocess
        try:
            out = subprocess.run(["tmux", "capture-pane", "-p", "-t", name],
                                 capture_output=True, text=True, timeout=10)
        except Exception:
            return None
        return out.stdout if out.returncode == 0 else None

    def send(self, name: str, text: str):
        from ai4science.harness.agents.machine import sessions
        return sessions.send_to_session(name, text)

    def key(self, name: str, key: str):
        from ai4science.harness.agents.machine import sessions
        return sessions.send_to_session(name, "", enter=False, key=key)
