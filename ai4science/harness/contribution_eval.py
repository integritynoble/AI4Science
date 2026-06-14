"""Contribution-improvement measurement — how much a user's tool / sub-agent
actually improves an agent, expressed as the `quality` multiplier the
agent-mining emission formula already consumes (w_k = usage x quality).

Usage measures *how often* a contribution is used; this module measures *how
much better* it makes the agent. The two combine in the per-agent pool:

    w_k = (Σ usage weight_units over k) × quality_k          (agent-mining §8)

where quality_k is the eval-delta produced here. A contribution that is used a
lot but never improves an eval (quality≈baseline) earns little; one that lifts a
held-out benchmark earns proportionally more.

Method (deterministic, A/B eval-delta):
  1. Fix an eval suite for the agent: tasks each with a pure grader → score in [0,1].
  2. Run the agent on the suite WITHOUT the candidate (baseline registry) and
     WITH it (candidate registry). The runner is injected, so this module never
     calls an LLM itself — the harness/CI wires the real session, tests stub it.
  3. improvement = mean(candidate_score - baseline_score), clamped to >= 0.
  4. quality_k = 1 + GAIN * improvement  (improvement 0 → neutral 1.0).

The eval is the contribution-measurement primitive; mainnet/governance decides
GAIN and which suites are canonical. Held-out, rotating suites (anti-gaming) are
the §E6 hardening concern, not this primitive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# quality_k = 1 + QUALITY_GAIN * improvement. improvement is a score delta in
# [0,1]; gain 4.0 means a +0.25 mean lift doubles the contribution's weight.
QUALITY_GAIN = 4.0


@dataclass(frozen=True)
class EvalTask:
    """One graded task. grader maps the agent's transcript -> score in [0,1]."""
    task_id: str
    prompt: str
    grader: Callable[[str], float]
    weight: float = 1.0


@dataclass(frozen=True)
class ContributionCandidate:
    """A user-contributed improvement under test."""
    contribution_id: str
    agent_name: str
    kind: str                       # "tool" | "subagent"
    title: str = ""


@dataclass
class TaskResult:
    task_id: str
    baseline_score: float
    candidate_score: float
    weight: float

    @property
    def delta(self) -> float:
        return self.candidate_score - self.baseline_score


@dataclass
class ContributionScore:
    contribution_id: str
    agent_name: str
    kind: str
    baseline: float                 # weighted-mean baseline score
    candidate: float                # weighted-mean candidate score
    improvement: float              # max(0, candidate - baseline)
    raw_improvement: float          # signed (candidate - baseline), may be < 0
    quality: float                  # the quality_k multiplier for emission
    per_task: List[TaskResult] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "contribution_id": self.contribution_id,
            "agent_name": self.agent_name,
            "kind": self.kind,
            "baseline": round(self.baseline, 6),
            "candidate": round(self.candidate, 6),
            "improvement": round(self.improvement, 6),
            "raw_improvement": round(self.raw_improvement, 6),
            "quality": round(self.quality, 6),
            "per_task": [
                {"task_id": r.task_id, "baseline": round(r.baseline_score, 6),
                 "candidate": round(r.candidate_score, 6),
                 "delta": round(r.delta, 6), "weight": r.weight}
                for r in self.per_task
            ],
            "notes": self.notes,
        }


# A runner executes one task under one variant and returns the transcript text.
# variant is "baseline" (contribution absent) or "candidate" (contribution present).
RunFn = Callable[[EvalTask, str], str]


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def quality_from_improvement(improvement: float, *, gain: float = QUALITY_GAIN) -> float:
    """Map a non-negative mean score delta to the emission quality multiplier.

    improvement 0.0 -> 1.0 (neutral); never below 1.0 (a contribution that
    doesn't help earns the baseline multiplier, not a penalty — usage already
    gates that w_k toward zero)."""
    return 1.0 + gain * max(0.0, improvement)


def evaluate_contribution(
    candidate: ContributionCandidate,
    tasks: List[EvalTask],
    run: RunFn,
    *,
    gain: float = QUALITY_GAIN,
) -> ContributionScore:
    """A/B the agent on `tasks` with and without `candidate`; score the lift.

    `run(task, variant)` returns the agent's transcript for that task under
    "baseline" / "candidate". Grading is pure (task.grader) so the score is
    reproducible from the transcripts.
    """
    if not tasks:
        raise ValueError("at least one eval task is required")

    results: List[TaskResult] = []
    notes: List[str] = []
    for t in tasks:
        try:
            base_txt = run(t, "baseline")
            cand_txt = run(t, "candidate")
            bs = _clamp01(float(t.grader(base_txt)))
            cs = _clamp01(float(t.grader(cand_txt)))
        except Exception as exc:  # a flaky task scores 0/0 (neutral), is noted
            notes.append(f"{t.task_id}: eval error ({exc}); scored 0/0")
            bs = cs = 0.0
        results.append(TaskResult(task_id=t.task_id, baseline_score=bs,
                                  candidate_score=cs, weight=t.weight))

    total_w = sum(r.weight for r in results) or 1.0
    baseline = sum(r.baseline_score * r.weight for r in results) / total_w
    candidate_mean = sum(r.candidate_score * r.weight for r in results) / total_w
    raw = candidate_mean - baseline
    improvement = max(0.0, raw)

    return ContributionScore(
        contribution_id=candidate.contribution_id,
        agent_name=candidate.agent_name,
        kind=candidate.kind,
        baseline=baseline,
        candidate=candidate_mean,
        improvement=improvement,
        raw_improvement=raw,
        quality=quality_from_improvement(improvement, gain=gain),
        per_task=results,
        notes=notes,
    )


# --- Graders: reusable pure scorers for eval tasks -------------------------

def contains_grader(*needles: str, all_required: bool = True) -> Callable[[str], float]:
    """Score 1.0 if the transcript contains the needle(s)."""
    def _g(text: str) -> float:
        low = (text or "").lower()
        hits = [n.lower() in low for n in needles]
        if not hits:
            return 0.0
        return 1.0 if (all(hits) if all_required else any(hits)) else 0.0
    return _g


def threshold_grader(extract: Callable[[str], Optional[float]], target: float,
                     *, higher_is_better: bool = True) -> Callable[[str], float]:
    """Score by how a metric extracted from the transcript compares to target.

    Returns a graded ramp in [0,1] (not just pass/fail) so small reconstruction
    improvements still register — e.g. PSNR/score_q from a physics judge line.
    """
    def _g(text: str) -> float:
        v = extract(text or "")
        if v is None:
            return 0.0
        if higher_is_better:
            return _clamp01(v / target) if target > 0 else (1.0 if v > 0 else 0.0)
        return _clamp01(target / v) if v > 0 else 0.0
    return _g
