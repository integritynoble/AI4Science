"""Live end-to-end test: sarsi-worker drives a real claude session to completion.

Skipped unless the environment opt-in is set:

    SARSI_LIVE_TEST=1 pytest tests/sarsi/test_live_e2e.py -s

What it does:
  1. Creates a task with a fully-agreed plan (skips the planning phase so the
     session starts at the working ceiling immediately).
  2. Calls session.assign() with MachineRuntime — spawns a real tmux claude
     session.
  3. Delivers the kickoff brief.
  4. Runs operator.run() with a deterministic verifier stub; _verify_phase
     runs verify.check() first, which evaluates the shell-command criterion
     without an LLM call.
  5. Asserts the task reaches state=verified with verdict=PASS within 2 minutes.

Key findings from 2026-08-21 live run:
  - sarsi-claude wrote result.txt and reported evidence in ~11s.
  - operator loop caught the PASS on pass 8 of 40 (22s total).
  - installed=lambda: set() is required: 'claude-code' is not in the
    ai4science agent registry, but the vendor binary is on PATH.
"""
import os, time
import pytest
from pathlib import Path

LIVE = os.environ.get("SARSI_LIVE_TEST") == "1"

pytestmark = pytest.mark.skipif(not LIVE, reason="set SARSI_LIVE_TEST=1 to run")


@pytest.fixture()
def sarsi_env(tmp_path):
    import sys
    repo = Path(__file__).parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    state_dir = Path(os.environ.get("SARSI_STATE_DIR",
                                    Path.home() / ".sarsi"))
    from ai4science.harness.agents.sarsi.registry import load, config_path
    config = load(config_path(state_dir))
    agent  = config.agents["sarsi-worker"]
    return config, agent, tmp_path


def _det_verifier_stub(**_kw):
    """Stub: _verify_phase runs verify.check() before calling this.
    PASS/FAIL from the deterministic pre-check never reaches here.
    Only UNVERIFIED criteria (no parseable shell command) fall through."""
    return {"state": "UNVERIFIED", "why": "no LLM verifier in live test"}


def test_sarsi_worker_drives_claude_to_verified(sarsi_env):
    config, agent, tmp_path = sarsi_env

    workdir = tmp_path / "work"
    workdir.mkdir()
    result  = workdir / "result.txt"
    criterion = f"`cat {result}` exits with 0"

    from ai4science.harness.agents.sarsi import (
        worker as wk, task as tsk, plan as pl, session as ses,
    )
    from ai4science.harness.agents.sarsi.operator import run as op_run, TmuxPane
    from dataclasses import replace as dr

    directive = wk.Directive(agent_id=agent.id,
                             goal=f"write hello into {result}")
    out = wk.admit(config, agent, directive)
    assert out.admitted, out.message

    phase  = pl.Phase(title="write hello", verified_when=criterion)
    task   = tsk.create(config, agent, directive, backend="sarsi-claude")
    draft  = dr(pl.draft(directive), phases=(phase,), work_root=str(workdir))
    task   = tsk.attach_plan(config, agent, task, draft)
    # `set_owner_plan`, not `adopt_plan`. Both agree the plan and reach the
    # working ceiling, but only one records WHO wrote it, and `ses.verify`
    # reads exactly that: `trusted = plan_owner_edited`. Under `adopt_plan`
    # ("a plan the SESSION wrote") this criterion names a command, so it is
    # classified judgmental and handed to the model verifier — which here is a
    # stub that returns UNVERIFIED, so the task can never reach `verified` and
    # the loop abstains for all 40 passes.
    #
    # That is the correct rule, not a bug: an executor that writes its own
    # `Verified when:` line would otherwise choose the code that judges it
    # [§M4.2]. The criterion itself was always fine — `verify.check` with
    # `trusted=True` returns PASS on it. Here the OWNER wrote it: this test did.
    task   = tsk.set_owner_plan(config, agent, task, draft.render())

    runtime = ses.MachineRuntime()
    # installed=lambda: set() bypasses the ai4science agent-registry check;
    # 'claude-code' (the vendor binary) is not in that registry.
    task = ses.assign(config, agent, task, runtime=runtime,
                      installed=lambda: set())

    session_name = task.session["name"]
    time.sleep(3)   # wait for claude to boot before delivering the brief

    try:
        task = ses.deliver_kickoff(config, agent, task, runtime=runtime)
    except Exception:
        pass   # kickoff-pending is checked by the operator loop too

    pane    = TmuxPane()
    actions = op_run(config, agent, task, pane=pane,
                     verifier=_det_verifier_stub, engine="deterministic",
                     passes=40, interval=3.0)

    # reload from disk — op_run returns the task at last tick, but finish()
    # writes the final state there
    task = tsk.get(config, agent, task.id)

    try:
        runtime.stop(session_name)
    except Exception:
        pass

    assert task.state == tsk.VERIFIED, (
        f"task state={task.state!r}; last operator action="
        f"{getattr(actions[-1], 'kind', '?') if actions else 'none'!r}"
    )
    verdict = task.verdict or {}
    assert verdict.get("state") == "PASS", f"verdict={verdict}"
    assert result.exists(), "result.txt was not written"
