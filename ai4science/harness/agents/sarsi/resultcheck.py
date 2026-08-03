"""`EC` — did something visibly break?

Deterministic by design: a literal match on real output, no model call, so
nothing can be talked into a finding or out of one.

> **It reports; it never rules.** A scan that matches nothing means *no
> signature matched*, not *the work is good* — most ways of being wrong leave no
> trace at all. There is deliberately no API here for a positive verdict, and an
> empty scan renders as an **empty string** rather than as reassurance, so
> nothing downstream can mistake quiet for correct.

Two guards keep false positives out, and both cost real matches to hold:

  * **prose is not evidence.** *"Next, fix the FAILED test"* is an instruction.
    Every signature is anchored to the *shape* the tool actually prints — a line
    beginning with `FAILED `, a `Traceback (most recent call last):` header —
    never to the bare word.
  * **one error is one finding.** The same traceback twice is one, so a single
    failure cannot become a stream of identical reports.

**Honest limit:** this scans the visible pane, which contains both what the
session printed and what was typed into it. The shape anchors are what keep the
owner's own words from matching; there is no separate assistant-only stream to
read here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence

#: (kind, pattern). Each is anchored to the shape a tool prints, not a word.
_SIGNATURES = (
    ("traceback", re.compile(r"^Traceback \(most recent call last\):", re.M)),
    ("test-failure", re.compile(r"^(?:FAILED|ERROR)\s+\S+::\S+", re.M)),
    ("test-failure", re.compile(r"^\d+ failed(?:,|\s)", re.M)),
    ("merge-conflict", re.compile(r"^<{7} \S+", re.M)),
    ("build-error", re.compile(r"^(?:npm ERR!|error\[E\d+\]:|make: \*\*\*)", re.M)),
    ("build-error", re.compile(r"^\S+\.\w+:\d+:\d+: error:", re.M)),
)


@dataclass(frozen=True)
class Finding:
    kind: str
    line: str


def scan(screen: str) -> List[Finding]:
    """Every distinct failure signature on this screen, in the order found."""
    text = screen or ""
    lines = text.splitlines()
    seen = set()
    out: List[Finding] = []
    for kind, pattern in _SIGNATURES:
        for match in pattern.finditer(text):
            line = _line_at(text, lines, match.start())
            key = (kind, line.strip())
            if key in seen:
                continue          # one error is one finding, not a stream
            seen.add(key)
            out.append(Finding(kind=kind, line=line.strip()))
    return out


def render(findings: Sequence[Finding]) -> str:
    """For splicing into the composer's prompt.

    **Empty when nothing matched** — never "no problems found", which would be a
    positive verdict this module has no authority to give.
    """
    if not findings:
        return ""
    lines = ["Failure signatures currently on screen — address these first:"]
    lines += [f"  [{f.kind}] {f.line}" for f in findings]
    return "\n".join(lines)


def _line_at(text: str, lines: List[str], offset: int) -> str:
    before = text.count("\n", 0, offset)
    return lines[before] if before < len(lines) else ""
