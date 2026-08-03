"""The one destructive gate the loop may answer, and everything it may not.

> **2026-08-03, grace.** The session chose to prove its own reproducibility by
> deleting `result.json` and regenerating it. The `rm` tripped a hook, the loop
> had no rule for it, and the task stalled for four supervise passes. Nothing
> was wrong with the session's plan.

The temptation is "allow `rm` inside the working directory". That would make the
abstention decorative, because almost every dangerous delete *is* inside the
directory the agent was given. So the rule is narrow enough to state in a
sentence and check mechanically:

  **a non-recursive delete, of named paths that all resolve inside the declared
  working directory, in a command that does nothing else, when the owner has
  granted this task the permission to delete there.**

Every clause is load-bearing, and each one is a test below. The honest
consequence is stated in `test_the_grace_command_itself_is_still_the_owners`:
the command actually observed **still abstains**, because it chained a delete to
running a script, and a delete rule that approves running scripts is not a
delete rule.
"""
import pytest

from ai4science.harness.agents.sarsi import deletion as dl

GRANT = "delete files in the working directory"


def _ok(command, root="/work", granted=(GRANT,)):
    return dl.permitted(command, root=root, granted=list(granted))


# ── what it may answer ────────────────────────────────────────────────

def test_a_plain_delete_inside_the_root_with_a_grant_is_allowed():
    allowed, why = _ok("rm -f /work/result.json")
    assert allowed is True


def test_a_relative_path_is_resolved_against_the_root():
    assert _ok("rm -f result.json")[0] is True


def test_several_files_inside_the_root_are_allowed():
    assert _ok("rm -f result.json output.csv")[0] is True


# ── the grant ─────────────────────────────────────────────────────────

def test_without_the_grant_it_abstains_and_names_it():
    allowed, why = _ok("rm -f result.json", granted=())
    assert allowed is False
    assert GRANT in why


def test_an_unrelated_grant_does_not_authorise_deleting():
    allowed, _ = _ok("rm -f result.json", granted=["read secret mail.read"])
    assert allowed is False


# ── the boundary ──────────────────────────────────────────────────────

def test_a_path_outside_the_root_is_refused():
    allowed, why = _ok("rm -f /etc/passwd")
    assert allowed is False and "outside" in why


def test_a_parent_traversal_is_refused():
    allowed, why = _ok("rm -f ../secrets.txt")
    assert allowed is False and "outside" in why


def test_the_root_itself_is_refused():
    """Deleting the working directory is not working inside it."""
    allowed, _ = _ok("rm -rf /work")
    assert allowed is False


# ── what it must never answer ─────────────────────────────────────────

def test_a_recursive_delete_is_refused_even_inside_the_root():
    """Narrow is the point. `-r` turns one mistake into all of them."""
    allowed, why = _ok("rm -rf /work/build")
    assert allowed is False and "recursive" in why


def test_a_wildcard_is_refused_because_what_it_hits_is_unknown():
    allowed, why = _ok("rm -f /work/*.json")
    assert allowed is False
    assert "wildcard" in why or "cannot" in why


def test_no_preserve_root_is_refused():
    allowed, _ = _ok("rm -rf --no-preserve-root /work")
    assert allowed is False


def test_a_command_that_is_not_a_delete_is_not_this_rules_business():
    allowed, why = _ok("python3 gaptv.py")
    assert allowed is False
    assert "not a delete" in why.lower()


def test_a_delete_chained_to_anything_else_is_refused():
    """Approving it would approve the other half."""
    allowed, why = _ok("rm -f result.json && python3 gaptv.py")
    assert allowed is False
    assert "only" in why.lower() or "chain" in why.lower()


def test_a_piped_delete_is_refused():
    assert _ok("rm -f result.json | tee log")[0] is False


def test_a_redirect_is_refused():
    assert _ok("rm -f result.json > out.txt")[0] is False


def test_a_delete_by_another_name_is_still_a_delete():
    """`unlink` and `shred` are not exceptions to a rule about deleting."""
    assert _ok("shred -u /work/result.json")[0] is False
    assert _ok("unlink /work/result.json")[0] is True


def test_the_grace_command_itself_is_still_the_owners():
    """The command that prompted this rule chained a delete to running a
    script. A delete rule that approves running scripts is not a delete rule —
    so this one still stops, and says why."""
    allowed, why = _ok('rm -f result.json && echo "deleted" '
                       '&& python3 gaptv.py')
    assert allowed is False
    assert "only" in why.lower() or "chain" in why.lower()


# ── in the loop ───────────────────────────────────────────────────────

DELETE_GATE = """\
 Bash command

   rm -f result.json

 Do you want to proceed?
 ❯ 1. Yes
   2. No
"""

CHAINED_GATE = """\
 Bash command

   rm -f result.json && python3 gaptv.py

 Do you want to proceed?
 ❯ 1. Yes
   2. No
"""


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


def _task_at(tmp_path, granted):
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 task as tsk, worker)
    config = reg.parse(reg.default_config(owner_id="1"), root=tmp_path / "state")
    config.ensure_dirs()
    agent = config.agents["work"]
    root = tmp_path / "work"
    root.mkdir(exist_ok=True)
    plan = pl.Plan(goal="g", work_root=str(root),
                   permissions=[GRANT],
                   phases=[pl.Phase(title="x", verified_when="result.json exists")])
    d = worker.Directive(agent_id=agent.id, goal="g")
    t = tsk.create(config, agent, d)
    t.grants = list(granted)
    t = tsk.attach_plan(config, agent, t, plan)
    t.plan_agreed = True
    t.session = {"name": "work-0001", "pid": 1, "cwd": str(root), "ceiling": "A2"}
    tsk._touch(agent, t, __import__("time").time)
    return config, agent, t


class Pane:
    def __init__(self, text):
        self.text, self.sent = text, []

    def capture(self, name):
        return self.text

    def send(self, name, text):
        self.sent.append(text)

    def key(self, name, key):
        pass


def test_the_loop_answers_a_granted_delete(tmp_path):
    from ai4science.harness.agents.sarsi import operator as op
    config, agent, t = _task_at(tmp_path, [GRANT])
    pane = Pane(DELETE_GATE)
    action = op.tick(config, agent, t, pane=pane)
    assert action.kind == "answered" and pane.sent == ["1"]


def test_the_loop_abstains_without_the_grant(tmp_path):
    from ai4science.harness.agents.sarsi import operator as op
    config, agent, t = _task_at(tmp_path, [])
    pane = Pane(DELETE_GATE)
    assert op.tick(config, agent, t, pane=pane).kind == "abstained"
    assert pane.sent == []


def test_the_loop_abstains_on_the_chained_command(tmp_path):
    from ai4science.harness.agents.sarsi import operator as op
    config, agent, t = _task_at(tmp_path, [GRANT])
    pane = Pane(CHAINED_GATE)
    assert op.tick(config, agent, t, pane=pane).kind == "abstained"
    assert pane.sent == []


# ── the owner's door to it ────────────────────────────────────────────

def test_the_grant_string_is_the_one_the_plan_declares(tmp_path):
    """A plan declaring this permission puts it in `awaiting`, so the owner is
    ASKED — the same machinery as every other permission, not a side channel."""
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 task as tsk, worker)
    config = reg.parse(reg.default_config(owner_id="1"), root=tmp_path / "state2")
    config.ensure_dirs()
    agent = config.agents["work"]
    plan = pl.Plan(goal="g", work_root=str(tmp_path), permissions=[dl.GRANT],
                   phases=[pl.Phase(title="x", verified_when="y")])
    d = worker.Directive(agent_id=agent.id, goal="g")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), plan)
    assert dl.GRANT in t.awaiting

    t = tsk.grant(config, agent, t, dl.GRANT)
    assert dl.GRANT in t.grants and dl.GRANT not in t.awaiting
