"""The frozen task, and where its answer comes from.

A01 wants "frozen task contract and local fixture … negative controls". The
local fixture for low-dose CT is the one this repo already ships: the LDCT
benchmark's scorer, its judge, and the thresholds the field's experts fixed
before any agent ran — `ai4science/harness/agents/research_agents/runners/
domains.py`, `_score_ldct`/`_judge_ldct`. That is the part of the fixture that
is *in version control*. The paired TCIA reconstructions the scorer reads are a
~200 MB download under `AI4SCIENCE_DATA` and are not present on every host; see
`corpus.LDCT`. This task therefore uses the fixture's contract, not its pixels,
and says so rather than pretending a corpus is here.

The task: three candidate denoisers, described only by the metrics the fixture's
own scorer reports, are put to the benchmark's criterion. One is a genuine
restoration. **One is the negative control this field exists for** — a blur that
wins on PSNR and erases the lesion; the domain doc calls it "the blur that wins
on fidelity and fails the benchmark, kept in the suite permanently". One made
fidelity worse.

The answer key is not written here. It is COMPUTED by calling the repo's own
`_judge_ldct` on the frozen metrics, so the key cannot drift away from the
criterion it claims to encode: change the judge and the key changes with it, and
the task digest changes too, which is the point of sealing the digest into every
record.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence, Tuple

#: Where the criterion lives, cited so a reader can check it rather than trust
#: this docstring.
CRITERION_SOURCE = (
    "ai4science/harness/agents/research_agents/runners/domains.py::_judge_ldct "
    "(PSNR must exceed the untouched low-dose scan; lesion CNR >= 3, the Rose "
    "criterion; >= 50% of the inserted lesion contrast retained)")

#: Metric bundles in the fixture scorer's own field names (`_score_ldct`).
#: Values are plausible for this collection — ~100 HU noise at full dose,
#: 226-336 HU at low dose, a 150 HU 5 px lesion — and are frozen: editing one
#: changes the task digest and so invalidates every record sealed against it.
CASES: Tuple[Tuple[str, Dict[str, float]], ...] = (
    ("A", {"psnr": 33.0, "psnr_before": 28.0, "rmse_hu": 41.0,
           "noise_hu": 38.0, "noise_before_hu": 275.0,
           "lesion_cnr": 4.8, "lesion_contrast_retained": 0.81}),
    # The negative control: best PSNR of the three, lesion gone.
    ("B", {"psnr": 35.5, "psnr_before": 28.0, "rmse_hu": 32.0,
           "noise_hu": 17.0, "noise_before_hu": 275.0,
           "lesion_cnr": 1.9, "lesion_contrast_retained": 0.22}),
    ("C", {"psnr": 27.1, "psnr_before": 28.0, "rmse_hu": 56.0,
           "noise_hu": 44.0, "noise_before_hu": 275.0,
           "lesion_cnr": 4.4, "lesion_contrast_retained": 0.77}),
)

#: Which case is the negative control. A run that gets every other case right
#: and this one wrong has failed the task, whatever its score.
NEGATIVE_CONTROL = "B"

PROMPT = """\
You are judging candidate denoisers on a low-dose CT benchmark. The benchmark's
criterion was fixed by radiologists and medical physicists BEFORE any candidate
existed, and you may not substitute your own:

  1. PSNR of the restored image must EXCEED the PSNR of the untouched low-dose
     scan (`psnr` > `psnr_before`), otherwise the restoration made it worse.
  2. Lesion CNR must be at least 3.0 (the Rose criterion for reliable
     detection).
  3. At least 50% of the inserted lesion's peak contrast must survive
     (`lesion_contrast_retained` >= 0.5).

A candidate PASSES only if all three hold. A fidelity gain with the lesion
smoothed away is a FAILURE, not a mixed result.

Here are the measured metrics for three candidates:

{cases}

Answer with exactly one line per candidate and nothing else, in this form:

A: PASS
B: PASS
C: PASS

replacing PASS with FAIL where the criterion is not met."""


def _cases_block() -> str:
    return "\n".join(
        "%s: %s" % (name, ", ".join("%s=%g" % (k, m[k]) for k in sorted(m)))
        for name, m in CASES)


@dataclass(frozen=True)
class FrozenTask:
    task_id: str
    prompt: str
    answer_key: Mapping[str, bool]        # case -> passes
    reasons: Mapping[str, Sequence[str]]  # case -> the judge's own reasons
    criterion_source: str
    fixture: Dict[str, Any]

    @property
    def digest(self) -> str:
        """Hash of everything that decides what a correct answer is."""
        body = {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "answer_key": dict(self.answer_key),
            "criterion_source": self.criterion_source,
            "fixture": self.fixture,
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")).hexdigest()

    # -- grading ----------------------------------------------------------
    def parse(self, output: str) -> Dict[str, bool]:
        """Read `A: PASS` lines out of a model's output.

        Tolerant of surrounding prose and of markdown emphasis, because a model
        that answers correctly in a slightly different shape has not got the
        science wrong and a parser that says it did would make the reference
        measure formatting.
        """
        got: Dict[str, bool] = {}
        for raw in output.splitlines():
            line = raw.strip().strip("*` -")
            if ":" not in line:
                continue
            name, _, rest = line.partition(":")
            name = name.strip().strip("*`").upper()
            if name not in {c for c, _ in CASES}:
                continue
            verdict = rest.strip().strip("*`.").upper()
            if verdict.startswith("PASS"):
                got[name] = True
            elif verdict.startswith("FAIL"):
                got[name] = False
        return got

    def grade(self, output: str) -> Dict[str, Any]:
        """Score one output against the key. Deterministic, no model involved."""
        got = self.parse(output)
        per_case = {name: (name in got and got[name] == self.answer_key[name])
                    for name in self.answer_key}
        answered = [n for n in self.answer_key if n in got]
        correct = sum(1 for v in per_case.values() if v)
        nc = NEGATIVE_CONTROL
        return {
            "score": round(correct / len(self.answer_key), 6),
            "correct": correct,
            "of": len(self.answer_key),
            "unanswered": sorted(n for n in self.answer_key if n not in got),
            "per_case": per_case,
            "negative_control": nc,
            "negative_control_passed": per_case.get(nc, False),
            "answered": sorted(answered),
        }


_TASK: FrozenTask | None = None


def ldct_judge_task() -> FrozenTask:
    """Build the frozen task, computing the key with the repo's own judge."""
    global _TASK
    if _TASK is not None:
        return _TASK
    from ai4science.harness.agents.research_agents.runners.domains import (
        _judge_ldct)
    key, reasons = {}, {}
    for name, metrics in CASES:
        verdict = _judge_ldct(dict(metrics))
        key[name] = bool(verdict.passed)
        reasons[name] = tuple(verdict.reasons)
    _TASK = FrozenTask(
        task_id="ldct-judge-3-candidates/1",
        prompt=PROMPT.replace("{cases}", _cases_block()),
        answer_key=key,
        reasons=reasons,
        criterion_source=CRITERION_SOURCE,
        fixture={
            "corpus": "ldct (TCIA LDCT-and-Projection-data)",
            "corpus_present": False,
            "what_is_local": "the scorer, the judge and the expert-fixed "
                             "thresholds, in version control",
            "what_is_not_local": "the paired full/low-dose reconstructions "
                                 "themselves (~200 MB under AI4SCIENCE_DATA)",
            "cases": {name: dict(m) for name, m in CASES},
        },
    )
    return _TASK


class _Lazy:
    """`LDCT_JUDGE_TASK` without importing numpy/scipy at import time."""

    def __getattr__(self, name: str) -> Any:
        return getattr(ldct_judge_task(), name)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return repr(ldct_judge_task())


LDCT_JUDGE_TASK = _Lazy()
