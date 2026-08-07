"""The worker and the session share one history — guided AND interact.

From `guide-sarsi-claude-overview.md`:

    What you type is also recorded (`ownerlog`, mode `guided`) and now reaches
    the **composer** as `owner-said`. That closed a real bug: your instruction
    used to reach `clarify` and nothing else, so telling the agent *"use the
    staging host, not production"* never got in front of the node that writes
    the next prompt, and it could steer straight against you.

and, for interact mode:

    | every message | stamps `interact_at` | makes the plan **stale**, so `S`
      withholds phases you may have just abandoned |

Both matter for the same reason the owner gave: **most of the time the worker
occupies the guide role, and the human joins occasionally.** Two drivers, one
session — so whatever either of them does has to be visible to the other, or
the one that was away steers against what just happened.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (ownerlog, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


class _RT:
    engine = "claude"
    def __init__(self): self.sent = []
    def send(self, name, text): self.sent.append(text); return {"ok": True}


def _task(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t.session = {"name": "sarsi-worker-abcd"}
    return a, t


# ── guided ────────────────────────────────────────────────────────────

def test_what_the_owner_guides_reaches_the_shared_history(config):
    """It was recorded in the LEDGER only, and the worker's workspace reads the
    OWNERLOG — so the one thing the owner said by hand was the one thing the
    worker could not see."""
    a, t = _task(config)
    ses.guide(config, a, t, "use the staging host, not production",
              by_owner=True, runtime=_RT())
    said = [r for r in ownerlog.said(config, a, limit=0)
            if "staging host" in r.get("text", "")]
    assert said, "the owner's instruction never reached the shared history"


def test_and_it_is_marked_as_guided_by_whom(config):
    """Two drivers, one session: 'the worker said this' and 'the human said
    this' are different facts, and merging them loses the one that matters."""
    a, t = _task(config)
    ses.guide(config, a, t, "owner words", by_owner=True, runtime=_RT())
    ses.guide(config, a, t, "worker words", by_owner=False, runtime=_RT())
    rows = {r.get("text"): r.get("mode") for r in ownerlog.said(config, a, limit=0)}
    assert rows.get("owner words") == "guided"
    assert rows.get("worker words") == "worker-guided"


# ── interact ──────────────────────────────────────────────────────────

def test_taking_the_wheel_stamps_interact_at(config):
    """Pausing stops the operator COLLIDING with you; it does not stop it
    steering wrong afterwards. Without a stamp the plan never goes stale, and
    the next pass drives confidently through phases you just overrode by hand.
    """
    a, t = _task(config)
    assert getattr(t, "interact_at", None) in (None, 0)
    ses.took_the_wheel(config, a, t, now=lambda: 1000.0)
    assert t.interact_at == 1000.0


def test_a_hand_driven_plan_is_stale(config):
    """`plan_at < max(set_at, interact_at)` — the same protection a re-set goal
    already had, extended to being hand-driven."""
    a, t = _task(config)
    t.plan_version = 1          # it HAS a plan — see the no-plan guard below
    t.plan_at = 500.0
    assert ses.plan_is_stale(t) is False
    ses.took_the_wheel(config, a, t, now=lambda: 1000.0)
    assert ses.plan_is_stale(t) is True


def test_a_stale_plan_is_withheld_not_deleted(config):
    """`S` improvises against the goal until a fresh one is drafted — the plan
    itself survives, because deleting it would lose what the owner agreed."""
    a, t = _task(config)
    t.plan_version = 3
    ses.took_the_wheel(config, a, t, now=lambda: 1000.0)
    assert t.plan_version == 3


def test_the_stamp_survives_a_round_trip(config):
    a, t = _task(config)
    ses.took_the_wheel(config, a, t, now=lambda: 1000.0)
    again = [x for x in tsk.all_of(config, a) if x.id == t.id][0]
    assert again.interact_at == 1000.0


def test_the_repl_interact_path_stamps_it_too(config, monkeypatch, tmp_path):
    """The stamp has to fire where the owner actually takes the wheel, not only
    where a unit test calls it. `/interact` pauses the worker first — that is
    the moment."""
    from ai4science.harness import repl
    a, t = _task(config)
    import ai4science.harness.agents.sarsi.task as _tsk
    _tsk._save(a, t)

    deps = repl._console_deps({})
    got = deps["pause_for_interact"](t.id)
    assert got == a.id, got
    again = [x for x in tsk.all_of(config, a) if x.id == t.id][0]
    assert again.interact_at, "interact_at was not stamped on the real path"
    assert again.steering_paused is True


def test_a_task_with_no_plan_is_not_stale(config):
    """Borrowed from the proven implementation — `runtime_agent.plan_is_stale`
    returns False when there is no plan file at all:

        if not rec.get("plan") or not os.path.exists(rec["plan"]):
            return False

    "Stale" means *written for an earlier goal*. A task that has no plan yet is
    not stale; it has nothing. Without this guard, hand-driving a task before it
    ever planned marks a non-existent plan stale, and every reader that asks
    "should I withhold the plan?" gets a yes about nothing.
    """
    a, t = _task(config)
    t.plan_version = 0
    ses.took_the_wheel(config, a, t, now=lambda: 1000.0)
    assert ses.plan_is_stale(t) is False


def test_but_a_task_that_HAS_one_still_goes_stale(config):
    a, t = _task(config)
    t.plan_version = 2
    t.plan_at = 500.0
    ses.took_the_wheel(config, a, t, now=lambda: 1000.0)
    assert ses.plan_is_stale(t) is True
