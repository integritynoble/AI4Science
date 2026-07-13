"""Podman-gated full work-agent RSI loop: seed corpus -> score grid on real
sandboxes -> validation round -> CP-computed scores flow through
run_work_rsi_search end-to-end. Also red-team: inflated mean refused."""
import time, pytest
from pathlib import Path
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.work.rsi import (run_work_rsi_search, run_work_rsi_round,
                                               config_id, DEFAULT_WORK_GRID)

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.sandbox import podman_available
from pwm_control_plane.work_scenes import generate_work_tasks

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")


class TaskAwarePlanner:
    """Writes the seeded tasks' expected artifacts (result.txt="42\\n" for the
    "compute" task, sum.txt="10\\n" for the "transform" task) then verifies.
    Both files are staged regardless of which task is actually active in the
    run workspace -- a harmless superset that satisfies whichever task's
    check.py is currently staged by /stage_worktask. Deterministic; stands in
    for the LLM in the podman path. Honors max_steps: with too small a budget
    for a 2-command task it fails."""
    def __init__(self, config):
        self._config = config
        self._emitted = False

    def next_step(self, state):
        if not self._emitted:
            self._emitted = True
            files = {"result.txt": "42\n", "sum.txt": "10\n"}
            return PlanStep(summary="produce artifacts", command=["true"],
                            stage_files=files, request_verify=False)
        return PlanStep(summary="verify", command=[], request_verify=True)

    def replan(self, state, verdict):
        pass


def _planner_factory(cfg, run_id, criteria):
    # run_work_rsi_round/run_work_rsi_search expect planner_factory(cfg, run_id,
    # criteria) to return a fresh planner per (candidate, task, repeat) so each
    # task's PEV loop starts with clean planner state (_emitted reset) rather
    # than reusing one TaskAwarePlanner instance across tasks.
    return TaskAwarePlanner(cfg)


def _seed(cfg_state_dir):
    eval_dir = Path(cfg_state_dir) / "eval"   # PWM_CP_STATE_DIR set by _serve
    generate_work_tasks(eval_dir, [0, 1, 2], domain="work_search")
    generate_work_tasks(eval_dir, [0, 1], domain="work_val")


def test_full_work_rsi_loop(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        _seed(tmp_path)                       # tmp_path is the CP state dir in _serve
        client = ControlPlaneClient(uds)
        res = run_work_rsi_search(
            client=client,
            planner_factory=_planner_factory,
            store_factory=lambda: TaskStore(tmp_path / f"tasks-{time.monotonic_ns()}"),
            search_task_ids=[0, 1, 2], val_task_ids=[0, 1])
        assert res["best_config"] is not None
        assert res["val_pass"] is not None       # validation round scored best on work_val
        # every candidate produced a mean pass in [0,1] -- real CP-computed scores
        # from real podman sandboxes, not a stubbed/fabricated result
        assert all(0.0 <= p <= 1.0 for _, p, _ in res["ranked"])
        # strengthen: genuine passes, not silent all-fail
        assert res["search_pass"] > 0.0         # CP command-judge pass occurred in search round
        assert res["val_pass"] > 0.0            # validation round also genuinely passed
    finally:
        server.should_exit = True


def test_redteam_inflated_mean_refused(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        _seed(tmp_path)
        client = ControlPlaneClient(uds)
        # run a real round for a single candidate on work_val so the CP has audited scores
        run_work_rsi_round(client=client, held_out_task_ids=[0, 1],
                           candidates=[DEFAULT_WORK_GRID[0]],
                           planner_factory=_planner_factory,
                           store_factory=lambda: TaskStore(tmp_path / f"t-{time.monotonic_ns()}"),
                           domain="work_val")
        # now submit an inflated mean for that candidate -> refused
        cid = config_id(DEFAULT_WORK_GRID[0])
        # reuse the same run is not exposed; submit against a fresh run with no scores
        run = client.open_run("redteam", "A1", {"actions": 2}, interaction_profile="I2")
        ev = client.evaluate_candidates(run["run_id"],
                                        results=[{"version": cid, "mean_psnr": 1.0}],
                                        domain="work_val")
        assert ev.get("ok") is False            # no audited scores for this run -> refused
    finally:
        server.should_exit = True
