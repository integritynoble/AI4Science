"""Real-sandbox acceptance: the work agent completes a coding task end-to-end
through the LIVE control plane with a REAL podman sandbox, and delivery is
gated by the CP-side command judge (verify commands re-run CP-initiated)."""
import pytest
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.work.agent import run_work_task

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.sandbox import podman_available

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

# calc.py starts broken; tests_check.py exits 0 only when add() is fixed.
DEMAND = {
    "objective": "fix add() in calc.py so tests_check.py passes",
    "input_files": {
        "calc.py": "def add(a, b):\n    return a - b\n",
        "tests_check.py": ("import sys\nfrom calc import add\n"
                           "sys.exit(0 if add(1, 2) == 3 else 1)\n"),
    },
    "verify_commands": [["python3", "tests_check.py"]],
    "required_artifacts": ["calc.py"],
}

class ScriptedPlanner:
    """Deterministic stand-in for the LLM: fix the file, then request verify."""
    def __init__(self):
        self._steps = [
            PlanStep(summary="fix add()", command=["python3", "-c", "print('patched')"],
                     stage_files={"calc.py": "def add(a, b):\n    return a + b\n"},
                     request_verify=False),
            PlanStep(summary="verify success criteria", command=[], request_verify=True),
        ]
    def next_step(self, state):
        return self._steps.pop(0)
    def replan(self, state, verdict):
        pass

def test_work_agent_delivers_end_to_end_i2(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        out = run_work_task(demand=DEMAND, client=client,
                            store=TaskStore(tmp_path / "tasks"), task_id="e2e-work-1",
                            interaction_mode="I2", planner=ScriptedPlanner())
        # delivery required a CP-side re-run of tests_check.py in a real container
        assert out["status"] == "delivered", out
    finally:
        server.should_exit = True

def test_work_agent_broken_fix_never_delivers(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        class BadPlanner(ScriptedPlanner):
            def __init__(self):
                self._steps = [
                    PlanStep(summary="wrong fix", command=["python3", "-c", "print('x')"],
                             stage_files={"calc.py": "def add(a, b):\n    return a * b\n"},
                             request_verify=False),
                    PlanStep(summary="verify", command=[], request_verify=True),
                    PlanStep(summary="give up", command=[], done=True),
                ]
        out = run_work_task(demand=DEMAND, client=client,
                            store=TaskStore(tmp_path / "tasks"), task_id="e2e-work-2",
                            interaction_mode="I2", planner=BadPlanner())
        assert out["status"] == "blocked"       # CP judge failed it; no self-declared success
    finally:
        server.should_exit = True

def test_criteria_proposal_pauses_in_i0(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        proposal = {"verify_commands": [["python3", "tests_check.py"]],
                    "required_artifacts": []}
        demand = {k: v for k, v in DEMAND.items()
                  if k not in ("verify_commands", "required_artifacts")}
        out = run_work_task(demand=demand, client=client,
                            store=TaskStore(tmp_path / "tasks"), task_id="e2e-work-3",
                            interaction_mode="I0",
                            propose=lambda client, run_id, objective, input_files, model: proposal)
        assert out["status"] == "awaiting_owner"
        assert out["proposed_criteria"] == proposal
    finally:
        server.should_exit = True

def test_redteam_second_set_criteria_refused(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        run = client.open_run("g", "A1", {"actions": 5}, interaction_profile="I2")
        assert client.set_criteria(run["run_id"], [["true"]], [])["ok"] is True
        weakened = client.set_criteria(run["run_id"], [["python3", "-c", "exit(0)"]], [])
        assert weakened["ok"] is False           # the gate cannot be weakened mid-run
    finally:
        server.should_exit = True

def test_redteam_a1_sandbox_has_no_network(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        run = client.open_run("g", "A1", {"actions": 5}, interaction_profile="I2")
        probe = ("import urllib.request, sys\n"
                 "try:\n"
                 "    urllib.request.urlopen('http://example.com', timeout=3)\n"
                 "    sys.exit(0)\n"
                 "except Exception:\n"
                 "    sys.exit(7)\n")
        result = client.sandbox_execute(run["run_id"], ["python3", "-c", probe])
        assert result["exit_code"] == 7          # --network none held for authored code
    finally:
        server.should_exit = True

def test_resume_after_crash_continues(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        store = TaskStore(tmp_path / "tasks")
        class CrashingPlanner(ScriptedPlanner):
            def next_step(self, state):
                step = super().next_step(state)
                if step.request_verify:
                    raise RuntimeError("simulated crash before verify")
                return step
        with pytest.raises(RuntimeError):
            run_work_task(demand=DEMAND, client=client, store=store,
                          task_id="e2e-work-4", interaction_mode="I2",
                          planner=CrashingPlanner())
        state = store.resume("e2e-work-4")
        assert state is not None and len(state.journal) >= 1   # pre-crash step persisted
        out = run_work_task(demand=DEMAND, client=client, store=store,
                            task_id="e2e-work-4", interaction_mode="I2",
                            planner=ScriptedPlanner())
        assert out["status"] == "delivered"                    # resumed and finished
    finally:
        server.should_exit = True
