import os, pytest
from ai4science.harness.agents import registry

@pytest.mark.parametrize("name,fname,backend", [
    ("claude-code", "claude_code.py", "anthropic"),
    ("codex", "codex.py", "openai"),
])
def test_passthrough_agent_sourced_from_package(name, fname, backend):
    registry.reload()
    spec = registry.get(name)
    assert spec is not None and spec.name == name
    assert spec.default_backend == backend
    assert spec.allow_as_subagent is False
    assert not os.path.exists(f"ai4science/harness/agents/specs/{fname}")
