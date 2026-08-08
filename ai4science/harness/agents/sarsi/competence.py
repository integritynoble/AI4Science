"""`L4` — what this worker has been *verified* to do, aggregated.

Ported from the console's `sarsi/competence.py`. The self-model could say what
a worker **is** and what it is **holding**, and not what it has **proven**:
every verdict was already on disk and nothing read them back.

Four rules govern this module, and every one of them is a refusal.

  **Only verified outcomes count.** A task the verifier never judged, or refused
  to judge, is not evidence about capability. The worker's own account of how it
  went is `L7` and is not admitted here at any weight.

  **Unmeasured is `None`, never zero.** A worker with no verified outcomes has
  no competence estimate. Substituting `0.0` would make "we have never seen it
  work" indistinguishable from "we have seen it fail", and the second is a much
  stronger claim than the evidence supports.

  **The mean is never published alone.** `(k+1)/(n+2)` with its sample count and
  interval, because 1 of 1 and 100 of 100 are both "100%" and only one of them
  is worth acting on. A bare scalar is not a report.

  **It may narrow what a worker does. It may never widen it.** A strong record
  cannot turn a refused gate into an act, skip a verification, or answer a
  reserved class. Without that asymmetry, "I have been succeeding, so I will
  check less" becomes reachable — autonomy bought with correctness, which is
  exactly the trade the governance plane exists to prevent.

**One thing is added, because this system records something the console does
not.** An ai4science verdict carries `independent` — whether the engine that
judged is the engine that did the work. The system already states this in its
own output ("judged by the same engine that did the work"), and a self-judged
PASS is weaker evidence. Averaging the two together destroys precisely the
distinction the flag exists to make, so the split is reported and the headline
says how much of its own evidence it judged itself.

The estimator is Laplace-smoothed rather than `k/n` for a reason that shows up
immediately in practice: three lucky runs should not read as total reliability,
and `k/n` says exactly that.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

#: A verdict counts as evidence only if it is one of these. Anything else — a
#: refusal to judge, an error, a missing verdict — is not a failure. It is an
#: absence, and absences do not move a posterior.
PASSED = ("pass",)
FAILED = ("fail",)


def _outcome(task) -> Optional[bool]:
    """True, False, or None for "this task is not evidence".

    The third case is the one that matters. A task the verifier declined to
    judge tells us nothing about the worker, and counting it as a failure would
    charge the worker for the judge being unavailable.
    """
    v = (task.verdict or {}).get("state")
    s = str(v or "").strip().lower()
    if not s:
        return None
    if s.startswith(PASSED):
        return True
    if s.startswith(FAILED):
        return False
    return None


def outcomes(config: Config, agent: Agent) -> List[Any]:
    """Every judged task for this worker. Unjudged ones are simply absent."""
    from ai4science.harness.agents.sarsi import task as tsk
    try:
        rows = list(tsk.all_of(config, agent))
    except Exception:
        return []
    return [t for t in rows if _outcome(t) is not None]


def _posterior(rows: List[Any]) -> Dict[str, Any]:
    n = len(rows)
    k = sum(1 for t in rows if _outcome(t) is True)
    # Laplace, not k/n: three lucky runs are not certainty.
    p = (k + 1) / (n + 2)
    # The interval is published WITH the mean because 1-of-1 and 100-of-100 are
    # the same number and not the same claim.
    ci = 1.96 * math.sqrt(p * (1 - p) / (n + 3))
    return {"p": round(p, 4), "ci": round(ci, 4),
            "n": n, "passed": k, "failed": n - k}


def _is_independent(task) -> bool:
    return bool((task.verdict or {}).get("independent"))


def competence(config: Config, agent: Agent) -> Optional[Dict[str, Any]]:
    """The Beta-Bernoulli posterior over verified outcomes, or `None`.

    Returns `None` — not a zero, not a default — when nothing has been verified.
    The caller must be able to tell "no evidence" from "bad evidence", so this
    refuses to express the first as the second.
    """
    rows = outcomes(config, agent)
    if not rows:
        return None
    est = _posterior(rows)
    est["agent"] = agent.id
    # How much of its own evidence it judged itself. A single number hiding four
    # self-judged passes is the number an owner would act on wrongly.
    est["self_judged"] = sum(1 for t in rows if not _is_independent(t))
    est["source"] = "%d verified outcome%s" % (est["n"], "" if est["n"] == 1 else "s")
    return est


def by_independence(config: Config, agent: Agent) -> Dict[str, Dict[str, Any]]:
    """Split by whether the judge was the engine that did the work.

    The system already says "judged by the same engine that did the work" in its
    own verdicts. Aggregating across that line would average away the weaker
    claim into the stronger one.
    """
    rows = outcomes(config, agent)
    out: Dict[str, Dict[str, Any]] = {}
    for label, want in (("independent", True), ("self-judged", False)):
        group = [t for t in rows if _is_independent(t) is want]
        if group:
            out[label] = _posterior(group)
    return out


def by_ceiling(config: Config, agent: Agent) -> Dict[str, Dict[str, Any]]:
    """Competence split by the ceiling the work ran under.

    The same verdict reached under a wider grant is a weaker claim, and the task
    record already carries the ceiling for exactly that reason. Aggregating
    across tiers would average away the distinction the ladder exists to make.
    """
    buckets: Dict[str, List[Any]] = {}
    for t in outcomes(config, agent):
        tier = str((t.session or {}).get("ceiling") or "A1")
        buckets.setdefault(tier, []).append(t)
    return {tier: _posterior(rows) for tier, rows in sorted(buckets.items())}


def render(est: Optional[Dict[str, Any]]) -> str:
    """One line an owner can read, including when there is nothing to say.

    The unmeasured case gets a sentence rather than an empty string, because a
    blank reads as a rendering fault and invites the reader to supply their own
    number.
    """
    if not est:
        return "no verified outcomes yet"
    line = ("%.0f%% (±%.0f) over %d verified outcome%s — %d passed, %d failed"
            % (est["p"] * 100, est["ci"] * 100, est["n"],
               "" if est["n"] == 1 else "s", est["passed"], est["failed"]))
    if est.get("self_judged"):
        line += (" — but %d of those %s judged by the engine that did the work"
                 % (est["self_judged"],
                    "was" if est["self_judged"] == 1 else "were"))
    return line


def may_widen(*_args, **_kwargs) -> bool:
    """Always False, and it exists to be called.

    A competence estimate may NARROW what a worker does — add a confirmation,
    downgrade an action, decline a round — and may never widen it. Writing that
    as a function rather than a comment means a future caller reaching for "the
    record is good enough to skip this" finds a refusal instead of a convention,
    and finds it at the call site.
    """
    return False
