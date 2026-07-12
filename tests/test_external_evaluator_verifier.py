from ai4science.harness.runtime.verifier import ExternalEvaluatorVerifier

class FakeClient:
    def __init__(self, decision): self._d = decision
    def evaluate(self, run_id): return {"decision": self._d, "score": 0.0, "feedback": {}}

def test_pass_is_complete():
    v = ExternalEvaluatorVerifier(FakeClient("pass"), "r1").check({}, None)
    assert v.complete is True

def test_fail_is_repairable_not_complete():
    v = ExternalEvaluatorVerifier(FakeClient("fail"), "r1").check({}, None)
    assert v.complete is False and v.repairable is True

def test_needs_review_neither():
    v = ExternalEvaluatorVerifier(FakeClient("needs_review"), "r1").check({}, None)
    assert v.complete is False and v.repairable is False
