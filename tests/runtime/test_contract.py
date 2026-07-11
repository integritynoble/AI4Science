import pytest
from ai4science.harness.runtime.contract import TaskContract, compile_contract

def test_compile_defaults_and_roundtrip():
    c = compile_contract(objective="Reconstruct scene", capability_profile="A1",
                         deliverables=["recon.npy"], success_criteria=["judge passes"])
    assert c.interaction_mode == "I1"
    assert c.authority["network"] == "none"
    assert c.budget["tool_calls"] == 100
    d = c.to_dict()
    assert TaskContract.from_dict(d) == c

def test_compile_rejects_bad_mode():
    with pytest.raises(ValueError):
        compile_contract(objective="x", capability_profile="A1", interaction_mode="I9")

def test_hash_is_stable_and_content_sensitive():
    a = compile_contract(objective="x", capability_profile="A1")
    b = compile_contract(objective="x", capability_profile="A1")
    c = compile_contract(objective="y", capability_profile="A1")
    assert a.hash() == b.hash() and a.hash() != c.hash()
