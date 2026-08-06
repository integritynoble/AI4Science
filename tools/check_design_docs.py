#!/usr/bin/env python3
"""Do the three design sources still agree?

Three documents describe one system, and they drift:

  * `docs/AI4SCIENCE_ONE_MACHINE_DESIGN.md` — the design of record
  * `<singularity>/docs/specs/2026-08-04-sarsi-agent-market-and-pwm-design.md`
  * `docs/research-agents/` — one page per research agent, plus its scope and
    roster objects

On 2026-08-06 they disagreed in **fourteen** ways at once: the record described
as a design a subsystem with 113 tests behind it, the market spec's §13b listed
five governor agents when eight had pages, the two copies of the research-agents
tree had forked in both directions, and a restructure had dropped the per-field
sub-ladder from every page — including the one the record had just linked to.

None of that was anyone being careless. It is what a document set does when the
only thing keeping it consistent is that somebody remembers. So the rules are
here, where they can fail:

  A. one roster — the pages, the scope objects, the roster objects and the code
     name the same agents, allowing for a **documented alias** and for pages
     that say plainly that nothing is built yet.
  B. the two copies of a page are byte-identical, or one of them is stale and
     nobody can tell which.
  C. the record and its mirror agree section by section.
  D. every `research-agents/...` link resolves from the file that makes it.

Run it: `python3 tools/check_design_docs.py [--singularity <dir>]`
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECORD = REPO / "docs/AI4SCIENCE_ONE_MACHINE_DESIGN.md"
RA = REPO / "docs/research-agents"

#: `imaging` is not a typo for `computational-imaging`. It had a runner before
#: research_agents existed (`agents/imaging/`, driven by `run_imaging_task`) and
#: registry.py records the reason. An alias with a stated reason is a fact about
#: history; the same alias undeclared is two names for one field.
ALIAS = {"imaging": "computational-imaging"}

#: Pages that are not agents.
NOT_AGENTS = {"README", "lifecycle", "medical-physics-3d-plan"}

#: A page may be absent from the code only if it says so in these words. This is
#: the check with teeth: an unbuilt agent whose page reads like a built one is
#: the failure the whole research-agents directory is written against.
SAYS_UNBUILT = ("nothing is built", "design only", "not built", "status: design")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def __call__(self, name: str, ok: bool, detail: str = "") -> None:
        print(("  ok    " if ok else "  FAIL  ") + name +
              (("\n          " + detail) if detail and not ok else ""))
        if not ok:
            self.failures.append(name)


def agent_pages(root: Path) -> set:
    return {p.stem for p in root.glob("*.md")} - NOT_AGENTS


def check(singularity: Path | None) -> int:
    r = Report()
    sd = singularity / "docs/specs" if singularity else None
    ra_sd = sd / "research-agents" if sd else None

    print("\nA. one roster")
    pages = agent_pages(RA)
    scope = {p.stem for p in (ra_sd / "scope").glob("*.json")} if ra_sd else None
    roster = {p.stem for p in (ra_sd / "roster").glob("*.json")} if ra_sd else None
    try:
        sys.path.insert(0, str(REPO))
        from ai4science.harness.agents import research_agents as ra_mod
        code = {ALIAS.get(n, n) for n in ra_mod.NAMES}
    except Exception as e:                                # pragma: no cover
        code = None
        print("        (code not importable: %s)" % e)

    if scope is not None:
        r("every page has a scope object", pages <= scope,
          "missing: %s" % sorted(pages - scope))
        r("every scope object has a page", scope <= pages,
          "orphaned: %s" % sorted(scope - pages))
    if roster is not None:
        r("every page has a roster object", pages <= roster,
          "missing: %s" % sorted(pages - roster))
    if code is not None:
        r("every implemented agent has a page", code <= pages,
          "implemented but undocumented: %s" % sorted(code - pages))
        for name in sorted(pages - code):
            text = (RA / (name + ".md")).read_text().lower()
            r("%s is absent from the code and its page says so" % name,
              any(s in text for s in SAYS_UNBUILT),
              "no page in this directory may read as built when it is not")

    if ra_sd is None:
        print("\n(no singularity checkout given — B and C skipped, which is not "
              "the same as passing)")
        print("\n%d failed" % len(r.failures))
        return 1 if r.failures else 0

    print("\nB. one copy of each page")
    for p in sorted(RA.glob("*.md")):
        q = ra_sd / p.name
        if q.exists():
            r("%s identical" % p.name, p.read_text() == q.read_text(),
              "%d vs %d lines — one of these is stale and the reader cannot tell which"
              % (len(p.read_text().splitlines()), len(q.read_text().splitlines())))
        else:
            r("%s exists in both trees" % p.name, False, "missing from %s" % ra_sd)

    print("\nC. the record and its mirror")
    mirror = sd / "2026-08-04-ai4science-one-machine-design.md"
    if mirror.exists():
        rec, mir = RECORD.read_text(), mirror.read_text()
        for start, end in (("## 11. The market", "## 11a."),
                           ("## 11b. Research agents", "## 12. Self-awareness"),
                           ("## 13. What runs it costs", "## 14. What this does not do")):
            def cut(t):
                i = t.find(start)
                return None if i < 0 else t[i:t.find(end, i)]
            a, b = cut(rec), cut(mir)
            r("%s agrees in both copies" % start.lstrip("# "), a is not None and a == b,
              "record=%s mirror=%s chars" % (len(a or ""), len(b or "")))

    print("\nD. links resolve")
    for path, base in ((RECORD, RA.parent), (mirror, sd),
                       (sd / "2026-08-04-sarsi-agent-market-and-pwm-design.md", sd)):
        if not path.exists():
            continue
        for link in sorted(set(re.findall(r"\]\((research-agents/[^)#]+)\)", path.read_text()))):
            r("%s -> %s" % (path.name[:34], link), (base / link).exists())

    print("\n%d failed" % len(r.failures))
    return 1 if r.failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--singularity", type=Path,
                    default=Path("/home/spiritai/pwm/singularity-docs"))
    a = ap.parse_args()
    sys.exit(check(a.singularity if a.singularity.exists() else None))
