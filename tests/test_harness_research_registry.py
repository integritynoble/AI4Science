from ai4science.harness.repl import build_research_registry, build_common_registry, RESEARCH_PROMPT


def test_research_registry_has_pwm_data_tools(tmp_path):
    reg = build_research_registry(workspace=tmp_path, session_factory=lambda **k: None)
    names = set(reg.names())
    assert {"read", "edit"}.issubset(names)              # common core
    assert "pwm_solutions" in names and "pwm_principles" in names   # research data tools


def test_common_registry_excludes_research_tools(tmp_path):
    reg = build_common_registry(workspace=tmp_path, session_factory=lambda **k: None)
    names = set(reg.names())
    assert "pwm_solutions" not in names                  # the moat: common can't use solutions


def test_research_prompt_mentions_pwm():
    assert "PWM" in RESEARCH_PROMPT or "principle" in RESEARCH_PROMPT.lower()
