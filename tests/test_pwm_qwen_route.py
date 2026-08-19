from ai4science.llm import execute, openai_compat, routing


def test_pwm_qwen_is_a_distinct_exact_backend():
    assert openai_compat.resolve_base("pwm_qwen") == "https://physicsworldmodel.org/qwen/v1"
    assert openai_compat.default_model("pwm_qwen") == "qwen3.8:27b"
    assert openai_compat.default_model("qwen") != "qwen3.8:27b"
    assert "pwm_qwen" in execute._EXECUTORS


def test_pwm_qwen_is_not_in_an_ordinary_fallback_chain():
    assert all(backend != "pwm_qwen"
               for chain in routing.AGENT_CHAINS.values()
               for backend, _model in chain)
