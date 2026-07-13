from pathlib import Path
from ai4science.harness.agents.learning.capability_graph import record_measurement, history
from ai4science.harness.agents.learning.examiner import grade_and_record

def test_record_and_history(tmp_path):
    store = tmp_path / "cap.jsonl"
    record_measurement(store, "biology", 0.5, 4, 1000)
    record_measurement(store, "biology", 0.75, 4, 2000)
    record_measurement(store, "math", 1.0, 2, 1500)
    bio = history(store, "biology")
    assert [m["score"] for m in bio] == [0.5, 0.75]     # ordered, topic-filtered
    assert [m["timestamp"] for m in bio] == [1000, 2000]
    assert len(history(store, "math")) == 1
    assert history(store, "absent") == []

def test_grade_and_record(tmp_path):
    store = tmp_path / "cap.jsonl"
    quiz = {"questions": [{"id": "q1", "type": "mcq", "answer": "B"},
                          {"id": "q2", "type": "short", "answer": "cell"}]}
    m = grade_and_record(quiz=quiz, answers={"q1": "B", "q2": "cell"},
                         store_path=store, topic="biology", timestamp=3000)
    assert m["score"] == 1.0 and m["n"] == 2 and m["topic"] == "biology"
    assert history(store, "biology")[0]["score"] == 1.0
