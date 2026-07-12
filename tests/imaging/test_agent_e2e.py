"""Task 4: real-sandbox acceptance drill.

Runs the imaging agent's real GAP-TV reconstruction in a REAL podman sandbox
via the LIVE control plane, gated by the REAL Physics Judge. With input
staging in place (`/stage_input`), the real container finds the staged
`code/`+`data/`, runs GAP-TV, writes `results/` into the run workspace, and
the real judge gates delivery. This is the authoritative real-sandbox proof;
the host-sim test (test_agent_hostsim.py) only validates agent *logic*
deterministically (it executes the solver directly on the host workspace,
with no container indirection).
"""
import json
import pytest
from pathlib import Path
from pwm_control_plane.sandbox import podman_available
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.agents.imaging.agent import run_imaging_task

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")


def test_imaging_agent_delivers_end_to_end_i2(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        out = run_imaging_task(workspace=tmp_path / "seed", client=client,
                               store=TaskStore(tmp_path / "tasks"), task_id="e2e-img-1",
                               interaction_mode="I2", seed=42, max_repairs=2, governed=False)
        assert out["status"] == "delivered", out
        # completion was gated by the REAL judge, run in a REAL container:
        report = json.loads(Path(out["judge_report"]).read_text())
        assert report["final_decision"] == "pass", report
    finally:
        server.should_exit = True


def test_imaging_agent_interactive_pauses_i0(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        out = run_imaging_task(workspace=tmp_path / "seed0", client=client,
                               store=TaskStore(tmp_path / "tasks0"), task_id="e2e-img-0",
                               interaction_mode="I0", seed=42, governed=False)
        assert out["status"] == "awaiting_owner"        # gateway ASKed at the reconstruction fork
    finally:
        server.should_exit = True
