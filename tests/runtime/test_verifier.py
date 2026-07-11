from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.verifier import CommandExitVerifier, PhysicsJudgeVerifier, Verdict

C = compile_contract(objective="x", capability_profile="A1")

def test_command_exit_complete_on_zero_with_artifacts():
    v = CommandExitVerifier(required_artifacts=["out.npy"])
    ok = v.check({"exit_code": 0, "artifacts": ["out.npy"]}, C)
    assert ok.complete is True

def test_command_exit_repairable_on_nonzero():
    v = CommandExitVerifier()
    r = v.check({"exit_code": 1, "timed_out": False}, C)
    assert r.complete is False and r.repairable is True

def test_command_exit_missing_artifact_not_complete():
    v = CommandExitVerifier(required_artifacts=["out.npy"])
    r = v.check({"exit_code": 0, "artifacts": []}, C)
    assert r.complete is False

def test_physics_judge_maps_final_decision(monkeypatch, tmp_path):
    import ai4science.harness.runtime.verifier as mod
    monkeypatch.setattr(mod, "judge_cassi", lambda submission, benchmark=None: {"final_decision": "pass"})
    v = PhysicsJudgeVerifier(tmp_path)
    assert v.check({}, C).complete is True
    monkeypatch.setattr(mod, "judge_cassi", lambda submission, benchmark=None: {"final_decision": "fail"})
    r = v.check({}, C); assert r.complete is False and r.repairable is True
    monkeypatch.setattr(mod, "judge_cassi", lambda submission, benchmark=None: {"final_decision": "needs_review"})
    n = v.check({}, C); assert n.complete is False and n.repairable is False
