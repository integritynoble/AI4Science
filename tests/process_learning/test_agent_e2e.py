"""Real-sandbox acceptance: the work-process learning agent delivers only when the
CP-side grounding gate passes; a fabricated step (a References span not in the trace)
and a trace-tamper are blocked."""
import json
import pytest
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.process_learning.agent import run_process_learning_task

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.sandbox import podman_available
pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

TRACE = {"journal.md": ("step 1: ran the GAP-TV solver. "
                        "step 2: the physics judge failed with a high residual. "
                        "step 3: increased iterations and the retry passed.\n")}
DEMAND = {"run_label": "cassi-run-42", "trace": TRACE, "coverage_points": ["retry", "judge"]}

_GOOD = (
    "# Postmortem: cassi-run-42\n\n"
    "The agent first ran the GAP-TV solver, then the physics judge failed [S1], so it "
    "increased iterations and the retry passed [S1]. The judge gating the outcome is "
    "the key control point in this run [S1].\n\n"
    "## References\n"
    'S1: trace/journal.md — "the physics judge failed"\n')


def _files(explanation=_GOOD):
    return {"explanation.md": explanation}


class GroundedPlanner:
    def __init__(self, files):
        self._s = [PlanStep(summary="write", command=["true"], stage_files=files, request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True),
                   PlanStep(summary="give up", command=[], done=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass


def test_grounded_explanation_delivers(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        out = run_process_learning_task(demand=DEMAND, client=ControlPlaneClient(uds),
                                        store=TaskStore(tmp_path / "t"), task_id="e2e-p-1",
                                        interaction_mode="I2", planner=GroundedPlanner(_files()))
        assert out["status"] == "delivered", out
    finally:
        server.should_exit = True


def test_fabricated_step_blocked(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        bad = _GOOD.replace('"the physics judge failed"', '"the agent deleted the database"')
        out = run_process_learning_task(demand=DEMAND, client=ControlPlaneClient(uds),
                                        store=TaskStore(tmp_path / "t"), task_id="e2e-p-2",
                                        interaction_mode="I2", planner=GroundedPlanner(_files(bad)))
        assert out["status"] == "blocked"     # invented step not in the trace
    finally:
        server.should_exit = True


def test_trace_tamper_blocked(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        files = _files(); files["trace/journal.md"] = "rewritten trace\n"   # overwrite staged trace
        out = run_process_learning_task(demand=DEMAND, client=ControlPlaneClient(uds),
                                        store=TaskStore(tmp_path / "t"), task_id="e2e-p-3",
                                        interaction_mode="I2", planner=GroundedPlanner(files))
        assert out["status"] == "blocked"     # SHA integrity
    finally:
        server.should_exit = True
