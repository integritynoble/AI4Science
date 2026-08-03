"""The evidence root — letting evidence follow the work, without letting it roam.

Evidence gathering never leaves the task folder. That boundary is right, and it
was also why a run that **succeeded** was recorded as `UNVERIFIED`:

  > **2026-08-03, grace.** The goal named `/home/grace/live-gaptv`. The session
  > wrote `gaptv.py` and `result.json` there and finished correctly. `check`
  > answered *"nothing visible was supplied, so nothing was judged."* Passing
  > the listing by hand with `--evidence` produced an immediate `PASS` citing
  > `"psnr": 25.41`. The work was done; only the looking failed.

The fix is not to remove the boundary — it is to let the plan **declare where
the work happens**, and to look there. A declared root is still a fixed
boundary; a search is not.

  * **declared, not inferred.** A criterion naming `/etc/passwd` does not make
    `/etc` an evidence root. Only the plan's own declaration moves it.
  * **the task folder stays the default.** No declaration, no change.
  * **a path outside the root is reported as outside it**, never read and never
    silently dropped — silence about a file the owner named reads as "nothing
    to report", which is the failure this whole module exists to prevent.
  * **symlinks do not widen it.** The check is on the resolved path.
"""
import pytest

from ai4science.harness.agents.sarsi import (evidence as evd, plan as pl,
                                             registry as reg, task as tsk,
                                             worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"),
                  root=tmp_path / "state")
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["work"]


# ── the plan declares it ──────────────────────────────────────────────

def test_a_plan_can_declare_where_the_work_happens(tmp_path):
    text = f"""\
# finish the export

Working directory: {tmp_path}/live-gaptv

## Phase 1 — do it
Verified when: result.json reports a psnr above 15

## Permissions needed
- none
"""
    parsed = pl.parse(text)
    assert parsed.work_root == f"{tmp_path}/live-gaptv"


def test_a_plan_without_one_declares_nothing(tmp_path):
    assert pl.draft(worker.Directive(agent_id="work",
                                     goal="tidy up")).work_root is None


def test_the_declaration_survives_a_render_and_reparse(tmp_path):
    original = pl.Plan(goal="g", work_root=f"{tmp_path}/w",
                       phases=[pl.Phase(title="x", verified_when="y")])
    assert pl.parse(original.render()).work_root == f"{tmp_path}/w"


def test_the_task_takes_the_declared_root_from_its_plan(config, agent, tmp_path):
    root = tmp_path / "live-gaptv"
    root.mkdir()
    plan = pl.Plan(goal="g", work_root=str(root),
                   phases=[pl.Phase(title="x", verified_when="result.json exists")])
    d = worker.Directive(agent_id=agent.id, goal="g")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), plan)
    assert tsk.evidence_root(agent, t) == root.resolve()


def test_with_no_declaration_the_task_folder_is_the_root(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="g")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    assert tsk.evidence_root(agent, t) == tsk.dir_of(agent, t.id).resolve()


# ── gathering from it ─────────────────────────────────────────────────

def test_evidence_is_read_from_the_declared_root(tmp_path):
    root = tmp_path / "live-gaptv"
    root.mkdir()
    (root / "result.json").write_text('{"psnr": 25.41}')
    out = evd.gather(root, ["result.json reports a psnr above 15"])
    assert "25.41" in out
    assert "result.json" in out


def test_the_listing_names_the_folder_it_listed(tmp_path):
    """A listing whose location is unstated invites the verifier to assume it
    was the task folder."""
    root = tmp_path / "live-gaptv"
    root.mkdir()
    (root / "gaptv.py").write_text("# code")
    assert str(root) in evd.gather(root, ["gaptv.py exists"])


def test_a_file_outside_the_declared_root_is_reported_not_read(tmp_path):
    root = tmp_path / "live-gaptv"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("PRIVATE")
    out = evd.gather(root, [f"{secret} contains the key"])
    assert "PRIVATE" not in out
    assert "outside" in out


def test_a_symlink_does_not_widen_the_root(tmp_path):
    root = tmp_path / "live-gaptv"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("PRIVATE")
    (root / "peek.txt").symlink_to(secret)
    out = evd.gather(root, ["peek.txt has the value"])
    assert "PRIVATE" not in out
    assert "outside" in out


def test_an_absolute_path_inside_the_root_is_read(tmp_path):
    """The criterion the grace run actually had."""
    root = tmp_path / "live-gaptv"
    root.mkdir()
    (root / "result.json").write_text('{"psnr": 25.41}')
    out = evd.gather(root, [f"{root}/result.json contains a psnr above 15"])
    assert "25.41" in out


def test_a_missing_file_in_the_root_is_stated_as_absent(tmp_path):
    root = tmp_path / "live-gaptv"
    root.mkdir()
    out = evd.gather(root, ["result.json exists"])
    assert "NOT PRESENT" in out


def test_a_declared_root_that_does_not_exist_says_so(tmp_path):
    """Not an empty listing — that reads as "the folder is empty", which is a
    different fact and a much more damning one."""
    out = evd.gather(tmp_path / "never-made", ["result.json exists"])
    assert "does not exist" in out.lower()


# ── the loop uses it ──────────────────────────────────────────────────

def test_the_supervision_loop_gathers_from_the_declared_root(config, agent, tmp_path):
    """The grace failure, end to end: the artefacts are outside the task
    folder and the verifier must still see them."""
    from ai4science.harness.agents.sarsi import operator as op, session as ses

    root = tmp_path / "live-gaptv"
    root.mkdir()
    (root / "result.json").write_text('{"psnr": 25.41}')

    plan = pl.Plan(goal="reconstruct the cube", work_root=str(root),
                   phases=[pl.Phase(title="run it",
                                    verified_when="result.json reports a psnr above 15")])
    d = worker.Directive(agent_id=agent.id, goal="reconstruct the cube")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), plan)
    t = tsk.start(config, agent, t)
    t.plan_agreed = True
    t.session = {"name": "work-0001", "pid": 1, "cwd": str(root)}
    t.kickoff_pending = None
    tsk._touch(agent, t, __import__("time").time)

    seen = {}

    class Pane:
        def capture(self, name):
            return "done\n❯ "

        def send(self, name, text):
            pass

        def key(self, name, key):
            pass

    def judge(**kw):
        seen.update(kw)
        return {"state": "PASS", "why": "psnr 25.41 is above 15"}

    op.tick(config, agent, t, pane=Pane(), verifier=judge, engine="gpt")
    assert "25.41" in seen["evidence"]


def test_check_gathers_its_own_evidence_when_none_is_given(tmp_path, monkeypatch):
    """The grace failure in one command: the artefacts existed, `check` was
    given no `--evidence`, and it answered UNVERIFIED — 'nothing visible was
    supplied'. Having to paste a listing by hand is the defect, not the fix."""
    from typer.testing import CliRunner

    from ai4science.cli import app
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 task as tsk, worker)

    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "live-gaptv"
    root.mkdir()
    (root / "result.json").write_text('{"psnr": 25.41}')

    runner = CliRunner()
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    agent = config.agents["work"]
    plan = pl.Plan(goal="reconstruct the cube", work_root=str(root),
                   phases=[pl.Phase(title="run it",
                                    verified_when="result.json reports a psnr above 15")])
    d = worker.Directive(agent_id="work", goal="reconstruct the cube")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), plan)

    seen = {}
    from ai4science.harness.agents.sarsi import verifier as vf
    monkeypatch.setattr(vf, "default_verifier",
                        lambda *a, **k: (lambda **kw: seen.update(kw) or
                                         {"state": "PASS", "why": "25.41 > 15"}))
    result = runner.invoke(app, ["sarsi", "check", "work", t.id])
    assert result.exit_code == 0
    assert "25.41" in seen.get("evidence", "")
