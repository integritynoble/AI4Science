"""Scripted policies, so the environments can be shown to open as well as close.

Each environment gets two. The **competent** policy does what the level asks
and must pass. The **naive** one plays the way an agent actually plays when it
is not doing the level -- it acts on the brief without checking the world,
commits on surface signal, and never persists anything -- and must fail.

Both are policies, not solvers with the key: they see only what
``observe``/``act`` return. The scoring they are checked against reads hidden
state they never touched.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .charter import CharterEnv
from .core import Environment
from .mission import MissionEnv, COMPONENTS
from .project import MODELS, ProjectEnv


# ------------------------------------------------------------------ DL4

def project_competent(env: ProjectEnv) -> None:
    """Look before using; average before deciding; checkpoint before it is needed."""
    srcs = env.act("list_sources")["sources"]

    # Inspect everything first. The corruption is only visible to whoever looks.
    quality: Dict[str, float] = {}
    for s in srcs:
        r = env.act("inspect_source", id=s)
        if "error" in r:
            continue
        quality[s] = r["null_fraction"] + r["duplicate_fraction"]
    corrupt = max(quality, key=lambda k: quality[k]) if quality else None
    good = sorted(quality, key=lambda k: quality[k])
    use = good[0] if good else srcs[0]

    # Clean the bad one rather than discarding it: it is still data.
    if corrupt is not None:
        env.act("clean", source=corrupt, method="dedupe_and_bound")

    env.act("checkpoint", blob={"phase": "surveyed", "use": use, "corrupt": corrupt,
                                "scores": {}})

    scores: Dict[str, List[float]] = {}
    dead_seen: set = set()
    for rep in range(10):
        for model in MODELS:
            if model in scores and scores[model] == []:
                continue                      # known not to apply here
            if use in env.observe()["sources_offline"]:
                dead_seen.add(use)
                alive = [s for s in env.observe()["sources_online"] if s != corrupt]
                if not alive:
                    break
                use = alive[0]                # replan around the outage
            r = env.act("run_experiment", model=model, source=use)
            if r.get("error") and "converge" in str(r.get("error")):
                scores.setdefault(model, [])
                continue
            if "validation_score" in r:
                scores.setdefault(model, []).append(r["validation_score"])
        if rep in (2, 6):
            env.act("checkpoint", blob={"phase": "experimenting", "use": use,
                                        "corrupt": corrupt, "scores": scores})
        if env.observe()["was_interrupted"]:
            blob = env.act("resume")["blob"] or {}
            scores = {k: list(v) for k, v in (blob.get("scores") or {}).items()}
            use = blob.get("use", use)
            corrupt = blob.get("corrupt", corrupt)

    if env.observe()["was_interrupted"]:
        env.act("resume")

    live = {k: v for k, v in scores.items() if v}
    best = max(live, key=lambda k: sum(live[k]) / len(live[k])) if live else None
    mean = (sum(live[best]) / len(live[best])) if best else 0.0
    dead = [k for k, v in scores.items() if not v]
    env.act("submit", best_model=best, score=round(mean, 4),
            sources_used=[use],
            notes=("compared %s over %d runs each; %s did not converge on this "
                   "data and is reported as inapplicable rather than scored"
                   % (", ".join(sorted(live)), len(live.get(best, [])) if best else 0,
                      ", ".join(dead) or "nothing")))


def project_naive(env: ProjectEnv) -> None:
    """Trusts the brief. One run each, no inspection, nothing persisted."""
    srcs = env.act("list_sources")["sources"]
    use = srcs[0]
    scores: Dict[str, float] = {}
    for model in MODELS:
        r = env.act("run_experiment", model=model, source=use)
        if "validation_score" in r:
            scores[model] = r["validation_score"]
        else:
            scores[model] = 0.5          # invented, because the brief said three
    best = max(scores, key=lambda k: scores[k])
    env.act("submit", best_model=best, score=scores[best], sources_used=[use],
            scores=scores, notes="compared all three approaches")


# ------------------------------------------------------------------ DL6

def mission_competent(env: MissionEnv) -> None:
    """Re-reads the world after every notice, and lets it change the plan."""
    known: Dict[str, str] = {}
    for c in COMPONENTS:
        r = env.act("inspect", component=c)
        known[c] = r["recommended_method"]
    breaking = None
    r = env.act("inspect", component=COMPONENTS[0])
    warn = str(r.get("compatibility_warning", ""))
    for m in ("rebuild", "patch", "reroute", "rewrite"):
        if "'%s'" % m in warn or '"%s"' % m in warn or m in warn:
            breaking = m
            break

    opened: List[str] = []
    dropped: List[str] = []
    for round_no in range(4):
        met = env.act("metrics")["components"]
        # Only what still matters: a component with no load and no errors is
        # not work, whatever the earlier plan said.
        todo = [c for c, v in met.items()
                if v["error_rate"] > 0.03 and v["load"] > 0.2
                and c not in env.observe()["fixes_applied"]]
        todo.sort(key=lambda c: -met[c]["error_rate"] * met[c]["load"])
        if not todo:
            break
        # One project per component. Batching them would report fewer projects
        # than the agent actually ran, and the count is part of the evidence.
        for c in todo[:2]:
            name = "p%s_%d" % (c, round_no + 1)
            env.act("open_project", name=name, goal="reduce error rate on %s" % c)
            env.act("add_task", project=name, task="confirm the cause on %s" % c)
            env.act("add_task", project=name, task="apply the recommended method")
            opened.append(name)
            meth = known.get(c)
            if meth and meth != breaking:
                env.act("apply_fix", component=c, method=meth)
            env.act("close_project", name=name, why="handled")
            if env.observe()["budget_remaining"] < 15:
                dropped.append("remaining low-load components, after the budget cut")
                break
        if dropped:
            break

    env.act("report",
            summary="worked the components carrying load, in error-rate order, "
                    "reprioritising after each change in the world",
            dropped="; ".join(dropped) or "nothing was dropped")


def mission_naive(env: MissionEnv) -> None:
    """Makes a plan at the start and executes it. Never looks again."""
    met = env.act("metrics")["components"]
    plan = sorted(met, key=lambda c: -met[c]["error_rate"])[:3]
    env.act("open_project", name="cleanup", goal="fix the top three")
    env.act("add_task", project="cleanup", task="fix them")
    for c in plan:
        for meth in ("rebuild", "patch", "reroute"):
            env.act("apply_fix", component=c, method=meth)
    # Keeps working the first component in the plan, whatever the world did.
    for _ in range(3):
        env.act("inspect", component=plan[0])
    env.act("report", summary="executed the plan")


# --------------------------------------------------------------- DLOmega

def charter_competent(env: CharterEnv) -> None:
    """Buys evidence before committing, and prefers what opens the frontier."""
    solved_any = True
    mission_no = 0
    checked: Dict[str, Dict[str, Any]] = {}

    while solved_any and env.observe()["budget_remaining"] > 20:
        solved_any = False
        open_qs = env.act("survey")["open_questions"]
        # Investigate before believing the surface. A high promise with no
        # evidence behind it is exactly what a distractor looks like.
        for q in list(open_qs)[:6]:
            if q in checked:
                continue
            r = env.act("investigate", q=q, effort=2.0)
            if "is_substantive" in r:
                checked[q] = r
            if env.observe()["budget_remaining"] < 20:
                break

        # Prefer what unlocks. A cheap dull question that opens three others is
        # worth more than an expensive bright one that opens none.
        candidates = [q for q, v in checked.items()
                      if v.get("is_substantive") and q in env._reachable()
                      and q not in env.observe()["established"]]
        candidates.sort(key=lambda q: -len(checked[q].get("unlocks") or []))
        for q in candidates:
            if env.observe()["budget_remaining"] < 10:
                break
            mission_no += 1
            name = "m%d" % mission_no
            env.act("register_mission", name=name, targets=[q])
            r = env.act("attempt", q=q, method=checked[q]["method_required"])
            env.act("close_mission", name=name,
                    outcome="validated" if r.get("validated") else "not validated")
            if r.get("validated"):
                solved_any = True
                break              # re-survey: the frontier just moved

    env.act("report", summary="investigated before committing; ordered by what "
                              "each finding made reachable")


def charter_naive(env: CharterEnv) -> None:
    """Chases the strongest surface signal, which is what a distractor is for."""
    for i in range(6):
        open_qs = env.act("survey")["open_questions"]
        if not open_qs:
            break
        q = max(open_qs, key=lambda k: open_qs[k]["promise"])
        env.act("register_mission", name="m%d" % (i + 1), targets=[q])
        for meth in ("bisect", "ablate", "replicate", "model"):
            r = env.act("attempt", q=q, method=meth)
            if r.get("validated"):
                break
        env.act("close_mission", name="m%d" % (i + 1), outcome="done")
        if env.observe()["budget_remaining"] < 10:
            break
    env.act("report", summary="worked the most promising questions first")


COMPETENT = {"dl4.project": project_competent, "dl6.mission": mission_competent,
             "dlomega.charter": charter_competent}
NAIVE = {"dl4.project": project_naive, "dl6.mission": mission_naive,
         "dlomega.charter": charter_naive}
