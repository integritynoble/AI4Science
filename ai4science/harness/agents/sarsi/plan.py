"""`PLN` — the plan a task runs on.

One document doing four jobs: it names the phase the session works next, it
supplies the criteria the **verifier** judges by, it declares the permissions
the owner grants at `GRT`, and its successors carry what the work revealed.

Three rules are refusals rather than behaviours:

  * **a phase without a `Verified when:` line is not a phase.** It gives the
    verifier nothing to judge, which means the task can only ever be graded by
    the agent that did it.
  * **a new generation is the owner's act alone.** Successors inside a
    generation (`plan0_1`, `plan0_2`, …) are the agent's; `plan1` is not.
  * **an owner edit is authoritative.** Polish may propose a successor to it and
    may not replace it — the same propose-then-sign shape as RSI, for the same
    reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence

PERMISSIONS_HEADING = "## Permissions needed"
VERIFIED_PREFIX = "Verified when:"
#: where the work happens, when it is not the task's own folder
WORK_ROOT_PREFIX = "Working directory:"
#: other paths the plan may change, one per line
MAY_TOUCH_PREFIX = "May also touch:"
#: a declared ceiling — "Budget: 40 steps, 30 minutes". Absent means none.
BUDGET_PREFIX = "Budget:"
#: another task this one waits on — `<agent>/<task>`, one per line
DEPENDS_PREFIX = "Depends on:"
_PHASE_RE = re.compile(r"^##\s+Phase\s+\d+\s+—\s+(?P<title>.+?)\s*$", re.M)


class BadPlan(Exception):
    """The plan cannot do the job a plan exists for. Refused at construction."""


class OwnerOnly(Exception):
    """Only the owner may do this. The agent asked anyway."""


@dataclass(frozen=True)
class Phase:
    title: str
    verified_when: str = ""
    body: str = ""

    def __post_init__(self) -> None:
        if not (self.verified_when or "").strip():
            raise BadPlan(
                f"phase {self.title!r} has no `{VERIFIED_PREFIX}` line — the "
                f"verifier would have nothing to judge it by, and the only "
                f"grader left would be the agent that did the work")
        object.__setattr__(self, "title", (self.title or "").strip())
        object.__setattr__(self, "verified_when", self.verified_when.strip())


@dataclass(frozen=True)
class Polish:
    """The outcome of a polish round: adopted, or merely proposed."""
    plan: "Plan"                       # what stands now
    adopted: bool
    proposal: Optional["Plan"] = None  # what the agent would have written


@dataclass(frozen=True)
class Plan:
    goal: str
    phases: Sequence[Phase] = field(default_factory=tuple)
    permissions: Sequence[str] = field(default_factory=tuple)
    version: str = "plan0"
    stale: bool = False
    owner_edited: bool = False
    #: Limits the plan states rather than asks for — "no network", "no
    #: credentials". Asking the owner to GRANT one of these is nonsense.
    constraints: Sequence[str] = field(default_factory=tuple)
    #: Where the work happens, when it is not the task's own folder. DECLARED,
    #: never inferred: evidence is gathered from here, so a criterion naming a
    #: path cannot move it. `None` means the task folder, which stays the
    #: default — the boundary moves only when the plan says to move it.
    work_root: Optional[str] = None
    #: Paths BESIDES the working directory this plan may change. Declared, so
    #: the blast-radius check has something to check against; a path the agent
    #: touched must never be able to authorise itself.
    may_touch: Sequence[str] = field(default_factory=tuple)
    #: Declared ceilings. `None` means no budget — there is deliberately no
    #: default, because one either kills legitimate long work or never fires.
    max_steps: Optional[int] = None
    max_minutes: Optional[int] = None
    #: tasks that must be VERIFIED before this one starts
    depends_on: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.phases:
            raise BadPlan("a plan needs at least one phase")
        object.__setattr__(self, "phases", tuple(self.phases))
        object.__setattr__(self, "permissions", tuple(self.permissions))
        object.__setattr__(self, "may_touch", tuple(self.may_touch))
        object.__setattr__(self, "depends_on", tuple(self.depends_on))
        object.__setattr__(self, "constraints", tuple(self.constraints))

    # ── what the verifier is given ────────────────────────────────────

    def criteria(self) -> List[str]:
        """The ordered `Verified when:` lines — **withheld while stale.**

        Judging this run against a superseded mission's standard is worse than
        judging against the goal alone.
        """
        if self.stale:
            return []
        return [p.verified_when for p in self.phases]

    # ── rendering and parsing ─────────────────────────────────────────

    def render(self) -> str:
        out = [f"# {self.goal}", ""]
        if self.work_root:
            out += [f"{WORK_ROOT_PREFIX} {self.work_root}", ""]
        for path in self.may_touch:
            out += [f"{MAY_TOUCH_PREFIX} {path}"]
        if self.may_touch:
            out.append("")
        for ref in self.depends_on:
            out += [f"{DEPENDS_PREFIX} {ref}"]
        if self.depends_on:
            out.append("")
        if self.max_steps or self.max_minutes:
            parts = ([f"{self.max_steps} steps"] if self.max_steps else []) + \
                    ([f"{self.max_minutes} minutes"] if self.max_minutes else [])
            out += [f"{BUDGET_PREFIX} {', '.join(parts)}", ""]
        for i, phase in enumerate(self.phases, start=1):
            out.append(f"## Phase {i} — {phase.title}")
            if phase.body:
                out.append(phase.body)
            out.append(f"{VERIFIED_PREFIX} {phase.verified_when}")
            out.append("")
        out.append(PERMISSIONS_HEADING)
        # never omitted: an absent section reads as "not considered"
        out.extend([f"- {p}" for p in self.permissions] or ["- none"])
        out.append("")
        return "\n".join(out)

    # ── generations ───────────────────────────────────────────────────

    def successor_version(self) -> str:
        base, _, tail = self.version.partition("_")
        n = int(tail) if tail.isdigit() else 0
        return f"{base}_{n + 1}"

    def next_generation(self, *, by_owner: bool = False) -> "Plan":
        if not by_owner:
            raise OwnerOnly(
                "a new generation is a new mission, and that is the owner's act "
                "alone; the agent writes successors inside this one")
        gen = int(re.sub(r"\D", "", self.version.partition("_")[0]) or 0)
        return replace(self, version=f"plan{gen + 1}", stale=False,
                       owner_edited=False)

    # ── the owner's edit, and the agent's polish ──────────────────────

    def owner_edit(self, *, phases: Optional[Sequence[Phase]] = None,
                   goal: Optional[str] = None,
                   permissions: Optional[Sequence[str]] = None) -> "Plan":
        """An owner edit is the mission restated: authoritative, and **fresh**."""
        return replace(self,
                       goal=goal if goal is not None else self.goal,
                       phases=tuple(phases) if phases is not None else self.phases,
                       permissions=tuple(permissions) if permissions is not None
                       else self.permissions,
                       stale=False, owner_edited=True)

    def polish(self, *, phases: Sequence[Phase],
               permissions: Optional[Sequence[str]] = None) -> Polish:
        """Rewrite the plan against what the work revealed.

        Over an owner-edited plan this only **proposes**: the agent may improve
        its own plan and may not adopt that improvement by itself.
        """
        candidate = replace(self, phases=tuple(phases),
                            permissions=tuple(permissions) if permissions is not None
                            else self.permissions,
                            version=self.successor_version(),
                            stale=False, owner_edited=False)
        if self.owner_edited:
            return Polish(plan=self, adopted=False, proposal=candidate)
        return Polish(plan=candidate, adopted=True)


def draft(directive) -> Plan:
    """The deterministic first plan for a directive.

    One phase per criterion the directive already carries. When it carries none,
    the goal itself becomes the criterion — marked as the provisional thing it
    is, because a plan with nothing to verify is not a plan.

    It **never invents a resource the goal did not name**: `Permissions needed`
    is built only from the scope and secrets the directive declared. A better
    plan is a model's job; an honest one is this function's.
    """
    criteria = [c for c in (directive.criteria or []) if (c or "").strip()]
    if criteria:
        phases = [Phase(title=f"phase {i}", verified_when=c)
                  for i, c in enumerate(criteria, start=1)]
    else:
        phases = [Phase(
            title="do the work",
            verified_when=(f"visible evidence shows: {directive.goal} "
                           f"(provisional — no criterion was given)"))]
    permissions = [f"use {s}" for s in (directive.scope or [])]
    permissions += [f"read secret {s}" for s in (directive.requires_secrets or [])]
    return Plan(goal=directive.goal, phases=phases, permissions=permissions)


def _budget(text: str):
    """`40 steps, 30 minutes` -> (40, 30). A unit it does not know is ignored
    rather than guessed at — a budget read wrong is worse than none."""
    import re as _re
    steps = minutes = None
    for value, unit in _re.findall(r"(\d+)\s*(step|minute|min|hour)s?\b",
                                   text, _re.I):
        unit = unit.lower()
        if unit == "step":
            steps = int(value)
        elif unit in ("minute", "min"):
            minutes = int(value)
        elif unit == "hour":
            minutes = int(value) * 60
    return steps, minutes


def parse(text: str) -> Plan:
    lines = (text or "").splitlines()
    goal = ""
    for line in lines:
        if line.startswith("# "):
            goal = line[2:].strip()
            break

    work_root = None
    may_touch: List[str] = []
    max_steps: Optional[int] = None
    max_minutes: Optional[int] = None
    depends_on: List[str] = []
    for line in lines:
        stripped = line.strip()
        if work_root is None and stripped.lower().startswith(WORK_ROOT_PREFIX.lower()):
            work_root = stripped.split(":", 1)[1].strip() or None
        elif stripped.lower().startswith(MAY_TOUCH_PREFIX.lower()):
            extra = stripped.split(":", 1)[1].strip()
            if extra:
                may_touch.append(extra)
        elif stripped.lower().startswith(BUDGET_PREFIX.lower()):
            max_steps, max_minutes = _budget(stripped.split(":", 1)[1])
        elif stripped.lower().startswith(DEPENDS_PREFIX.lower()):
            ref = stripped.split(":", 1)[1].strip()
            if ref:
                depends_on.append(ref)

    phases: List[Phase] = []
    permissions: List[str] = []
    current_title: Optional[str] = None
    current_body: List[str] = []
    current_verified = ""
    in_permissions = False
    in_verified = False
    constraints: List[str] = []

    def flush() -> None:
        nonlocal current_title, current_body, current_verified, in_verified
        in_verified = False
        if current_title is not None:
            phases.append(Phase(title=current_title,
                                verified_when=current_verified,
                                body="\n".join(current_body).strip()))
        current_title, current_body, current_verified = None, [], ""

    for line in lines:
        m = _PHASE_RE.match(line)
        if m:
            flush()
            in_permissions = False
            current_title = m.group("title")
            continue
        if line.strip() == PERMISSIONS_HEADING:
            flush()
            in_permissions = True
            continue
        if in_permissions:
            if line.strip().startswith("- "):
                item = line.strip()[2:].strip()
                if item.lower() == "none":
                    continue
                if _is_constraint(item):
                    # a limit the plan accepts, not a request to grant
                    constraints.append(item)
                else:
                    permissions.append(item)
            continue
        if current_title is not None:
            if line.startswith(VERIFIED_PREFIX):
                current_verified = line[len(VERIFIED_PREFIX):].strip()
                in_verified = True
                continue
            if in_verified:
                # A criterion that wraps is ONE criterion. Taking only its first
                # line hands the verifier a weaker standard than the plan states
                # — and the plan is the standard. It ends at a blank line.
                if line.strip():
                    current_verified += " " + line.strip()
                    continue
                in_verified = False
                continue
            if line.strip():
                current_body.append(line)
    flush()
    return Plan(goal=goal, phases=phases, permissions=permissions,
                constraints=constraints, work_root=work_root,
                may_touch=may_touch, max_steps=max_steps,
                max_minutes=max_minutes, depends_on=depends_on)


_NEGATIVE = re.compile(r"^(no|none|not|never|nothing)\b", re.I)


def _is_constraint(item: str) -> bool:
    """A line that states a limit rather than asks for a capability.

    The model writes these among the bullets — *"No network, no credentials"* —
    and putting one in front of the owner as something to grant is nonsense.
    """
    return bool(_NEGATIVE.match(item.strip()))
