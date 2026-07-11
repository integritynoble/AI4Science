"""Task 9: end-to-end dual-mode drill.

Spins the real control plane over a UNIX socket and drives the
computational-imaging agent through the PEV loop to verified completion,
then proves the I2->I0 interaction switch changes the next decision.
"""
import pytest
from pathlib import Path
from pwm_control_plane.sandbox import podman_available
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.verifier import CommandExitVerifier
from ai4science.harness.runtime.pev import run_task, PlanStep

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")


class ImagingPlanner:
    """Emits one compute step that writes an artifact to the workspace, then done."""

    def __init__(self):
        self.emitted = False

    def next_step(self, state):
        if self.emitted:
            return PlanStep(summary="deliver", command=[], done=True)
        self.emitted = True
        return PlanStep(summary="compute reconstruction",
                        command=["sh", "-c", "echo recon > /workspace/out.npy"])

    def replan(self, state, verdict):
        pass


def test_imaging_agent_delivers_end_to_end(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        c = ControlPlaneClient(uds)
        run = c.open_run("reconstruct", "A1", {"actions": 20}, interaction_profile="I2")
        out = run_task(run_id=run["run_id"],
                       contract=compile_contract(objective="reconstruct", capability_profile="A1",
                                                 interaction_mode="I2", deliverables=["out.npy"]),
                       client=c, planner=ImagingPlanner(),
                       verifier=CommandExitVerifier(required_artifacts=[]),
                       store=TaskStore(Path(tmp_path) / "tasks"), task_id="e2e1")
        assert out["status"] == "delivered"
    finally:
        server.should_exit = True


def test_switch_to_i0_makes_reversible_default_ask(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        c = ControlPlaneClient(uds)
        run = c.open_run("g", "A1", {"actions": 5}, interaction_profile="I2")
        # I2 acts on reversible_default; after reducing to I0 it must ASK
        assert c.classify(run["run_id"], "reversible_default")["decision"] == "ACT"
        assert c.set_interaction_profile(run["run_id"], "I0")["ok"] is True
        assert c.classify(run["run_id"], "reversible_default")["decision"] == "ASK"
    finally:
        server.should_exit = True
