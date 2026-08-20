"""What KIND of line the worker just received.

Every line became a task goal, verbatim — so a request to *make* a task became
the task, and the owner's framing became part of the goal:

    ❯ pleasa make a plan for me and create task
      goal:   pleasa make a plan for me and create task
    ❯ the goal is please write GAP-TV algorithm based on python for CASSI
      goal:   the goal is please write GAP-TV algorithm based on python …

The distinction this module exists for: **a request to make a task is not a
goal.** Strip the request and what remains is the goal — or nothing, and
"nothing" is a question to ask rather than a sentence to file.

**Narrow on purpose.** A router that guesses is worse than one that is quiet,
and the two costs are not symmetric: an `ambiguous` verdict costs one round
trip, while guessing costs a task nobody asked for, which the owner then has to
notice and stop. So anything this cannot place lands in `ambiguous`, and
`ambiguous` asks.

This does not call a model. It is the cheap half of the reasoning the worker was
missing — enough to stop filing the wrong thing. Judging whether a *goal* is a
good goal is a different job and belongs to the session that plans it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    """What the line is, and — for a directive — the goal inside it."""
    kind: str          # empty | greeting | question | meta | directive | ambiguous
    goal: str = ""
    why: str = ""      # for `meta` and `ambiguous`: what to ask the owner


#: Bare social lines. Matched whole, so "hi-res reconstruction" is untouched.
_GREETINGS = frozenset("""
hi hello hey yo hiya sup thanks thanx cheers ok okay k bye goodbye
""".split()) | frozenset([
    "thank you", "good morning", "good afternoon", "good evening",
])

#: Framing the owner puts in FRONT of a goal. Stripped, because it describes the
#: sentence rather than the work — "the goal is X" files a task whose goal is
#: "the goal is X", which reads back as noise in every listing thereafter.
_PREAMBLE = [
    re.compile(r"^\s*(please|pls|kindly)\s+", re.I),
    re.compile(r"^\s*the goal is\s+(that\s+)?", re.I),
    re.compile(r"^\s*(i want you to|i'd like you to|i would like you to)\s+", re.I),
    re.compile(r"^\s*(your goal is\s+(to\s+)?|goal:\s*)", re.I),
]

#: A request to MAKE a task or plan. What follows it — if anything — is the goal.
#: `make a task to write X` therefore works, which is how people actually ask.
_MAKE_BODY = (
    r"(?:can you\s+|could you\s+)?"
    r"(?:make|create|open|start|draft|set\s*up|generate|add)\s+"
    r"(?:me\s+)?(?:a|an|the|one)?\s*"
    r"(?:new\s+)?(?:task|plan|job)s?\b"
    r"(?:\s+for\s+me)?"
    r"(?:\s*(?:to|that|which|:|,)\s*)?")
#: Anchored, and the same thing unanchored. `search` on a `^`-anchored pattern
#: only ever matches at position 0, so the "one leading typo" tolerance below
#: silently did nothing until these were separated.
_MAKE = re.compile(r"^\s*" + _MAKE_BODY, re.I)
_MAKE_ANY = re.compile(_MAKE_BODY, re.I)

#: What is left of a make-request when it named no work: filler and back-
#: references to a goal the worker cannot see.
_REFERENTIAL = re.compile(
    r"^(?:\s*(?:and|then|also|please|pls|for me|for us|now|too|as well|"
    r"according to (?:this|that|the) goal|based on (?:this|that|the) goal|"
    r"from (?:this|that|the) goal|about (?:this|that|it)|"
    r"(?:this|that|the) goal|it|them|task|plan)\b[\s,.;:]*)*$", re.I)

#: Verbs that make a line an instruction. Deliberately a list rather than a
#: guess: "starts with a verb" is not something a regex knows, and a wrong yes
#: here files a task.
_ACTION = frozenset("""
write create make build add fix update change modify remove delete refactor
implement generate produce draft run test check verify validate review analyse
analyze compare measure benchmark profile debug investigate find search read
document explain summarise summarize translate port migrate deploy install
configure set setup train evaluate plot draw render extract collect gather
clean prepare split merge convert export import upload download publish submit
reproduce replicate optimise optimize tune calibrate solve compute calculate
develop design code program simulate model reconstruct apply integrate automate
adapt extend improve complete finish attempt try use apply combine extend show
""".split())


def _strip_preamble(text: str) -> str:
    """Peel framing off the front, repeatedly — "please the goal is …" happens."""
    prev = None
    while prev != text:
        prev = text
        for p in _PREAMBLE:
            text = p.sub("", text, count=1)
    return text.strip()


def _looks_actionable(text: str) -> bool:
    """Does this tell the worker to DO something?

    First word only. A line whose first word is not an action verb may still be
    a fine goal ("GAP-TV solver for CASSI"), which is exactly why the answer to
    "not actionable" is `ambiguous` — ask — and never a silent refusal.
    """
    words = re.findall(r"[A-Za-z][\w'-]*", text)
    return bool(words) and words[0].lower() in _ACTION


def classify(line: str) -> Intent:
    """What kind of line this is, and the goal inside it if there is one."""
    text = (line or "").strip()
    if not text:
        return Intent("empty")

    bare = text.rstrip("!.").strip().lower()
    if bare in _GREETINGS:
        return Intent("greeting")

    if text.endswith("?"):
        # Answered elsewhere — by the self-model when it is about the worker,
        # by the model otherwise. Either way it is not a goal.
        return Intent("question")

    body = _strip_preamble(text)

    # At the start, or just after ONE unrecognised word. The owner typed
    # "pleasa make a plan for me and create task" — a typo for "please" — and a
    # strict match-at-position-0 fell through to `ambiguous`. That was the safe
    # outcome (it asks rather than files) but the wrong message.
    #
    # Bounded to the first few characters ON PURPOSE: an unanchored search would
    # read "write a script to create a task queue" as a request to make a task
    # and throw the real goal away.
    m = _MAKE.match(body)
    if not m:
        found = _MAKE_ANY.search(body)
        if found and found.start() <= 12:
            m = found
            body = body[found.start():]
            m = _MAKE.match(body)
    if m:
        rest = _strip_preamble(body[m.end():])
        # A compound request is still a request. The owner wrote "make a plan
        # for me AND create task" -- two make-phrases joined -- and stripping
        # only the first left "and create task", which is not work either.
        # Peel connectives and further make-phrases until something else shows
        # up or nothing does.
        prev = None
        while prev != rest:
            prev = rest
            rest = re.sub(r"^\s*(and|then|also|plus)\b\s*", "", rest, flags=re.I)
            again = _MAKE.match(rest)
            if again:
                rest = _strip_preamble(rest[again.end():])
        if not rest or _REFERENTIAL.match(rest):
            return Intent("meta", why=(
                "that asks me to make a task but does not say what the task is "
                "for. Tell me the goal — one sentence, what you want to end up "
                "with — and I will offer it."))
        body = rest        # `make a task to write X` — the goal is X

    if _looks_actionable(body):
        return Intent("directive", goal=body)

    return Intent("ambiguous", why=(
        "I could not tell whether that is a goal for a task or something you "
        "were telling me. If it is a goal, say it as an instruction — "
        "\"write …\", \"fix …\", \"add …\" — or use /do to make it one."))
