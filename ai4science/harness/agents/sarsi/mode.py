"""How much cognition this turn is worth buying. [plan v3 §7.0, M2.3]

`hello` and `implement M2` used to cost the same thing. Every plain line in
agent mode was prefixed with the entire assembled workspace — the semantic
store, the task board, the standing plan, both memory indexes, a **live
self-model probe**, and a scored pass over the whole conversation log — before
the model saw a single word of it. That is the right price for an instruction
that will spawn an executor. It is the wrong price for `why?`.

So a turn gets a **cognitive mode**, and the mode decides what the gate
assembles:

| mode | the turn | what it buys |
|---|---|---|
| `CHAT` | greeting, explanation, local follow-up | recent dialogue + minimal identity |
| `REASON` | comparison, planning talk, explicit recall | + retrieved semantic/episodic memory |
| `ACTION` | create/assign/steer/archive/edit/run | full protected context, readiness, prediction, verification |

**The mode controls cost, never authority.** Nothing here grants, widens, or
skips a permission: `ACTION` does not mean allowed, and `CHAT` does not mean
unguarded. Every safeguard on the path a turn actually takes stays exactly where
it was — this only decides how much the worker reads before it gets there.

**It fails upward, never downward.** The two errors are not symmetric. Routing
an instruction to `CHAT` answers a request that should have been carried out
under supervision; routing a question to `ACTION` costs some tokens and a
clarifying line. So anything with side-effecting language in request position,
and anything the intent classifier cannot place, lands in `ACTION` — the same
argument `intent.py` makes for `ambiguous`, applied one layer up.

**Deterministic first.** A slash command and a parsed intent are facts; only
genuinely ambiguous prose reaches the heuristics, and none of it reaches a
model. The router's own version is recorded with every context so a routing
mistake can be replayed apart from a retrieval mistake. [§7.4]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from ai4science.harness.agents.sarsi import discourse as _disc

#: Bumped whenever a routing rule changes. Recorded in the context manifest —
#: a replay that cannot tell which router produced a decision cannot separate a
#: routing bug from a retrieval bug.
ROUTER_VERSION = "mode/1"

CHAT = "CHAT"
REASON = "REASON"
ACTION = "ACTION"

#: Increasing cost/care. Escalation moves right and never left.
ORDER = (CHAT, REASON, ACTION)


def higher(a: str, b: str) -> str:
    """The more careful of two modes."""
    return a if ORDER.index(a) >= ORDER.index(b) else b


#: Slash verbs that change something. `/<task>` and the read-only board verbs
#: are not here: they render state, and rendering is not acting.
_MUTATING = frozenset("""
new answer guided interact resume resume-task edit stop archive reopen goal
""".split())

#: Slash verbs that only read. Deterministic renders — no model call, no memory
#: retrieval, nothing to assemble.
_READ_ONLY = frozenset("""
tasks task archived who questions history plan why
""".split())

#: Side-effecting language. Broader than `intent._ACTION` on purpose: this list
#: is used to ESCALATE, so a false positive costs a round trip and a false
#: negative carries out an instruction as if it were small talk.
_SIDE_EFFECT = frozenset("""
create make build open start run execute launch spawn assign delegate
write edit modify change update rewrite refactor patch fix add remove delete
drop archive close reopen stop kill cancel abort revert rollback
commit push merge rebase tag deploy release publish install uninstall configure
send submit upload download sync migrate rename move copy
file steer guide answer approve sign promote activate enable disable
""".split())

#: The same verbs in a request wrapper: "can you run the tests", "go ahead and
#: commit". Matched at the front, so a mention deep in a sentence does not
#: escalate a question about the past.
_REQUEST = re.compile(
    r"^\s*(?:please\s+|pls\s+|kindly\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|i(?:'d| would)? (?:like|want) you to\s+"
    r"|i want\s+(?:you\s+to\s+)?"
    r"|(?:let'?s|lets)\s+"
    r"|go ahead and\s+"
    r"|(?:now\s+)?(?:you should|you can)\s+)?"
    r"(?P<verb>[a-z][\w-]*)", re.I)

#: Asking ABOUT an act is not asking FOR one. "why did you create the task?"
#: names a side-effect verb and must not be escalated for it.
_ABOUT_THE_PAST = re.compile(
    r"^\s*(?:why|when|who|what|which|how|where)\b"
    r"|^\s*(?:did|does|do|has|have|had|is|are|was|were|can|could|should|would)\s+"
    r"(?:you|we|i|it|that|this|the)\b",
    re.I)

#: A question that wants more than the last few turns: architecture, a
#: comparison, a named task, or memory older than the window.
_DELIBERATE = re.compile(
    r"\b(architecture|design|approach|tradeoff|trade-off|compare|comparison|"
    r"versus|vs\.?|better|worse|why (?:does|is|are|do)|how (?:does|do|should)|"
    r"plan|phase|criterion|criteria|verified|verification|strategy|"
    r"consolidat|retriev|semantic|episodic|calibrat|forecast|"
    r"tsk_[a-z0-9]+)\b", re.I)


@dataclass(frozen=True)
class Route:
    """The routing decision, and enough of its reasoning to replay it."""
    mode: str = CHAT
    why: str = ""
    signals: List[str] = field(default_factory=list)
    query: str = ""             #: what to retrieve/route on — never the answer
    line: str = ""              #: what the owner typed, unchanged
    referent: str = ""
    deterministic: bool = True  #: no heuristic was needed
    escalated: bool = False     #: failed upward rather than being placed
    asks_older: bool = False
    router_version: str = ROUTER_VERSION

    def as_record(self) -> dict:
        return {"mode": self.mode, "why": self.why, "signals": list(self.signals),
                "deterministic": self.deterministic, "escalated": self.escalated,
                "asks_older": self.asks_older,
                "router_version": self.router_version,
                "referent": self.referent[:120]}


def requests_action(text: str) -> bool:
    """Is this turn asking for something to be DONE, right now, by us?

    Position matters more than vocabulary. `commit the fix` is an instruction;
    `why did you commit the fix?` names the same verb and asks about the past;
    `write a script that deletes stale rows` describes work whose verb sits in
    a relative clause. Only the first is a request, and only the first escalates.
    """
    body = (text or "").strip()
    if not body:
        return False
    if _ABOUT_THE_PAST.match(body) and not _MAKE_REQUEST.search(body):
        return False
    m = _REQUEST.match(body)
    if not m:
        return False
    return m.group("verb").lower() in _SIDE_EFFECT


#: "can you create a task for X?" opens with `can`, which `_ABOUT_THE_PAST`
#: also matches. The request form wins: it is an instruction wearing a question
#: mark, and treating it as a question is the exact downgrade §7.0 forbids.
_MAKE_REQUEST = re.compile(
    r"\b(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"(?:" + "|".join(sorted(_SIDE_EFFECT)) + r")\b", re.I)


def slash_mode(line: str) -> Optional[str]:
    """The mode of a slash command, or None when it is not one."""
    body = (line or "").strip()
    if not body.startswith("/"):
        return None
    verb = body[1:].partition(" ")[0].strip().lower()
    if verb in _MUTATING:
        return ACTION
    if verb in _READ_ONLY:
        return CHAT
    # `/<task>` opens one, and an unknown verb prints the command list. Neither
    # touches the world outside this surface.
    return CHAT


def route(line: str, *, buf: Optional["_disc.Buffer"] = None,
          cursor: bool = False, intent_of: Optional[Any] = None) -> Route:
    """Which mode this turn gets, and why.

    `cursor` is True when the surface is standing inside a task, because there
    a plain line is not conversation — it is steered into the live session as
    keystrokes, which is as consequential as anything gets here.
    """
    text = (line or "").strip()
    if not text:
        return Route(mode=CHAT, why="empty turn", signals=["empty"],
                     query="", line=text)

    sm = slash_mode(text)
    if sm is not None:
        verb = text[1:].partition(" ")[0].strip().lower()
        return Route(mode=sm, why=f"/{verb} is a {'mutating' if sm == ACTION else 'read-only'} command",
                     signals=[f"slash:{verb}"], query=text, line=text)

    got = intent_of
    if got is None:
        from ai4science.harness.agents.sarsi import intent as _intent
        got = _intent.classify(text)

    resolved = _disc.resolve(text, buf)
    signals: List[str] = [f"intent:{getattr(got, 'kind', '?')}"]
    if resolved.used_recent:
        signals.append("resolved-from-recent")
    if resolved.asks_older:
        signals.append("asks-older-memory")

    if cursor:
        return Route(mode=ACTION,
                     why="a plain line inside a task is steered into its live "
                         "session — that is keystrokes at a running executor",
                     signals=signals + ["cursor"], query=resolved.query,
                     line=text, referent=resolved.referent,
                     asks_older=resolved.asks_older)

    # An elliptical turn inherits the weight of what it points at: `do that`
    # after `create a task for X` is that instruction, said shorter.
    if resolved.used_recent and resolved.referent:
        from ai4science.harness.agents.sarsi import intent as _intent
        back = _intent.classify(resolved.referent)
        if back.kind == "directive" or requests_action(resolved.referent):
            return Route(mode=ACTION,
                         why="a short follow-up to an instruction is that "
                             "instruction — the referent is a directive",
                         signals=signals + ["referent:directive"],
                         query=resolved.query, line=text,
                         referent=resolved.referent, deterministic=False,
                         escalated=True, asks_older=resolved.asks_older)

    # `why?`, `continue`, `go on` — the follow-ups that ask for more words.
    # Their referent is not an instruction, so they stay on the fast path: this
    # is the turn the whole mode split exists for. An explicit reach into older
    # memory is still honoured, because the content asked for it.
    if _disc.is_discourse_followup(text):
        if resolved.asks_older:
            return Route(mode=REASON,
                         why="a follow-up that reaches past the recent window",
                         signals=signals + ["discourse-followup"],
                         query=resolved.query, line=text,
                         referent=resolved.referent, deterministic=False,
                         asks_older=True)
        return Route(mode=CHAT,
                     why=("a local follow-up — the recent window already holds "
                          "what it points at" if resolved.used_recent else
                          "a follow-up with nothing yet to follow"),
                     signals=signals + ["discourse-followup"],
                     query=resolved.query, line=text,
                     referent=resolved.referent, deterministic=False)

    kind = getattr(got, "kind", "ambiguous")
    mode, why, deterministic, escalated = _place(kind, text, resolved)

    # The one-way valve. Whatever placed the turn above, side-effecting
    # language in request position pulls it up — a classifier that is unsure is
    # not a reason to act as though the turn were small talk. [§7.0]
    if mode != ACTION and requests_action(text):
        mode, why, escalated = ACTION, (
            "side-effecting language in request position — routing up rather "
            "than answering a request as conversation"), True
        signals.append("requests-action")

    return Route(mode=mode, why=why, signals=signals, query=resolved.query,
                 line=text, referent=resolved.referent,
                 deterministic=deterministic, escalated=escalated,
                 asks_older=resolved.asks_older)


def _place(kind: str, text: str, resolved: "_disc.Resolved"):
    """Mode from the parsed intent alone. Returns (mode, why, det, escalated)."""
    if kind == "greeting":
        return CHAT, "a greeting", True, False
    if kind == "correction":
        return REASON, ("a correction is about what was just said — it needs "
                        "the recent window, not an executor"), True, False
    if kind == "directive":
        return ACTION, "a parsed directive", True, False
    if kind == "meta":
        return ACTION, ("a request to make a task, with the goal missing — "
                        "creation, pending one question"), True, False
    if kind == "ambiguous":
        return ACTION, ("could not be placed; an unplaced line routes up, "
                        "never down"), False, True
    if kind == "question":
        if resolved.asks_older:
            return REASON, ("the question reaches past the recent window into "
                            "long-term memory"), True, False
        if _DELIBERATE.search(text):
            return REASON, ("a deliberative question — worth retrieving "
                            "relevant memory for"), False, False
        return CHAT, "an ordinary question, answerable from recent context", False, False
    return CHAT, "an ordinary turn", False, False


#: The polite wrapper a request arrives in. Stripped to get at the instruction.
_WRAPPER = re.compile(
    r"^\s*(?:please\s+|pls\s+|kindly\s+"
    r"|(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|i(?:'d| would)? (?:like|want) you to\s+"
    r"|i want\s+(?:you\s+to\s+)?"
    r"|(?:let'?s|lets)\s+"
    r"|go ahead and\s+"
    r"|(?:now\s+)?(?:you should|you can)\s+)", re.I)


def action_goal(text: str) -> str:
    """The instruction inside a request, without the wrapper or the question mark.

    `can you create a task to port the solver?` is a request to do a thing, and
    the thing is `create a task to port the solver`. Offering the owner their
    own sentence back with `can you` still in it makes a goal that reads as a
    question forever after — the same defect `intent._strip_preamble` exists
    for, one wrapper further out.
    """
    body = (text or "").strip().rstrip("?").strip()
    prev = None
    while prev != body:
        prev = body
        body = _WRAPPER.sub("", body, count=1).strip()
    return body or (text or "").strip()
