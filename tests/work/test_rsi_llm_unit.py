from ai4science.harness.agents.work.rsi_llm import llm_planner_factory
from ai4science.harness.agents.work.planner import LLMWorkPlanner, DEFAULT_MODEL

def test_factory_builds_llm_planner_with_profile_and_criteria():
    factory = llm_planner_factory(client=object(), model=DEFAULT_MODEL)
    cfg = {"prompt_profile": "checklist", "max_steps": 8}
    criteria = {"verify_commands": [["true"]], "required_artifacts": ["out.txt"]}
    planner = factory(cfg, "run-1", criteria)
    assert isinstance(planner, LLMWorkPlanner)
    assert planner._prompt_profile == "checklist"     # threaded from cfg
    assert planner.run_id == "run-1"
    assert planner._criteria == criteria

def test_factory_defaults_criteria_when_none():
    factory = llm_planner_factory(client=object())
    planner = factory({"prompt_profile": "terse", "max_steps": 20}, "r", None)
    # a None criteria must not crash construction; planner uses an empty gate
    assert isinstance(planner, LLMWorkPlanner)
