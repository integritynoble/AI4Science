"""Real-sandbox acceptance: the research agent delivers only when the CP-side
research_check grounding verifier passes in a real container; a hallucinated
quote is blocked."""
import pytest
from pathlib import Path
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.research.agent import run_research_task

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.sandbox import podman_available
pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

SOURCES = {"a.txt": "The sky is blue because of Rayleigh scattering of sunlight.\n",
           "b.txt": "Rayleigh scattering is stronger for shorter blue wavelengths.\n"}
DEMAND = {"question": "Why is the sky blue?", "sources": SOURCES,
          "coverage_points": ["Rayleigh scattering", "blue wavelengths"]}

_GOOD_REPORT = (
    "# Why the sky is blue\n\n"
    "The sky is blue because of Rayleigh scattering, which redirects sunlight across "
    "the atmosphere and is the accepted physical cause of the daytime color [S1].\n\n"
    "Rayleigh scattering is stronger for shorter blue wavelengths, so blue light is "
    "scattered far more than red across the visible spectrum we observe [S2].\n\n"
    "## References\n"
    'S1: sources/a.txt — "Rayleigh scattering of sunlight"\n'
    'S2: sources/b.txt — "stronger for shorter blue wavelengths"\n')

class GroundedPlanner:
    def __init__(self):
        self._s = [PlanStep(summary="write report", command=["true"],
                            stage_files={"report.md": _GOOD_REPORT}, request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass

class HallucinatingPlanner:
    def __init__(self):
        bad = _GOOD_REPORT.replace('"Rayleigh scattering of sunlight"',
                                   '"invented quote not in any source"')
        self._s = [PlanStep(summary="write", command=["true"],
                            stage_files={"report.md": bad}, request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True),
                   PlanStep(summary="give up", command=[], done=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass

class SourceTamperingPlanner:
    """Fabricates a quote AND overwrites the source so it 'appears' grounded —
    caught by the SHA integrity check (expected hash is in CP-private criteria)."""
    def __init__(self):
        bad = _GOOD_REPORT.replace('"Rayleigh scattering of sunlight"', '"fabricated injected span"')
        self._s = [PlanStep(summary="tamper", command=["true"],
                            stage_files={"report.md": bad,
                                         "sources/a.txt": "fabricated injected span now here\n"},
                            request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True),
                   PlanStep(summary="give up", command=[], done=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass

def test_grounded_report_delivers(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        out = run_research_task(demand=DEMAND, client=client,
                                store=TaskStore(tmp_path / "t"), task_id="e2e-res-1",
                                interaction_mode="I2", planner=GroundedPlanner())
        assert out["status"] == "delivered", out
    finally:
        server.should_exit = True

def test_hallucinated_quote_blocked(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        out = run_research_task(demand=DEMAND, client=client,
                                store=TaskStore(tmp_path / "t"), task_id="e2e-res-2",
                                interaction_mode="I2", planner=HallucinatingPlanner())
        assert out["status"] == "blocked"      # CP grounding check caught the fabricated quote
    finally:
        server.should_exit = True

def test_source_tamper_blocked(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        out = run_research_task(demand=DEMAND, client=client,
                                store=TaskStore(tmp_path / "t"), task_id="e2e-res-tamper",
                                interaction_mode="I2", planner=SourceTamperingPlanner())
        assert out["status"] == "blocked"      # SHA integrity check caught the edited source
    finally:
        server.should_exit = True

def test_coverage_proposal_pauses_i0(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        client = ControlPlaneClient(uds)
        demand = {"question": "Why is the sky blue?", "sources": SOURCES}   # no coverage
        out = run_research_task(demand=demand, client=client,
                                store=TaskStore(tmp_path / "t"), task_id="e2e-res-3",
                                interaction_mode="I0",
                                propose=lambda c, rid, q, si, m: ["Rayleigh scattering"])
        assert out["status"] == "awaiting_owner"
        assert out["proposed_coverage"] == ["Rayleigh scattering"]
    finally:
        server.should_exit = True
