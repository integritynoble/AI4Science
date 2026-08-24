"""Found by walking the long cycle: constraint, failure, lesson, recurrence, skill.

`tools/sarsi-examples/ten_memory_steps.py` runs §16's conditions 4, 9, 10, 11
and 12 — the ones the task walk and the conversation walk never touched.
Everything here came out of that walk.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (consolidate, forecast as fc,
                                             ledger, memory as mem, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, verify, worker as wk)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["sarsi-worker"]


class Rt:
    def start(self, name, cwd, **kw): return {"ok": True, "name": name, "pid": 1, "cwd": cwd}
    def send(self, name, text): return {"ok": True}
    def stop(self, name): return {"ok": True}
    def set_ceiling(self, name, c): return {"name": name, "ceiling": c}


def _ready(config, agent, goal, criteria, artifacts):
    """A task with an owner-authored plan, assigned, with its artifacts written."""
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal=goal))
    p = pl.Plan(goal=goal, phases=[pl.Phase(title=f"p{i}", verified_when=c)
                                   for i, c in enumerate(criteria)])
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(p.render())
    t = tsk.attach_plan(config, agent, t, p)
    t.plan_owner_edited = True
    tsk._save(agent, t)
    t = ses.assign(config, agent, t, runtime=Rt(), installed=lambda: set())
    wd = ses.work_dir_for(agent, t)
    wd.mkdir(parents=True, exist_ok=True)
    for name, body in artifacts.items():
        (wd / name).write_text(body)
    return t


def _stub(**kw):
    return {"state": "FAIL", "why": "a model that was never shown the artifact"}


# ── the whole-task path asked a model what a check could settle ─────────────

def test_a_criterion_a_check_can_settle_is_not_handed_to_a_model(config, agent):
    """§0.1 rule 6: "If a pass condition can be expressed as a test, file/hash
    check, JSON predicate, or exit code, do that instead of asking a model to
    judge it."

    `_verify_phase` obeyed it. `session.verify` without a phase did not — and
    that is the path `ai4science sarsi check <agent> <task>` takes when no
    `--phase` is given, which is the owner's default. `verify.check` said PASS
    on the very same criterion while the model verifier's FAIL was recorded as
    the verdict."""
    t = _ready(config, agent, "export the manifest", ["manifest.json exists"],
               {"manifest.json": '{"ok": true}\n'})
    assert verify.check("manifest.json exists",
                        ses.work_dir_for(agent, t))["state"] == "PASS"

    t = ses.verify(config, agent, t, verifier=_stub, evidence="", engine="stub",
                   runtime=Rt(), now=time.time)

    assert t.verdict["state"] == "PASS", t.verdict
    assert t.verdict.get("deterministic") is True
    assert t.verdict["engine"] == "deterministic"


def test_a_deterministic_fail_is_not_overturned_by_a_model_pass(config, agent):
    """The direction that matters. A model saying PASS about a criterion a
    check has already failed is the judged party's opinion beating the
    evidence."""
    t = _ready(config, agent, "write the report", ["report.txt contains CALIBRATED"],
               {"report.txt": "nothing was calibrated\n"})

    t = ses.verify(config, agent, t,
                   verifier=lambda **kw: {"state": "PASS", "why": "looks fine to me"},
                   evidence="", engine="stub", runtime=Rt(), now=time.time)

    assert t.verdict["state"] == "FAIL", t.verdict
    assert t.verdict.get("deterministic") is True


def test_criteria_no_check_can_settle_still_reach_the_model(config, agent):
    """The other half: this must not become a refusal to use a judge at all.
    A criterion no check can express is exactly what a model is for."""
    t = _ready(config, agent, "write a design note",
               ["DESIGN.md reads well and explains the approach"],
               {"DESIGN.md": "# Design\n\nSome prose.\n"})

    t = ses.verify(config, agent, t,
                   verifier=lambda **kw: {"state": "PASS", "why": "it reads well"},
                   evidence="", engine="stub", runtime=Rt(), now=time.time)

    assert t.verdict["state"] == "PASS"
    assert t.verdict["engine"] == "stub"
    assert not t.verdict.get("deterministic")


def test_a_mixed_task_settles_what_it_can_and_asks_about_the_rest(config, agent):
    """Both kinds in one task. The check settles its own criterion; the model
    is asked only about the one it is needed for, and the verdict says which
    of the two decided it."""
    asked = []

    def judge(**kw):
        asked.append(list(kw.get("criteria") or []))
        return {"state": "PASS", "why": "the prose is fine"}

    t = _ready(config, agent, "ship it",
               ["manifest.json exists", "DESIGN.md reads well"],
               {"manifest.json": "{}\n", "DESIGN.md": "# D\n"})

    t = ses.verify(config, agent, t, verifier=judge, evidence="",
                   engine="stub", runtime=Rt(), now=time.time)

    assert asked == [["DESIGN.md reads well"]], (
        f"the model should be asked only what no check could settle: {asked}")
    assert t.verdict["state"] == "PASS"
    assert t.verdict["settled_by_check"] == ["manifest.json exists"]


# ── two identical failures that could never be seen as one pattern ──────────

def test_the_same_failure_twice_clusters_into_one_group(config, agent):
    """§11.9(b): "repeated supported pattern can produce candidate semantic
    rule". `MIN_SUPPORT_FOR_CANDIDATE` is 2 — and the live path could never
    reach it.

    The failure episode's summary is written as `f"{task.id} refuted: {goal}"`,
    and `_fingerprint` clusters on the first 40 characters of it. A task id is
    14 characters and different every time, so **every failure was its own
    group**: the semantic arm of the consolidator was unreachable from the live
    failure path however often the same thing broke. The success arm, whose
    summary starts with the goal, worked all along — which is how the asymmetry
    stayed invisible."""
    for _ in range(2):
        t = _ready(config, agent, "write the calibration report",
                   ["report.txt contains CALIBRATED"], {"report.txt": "no\n"})
        t = fc.record(config, agent, t, 0.8, why="usually works")
        ses.verify(config, agent, t, verifier=_stub, evidence="",
                   engine="stub", runtime=Rt(), now=time.time)

    eps = [e for e in ledger.read(config, "episodes")
           if e["trigger"] == "refuted_prediction"]
    assert len(eps) == 2, [e["summary"] for e in eps]
    assert len({consolidate._fingerprint(e) for e in eps}) == 1, (
        f"two identical failures produced two groups: "
        f"{[consolidate._fingerprint(e) for e in eps]}")

    rep = consolidate.run(config, agent)
    assert rep["error_groups_qualifying"], rep
    assert rep["semantic_candidates"], "no candidate from a twice-repeated failure"


def test_but_two_different_failures_stay_apart(config, agent):
    """Narrowing the fingerprint must not merge things that are not the same
    failure — a group of unrelated episodes would produce a lesson about
    nothing."""
    for goal, crit in (("write the calibration report", "report.txt contains CALIBRATED"),
                       ("export the run manifest", "manifest.json exists")):
        t = _ready(config, agent, goal, [crit], {})
        t = fc.record(config, agent, t, 0.8)
        ses.verify(config, agent, t, verifier=_stub, evidence="",
                   engine="stub", runtime=Rt(), now=time.time)

    eps = [e for e in ledger.read(config, "episodes")
           if e["trigger"] == "refuted_prediction"]
    assert len({consolidate._fingerprint(e) for e in eps}) == 2
    assert not consolidate.run(config, agent)["semantic_candidates"]


def test_a_failure_episode_still_names_the_task_it_came_from(config, agent):
    """The task id must not simply be dropped: an episode nobody can trace back
    to its task is evidence about nothing. It belongs in the field that exists
    for it, not in the prose the clusterer reads."""
    t = _ready(config, agent, "write the calibration report",
               ["report.txt contains CALIBRATED"], {"report.txt": "no\n"})
    t = fc.record(config, agent, t, 0.8)
    ses.verify(config, agent, t, verifier=_stub, evidence="", engine="stub",
               runtime=Rt(), now=time.time)

    ep = [e for e in ledger.read(config, "episodes")
          if e["trigger"] == "refuted_prediction"][-1]
    assert ep["task_id"] == t.id
    assert t.id in ep.get("detail", "") or t.id == ep["task_id"]


# ── a skill candidate that could not say what it had proved ────────────────

def _verified_run(config, agent, goal="export the run manifest",
                  criterion="manifest.json exists"):
    t = _ready(config, agent, goal, [criterion], {"manifest.json": "{}\n"})
    return ses.verify(config, agent, t, verifier=_stub, evidence="",
                      engine="stub", runtime=Rt(), now=time.time)


def test_a_skill_candidate_carries_the_criteria_that_actually_passed(config, agent):
    """§16.11 promotes a repeated verified workflow into a procedure "only
    after tests". The gate enforces that, and correctly refuses a candidate
    with no tests — but the candidate the consolidator proposes has `tests: []`
    with the comment "owner fills in", and carried no record of WHAT had been
    verified three times. The owner was asked to declare tests for a workflow
    whose proof the record had thrown away.

    The criteria travel now. They are NOT written into `tests`: a skill whose
    tests the agent wrote for itself is the agent setting its own exam, which
    §13 puts outside mutable cognition."""
    for _ in range(3):
        t = _verified_run(config, agent)
        assert t.verdict["state"] == "PASS", t.verdict

    cands = consolidate.run(config, agent)["skill_candidates"]
    assert cands, "three verified runs of one workflow proposed no skill"
    sk = cands[-1]
    assert sk["verified_criteria"] == ["manifest.json exists"]
    assert sk["tests"] == [], "the agent must not write its own tests"
    assert len(sk["evidence_refs"]) == 3


def test_and_it_still_cannot_activate_until_the_owner_declares_tests(config, agent):
    """The gate, unchanged and doing its job. Evidence is not a test: knowing
    which check passed is not the same as declaring the check a procedure must
    keep passing, and only the second is the owner's to make."""
    for _ in range(3):
        _verified_run(config, agent)
    sk = consolidate.run(config, agent)["skill_candidates"][-1]

    with pytest.raises(consolidate.SkillPromotionError, match="tests"):
        consolidate.promote_skill(config, agent, sk["skill_id"],
                                  sandbox_exit_code=0)

    # the owner declares them, from the evidence the candidate carried
    ledger.append(config, "skills", dict(sk, op="declare",
                                         tests=sk["verified_criteria"],
                                         postconditions=["manifest.json exists"],
                                         rollback="delete manifest.json"))

    with pytest.raises(consolidate.SkillPromotionError, match="sandbox"):
        consolidate.promote_skill(config, agent, sk["skill_id"],
                                  sandbox_exit_code=1)

    consolidate.promote_skill(config, agent, sk["skill_id"], sandbox_exit_code=0)
    assert sk["skill_id"] in [s["skill_id"] for s in
                              consolidate.active_skills(config, agent)]


def test_an_old_episode_without_criteria_still_reads(config, agent):
    """The field is additive. A row written before it existed has no such key
    and must read exactly as it did — §0.1 rule 4, no silent migrations."""
    old = {"schema_version": 1, "episode_id": "ep_old", "agent_id": agent.id,
           "trigger": "success", "outcome": "pass", "summary": "verified: old",
           "detail": "", "tags": ["success"], "task_id": "tsk_old"}
    ledger.append(config, "episodes", old)
    for _ in range(2):
        _verified_run(config, agent, goal="old", criterion="manifest.json exists")

    rep = consolidate.run(config, agent)
    assert rep["episodes_read"] >= 3
    for sk in rep["skill_candidates"]:
        assert isinstance(sk["verified_criteria"], list)


# ── every failure episode, traceable and clusterable ───────────────────────

def test_no_failure_episode_writes_the_task_id_into_its_title(config, agent):
    """The same mistake was in five other places. `clash`, `refusal` and
    `rollback` are all in `FAILURE_TRIGGERS`, so each one clusters — and each
    one wrote `f"{task.id} …"` as its title, splitting every group into groups
    of one exactly as `refuted_prediction` did.

    Checked as a property of the writers rather than one call site: a new
    trigger that reintroduces it fails here."""
    import re
    from ai4science.harness.agents.sarsi import chat as _chat

    for mod in (ses, _chat):
        src = open(mod.__file__).read()
        for m in re.finditer(r'(?:memory|_mem)\.record\(\s*config,\s*agent,\s*'
                             r'"(\w+)",\s*\n?\s*f?"([^"]{0,60})', src):
            trigger, title = m.group(1), m.group(2)
            if trigger not in consolidate.FAILURE_TRIGGERS:
                continue
            assert "{task.id}" not in title and "{t.id}" not in title, (
                f"{mod.__name__}: the {trigger!r} title leads with the task id "
                f"— it belongs in task_id, not in the prose the clusterer "
                f"reads: {title!r}")


def test_a_double_assign_clash_is_traceable_to_its_task(config, agent):
    """One live writer, end to end: the episode names its task in the field a
    reader would look in."""
    t = _ready(config, agent, "do it", ["out.txt exists"], {})
    try:
        ses.assign(config, agent, t, runtime=Rt(), installed=lambda: set())
    except Exception:
        pass

    clashes = [e for e in ledger.read(config, "episodes")
               if e["trigger"] == "clash"]
    assert clashes, "assigning twice wrote no clash episode"
    assert clashes[-1]["task_id"] == t.id
