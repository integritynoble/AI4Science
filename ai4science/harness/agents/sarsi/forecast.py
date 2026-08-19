"""`L3` — how well-calibrated this worker is.

`competence.py` answers *what has it proven*. This answers a harder and more
useful question: **when it says something will work, is it right?** A worker
that succeeds 70% of the time and says 70% is more useful than one that succeeds
90% of the time and claims 100%, because only the first can be planned around.

Calibration needs a forecast, and a forecast has one property that makes it
evidence rather than narration:

  **It must be made BEFORE the outcome.** Not a convention — enforced.
  `record()` raises on a task that already has a verdict. A number written
  afterwards is a story about the past wearing the costume of a prediction: it
  would score perfectly and mean nothing. This is the same rule that keeps L7
  self-report out of `competence`, moved earlier in time.

Three refusals are inherited from `competence.py` deliberately, because the
failure modes are identical:

  **Unmeasured is `None`, never zero.** A Brier score of `0.0` is *perfect*
  calibration. Returning it for "nothing forecast yet" would be the most
  flattering possible lie this module could tell.

  **The score never travels alone.** A Brier number is uninterpretable without
  its sample size and a baseline. `0.25` is what always-saying-50% scores, and
  a forecaster below that has added nothing.

  **It may narrow, never widen.** Good calibration cannot buy a skipped check.
  `may_widen()` exists to be called and always refuses.

**Nothing forecasts automatically yet.** The mechanism, the scoring and the
self-model claim are here; a worker that predicts its own odds needs a model
call at plan time, which is a separate decision. Until then a forecast is the
owner's to record, and a worker with none says so rather than implying it has
never been wrong.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config


class TooLate(Exception):
    """A forecast offered after the outcome. Refused, and says so."""


def record(config: Config, agent: Agent, task, p: float, *, why: str = "",
           now=time.time):
    """Record a pre-action forecast: the probability this task will be VERIFIED.

    Refuses once a verdict exists. That refusal is the whole basis of the
    measurement — a forecast made after the fact scores perfectly and means
    nothing — so it raises rather than returning a flag nobody checks.
    """
    from ai4science.harness.agents.sarsi import task as tsk
    value = float(p)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"a forecast is a probability in [0, 1]; got {p!r}")
    if (task.verdict or {}).get("state"):
        raise TooLate(
            f"{task.id} has already been judged — a forecast recorded now is "
            f"not a forecast. Record it before the work is verified, or not at "
            f"all.")
    task.forecast = {"p": value, "at": float(now()), "why": (why or "").strip()}
    tsk._save(agent, task)
    return task


def _outcome(task) -> Optional[bool]:
    """True, False, or None for "not evidence" — the same rule as competence."""
    s = str((task.verdict or {}).get("state") or "").strip().lower()
    if s.startswith("pass"):
        return True
    if s.startswith("fail"):
        return False
    return None


def scored(config: Config, agent: Agent) -> List[Any]:
    """Tasks that were BOTH forecast and judged. Everything else is an absence.

    A forecast with no verdict is not yet evidence; a verdict with no forecast
    is evidence about competence and says nothing about calibration.
    """
    from ai4science.harness.agents.sarsi import task as tsk
    try:
        rows = list(tsk.all_of(config, agent))
    except Exception:
        return []
    return [t for t in rows
            if (t.forecast or {}).get("p") is not None and _outcome(t) is not None]


def calibration(config: Config, agent: Agent) -> Optional[Dict[str, Any]]:
    """Brier score over pre-action forecasts, or `None` when there are none.

    `None`, never `0.0`. The caller must be able to tell "never forecast" from
    "forecast perfectly", and those are opposite claims.
    """
    rows = scored(config, agent)
    n = len(rows)
    if n == 0:
        return None

    ps = [float(t.forecast["p"]) for t in rows]
    ys = [1.0 if _outcome(t) else 0.0 for t in rows]
    brier = sum((p - y) ** 2 for p, y in zip(ps, ys)) / n

    observed = sum(ys) / n
    predicted = sum(ps) / n
    # Positive: it predicted LESS than it achieved (underconfident). Negative:
    # it promised more than it delivered — the fault that gets an owner hurt.
    bias = observed - predicted

    # What a forecaster must beat to have added anything. 0.25 is always-50%;
    # the base rate is the harder, honest baseline once there is enough data to
    # know it.
    uninformed = 0.25
    base_rate = sum((observed - y) ** 2 for y in ys) / n

    return {"agent": agent.id, "brier": round(brier, 4), "n": n,
            "observed": round(observed, 4), "predicted": round(predicted, 4),
            "bias": round(bias, 4),
            "uninformed": uninformed,
            "base_rate": round(base_rate, 4),
            "beats_uninformed": brier < uninformed,
            "beats_base_rate": brier < base_rate}


#: How far the average forecast may sit from the observed rate before it is
#: worth naming as a direction rather than noise. Small samples wander.
_BIAS_FLOOR = 0.10


def render(cal: Optional[Dict[str, Any]]) -> str:
    """One line an owner can read, including when there is nothing to say."""
    if not cal:
        return ("no forecasts scored yet — nothing has been predicted before it "
                "was judged, so how calibrated I am is unmeasured")

    line = ("Brier %.3f over %d scored forecast%s (predicted %.0f%%, achieved "
            "%.0f%%)" % (cal["brier"], cal["n"], "" if cal["n"] == 1 else "s",
                         cal["predicted"] * 100, cal["observed"] * 100))
    if not cal["beats_uninformed"]:
        line += " — worse than always saying 50%"
    if cal["bias"] <= -_BIAS_FLOOR:
        line += " — overconfident: I promise more than I deliver"
    elif cal["bias"] >= _BIAS_FLOOR:
        line += " — underconfident: I deliver more than I promise"
    return line


def may_widen(*_args, **_kwargs) -> bool:
    """Always False, and it exists to be called.

    Calibration may NARROW what a worker does — add a confirmation when it is
    unsure, decline a round, ask earlier. It may never widen it. A well-
    calibrated agent that skips a check has bought autonomy with correctness,
    which is the trade the governance plane exists to prevent.
    """
    return False
