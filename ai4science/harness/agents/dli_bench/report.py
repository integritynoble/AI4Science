"""The report. The frontier table is the result; the DL label is a caption.

Four things are always printed, because leaving any of them out is how a
delegation number stops meaning anything:

  * the frontier across budgets and reliabilities, not one number;
  * who accepted, and how much of the criteria the system wrote itself;
  * human load in seconds, and the latency inside it;
  * what the suite did not cover, including the levels it cannot pose at all.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .frontier import (BANDS, Cell, Frontier, attempts_for, ceiling, cells,
                       frontier, level, per_family)
from .spec import BUDGETS, Episode, TaskSpec


def frontier_table(cs: Dict[Tuple[str, str], Cell],
                   ps: Sequence[float] = (0.70, 0.80, 0.90, 0.95),
                   budgets: Sequence[str] = ("H0", "H1", "H2", "H3")) -> str:
    """The table the whole exercise is for.

    Rows are intervention budgets, columns reliability thresholds, cells the
    hardest band held. This is the measurement; ``DL4`` is a caption for it.
    """
    w = 14
    out = ["%-6s" % "" + "".join(("p>=%.2f" % p).rjust(w) for p in ps)]
    out.append("-" * (6 + w * len(ps)))
    for h in budgets:
        row = ["%-6s" % h]
        for p in ps:
            row.append(frontier(cs, h, p).label().rjust(w))
        out.append("".join(row))
    out.append("")
    out.append("Blank cells are not failures: a cell is blank when the run was")
    out.append("too short to establish that reliability, or had no episodes.")
    out.append("")
    out.append("Flawless attempts needed, before any p can be established:")
    out.append("  " + "   ".join("p>=%.2f: %d" % (p, attempts_for(p)) for p in ps))
    seen = sorted({c.attempts for c in cs.values() if c.attempts}, reverse=True)
    if seen:
        out.append("  largest cell in this run: %d attempts, which caps it at p>=%.2f"
                   % (seen[0], ceiling(seen[0])))
    return "\n".join(out)


def required_reliability(tasks: Dict[str, TaskSpec]) -> str:
    """What each class demands, against what a benchmark conventionally quotes.

    ``p`` is not the evaluator's to choose. A class with expensive failure
    fixes a floor, and quoting a frontier at 0.90 on such a class reports one
    the class does not permit.
    """
    rows = sorted({(t.family, t.level, round(t.loss.p_star, 3)) for t in tasks.values()})
    out = ["%-10s %-8s %10s   %s" % ("family", "level", "p* required", "0.90 convention")]
    out.append("-" * 62)
    for fam, lvl, ps in rows:
        verdict = "too lenient" if ps > 0.90 else ("stricter than needed" if ps < 0.90 else "matches")
        out.append("%-10s %-8s %10.3f   %s" % (fam, lvl, ps, verdict))
    return "\n".join(out)


def acceptance_block(episodes: Sequence[Episode]) -> str:
    if not episodes:
        return "no episodes"
    loci: Dict[str, int] = {}
    for e in episodes:
        loci[e.acceptance_locus] = loci.get(e.acceptance_locus, 0) + 1
    sigma = sum(e.sigma for e in episodes) / len(episodes)
    unknown = sum(1 for e in episodes if e.verifier_false_pass_rate is None)
    self_accepted = loci.get("alpha0", 0)
    out = ["acceptance locus: " + ", ".join("%s=%d" % kv for kv in sorted(loci.items()))]
    if self_accepted:
        out.append("  %d episode(s) were accepted by the system that performed them "
                   "and are EXCLUDED -- that is an assertion, not a level."
                   % self_accepted)
    out.append("mean sigma (share of criteria the system wrote): %.3f" % sigma)
    out.append("  sigma rises with the level by construction. A DL6 or higher "
               "claim needs it bounded below 1 by structure, not by intent.")
    out.append("verifier false-pass rate unknown on %d of %d episodes"
               % (unknown, len(episodes)))
    return "\n".join(out)


def load_block(episodes: Sequence[Episode]) -> str:
    if not episodes:
        return "no episodes"
    n = len(episodes)
    load = sum(e.load() for e in episodes) / n
    td = sum(e.t_delta_total for e in episodes) / n
    cids: Dict[int, int] = {}
    for e in episodes:
        for i in e.interventions:
            cids[i.cid] = cids.get(i.cid, 0) + 1
    gov = sum(1 for e in episodes for i in e.interventions if not i.cognitive)
    cog = sum(1 for e in episodes for i in e.interventions if i.cognitive)
    esc = sum(1 for e in episodes if e.outcome == "escalated")
    out = ["mean human load: %.1f s per episode, of which %.1f s is waiting (T_delta)"
           % (load, td)]
    out.append("interventions: %d cognitive, %d governance (governance does not "
               "lower the level)" % (cog, gov))
    out.append("CID distribution: " + (", ".join("CID%d=%d" % kv for kv in sorted(cids.items()))
                                       or "none"))
    out.append("escalations: %d -- an escalation costs load, not reliability" % esc)
    return "\n".join(out)


def full_report(episodes: Sequence[Episode], tasks: Dict[str, TaskSpec],
                system: str = "system under test") -> str:
    from .tasks import COVERAGE, missing_levels

    cs = cells(episodes, tasks)
    fams = per_family(episodes, tasks)
    L = ["DLI-Bench report", "=" * 16, "", "system: %s" % system,
         "episodes: %d" % len(episodes), "", "THE FRONTIER", "-" * 12, "",
         frontier_table(cs), "", "WHAT EACH CLASS REQUIRES", "-" * 24, "",
         required_reliability(tasks), "", "ACCEPTANCE", "-" * 10, "",
         acceptance_block(episodes), "", "HUMAN COST", "-" * 10, "",
         load_block(episodes), "", "LEVEL, PER FAMILY", "-" * 17, ""]
    for f, lv in sorted(fams.items()):
        L.append("  %-12s %s" % (f, lv))
    L += ["", "  The general label is the MINIMUM across families. One domain "
          "does not", "  set the level: a system at DL4 on software and DL2 on "
          "research is not DL4.", "", "WHAT THIS DID NOT COVER", "-" * 23, ""]
    absent = missing_levels()
    for lv in absent:
        L.append("  %-8s %s" % (lv, COVERAGE[lv]))
    if not absent:
        L.append("  Every level is posed by something.")
    # Every level being posed is not the same as coverage being complete, and
    # printing only the first would read as the second.
    try:
        from .catalog import crosswalk, load
        cards = load()
        xw = crosswalk(cards)
        gaps: Dict[str, List[str]] = {}
        for c in cards:
            if not xw[c.task_id]:
                gaps.setdefault(c.level, [])
                if c.family not in gaps[c.level]:
                    gaps[c.level].append(c.family)
        if gaps:
            L += ["", "  Specified but not posed, by level and family:"]
            for lv in sorted(gaps):
                L.append("    %-9s %s" % (lv, ", ".join(sorted(gaps[lv]))))
            n = sum(1 for c in cards if not xw[c.task_id])
            L.append("    %d of %d catalogue cards have nothing that can run them."
                     % (n, len(cards)))
    except Exception:                       # the catalogue is optional
        pass
    L += ["", "  A suite that covers less than its scale must say so. What is "
          "absent here", "  is absent from the evidence, not passed."]
    return "\n".join(L)
