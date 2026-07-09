import os
import pytest
from ai4science.harness.agents import registry

CASES = [
    ("paper", "paper.py"),
    ("computational-imaging", "computational_imaging.py"),
    ("drug-design", "drug_design.py"),
    ("cancer", "cancer.py"),
    ("unified-LLM", "unified_llm.py"),
]

@pytest.mark.parametrize("name,fname", CASES)
def test_agent_sourced_from_package(name, fname):
    registry.reload()
    spec = registry.get(name)
    assert spec is not None and spec.name == name
    assert not os.path.exists(f"ai4science/harness/agents/specs/{fname}"), \
        f"builtin {fname} should be deleted"

def test_unified_is_default_and_open_tier():
    registry.reload()
    u = registry.get("unified-LLM")
    assert u.tier == "open" and u.order == 1 and u.allow_as_subagent is False
    assert registry.get("common") is u   # alias preserved
