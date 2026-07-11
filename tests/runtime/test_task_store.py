from pathlib import Path
from ai4science.harness.runtime.contract import compile_contract
from ai4science.harness.runtime.task_store import TaskStore

def test_open_record_and_resume_roundtrip(tmp_path):
    store = TaskStore(Path(tmp_path))
    c = compile_contract(objective="x", capability_profile="A1")
    st = store.open_or_resume("t1", c)
    store.record(st, kind="step", payload={"plan": "step-1", "result": "ok"})
    store.record(st, kind="assumption", payload={"text": "used default seed"})
    store.checkpoint(st)
    # a fresh store instance rebuilds the same state from disk (simulates a restart)
    st2 = TaskStore(Path(tmp_path)).resume("t1")
    assert st2 is not None
    assert st2.contract.hash() == c.hash()
    assert any(j["plan"] == "step-1" for j in st2.journal)
    assert st2.assumptions[0]["text"] == "used default seed"
    assert st2.finished is False

def test_finish_marks_finished(tmp_path):
    store = TaskStore(Path(tmp_path))
    st = store.open_or_resume("t2", compile_contract(objective="x", capability_profile="A1"))
    store.record(st, kind="finish", payload={"status": "delivered"})
    assert st.finished is True
    assert TaskStore(Path(tmp_path)).resume("t2").finished is True

def test_open_or_resume_resumes_existing(tmp_path):
    store = TaskStore(Path(tmp_path))
    c = compile_contract(objective="x", capability_profile="A1")
    st = store.open_or_resume("t3", c)
    store.record(st, kind="step", payload={"plan": "s"})
    st_again = store.open_or_resume("t3", c)   # must resume, not clobber
    assert any(j["plan"] == "s" for j in st_again.journal)
