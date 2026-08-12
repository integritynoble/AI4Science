"""Where a measured number waits between one process and the next.

`SelfModel.observe()` is the only way a number enters a self-model, and
`registry.build()` hands out a FRESH agent per process. Those two facts together
meant the drug-design benchmark could produce a real EF number and
`selfmodel-report`, running minutes later in another process, would still print
seven `unmeasured` rows. Neither half was wrong; there was no floor under them.
This module is that floor: the scoring path writes a row, and `build()` replays
the rows back through `observe()`.

What it refuses to be:

  * **It grants nothing.** `replay()` returns a count of rows applied. A count
    is not a permission, and `SelfModel.authority()` raises exactly as loudly
    with a full store as with an empty one.
  * **It computes no aggregate the judge did not compute.** No mean across
    seeds, no best-of, no confidence interval. A row is one run's number. An
    average of six nights is a quantity no benchmark ever produced, and
    inventing it here would put a figure in the self-model that traces to no
    single run — which is refusal (1) with extra steps.
  * **It will not record a run the field's own judge refused.** See
    `record_run`.

And it sets nothing directly. Every value goes in through `observe()`, so the
four refusals in `selfmodel.py` apply to a replayed number exactly as they apply
to a fresh one. A second door into the model would be a second place to keep
them, and the second place is always the one that rots.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


def store_root() -> Path:
    """Where the rows live.

    Resolved at CALL time rather than at import: a test points the store at a
    tmp_path with `monkeypatch.setenv`, and a module-level constant would have
    frozen the real path before the test got the chance.

    Outside the repository by default, because data is not source — the same
    convention, and the same reasoning, as the seed cache in runners/common.py.
    """
    return Path(os.environ.get("AI4SCIENCE_SELFMODEL_STORE",
                               str(Path.home() / ".ai4science" / "selfmodel")))


def path_for(agent: str) -> Path:
    return store_root() / ("%s.jsonl" % agent)


def _evidence(bench, ob, value: float, seed: int) -> str:
    """The sentence that has to survive being read by a stranger.

    Composed HERE, from the run, and never accepted from a caller. `observe()`
    already refuses a value with no evidence; a value whose evidence is a
    sentence somebody typed passes that check while defeating it, because the
    string then attests to whatever its author wanted it to attest to. Every
    clause below is read off the run: which metric and what it came out at,
    which seed, which agent and benchmark, that the field's own judge passed it,
    where the data came from, and that the scoring happened outside the sandbox
    against a key the solver never saw.
    """
    parts = ["%s = %.6g on %s/%s at seed %d"
             % (ob.metric, value, bench.agent, bench.package, seed),
             "passed this benchmark's own judge",
             bench.provenance(),
             "scored outside the sandbox against the withheld answer key (%s)"
             % (", ".join(bench.answer_key) or "none declared")]
    if ob.note:
        parts.append(ob.note)
    return "; ".join(parts)


def record_run(bench, *, seed: int, metrics: Dict[str, float], verdict,
               params: Dict[str, float],
               run_workspace: str) -> List[Dict[str, Any]]:
    """Write what this run measured. Called from the scoring path, nowhere else.

    Returns the rows written, which is often none: most of this function is the
    list of runs that are not measurements of the agent's capability.
    """
    observes = getattr(bench, "observes", ())
    # The benchmark has not said which dimension any of its metrics measures.
    # That mapping is the benchmark's to declare, so silence here means there is
    # nothing to record — not that something should be guessed.
    if not observes:
        return []

    # A declared pair naming a metric the scorer does not produce is a wiring
    # mistake, and it is loud at the source rather than a row that quietly never
    # appears. Checked before any refusal below so that the first run finds it,
    # pass or fail, and before anything is written so a bad pair cannot leave
    # half a run in the file.
    for ob in observes:
        if ob.metric not in metrics:
            raise ValueError(
                "%s declares that %r measures %r, but score() returned no such "
                "metric — have: %s"
                % (bench.agent, ob.metric, ob.dimension,
                   ", ".join(sorted(metrics))))

    # A number the field's judge refused is not a measurement of capability.
    # The screening judge refuses a saturated EF@1% precisely because it "cannot
    # rank one method above another"; recording it as this agent's competence
    # would launder a figure the benchmark just said means nothing.
    if not verdict.passed:
        return []

    # A search candidate is a proposal about a METHOD, not a measurement of the
    # agent's shipped capability. Averaging or last-writing a night of
    # candidates into the self-model would report whichever variant happened to
    # run last, under a dimension that claims to describe the agent.
    if dict(params or {}) != bench.defaults():
        return []

    at = time.time()
    rows: List[Dict[str, Any]] = []
    for ob in observes:
        value = float(metrics[ob.metric])
        rows.append({
            "agent": bench.agent,
            "dimension": ob.dimension,
            "metric": ob.metric,
            "value": value,
            "seed": seed,
            "params": dict(params or {}),
            "package": bench.package,
            "corpus": bench.corpus,
            "real": bench.real,
            "provenance": bench.provenance(),
            "judge": list(verdict.reasons),
            "evidence": _evidence(bench, ob, value, seed),
            "metrics": {k: float(v) for k, v in metrics.items()},
            "run_workspace": str(run_workspace),
            "at": at,
        })

    p = path_for(bench.agent)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return rows


def replay(model) -> int:
    """Apply every stored row for this agent, in file order, through `observe()`.

    In file order and with no arbitration: later rows overwrite earlier ones
    because that is what `observe()` does, and picking a winner any other way —
    the highest, the one with the most seeds — would be this module computing an
    aggregate on the judge's behalf.

    A row that cannot be replayed raises. It is tempting to skip it and carry
    on, and that is precisely the failure this whole path exists to close: a
    number a run produced, silently absent from the report, with the report
    still saying `unmeasured` as though nothing had been run.
    """
    p = path_for(model.agent)
    if not p.exists():
        return 0
    n = 0
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            model.observe(row["dimension"], row["value"],
                          evidence=row["evidence"], now=row["at"])
        except Exception as exc:
            raise ValueError(
                "%s line %d cannot be replayed into %s's self-model: %s: %s\n"
                "  row: %s"
                % (p, i, model.agent, type(exc).__name__, exc, line[:400])
            ) from exc
        n += 1
    return n
