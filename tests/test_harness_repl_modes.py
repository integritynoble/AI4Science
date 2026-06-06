from ai4science.harness import repl
from ai4science.harness.agents import registry


def test_mode_menu_text_lists_core_and_specific():
    registry.reload()
    txt = repl._format_mode_menu()
    assert "unified-LLM" in txt and "research" in txt and "specific" in txt.lower()


def test_mode_specific_search_text():
    registry.reload()
    txt = repl._format_specific_list("imaging")
    assert "computational-imaging" in txt


def test_build_main_registry_for_spec(tmp_path):
    registry.reload()
    ctx = repl._make_build_context(workspace=tmp_path,
                                   brand_provider=lambda: ("gemini", "m"))
    reg = repl._registry_for_spec(registry.get("common"), is_subagent=False, ctx=ctx)
    assert "task" in reg.names() and not any(n.startswith("pwm_") for n in reg.names())
    rreg = repl._registry_for_spec(registry.get("research"), is_subagent=False, ctx=ctx)
    assert "pwm_solutions" in rreg.names()
