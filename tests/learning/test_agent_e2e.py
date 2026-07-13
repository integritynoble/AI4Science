"""Real-sandbox acceptance: the learning agent delivers only when the CP-side
quiz_check grounding gate passes; a hallucinated-answer quiz and a source-tamper
are blocked. Plus the deterministic grade_and_record produces a capability entry."""
import json
import pytest
from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.runtime.pev import PlanStep
from ai4science.harness.agents.learning.agent import run_learning_task
from ai4science.harness.agents.learning.examiner import grade_and_record
from ai4science.harness.agents.learning.capability_graph import history

pwm_cp = pytest.importorskip("pwm_control_plane")
from pwm_control_plane.sandbox import podman_available
pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")

MATERIAL = {"m.txt": "Photosynthesis occurs in the chloroplast. "
                     "The mitochondria is the powerhouse of the cell.\n"}
DEMAND = {"topic": "cell biology", "material": MATERIAL,
          "min_questions": 2, "coverage_points": ["photosynthesis", "mitochondria"]}

_QUIZ = {"topic": "cell biology", "questions": [
    {"id": "q1", "type": "mcq", "prompt": "Where does photosynthesis occur?",
     "options": {"A": "nucleus", "B": "chloroplast"}, "answer": "B",
     "grounding": "Photosynthesis occurs in the chloroplast"},
    {"id": "q2", "type": "short", "prompt": "Powerhouse of the cell?",
     "answer": "mitochondria", "grounding": "mitochondria is the powerhouse of the cell"}]}
_GUIDE = "# Cell biology\n\nCovers photosynthesis in the chloroplast and the mitochondria.\n"


def _files(quiz=_QUIZ, guide=_GUIDE):
    return {"study_guide.md": guide, "quiz.json": json.dumps(quiz)}


class GroundedPlanner:
    def __init__(self, files):
        self._s = [PlanStep(summary="write", command=["true"], stage_files=files, request_verify=False),
                   PlanStep(summary="verify", command=[], request_verify=True),
                   PlanStep(summary="give up", command=[], done=True)]
    def next_step(self, state): return self._s.pop(0)
    def replan(self, state, verdict): pass


def test_grounded_quiz_delivers(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        out = run_learning_task(demand=DEMAND, client=ControlPlaneClient(uds),
                                store=TaskStore(tmp_path / "t"), task_id="e2e-l-1",
                                interaction_mode="I2", planner=GroundedPlanner(_files()))
        assert out["status"] == "delivered", out
    finally:
        server.should_exit = True


def test_hallucinated_answer_blocked(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        bad = json.loads(json.dumps(_QUIZ)); bad["questions"][0]["grounding"] = "invented span"
        out = run_learning_task(demand=DEMAND, client=ControlPlaneClient(uds),
                                store=TaskStore(tmp_path / "t"), task_id="e2e-l-2",
                                interaction_mode="I2", planner=GroundedPlanner(_files(bad)))
        assert out["status"] == "blocked"
    finally:
        server.should_exit = True


def test_source_tamper_blocked(tmp_path):
    from tests.test_control_plane_client import _serve
    server, uds = _serve(tmp_path)
    try:
        files = _files(); files["material/m.txt"] = "edited material\n"   # overwrite the staged source
        out = run_learning_task(demand=DEMAND, client=ControlPlaneClient(uds),
                                store=TaskStore(tmp_path / "t"), task_id="e2e-l-3",
                                interaction_mode="I2", planner=GroundedPlanner(files))
        assert out["status"] == "blocked"      # SHA integrity
    finally:
        server.should_exit = True


def test_grade_and_record_end_to_end(tmp_path):
    store = tmp_path / "cap.jsonl"
    m = grade_and_record(quiz=_QUIZ, answers={"q1": "B", "q2": "mitochondria"},
                         store_path=store, topic="cell biology", timestamp=1000)
    assert m["score"] == 1.0
    assert history(store, "cell biology")[0]["score"] == 1.0
