from __future__ import annotations

from ai4science.harness.repl import build_common_registry


def test_registry_includes_core_pwm_and_task(tmp_path):
    reg = build_common_registry(workspace=tmp_path,
                                session_factory=lambda **k: None,
                                enable_pwm=True, enable_subagents=True)
    names = set(reg.names())
    assert {"read", "edit", "bash"}.issubset(names)   # core
    assert "pwm_status" in names                       # pwm
    assert "task" in names                             # sub-agents


def test_registry_can_disable(tmp_path):
    reg = build_common_registry(workspace=tmp_path,
                                session_factory=lambda **k: None,
                                enable_pwm=False, enable_subagents=False)
    names = set(reg.names())
    assert "pwm_status" not in names and "task" not in names
    assert "read" in names
