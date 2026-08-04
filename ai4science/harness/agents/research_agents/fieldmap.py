"""What the field claims, and which of those claims nobody has checked.

An agent that picks its next experiment by *"what would raise my score"* produces
the increment: a long series of defensible +0.2% results, none of which change
what anyone can do. That is also what a large part of the literature already is,
so an agent doing it has automated the field's worst habit.

The field map is the alternative. It holds claims and their **status**, and work
is chosen to reduce the map's uncertainty rather than to raise the agent's score.
The four statuses are the four shortages an agent can actually close:

    UNREPLICATED   published, never reproduced here
    UNCOMPARED     reproduced, but not on the same footing as its rivals
    UNTRIED        a method from a neighbouring subfield that has never been
                   tried on this one — the transfer surface, where the field
                   wastes the most and an agent is best placed to help
    PROXY_ONLY     measured, but against a proxy nobody has checked against the
                   thing that matters

and one terminal state, SETTLED, which is the only one that stops costing.

**Provenance.** A claim read in a paper is evidence that a paper said so, not a
fact. `Claim.trusted` is False until this agent reproduced it, and `believe()`
refuses to promote a claim on the strength of its source. This is the same rule
that stops an instruction inside an email being an instruction, applied to the
literature — which is a friendlier source and exactly as untrusted.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

UNREPLICATED = "unreplicated"
UNCOMPARED = "uncompared"
UNTRIED = "untried"
PROXY_ONLY = "proxy_only"
SETTLED = "settled"

#: Cost order, cheapest and most informative first. Reproduction comes first
#: because it is the strongest single use of an agent in any of these fields:
#: tedious, endless, and worth more than another method.
OPEN_ORDER = (UNREPLICATED, UNCOMPARED, UNTRIED, PROXY_ONLY)


@dataclass
class Claim:
    """One thing the field believes, and how well it is supported here."""

    key: str
    statement: str
    source: str                      # where it was read: a paper, a repo, a talk
    status: str = UNREPLICATED
    subfield: str = ""
    #: True only once this agent reproduced it. Never set by reading.
    trusted: bool = False
    #: For UNTRIED: where the method comes from. The transfer surface.
    from_subfield: str = ""
    note: str = ""
    at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.status not in OPEN_ORDER + (SETTLED,):
            raise ValueError("%s: unknown status %r" % (self.key, self.status))


class FieldMap:
    """The agent's picture of where its field is unsupported.

    Lives in the agent's own workspace (`W_name`): it is what makes the second
    night better than the first."""

    def __init__(self, agent: str, claims: Iterable[Claim] = ()):
        self.agent = agent
        self.claims: Dict[str, Claim] = {c.key: c for c in claims}

    # ------------------------------------------------------------------ edit

    def add(self, claim: Claim) -> Claim:
        self.claims[claim.key] = claim
        return claim

    def read_from_literature(self, key: str, statement: str, source: str,
                             *, subfield: str = "") -> Claim:
        """Record a claim found in a paper. It arrives untrusted, and there is no
        parameter on this method that can make it arrive any other way."""
        return self.add(Claim(key=key, statement=statement, source=source,
                              subfield=subfield, status=UNREPLICATED,
                              trusted=False))

    def reproduced(self, key: str, *, evidence: str, agrees: bool) -> Claim:
        """This agent ran it. Agreement makes it trusted; disagreement is a
        result in its own right and is kept, not deleted — a published number
        that does not reproduce is one of the most valuable things an agent in
        these fields can report."""
        c = self.claims[key]
        c.trusted = bool(agrees)
        c.status = UNCOMPARED if agrees else SETTLED
        c.note = ("reproduced: %s" % evidence if agrees
                  else "did NOT reproduce: %s" % evidence)
        return c

    def compared(self, key: str, *, evidence: str) -> Claim:
        c = self.claims[key]
        c.status = PROXY_ONLY if not c.trusted else SETTLED
        c.note = "compared on a common footing: %s" % evidence
        return c

    def believe(self, key: str) -> None:
        """There is no way to believe a claim because of where it was read."""
        raise PermissionError(
            "%s: %r cannot be promoted by its source. A claim read in a paper is "
            "evidence that a paper said so. Reproduce it." % (self.agent, key))

    # ------------------------------------------------------------- selection

    def open_claims(self) -> List[Claim]:
        return [c for c in self.claims.values() if c.status != SETTLED]

    def next_work(self, *, subfield: Optional[str] = None) -> Optional[Claim]:
        """The claim whose checking would remove the most uncertainty.

        Deliberately not "the experiment most likely to improve my score". The
        ordering is by *kind of ignorance*, oldest first within a kind, so the
        map is worked front to back rather than cherry-picked."""
        pool = [c for c in self.open_claims()
                if subfield is None or c.subfield == subfield]
        if not pool:
            return None
        return min(pool, key=lambda c: (OPEN_ORDER.index(c.status), c.at))

    def transfer_candidates(self) -> List[Claim]:
        """Empty cells of the transfer table: a method that works next door and
        has never been tried here."""
        return [c for c in self.claims.values()
                if c.status == UNTRIED and c.from_subfield]

    # -------------------------------------------------------------- reporting

    def summary(self) -> Dict[str, int]:
        out = {s: 0 for s in OPEN_ORDER + (SETTLED,)}
        for c in self.claims.values():
            out[c.status] += 1
        return out

    def report(self) -> str:
        """The weekly output an owner actually wants: not a result, a picture of
        where the field is unsupported."""
        s = self.summary()
        L = ["%s — field map: %d claims" % (self.agent, len(self.claims)), ""]
        for status in OPEN_ORDER:
            rows = [c for c in self.claims.values() if c.status == status]
            if not rows:
                continue
            L.append("%s (%d)" % (status, len(rows)))
            for c in sorted(rows, key=lambda c: c.at):
                tail = ("  ← %s" % c.from_subfield) if c.from_subfield else ""
                L.append("   %-14s %s%s" % (c.subfield or "-",
                                            c.statement[:88], tail))
            L.append("")
        settled = [c for c in self.claims.values() if c.status == SETTLED]
        if settled:
            L.append("settled (%d), including any that did not reproduce:" % len(settled))
            for c in settled:
                L.append("   %-14s %s — %s" % (c.subfield or "-",
                                               c.statement[:60], c.note[:60]))
        return "\n".join(L)

    # ------------------------------------------------------------ persistence

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"agent": self.agent,
             "claims": [asdict(c) for c in self.claims.values()]}, indent=1))
        return path

    @classmethod
    def load(cls, path: Path) -> "FieldMap":
        raw = json.loads(Path(path).read_text())
        return cls(raw["agent"], [Claim(**c) for c in raw.get("claims", ())])
