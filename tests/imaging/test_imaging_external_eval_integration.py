"""Task 8: integration proof that the GOVERNED imaging path delivers ONLY on a
control-plane `/evaluate` `pass` -- the verdict computed by the control plane
(`ExternalEvaluatorVerifier` -> `client.evaluate(run_id)`), never a local judge.

(A) Fast deterministic proxy (no podman, always runs): a host-sim double drives the
real planner/solver locally (same pattern as test_agent_hostsim.py /
test_agent_planner_injection.py) but its `.evaluate` returns a FIXED verdict, so
delivery is isolated to the control-plane decision alone.

(B) Live-server governed e2e (podman-gated): brings up the real control-plane
service (same fixture as test_agent_e2e.py), drives the real GAP-TV reconstruction
in a real podman sandbox, and lets the REAL vendored judge (via the service's
/evaluate endpoint) gate delivery through the default governed=True path.
"""
import subprocess, sys
import pytest
from pathlib import Path
from pwm_control_plane.sandbox import podman_available
from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore


class HostSimEvalClient:
    """Models the control plane for the fast deterministic proxy: open_run/stage_input/
    classify/sandbox_execute behave exactly like tests/imaging/test_agent_hostsim.py's
    HostSimClient (the real planner runs the real GAP-TV solver on the host, no container
    indirection) -- but `evaluate` returns a FIXED verdict supplied by the test, so we can
    prove delivery is gated purely by the control-plane decision, not by what the local
    reconstruction actually produced."""

    def __init__(self, run_ws: Path, verdict: dict):
        self.run_ws = Path(run_ws)
        self.run_ws.mkdir(parents=True, exist_ok=True)
        self._verdict = verdict
        self.executed = []

    def open_run(self, goal, capability_profile, hard_limits, interaction_profile="I1", agent_id=None):
        return {"run_id": "hostsim-eval", "capability_profile": capability_profile,
                "interaction_profile": interaction_profile, "limits": hard_limits,
                "workspace_path": str(self.run_ws)}

    def stage_input(self, run_id, rel_path, content):
        dest = self.run_ws / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return {"ok": True, "rel_path": rel_path}

    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": "ACT", "reason": "hostsim"}

    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None,
                        workspace_target=None):
        self.executed.append(command)
        p = subprocess.run([sys.executable] + command[1:], cwd=str(self.run_ws),
                           capture_output=True, text=True)
        return {"exit_code": p.returncode, "is_error": p.returncode != 0,
                "timed_out": False, "stdout": p.stdout, "stderr": p.stderr, "artifacts": []}

    def evaluate(self, run_id):
        # The FIXED verdict is what ExternalEvaluatorVerifier must trust -- not any
        # in-process reconstruction of pass/fail.
        return dict(self._verdict)


def test_governed_delivers_only_on_control_plane_pass(tmp_path):
    client = HostSimEvalClient(tmp_path / "runws",
                               {"decision": "pass", "score": 0.0, "feedback": {}})
    out = run_imaging_task(workspace=tmp_path / "seed", client=client,
                           store=TaskStore(tmp_path / "tasks"), task_id="ext-pass",
                           interaction_mode="I2", seed=42, max_repairs=2, governed=True)
    assert out["status"] == "delivered", out


def test_governed_does_not_deliver_on_control_plane_fail(tmp_path):
    client = HostSimEvalClient(tmp_path / "runws",
                               {"decision": "fail", "score": 0.0, "feedback": {}})
    out = run_imaging_task(workspace=tmp_path / "seed", client=client,
                           store=TaskStore(tmp_path / "tasks"), task_id="ext-fail",
                           interaction_mode="I2", seed=42, max_repairs=2, governed=True)
    # The planner would otherwise exhaust its repairs and stop -- but the point of this
    # assertion is that the control plane's "fail" verdict is what drives non-delivery,
    # for however many attempts the planner has left.
    assert out["status"] != "delivered", out


pytestmark_live = pytest.mark.skipif(not podman_available(), reason="podman not installed")


@pytestmark_live
def test_governed_live_control_plane_gates_delivery(tmp_path):
    """The real GAP-TV reconstruction, run in a real podman sandbox, gated by the real
    vendored judge served over the control plane's /evaluate endpoint -- through the
    DEFAULT governed=True path. `status == "delivered"` IS the proof: ExternalEvaluatorVerifier
    only reports `complete=True` when client.evaluate(run_id) returns decision == "pass",
    and that decision is computed control-plane-side (against the control-plane-owned
    run workspace), never by the harness itself. The governed path does not write
    reports/judge_report.json (that's the in-process PhysicsJudgeVerifier's artifact), so
    there is nothing to read here -- delivery itself is the assertion.
    """
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        out = run_imaging_task(workspace=tmp_path / "seed", client=client,
                               store=TaskStore(tmp_path / "tasks"), task_id="governed-e2e-img",
                               interaction_mode="I2", seed=42, max_repairs=2)
        assert out["status"] == "delivered", out
    finally:
        server.should_exit = True
