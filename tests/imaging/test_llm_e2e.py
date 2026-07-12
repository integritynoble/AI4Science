"""Task 7: end-to-end acceptance drill for the LLM imaging planner.

Drives the imaging agent — recall+select a CASSI solver, run it in a REAL
podman container, gate delivery with the REAL Physics Judge — through three
deterministic scenarios plus a gated real-LLM scenario:

  1. a recalled+selected solver runs and passes the real judge -> delivered
  2. a first selection that fails the judge escalates on residual feedback
     to a passing one -> delivered
  3. an invalid selection falls back to the deterministic GAP-TV planner
     and still delivers
  4. (gated, off by default) a real model selects correctly

The stubs inject a fixed two-solver menu explicitly, so the drill is
deterministic and independent of `algorithm_base` availability. Recall
itself is unit-tested in test_llm_recall.py.
"""
import json
import pytest
from pathlib import Path
from pwm_control_plane.sandbox import podman_available
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.agents.imaging.llm.planner import LLMImagingPlanner
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

# Confirmed against the real judge, repeatedly (see llm-task-7-report.md):
#   traditional_cpu (iters=100, lam=0.1) -> forward_residual ~0.10-0.13 -> judge FAIL (repairable)
#   best_quality    (iters=80,  lam=0.01) -> forward_residual ~0.02      -> judge PASS
# best_quality uses iters=80 rather than 200: GAP-TV at lam=0.01 already plateaus by ~iter 30
# on this fixture, and the sandbox enforces a 60s wall-clock timeout per container run
# (pwm_control_plane.sandbox.SandboxLimits default) -- 200 iterations occasionally overruns
# that budget under host CPU contention (each container is capped to --cpus 1.0), which starves
# the reconstruction step of its output file and makes the judge return "needs_review" instead of
# a genuine "pass". iters=80 converges to the same residual in a fraction of the time and was
# verified pass-clean across repeated runs.
_SOLVERS = [{"key": "traditional_cpu", "name": "GAP-TV", "reference": "",
             "cfg": {"iters": 100, "lam": 0.1, "tv_iter": 5}},
            {"key": "best_quality", "name": "GAP-TV (80 iter)", "reference": "",
             "cfg": {"iters": 80, "lam": 0.01, "tv_iter": 5}}]


def _pick(*keys):
    return StubAdapter([[TextDelta(text=f'```json\n{{"solver": "{k}"}}\n```')] for k in keys])


def _client(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    # ControlPlaneClient's default HTTP timeout (5s) is shorter than a real GAP-TV
    # reconstruction can take under host CPU contention (each sandboxed container is capped
    # to --cpus 1.0). A client-side timeout does NOT stop the server-side container -- it just
    # makes the client give up and report "control plane unreachable", producing a spurious
    # not_available/needs_review judge report instead of a genuine pass/fail. Give the client
    # more patience than the server's own sandbox wall-clock budget (60s) so every real
    # execution outcome (pass or repairable fail) reaches the judge.
    return server, ControlPlaneClient(uds, timeout=90.0)


def _judge_pass(out):
    return out["status"] == "delivered" and \
        json.loads(Path(out["judge_report"]).read_text())["final_decision"] == "pass"


def test_recalled_solver_selection_delivers(tmp_path):
    server, client = _client(tmp_path)
    try:
        planner = LLMImagingPlanner(_pick("best_quality"), model="stub", solvers=_SOLVERS, max_llm_attempts=2)
        out = run_imaging_task(workspace=tmp_path / "seed", client=client,
                               store=TaskStore(tmp_path / "tasks"), task_id="llm-sel",
                               interaction_mode="I2", planner=planner, governed=False)
        assert _judge_pass(out), out          # best_quality (lam 0.01) reconstructs & passes the real judge
    finally:
        server.should_exit = True


def test_escalates_on_judge_feedback(tmp_path):
    server, client = _client(tmp_path)
    try:
        # first pick traditional_cpu (lam 0.1) -> judge fails -> escalate -> best_quality -> pass
        planner = LLMImagingPlanner(_pick("traditional_cpu", "best_quality"), model="stub",
                                    solvers=_SOLVERS, max_llm_attempts=2)
        out = run_imaging_task(workspace=tmp_path / "seed2", client=client,
                               store=TaskStore(tmp_path / "tasks2"), task_id="llm-esc",
                               interaction_mode="I2", planner=planner, max_repairs=2, governed=False)
        assert _judge_pass(out), out
    finally:
        server.should_exit = True


def test_fallback_delivers_on_invalid_selection(tmp_path):
    server, client = _client(tmp_path)
    try:
        planner = LLMImagingPlanner(_pick("does_not_exist"), model="stub", solvers=_SOLVERS,
                                    max_llm_attempts=1)
        out = run_imaging_task(workspace=tmp_path / "seed3", client=client,
                               store=TaskStore(tmp_path / "tasks3"), task_id="llm-fb",
                               interaction_mode="I2", planner=planner, governed=False)
        assert _judge_pass(out), out          # GAP-TV fallback delivers
    finally:
        server.should_exit = True


@pytest.mark.skipif(True, reason="real-LLM: enable manually with a configured backend")
def test_real_llm_selects_and_delivers(tmp_path):
    from ai4science.harness.adapters.factory import adapter_for
    server, client = _client(tmp_path)
    try:
        planner = LLMImagingPlanner(adapter_for("anthropic"), model="claude-sonnet-5", max_llm_attempts=3)
        out = run_imaging_task(workspace=tmp_path / "seedR", client=client,
                               store=TaskStore(tmp_path / "tasksR"), task_id="llm-real",
                               interaction_mode="I2", planner=planner, governed=False)
        assert out["status"] == "delivered", out   # delivery guaranteed by fallback; LLM selection is the interest
    finally:
        server.should_exit = True
