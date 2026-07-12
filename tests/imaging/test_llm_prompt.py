from ai4science.harness.agents.imaging.llm.prompt import build_selection_messages
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskState

SOLVERS = [{"key": "traditional_cpu", "name": "GAP-TV", "reference": "Yuan 2016",
            "cfg": {"iters": 100, "lam": 0.1, "tv_iter": 5}},
           {"key": "best_quality", "name": "GAP-TV (200 iter)", "reference": "Yuan 2016",
            "cfg": {"iters": 200, "lam": 0.01, "tv_iter": 5}}]

def _state(journal=None):
    st = TaskState(task_id="t", contract=compile_contract(objective="reconstruct the CASSI scene",
                                                          capability_profile="A1"))
    st.journal = journal or []
    return st

def test_messages_carry_menu_and_spec():
    msgs = build_selection_messages(_state(), SOLVERS)
    assert {m.role for m in msgs} >= {"system", "user"}
    blob = "\n".join(m.content for m in msgs)
    assert "traditional_cpu" in blob and "best_quality" in blob   # the recalled menu
    assert "solver" in blob                                        # selection instruction
    assert "32" in blob                                            # spec text (real fixture)

def test_includes_residual_feedback_when_given():
    blob = "\n".join(m.content for m in build_selection_messages(_state(), SOLVERS, last_residual=0.12))
    assert "0.12" in blob and "residual" in blob.lower()

def test_no_feedback_when_none():
    # The system prompt legitimately mentions "forward residual" as domain framing (lam vs. residual
    # trade-off), so we assert on the injected feedback sentence itself, not the bare word "residual".
    blob = "\n".join(m.content for m in build_selection_messages(_state(), SOLVERS))
    assert "your previous solver" not in blob.lower()
