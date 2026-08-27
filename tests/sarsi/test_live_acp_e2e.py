"""Live end-to-end over the ACP transport — the path that used to stall.

    SARSI_LIVE_TEST=1 pytest tests/sarsi/test_live_acp_e2e.py -s

`test_live_e2e.py` proves the TMUX path, and it has passed for months. It is
not evidence about this one: it builds a `MachineRuntime` explicitly, so the
gateway is never involved. The `do → run → supervise` route people actually
use resolves an ACP runtime from the task's backend, and that route produced
a session that stayed alive for 85 minutes and returned nothing.

Two causes, both now fixed, and neither visible from the tmux test:

  * the `--session` key had no `agent:` prefix, so openclaw filed it as a
    session name under the DEFAULT agent — the live store still holds
    `agent:main:sarsi-claude:main:main` with `totalTokens: 0`;
  * there was no `sarsi-claude` agent to attach to in the first place.

This test is the one that would have caught that, so it asserts on the thing
that was wrong: a real prompt reaching a real engine and coming back.
"""
import os
import time
from dataclasses import replace as dr
from pathlib import Path

import pytest

LIVE = os.environ.get("SARSI_LIVE_TEST") == "1"

pytestmark = pytest.mark.skipif(not LIVE, reason="set SARSI_LIVE_TEST=1 to run")


def _det_verifier_stub(**_kw):
    """`_verify_phase` runs `verify.check()` first; a criterion naming a shell
    command is settled deterministically and never reaches here."""
    return {"state": "UNVERIFIED", "why": "no LLM verifier in live test"}


@pytest.fixture()
def sarsi_env(tmp_path):
    from ai4science.harness.agents.sarsi.registry import config_path, load
    state_dir = Path(os.environ.get("SARSI_STATE_DIR", Path.home() / ".sarsi"))
    config = load(config_path(state_dir))
    return config, config.agents["sarsi-worker"], tmp_path


def test_the_gateway_answers_at_all(sarsi_env):
    """The narrowest possible claim, asserted before the whole loop.

    If this fails, nothing below it can be interpreted: a task that never
    reaches `verified` would look like a planning or verification bug when the
    transport simply never carried a prompt. That ambiguity is precisely what
    cost 85 minutes, so the transport gets its own assertion.
    """
    from ai4science.harness.agents.sarsi.acp import openclaw_acp_runtime

    runtime = openclaw_acp_runtime("sarsi-claude")
    name = "sarsi-live-probe"
    try:
        runtime.start(name, cwd=str(sarsi_env[2]))
        reply = runtime.send(name, "Reply with exactly the word READY.")
    finally:
        try:
            runtime.stop(name)
        except Exception:
            pass

    assert reply.get("ok") is not False, reply
    assert "READY" in (reply.get("text") or "").upper(), reply


def test_sarsi_worker_drives_sarsi_claude_over_acp_to_verified(sarsi_env):
    config, agent, tmp_path = sarsi_env

    from ai4science.harness.agents.sarsi import (plan as pl, session as ses,
                                                 task as tsk, worker as wk)
    from ai4science.harness.agents.sarsi.operator import TmuxPane
    from ai4science.harness.agents.sarsi.operator import run as op_run

    workdir = tmp_path / "work"
    workdir.mkdir()
    result = workdir / "result.txt"

    directive = wk.Directive(agent_id=agent.id,
                             goal=f"write the word hello into {result}")
    admitted = wk.admit(config, agent, directive)
    assert admitted.admitted, admitted.message

    phase = pl.Phase(title="write hello",
                     verified_when=f"`cat {result}` exits with 0")
    task = tsk.create(config, agent, directive, backend="sarsi-claude")
    draft = dr(pl.draft(directive), phases=(phase,), work_root=str(workdir))

    # `set_owner_plan`, not `adopt_plan`, and the difference is the whole
    # reason the first version of this test could never pass.
    #
    # `adopt_plan` means "take a plan the SESSION wrote". Under it
    # `plan_owner_edited` stays False, so `ses.verify` treats a criterion that
    # names a command as JUDGMENTAL and refuses to run it — correctly, because
    # an executor that writes its own `Verified when:` line would otherwise
    # choose the code that judges it [§M4.2]. The deterministic check was fine
    # all along: called with `trusted=True` it returns PASS on this criterion.
    #
    # Here the OWNER wrote the criterion — this test did — so the provenance
    # the task records has to say so.
    task = tsk.set_owner_plan(config, agent, task, draft.render())

    # No `runtime=`. That is the point: the route under test is the one that
    # resolves a runtime from the task's BACKEND, which is what `do → run`
    # does and what the tmux test bypasses.
    task = ses.assign(config, agent, task, installed=lambda: set())
    assert task.session.get("transport") == "acp", task.session

    session_name = task.session["name"]
    try:
        time.sleep(3)
        try:
            task = ses.deliver_kickoff(config, agent, task)
        except Exception:
            pass  # the operator loop re-delivers a pending kickoff

        # 40 passes (2 min) is the tmux test's budget and it is too short
        # here: a gateway session boots a fresh engine before it reads the
        # brief. Measured, the first ACP run reached `acp-working` and was
        # still working when the loop gave up — a timeout being read as a
        # failure is the same mistake in miniature as the stall itself.
        actions = op_run(config, agent, task, pane=TmuxPane(),
                         verifier=_det_verifier_stub, engine="deterministic",
                         passes=int(os.environ.get("SARSI_LIVE_PASSES", "120")),
                         interval=3.0)
        task = tsk.get(config, agent, task.id)
    finally:
        # An ACP bridge is a PAIR and it detaches; a test that leaves one
        # running leaves it running with a deleted tmpdir as its cwd.
        try:
            ses.runtime_for(task).stop(session_name)
        except Exception:
            pass

    # On failure, say what the session actually did. A bare state comparison
    # cannot distinguish "never started" from "worked and wrote elsewhere".
    kinds = [getattr(a, "kind", "?") for a in (actions or [])]
    work = ses.work_dir_for(agent, task)
    seen = sorted(p.name for p in work.iterdir()) if work.exists() else []
    ctx = (f"state={task.state!r} kinds={kinds[-6:]} "
           f"work={work} holds={seen} target_exists={result.exists()}")

    assert task.state == tsk.VERIFIED, ctx
    assert (task.verdict or {}).get("state") == "PASS", ctx
    assert result.exists(), ctx
