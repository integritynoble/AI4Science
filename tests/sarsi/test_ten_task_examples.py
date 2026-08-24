"""The ten real tasks, replayed as a corpus.

On 2026-08-24 ten tasks were run end to end — a real worker on isolated state,
a real headless `claude -p` as `sarsi-claude`, and `verify.check` as the judge
with the model verifier stubbed to always FAIL. Six of the ten reached
`verified` while quietly not doing what the owner asked, and `task.goal_drift`
was built from reading them.

The tuning of that function is the whole of its value. An earlier version
compared every content word and fired on nine of ten, tripping over
`named`/`def` and `design`/`DESIGN.md`; a report that speaks that often is one
nobody reads. So the claim worth defending is not "it detects drift" but the
exact firing SET: these six and not those four.

A number in a prose report rots silently. `fixtures/ten_task_examples.json`
holds the goal and the plan `sarsi-claude` actually wrote for each of the ten,
verbatim from the run, so the claim is settled by running it.

Narrative and raw log: `singularity/docs/examples/2026-08-24-*`.
"""
import json
import pathlib

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             task as tsk, worker as wk)

CORPUS = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "ten_task_examples.json")
    .read_text())


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def agent(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c, c.agents["sarsi-worker"]


def _replay(agent, case):
    """File the owner's goal, then put the session's real plan0.md beside it.

    Deliberately NOT via `attach_plan`: what drifted is the plan FILE the
    session wrote, and `goal_drift` reads that file for exactly the reason
    `criteria_drift` does — it is the artifact of the party being judged.
    """
    config, a = agent
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal=case["goal"]))
    (tsk.dir_of(a, t.id) / "plan0.md").write_text(case["plan"])
    return t


@pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
def test_goal_drift_matches_what_the_ten_real_runs_showed(agent, case):
    """Fires on the six that narrowed or inverted the goal; quiet on the four
    whose plans genuinely carried it. Both halves are the assertion — a
    detector that fires on everything has found nothing."""
    note = tsk.goal_drift(agent[1], _replay(agent, case))

    if not case["dropped"]:
        assert not note, (
            f"example {case['id']} should stay quiet ({case['why']}), "
            f"but reported: {note}")
        return

    assert note, f"example {case['id']} should report drift: {case['why']}"
    for word in case["dropped"]:
        assert repr(word) in note, (
            f"example {case['id']} dropped {word!r} — {case['why']} — "
            f"but the report does not name it: {note}")
    assert case["goal"] in note, "the report quotes what the owner actually asked"


def test_the_corpus_is_the_run_that_was_published(agent):
    """Ten cases, six firing. If someone loosens `goal_drift` and updates the
    per-case expectations one at a time, this still catches it."""
    assert len(CORPUS) == 10
    assert sum(1 for c in CORPUS if c["dropped"]) == 6
    fired = {c["id"] for c in CORPUS
             if tsk.goal_drift(agent[1], _replay(agent, c))}
    assert fired == {"02", "04", "05", "06", "08", "09"}


@pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
def test_every_plan_the_session_wrote_still_parses(agent, case):
    """The worker adopts `plan0.md` by parsing it. Ten plans written by a real
    session in one afternoon are the only sample there is of what that file
    looks like when nobody is tidying it, so the parser is held to them."""
    p = pl.parse(case["plan"])
    assert p.phases, f"example {case['id']} parsed to no phases"
    assert all(ph.verified_when for ph in p.phases), (
        f"example {case['id']} has a phase with no criterion")


def test_goal_drift_reads_the_plan_and_never_edits_it(agent):
    """Reports; never adopts — the same doctrine as `criteria_drift`. The file
    belongs to the party being judged, so reconciling it is the owner's
    decision, not a refresh."""
    config, a = agent
    case = next(c for c in CORPUS if c["id"] == "09")
    t = _replay(agent, case)
    path = tsk.dir_of(a, t.id) / "plan0.md"
    before = path.read_text()

    assert tsk.goal_drift(a, t)
    assert path.read_text() == before, "the plan file was rewritten"
    assert tsk.get(config, a, t.id).goal == case["goal"], "the goal was rewritten"
