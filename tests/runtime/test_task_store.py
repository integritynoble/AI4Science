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

def test_resume_tolerates_torn_final_line(tmp_path):
    store = TaskStore(Path(tmp_path))
    c = compile_contract(objective="x", capability_profile="A1")
    st = store.open_or_resume("t5", c)
    store.record(st, kind="step", payload={"plan": "s1"})
    store.record(st, kind="step", payload={"plan": "s2"})
    p = Path(tmp_path) / "t5.jsonl"
    lines = p.read_text().splitlines()
    lines[-1] = lines[-1][: max(1, len(lines[-1]) // 2)]  # simulate a torn final append
    p.write_text("\n".join(lines) + "\n")
    recovered = TaskStore(Path(tmp_path)).resume("t5")   # must NOT raise
    assert recovered is not None
    assert recovered.contract.hash() == c.hash()
    assert any(j["plan"] == "s1" for j in recovered.journal)  # recoverable prefix intact

def test_append_repairs_torn_write_so_next_record_survives(tmp_path):
    c = compile_contract(objective="x", capability_profile="A1")
    store = TaskStore(Path(tmp_path))
    st = store.open_or_resume("t6", c)
    store.record(st, kind="step", payload={"plan": "s1"})
    # simulate a real crash mid-append: truncate the file mid-last-line, NO trailing newline
    p = Path(tmp_path) / "t6.jsonl"
    raw = p.read_text()
    p.write_text(raw[: len(raw) - 4])          # chops the trailing newline + part of the last record
    assert not p.read_text().endswith("\n")     # confirm the torn shape (no trailing newline)
    # a fresh process resumes and records a new COMMITTED step
    store2 = TaskStore(Path(tmp_path))
    st2 = store2.open_or_resume("t6", c)
    store2.record(st2, kind="step", payload={"plan": "s2-redone"})
    # a later resume must retain that post-crash committed step
    st3 = TaskStore(Path(tmp_path)).resume("t6")
    assert st3 is not None
    assert any(j.get("plan") == "s2-redone" for j in st3.journal)  # committed step NOT dropped
