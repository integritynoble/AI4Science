"""When two agents cover the same work.

`imaging` is a generalist over computational imaging, and CT, radiotherapy
imaging physics and capsule imaging are inside its field. `low-dose-ct`,
`medical-physics` and `pill-camera` are also standalone agents over those same
areas. Both are true, both are wanted, and an owner may install any combination —
the generalist alone, one specialist alone, or all four.

That leaves two questions, and the second one is a safety question.

**1. Who takes the task?** The most specific installed agent that covers the
subfield. A specialist knows its subfield's protocol, its splits and its
statistics; a generalist knows the transfer surface. When both are present the
specialist runs the work and the generalist is still the one that notices a
method next door worth carrying over.

**2. What happens to the specialist's refusals?**

> **A generalist doing a specialist's work inherits the specialist's refusals —
> whether or not that specialist is installed.**

This is the whole module. `medical-physics` refuses to export a deliverable plan
because a physicist must sign it. `low-dose-ct` refuses to headline fidelity
without detectability. If `imaging` could do that work under its own, looser
charter, then **uninstalling the specialist would widen what the machine is
allowed to do** — and the way round every clinical gate in this design would be
to install the generalist instead.

So the refusals travel with the *subfield*, not with the package. `refusals_for`
returns the union, and `check_subfield_work` raises when a generalist is about to
do covered work without carrying what covers it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .charter import Charter, CharterViolation


class NoAgentForWork(Exception):
    """Nothing installed covers this subfield."""


@dataclass(frozen=True)
class Assignment:
    """Who takes a piece of work, and why that one."""
    agent: str
    subfield: str
    specificity: int          # smaller field = more specific = wins
    because: str
    inherited_from: Tuple[str, ...] = ()
    #: Other agents that were equally good candidates. Non-empty means the pick
    #: was deterministic rather than principled, and the caller should say which
    #: agent it meant.
    tied_with: Tuple[str, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return bool(self.tied_with)

    def __str__(self) -> str:
        tail = ("  (carrying %s's refusals)" % ", ".join(self.inherited_from)
                if self.inherited_from else "")
        return "%s takes %s — %s%s" % (self.agent, self.subfield, self.because, tail)


class Coverage:
    """The installed research agents, and who owns which subfield."""

    def __init__(self, charters: Iterable[Charter]):
        self.charters: Dict[str, Charter] = {c.name: c for c in charters}

    # ------------------------------------------------------------------ facts

    def installed(self) -> Tuple[str, ...]:
        return tuple(sorted(self.charters))

    def covering(self, subfield: str) -> List[Charter]:
        return [c for c in self.charters.values() if c.covers(subfield)]

    def specialists_of(self, name: str) -> List[Charter]:
        """Charters that narrow `name`, installed or not is decided by the
        caller — this looks only at what is here."""
        return [c for c in self.charters.values() if c.specialises == name]

    # ---------------------------------------------------------------- routing

    def route(self, subfield: str) -> Assignment:
        """The most specific installed agent covering `subfield`.

        Specificity is the size of the agent's field. A charter with thirteen
        subfields is a generalist; one with eleven that are all capsule
        endoscopy is a specialist. Counting is crude and it is also right: the
        agent that named fewer things named them on purpose."""
        pool = self.covering(subfield)
        if not pool:
            raise NoAgentForWork(
                "nothing installed covers %r — installed: %s"
                % (subfield, ", ".join(self.installed()) or "nothing"))
        owners = [c for c in pool if c.owns_subfield(subfield)]
        if len(owners) == 1:
            winner, why = owners[0], (
                "it owns this subfield" if len(pool) == 1 else
                "it owns this subfield; %s also covers it"
                % ", ".join(sorted(c.name for c in pool if c is not owners[0])))
            tied = ()
        else:
            # Nobody owns it, or two agents both claim it. Fall back to the
            # narrower field, and report the tie rather than hiding it: an
            # arbitrary pick presented as a decision is worse than an arbitrary
            # pick presented as arbitrary.
            candidates = owners or pool
            candidates.sort(key=lambda c: (len(c.subfields), c.name))
            winner = candidates[0]
            close = [c.name for c in candidates
                     if len(c.subfields) == len(winner.subfields)]
            tied = tuple(sorted(n for n in close if n != winner.name))
            why = ("the only agent covering it" if len(pool) == 1 else
                   "the most specific of %d covering it (%s)"
                   % (len(pool), ", ".join(sorted(c.name for c in pool))))
            if tied:
                why += " — tied with %s, picked deterministically; name the "\
                       "agent you want if it matters" % ", ".join(tied)
        return Assignment(agent=winner.name, subfield=subfield,
                          specificity=len(winner.subfields), because=why,
                          tied_with=tied,
                          inherited_from=tuple(
                              sorted(c.name for c in self._refusal_sources(winner, subfield))))

    # -------------------------------------------------------------- refusals

    def _refusal_sources(self, doer: Charter, subfield: str) -> List[Charter]:
        """Charters whose refusals apply to `doer` doing work in `subfield`:
        **every** other agent that covers it.

        Symmetric on purpose. An earlier version inherited only from *narrower*
        agents, which is right for a generalist and its specialist and wrong for
        two peers. `cancer` and `drug-design` both cover drug response and
        neither is inside the other — but cancer's *never advises a patient* has
        to bind drug-design doing oncology work, and drug-design's *does not
        optimise for harm* has to bind cancer doing molecule work. Under a
        size rule, whichever happened to list more subfields would escape the
        other's refusals, which is an arbitrary basis for a clinical gate.

        Read from the *known* charters rather than the installed ones, because
        the point is that uninstalling an agent must never loosen anything."""
        return [c for c in KNOWN.values()
                if c.name != doer.name and c.covers(subfield)]

    def refusals_for(self, agent: str, subfield: str) -> Tuple[str, ...]:
        """Every refusal that binds `agent` doing work in `subfield` — its own,
        plus those of any narrower agent whose field this is."""
        doer = self.charters[agent]
        own = list(doer.refusals)
        for src in self._refusal_sources(doer, subfield):
            for r in src.refusals:
                if r not in own:
                    own.append("[%s] %s" % (src.name, r))
        return tuple(own)

    def never_touch_for(self, agent: str, subfield: str) -> Tuple[str, ...]:
        """The union of forbidden substrates. A generalist working on CT may not
        touch the dose-equivalence framework either."""
        doer = self.charters[agent]
        out = list(doer.never_touch)
        for src in self._refusal_sources(doer, subfield):
            out += [s for s in src.never_touch if s not in out]
        return tuple(out)

    def check(self, agent: str, subfield: str, substrate: str) -> None:
        """The check a run makes before proposing a candidate, with inheritance.

        `imaging.charter.check('dose_equivalence_framework')` passes, because
        imaging never declared it. `coverage.check('imaging', 'ct',
        'dose_equivalence_framework')` does not."""
        if substrate in self.never_touch_for(agent, subfield):
            owners = [c.name for c in self._refusal_sources(self.charters[agent], subfield)
                      if substrate in c.never_touch]
            via = (" — inherited from %s, which owns this subfield"
                   % ", ".join(owners)) if owners else ""
            raise CharterViolation(
                "%s may not modify the %s while working on %s%s"
                % (agent, substrate, subfield, via))
        self.charters[agent].check(substrate)

    # -------------------------------------------------------------- soundness

    def audit(self) -> List[str]:
        """Ways this arrangement could let work escape a gate.

        Run in a test rather than at import: the answer should be empty, and a
        non-empty answer is a design error someone has to look at, not a
        condition to handle at runtime."""
        problems = []
        for c in self.charters.values():
            for sub in c.subfields:
                covering = [x for x in self._refusal_sources(c, sub)]
                owners = [x for x in covering if x.owns_subfield(sub)]
                if c.owns_subfield(sub) and owners:
                    problems.append(
                        "%r is owned by more than one agent: %s"
                        % (sub, ", ".join(sorted([c.name] + [o.name for o in owners]))))
                if covering and not c.owns_subfield(sub) and not owners:
                    problems.append(
                        "%r is covered by %s and owned by nobody — routing will "
                        "be a deterministic guess"
                        % (sub, ", ".join(sorted([c.name] + [x.name for x in covering]))))
        return sorted(set(problems))

    def report(self) -> str:
        L = ["installed: %s" % ", ".join(self.installed()), ""]
        seen = set()
        for c in sorted(self.charters.values(), key=lambda c: len(c.subfields)):
            for sub in c.subfields:
                if sub in seen:
                    continue
                seen.add(sub)
                a = self.route(sub)
                if len(self.covering(sub)) > 1:
                    L.append("  %s" % a)
        return "\n".join(L) if len(L) > 2 else "\n".join(L + ["  no overlaps"])


#: Every charter this design knows about, whether installed or not. Refusal
#: inheritance reads from here on purpose: a gate that disappears when a package
#: is uninstalled is not a gate.
KNOWN: Dict[str, Charter] = {}


def register(charter: Charter) -> Charter:
    KNOWN[charter.name] = charter
    return charter


def load_known() -> Dict[str, Charter]:
    """Populate KNOWN from the registry. Idempotent."""
    from .registry import NAMES, build
    for name in NAMES:
        if name not in KNOWN:
            register(build(name).charter)
    return KNOWN
