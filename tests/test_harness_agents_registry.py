import textwrap
import pytest
from ai4science.harness.agents import registry


@pytest.fixture(autouse=True)
def _restore_default_registry():
    """Guarantee the global AGENT_REGISTRY is restored after every test, even if
    a test reloads a tmp specs dir and then raises before its inline restore."""
    yield
    registry.reload()


def test_ships_expected_agents():
    registry.reload()  # default specs dir
    reg = registry.AGENT_REGISTRY
    assert {"unified-LLM", "research", "computational-imaging",
            "general-purpose"} <= set(reg)
    assert reg["unified-LLM"].tier == "open"
    # 'common' is the back-compat alias for the renamed 'unified-LLM' mode
    assert registry.get("common").name == "unified-LLM"
    assert reg["research"].tier == "science"
    assert reg["research"].system_prompt and "pwm_solutions" in reg["research"].system_prompt


def test_search_finds_by_keyword():
    registry.reload()
    hits = [s.name for s in registry.search("imaging")]
    assert "computational-imaging" in hits
    hits2 = [s.name for s in registry.search("cassi")]   # keyword match
    assert "computational-imaging" in hits2


def test_menu_partitions_core_vs_specific():
    registry.reload()
    assert "unified-LLM" in {s.name for s in registry.core_agents()}
    assert "computational-imaging" in {s.name for s in registry.specific_agents()}
    assert "general-purpose" not in {s.name for s in registry.core_agents()}
    assert "general-purpose" not in {s.name for s in registry.specific_agents()}


def test_duplicate_name_raises(tmp_path):
    d = tmp_path / "specs"
    d.mkdir()
    (d / "a.py").write_text(textwrap.dedent('''
        from ai4science.harness.agents.spec import AgentSpec
        AGENT = AgentSpec(name="dup", tier="open", category="core", title="A", description="d")
    '''))
    (d / "b.py").write_text(textwrap.dedent('''
        from ai4science.harness.agents.spec import AgentSpec
        AGENT = AgentSpec(name="dup", tier="open", category="core", title="B", description="d")
    '''))
    with pytest.raises(ValueError) as e:
        registry.reload(specs_dir=d)
    assert "dup" in str(e.value)
    registry.reload()  # restore default for other tests


def test_unknown_capability_in_spec_raises(tmp_path):
    d = tmp_path / "specs"
    d.mkdir()
    (d / "bad.py").write_text(textwrap.dedent('''
        from ai4science.harness.agents.spec import AgentSpec
        AGENT = AgentSpec(name="bad", tier="science", category="specific",
                          title="B", description="d", capabilities=("no-such-bundle",))
    '''))
    with pytest.raises(ValueError) as e:
        registry.reload(specs_dir=d)
    assert "no-such-bundle" in str(e.value)
    registry.reload()
