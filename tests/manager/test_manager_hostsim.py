import pytest
from ai4science.harness.agents.manager.agent import run_manager, builtin_specs
from ai4science.harness.agents.spec import AgentSpec

SPECS = [
    AgentSpec(name="work", tier="open", category="core", title="General Work",
              description="coding data analysis files", keywords=("coding", "data", "files")),
    AgentSpec(name="imaging", tier="science", category="specific", title="Computational Imaging",
              description="cassi reconstruction", keywords=("cassi", "reconstruction")),
]


class NoActClient:
    """Any write/execute call fails the test — the manager must never act."""
    def open_run(self, *a, **k): raise AssertionError("manager must not open_run")
    def sandbox_execute(self, *a, **k): raise AssertionError("manager must not sandbox_execute")
    def set_criteria(self, *a, **k): raise AssertionError("manager must not set_criteria")
    def stage_input(self, *a, **k): raise AssertionError("manager must not stage_input")


def test_returns_proposal_and_executes_nothing():
    out = run_manager(demand={"intent": "reconstruct the cassi scene"},
                      client=NoActClient(), specs=SPECS)
    assert out["recommended_agent"] == "imaging"
    assert out["draft_demand"] == {"agent": "imaging", "objective": "reconstruct the cassi scene"}
    assert out["gap"] is None
    assert any(r["name"] == "imaging" for r in out["registry"])
    assert "confirmation required" in out["rationale"].lower()


def test_gap_when_no_agent_fits():
    out = run_manager(demand={"intent": "book me a flight to paris"}, specs=SPECS)
    assert out["recommended_agent"] is None and out["draft_demand"] is None
    assert out["gap"] and "niche agent" in out["gap"]


def test_works_with_no_client():
    out = run_manager(demand={"intent": "some coding on files"}, client=None, specs=SPECS)
    assert out["recommended_agent"] == "work"


def test_optional_llm_rationale_is_used():
    def propose(client, intent, recommended):
        return f"LLM rationale for {recommended}"
    out = run_manager(demand={"intent": "cassi reconstruction"}, specs=SPECS, propose=propose)
    assert out["rationale"] == "LLM rationale for imaging"


def test_builtin_specs_collects_shipped_agents():
    names = {s.name for s in builtin_specs()}
    # at least the ones known to exist in-tree
    assert {"work", "imaging"} <= names
