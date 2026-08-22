"""The recent conversation — what a follow-up is allowed to mean. [plan v3 §5.7]

`why?`, `continue`, `do that`. Three turns that carry no subject of their own
and are, on a normal day, most of what a person types. The worker used to send
every one of them through the whole workspace assembly — semantic store, task
board, plan, memory index, a live self-model probe, the scored episodic log —
because it had no cheaper place to look up what `that` was.

This module is that cheaper place: a **bounded window of the recent exchanges**,
measured in tokens rather than messages, with the referent a short turn needs
already inside it. It answers two questions and no others:

    recent(agent_dir, surface)     what was just said, within a token budget
    resolve(line, buffer)          what this turn is actually asking about

**It is not an authority.** Nothing here decides what the worker may do; it
decides what the worker was *talking about*, so the router downstream can tell a
question from an instruction. A directive that arrives as `do that` is still a
directive — resolving `that` is how the router gets to find that out, not a way
around it.

**Bounded on purpose.** The window is a token budget (default ~6k, mid of the
plan's 4k-8k) and older material is not deleted, only left where it already is:
in the log, retrievable through episodic memory when a turn actually asks for
it. Duplicating the whole transcript here would rebuild the exact problem the
gate exists to solve, one layer lower.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The default recent window. Tokens, not messages: a fixed message count is
#: wrong in both directions — ten one-word turns are free, and two turns that
#: each pasted a traceback are not.
DEFAULT_WINDOW_TOKENS = 6000

#: Cheap fallback ratio when no tokenizer is installed. Deliberately
#: conservative (under-counting a budget is how a "bounded" window stops being
#: one): ~3.5 bytes per token rather than the usual 4.
_BYTES_PER_TOKEN = 3.5

_TOKENIZER: Any = None
_TOKENIZER_TRIED = False


def _tokenizer():
    """A real tokenizer when this machine has one, else None. Tried once."""
    global _TOKENIZER, _TOKENIZER_TRIED
    if _TOKENIZER_TRIED:
        return _TOKENIZER
    _TOKENIZER_TRIED = True
    try:                                          # pragma: no cover - optional
        import tiktoken                           # type: ignore
        _TOKENIZER = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _TOKENIZER = None
    return _TOKENIZER


def estimate_tokens(text: str) -> int:
    """Tokens in `text` — measured where possible, bounded where not. [§2.6]

    A character cap is only a rough proxy and behaves badly across languages
    and code, so this uses a tokenizer when one is installed and a conservative
    byte ratio otherwise. The estimator used is recorded with the budget so a
    later reader knows which of the two produced a number.
    """
    if not text:
        return 0
    enc = _tokenizer()
    if enc is not None:                           # pragma: no cover - optional
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, int(len(text.encode("utf-8")) / _BYTES_PER_TOKEN) + 1)


def estimator() -> str:
    """Which estimator `estimate_tokens` is using — recorded in the manifest."""
    return "tiktoken/cl100k_base" if _tokenizer() is not None else "bytes/3.5"


@dataclass(frozen=True)
class Buffer:
    """`R_t` — the bounded recent window, oldest-first."""
    exchanges: List[Dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    budget_tokens: int = DEFAULT_WINDOW_TOKENS
    total: int = 0            #: exchanges in the log, all time
    omitted: int = 0          #: how many the window left behind — never silent
    log_path: str = ""
    task_id: str = ""         #: the topic, when one is cheaply derivable

    @property
    def empty(self) -> bool:
        return not self.exchanges

    @property
    def last_user(self) -> str:
        for e in reversed(self.exchanges):
            if (e.get("in") or "").strip():
                return str(e["in"]).strip()
        return ""

    @property
    def last_worker(self) -> str:
        for e in reversed(self.exchanges):
            if (e.get("out") or "").strip():
                return str(e["out"]).strip()
        return ""

    def ids(self) -> List[str]:
        return [str(e.get("exchange_id", "")) for e in self.exchanges
                if e.get("exchange_id")]


def recent(agent_dir: Path, surface: str = "cli", *,
           budget_tokens: int = DEFAULT_WINDOW_TOKENS) -> Buffer:
    """The last exchanges that fit in `budget_tokens`, oldest-first.

    Walks backwards from the newest so the window is anchored on *now*, and
    reports what it left behind rather than trimming quietly. [contract §0.1.7]
    """
    from ai4science.harness.agents.sarsi import log as _log
    try:
        rows = _log.read(agent_dir, surface, limit=0)
    except Exception:
        rows = []
    total = len(rows)

    kept: List[Dict[str, Any]] = []
    used = 0
    for e in reversed(rows):
        cost = estimate_tokens(_one(e))
        if kept and used + cost > budget_tokens:
            break
        kept.append(e)
        used += cost
        if used >= budget_tokens:
            break
    kept.reverse()

    task_id = ""
    for e in reversed(kept):
        if e.get("task_id"):
            task_id = str(e["task_id"])
            break

    try:
        path = str(_log._path(agent_dir, surface))
    except Exception:
        path = ""
    return Buffer(exchanges=kept, tokens=used, budget_tokens=budget_tokens,
                  total=total, omitted=max(0, total - len(kept)),
                  log_path=path, task_id=task_id)


def _one(e: Dict[str, Any]) -> str:
    return f"you: {(e.get('in') or '').strip()}\nworker: {(e.get('out') or '').strip()}"


def render(buf: Buffer) -> str:
    """The window as the model sees it — with the omission stated, not implied."""
    if buf.empty:
        return "recent conversation: none yet"
    head = (f"recent conversation ({len(buf.exchanges)} of {buf.total} exchanges, "
            f"~{buf.tokens} tokens")
    if buf.omitted:
        head += (f"; {buf.omitted} older not in this window — "
                 f"ask and I will look them up, full log: {buf.log_path}")
    head += "):"
    lines = [head]
    for e in buf.exchanges:
        ts = str(e.get("at", ""))[:16]
        tid = f" [{e['task_id']}]" if e.get("task_id") else ""
        lines.append(f"  [{ts}]{tid} you: {(e.get('in') or '').strip()}")
        lines.append(f"           worker: {(e.get('out') or '').strip()}")
    return "\n".join(lines)


# ── short turns that mean something else ──────────────────────────────────────

#: Turns whose whole content is a pointer backwards. Matched as complete lines,
#: because `why` alone is a follow-up and `why does GAP-TV diverge` is not.
_ELLIPTICAL = re.compile(
    r"^(?:"
    r"why|why not|how so|how come|and\??|so\??|then\??|ok(?:ay)? (?:and|so|now what)"
    r"|continue|go on|keep going|carry on|more|go ahead|proceed|next"
    r"|again|same|same thing|do that|do it|do so|that one|this one|the second one"
    r"|what about (?:that|this|it|that one|those)"
    r"|what do you mean|explain(?: that| it| more)?|elaborate|say more"
    r"|(?:and|but) (?:that|this|it)\??"
    r")[\s.!?]*$", re.I)

#: Words that only point at something already said.
_PRONOUN = re.compile(r"\b(that|this|it|those|these|them|the one|the same)\b", re.I)

#: The half of the elliptical set that only continues a CONVERSATION. `why?`
#: and `go on` ask for more words; `do that` and `run it again` ask for an act.
#: The distinction decides whether a short turn can stay cheap, so it is drawn
#: here rather than left to a classifier that would have to guess it.
_DISCOURSE_ONLY = re.compile(
    r"^(?:"
    r"why|why not|how so|how come|and\??|so\??|then\??|ok(?:ay)? (?:and|so|now what)"
    r"|continue|go on|keep going|carry on|more|next"
    r"|what about (?:that|this|it|that one|those)"
    r"|what do you mean|explain(?: that| it| more)?|elaborate|say more"
    r"|(?:and|but) (?:that|this|it)\??"
    r")[\s.!?]*$", re.I)


def is_discourse_followup(line: str) -> bool:
    """Does this short turn ask for more WORDS rather than for an act?

    `why?` cannot carry out anything; `do it` can. Both need the recent window
    to mean anything, and only the second one can turn into work.
    """
    return bool(_DISCOURSE_ONLY.match((line or "").strip()))


def is_elliptical(line: str) -> bool:
    """Does this turn need the recent window to mean anything at all?"""
    text = (line or "").strip()
    if not text:
        return False
    if _ELLIPTICAL.match(text):
        return True
    # Short and carrying a bare pronoun with no noun of its own: `do that now`,
    # `run it again`. Length-bounded so a real sentence that happens to say
    # "that" keeps its own subject.
    words = re.findall(r"[\w'-]+", text)
    return len(words) <= 5 and bool(_PRONOUN.search(text))


@dataclass(frozen=True)
class Resolved:
    """What the turn is about once the recent window has been consulted."""
    line: str                 #: what the owner typed, unchanged
    query: str                #: what to route and retrieve on
    referent: str = ""        #: the recent turn `that`/`why` points at
    used_recent: bool = False
    asks_older: bool = False  #: the turn explicitly reaches past the window


#: Turns that ask for memory older than the window — the one case where a chat
#: turn is *supposed* to pay for long-term retrieval. [§6.6]
_OLDER = re.compile(
    r"\b(yesterday|last (?:week|month|time|night)|earlier|previously|before|"
    r"back then|originally|at the start|first time|"
    r"do you remember|remember when|recall|"
    r"what did (?:we|you|i) (?:decide|say|agree|do|choose|pick)|"
    r"did (?:we|you|i) (?:ever|already)|"
    r"have (?:we|you) (?:ever|already)|"
    r"the (?:last|previous|earlier) (?:time|decision|discussion|session)|"
    r"history|log|transcript|"
    r"why did (?:we|you|i)|when did (?:we|you|i)|who (?:decided|chose|asked))\b",
    re.I)


def asks_for_older_memory(line: str) -> bool:
    """Is this turn explicitly reaching past the recent window? [§6.6]"""
    return bool(_OLDER.search(line or ""))


def resolve(line: str, buf: Optional[Buffer] = None) -> Resolved:
    """The retrieval/routing query for this turn — never the response. [§6.6]

    `why?` after a discussion of hybrid retrieval must not search memory for the
    word `why`; the recent window already holds the referent. So an elliptical
    turn is expanded with just enough of that window to carry a subject.

    The expansion is for **routing and retrieval only**. What the owner asked is
    `line`, unchanged, and that is what any answer or action contract is built
    from — expanding the query must never quietly rewrite the request.
    """
    text = (line or "").strip()
    older = asks_for_older_memory(text)
    if not text or buf is None or buf.empty:
        return Resolved(line=text, query=text, asks_older=older)

    if not is_elliptical(text):
        # A turn with its own subject still gets the standing topic when one is
        # active, because "the phase failed" means a different thing per task.
        query = f"{text} [task {buf.task_id}]" if buf.task_id else text
        return Resolved(line=text, query=query, asks_older=older)

    referent = buf.last_user
    reply = buf.last_worker
    parts = [text]
    if referent:
        parts.append(f"(follow-up to: {referent[:300]})")
    if reply:
        parts.append(f"(after I said: {reply[:300]})")
    if buf.task_id:
        parts.append(f"[task {buf.task_id}]")
    return Resolved(line=text, query=" ".join(parts), referent=referent,
                    used_recent=True, asks_older=older)
