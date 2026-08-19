"""5-B2 and 5-B3, both from one line of the owner's session.

    ❯ please create the task for me according to this goal
      goal:   please create the task for me according to this goal

Two different failures are visible in that one line.

**B3.** "this goal" refers to something the owner said a moment earlier. The
worker had no way to resolve the reference, so the sentence that explicitly
asked for a task produced a task whose goal was the request. After B1 it asks
"what is the goal?" instead of filing nonsense --- better, and still worse than
it needs to be, because the answer was on screen.

**B2.** The design says the owner may write the plan. In practice the session
drafts and the owner grants or refuses; `e=edit` at the confirmation edits the
GOAL, not the plan. The pieces existed --- `plan.parse`, `adopt_plan`, and a
`plan_owner_edited` flag that `adopt_plan` already honours by refusing to let a
session rewrite criteria the owner authored --- with no way in.

Both are about the same thing: the owner should not have to phrase what they
want in the shape the parser wants.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             task as tsk, worker as wk)
from ai4science.harness import console


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


def _deps():
    return {"resolve": lambda n: ("unknown", ""), "session_of": lambda t: "",
            "find_task": lambda t: (None, None), "create": lambda a, g: "tsk_x",
            "guide": lambda t, x: "sent", "suggest": lambda t: "",
            "unknown": lambda l: "not a command"}


# ── B3: resolve the back-reference instead of asking again ────────────

def test_the_worker_remembers_what_was_just_said():
    """A line it could not place is still worth keeping: it is usually the goal
    the NEXT line refers to."""
    m = console.Mode(kind="agent", name="sarsi-worker")
    _act, m2 = console.route("GAP-TV solver for CASSI, in python", m, _deps())
    assert m2.recent == "GAP-TV solver for CASSI, in python", m2


def test_a_request_that_points_back_uses_what_it_points_at():
    """The line from the owner's session. `this goal` referred to something
    said a moment earlier, and the worker had it."""
    m = console.Mode(kind="agent", name="sarsi-worker",
                     recent="write a GAP-TV solver for CASSI")
    act, mode = console.route(
        "please create the task for me according to this goal", m, _deps())
    assert act.kind == "confirm", act
    assert act.goal == "write a GAP-TV solver for CASSI", act.goal
    assert mode.pending == act.goal


def test_and_it_says_where_the_goal_came_from():
    """Filing a goal the owner did not type on THIS line, without saying so, is
    the loop putting words in their mouth."""
    m = console.Mode(kind="agent", name="sarsi-worker",
                     recent="write a GAP-TV solver for CASSI")
    act, _ = console.route("please make a task for me", m, _deps())
    assert "said" in act.text.lower() or "earlier" in act.text.lower(), act.text


def test_with_nothing_to_point_at_it_still_asks():
    """No memory, no guess. This is the B1 behaviour and it must survive."""
    m = console.Mode(kind="agent", name="sarsi-worker")
    act, mode = console.route("please create the task for me according to this goal",
                              m, _deps())
    assert act.kind == "say"
    assert mode.pending is None


def test_a_greeting_is_not_remembered_as_a_goal():
    """`hi` must never become the goal a later request points at."""
    m = console.Mode(kind="agent", name="sarsi-worker", recent="write a solver")
    _act, m2 = console.route("hi", m, _deps())
    assert m2.recent == "write a solver", "a greeting overwrote the memory"


# ── B2: the owner writes the plan ─────────────────────────────────────

PLAN = """\
# write a GAP-TV solver for CASSI

Working directory: /tmp/work

## Phase 1 — implement the solver
Write gaptv.py implementing GAP-TV for CASSI.
Verified when: `gaptv.py` exists and `python -c "import gaptv"` succeeds.

## Phase 2 — check it against the benchmark
Verified when: PSNR on the benchmark scene is recorded in `result.json`.

## Permissions needed
- Write access to /tmp/work
"""


def test_an_owner_written_plan_is_adopted_whole(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t = tsk.set_owner_plan(config, a, t, PLAN)
    assert t.criteria and len(t.criteria) == 2, t.criteria
    assert "gaptv.py" in t.criteria[0]


def test_and_it_is_marked_as_the_owners(config):
    """`adopt_plan` already honours this flag by refusing to let a session
    rewrite criteria the owner authored. Setting it is what was missing."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t = tsk.set_owner_plan(config, a, t, PLAN)
    assert t.plan_owner_edited is True
    assert t.plan_agreed is True, "the owner wrote it; there is nothing to agree"


def test_the_file_on_disk_is_the_owners_words(config):
    """Not a re-render. The session reads this file, and a plan the owner wrote
    that comes back paraphrased is not the plan they wrote."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t = tsk.set_owner_plan(config, a, t, PLAN)
    on_disk = (tsk.dir_of(a, t.id) / f"{t.plan_version}.md").read_text()
    assert "implement the solver" in on_disk
    assert on_disk.strip() == PLAN.strip()


def test_a_plan_that_will_not_parse_is_refused_not_filed(config):
    """Refused before it becomes the standard a verdict is measured against."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    with pytest.raises(pl.BadPlan):
        tsk.set_owner_plan(config, a, t, "this is not a plan at all")


def test_the_declared_permissions_still_need_granting(config):
    """Writing the plan is not granting what it declares. The owner authors the
    standard; the grant is still a separate, deliberate act."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t = tsk.set_owner_plan(config, a, t, PLAN)
    assert t.awaiting, "an owner-written plan still declares permissions"


# ── the way in ────────────────────────────────────────────────────────

def test_sarsi_plan_takes_a_file():
    """`sarsi adopt` takes a plan the owner edited IN PLACE, after a session
    wrote it. This is the other direction: a plan the owner wrote first."""
    import inspect
    from ai4science.commands import sarsi as cmd
    assert "set_from" in inspect.signature(cmd.plan_cmd).parameters


def test_the_repl_offers_it_at_the_confirmation():
    """`[Enter=yes / e=edit / n=no]` edits the GOAL. The owner writing the plan
    needs its own key, and the block has to say so or nobody finds it."""
    from ai4science.harness import console
    block = console.confirm_block("write a solver", "sarsi-worker")
    assert "p=plan" in block, block
