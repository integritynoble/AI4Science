from ai4science.harness.runtime.verifier import ExternalCommandVerifier
from ai4science.harness.control_plane.client import ControlPlaneClient

class StubClient:
    def __init__(self, decision, feedback=None):
        self._decision = decision
        self._feedback = feedback or {}
        self.calls = []
    def evaluate(self, run_id, domain="cassi"):
        self.calls.append((run_id, domain))
        return {"decision": self._decision, "score": 0.0, "feedback": self._feedback}

def test_pass_maps_to_complete():
    v = ExternalCommandVerifier(StubClient("pass"), "r1").check({}, None)
    assert v.complete is True and v.repairable is False

def test_fail_maps_to_repairable_with_feedback():
    fb = {"commands": [{"index": 0, "exit_code": 1, "stderr_tail": "boom", "timed_out": False}]}
    v = ExternalCommandVerifier(StubClient("fail", fb), "r1").check({}, None)
    assert v.complete is False and v.repairable is True
    assert v.evidence["feedback"] == fb

def test_needs_review_is_blocker():
    v = ExternalCommandVerifier(StubClient("needs_review"), "r1").check({}, None)
    assert v.complete is False and v.repairable is False

def test_verifier_requests_command_domain():
    stub = StubClient("pass")
    ExternalCommandVerifier(stub, "r7").check({}, None)
    assert stub.calls == [("r7", "command")]

def test_client_set_criteria_fails_closed_on_dead_socket(tmp_path):
    c = ControlPlaneClient(str(tmp_path / "no.sock"), timeout=0.2)
    r = c.set_criteria("r1", [["true"]], [])
    assert r["ok"] is False

def test_client_evaluate_domain_fails_closed_on_dead_socket(tmp_path):
    c = ControlPlaneClient(str(tmp_path / "no.sock"), timeout=0.2)
    r = c.evaluate("r1", domain="command")
    assert r["decision"] == "fail"
