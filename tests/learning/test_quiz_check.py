import hashlib, json
from pathlib import Path
from ai4science.harness.agents.learning.quiz_check import check_quiz, sha256_file

MATERIAL = {"m.txt": "The mitochondria is the powerhouse of the cell. "
                     "Photosynthesis occurs in the chloroplast.\n"}

GUIDE = ("# Study Guide\n\n"
         "This covers the mitochondria and photosynthesis in the chloroplast.\n")

QUIZ = {"topic": "cell biology", "questions": [
    {"id": "q1", "type": "mcq", "prompt": "Where does photosynthesis occur?",
     "options": {"A": "nucleus", "B": "chloroplast", "C": "ribosome"},
     "answer": "B", "grounding": "Photosynthesis occurs in the chloroplast"},
    {"id": "q2", "type": "short", "prompt": "What is the powerhouse of the cell?",
     "answer": "mitochondria", "grounding": "mitochondria is the powerhouse of the cell"},
]}

def _ws(tmp_path, material, guide, quiz, coverage, tamper=None):
    (tmp_path / "material").mkdir(exist_ok=True)
    src = {}
    for name, content in material.items():
        (tmp_path / "material" / name).write_text(content)
        src[f"material/{name}"] = hashlib.sha256(content.encode()).hexdigest()
    if tamper:
        for name, content in tamper.items():
            (tmp_path / "material" / name).write_text(content)
    (tmp_path / "study_guide.md").write_text(guide)
    (tmp_path / "quiz.json").write_text(json.dumps(quiz))
    cfg = {"study_guide": "study_guide.md", "quiz": "quiz.json",
           "sources": src, "min_questions": 2, "coverage_points": coverage}
    return tmp_path, cfg

def test_grounded_quiz_passes(tmp_path):
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, QUIZ, ["photosynthesis", "mitochondria"])
    assert check_quiz(ws, cfg)["ok"] is True

def test_fabricated_grounding_fails(tmp_path):
    bad = json.loads(json.dumps(QUIZ)); bad["questions"][0]["grounding"] = "invented span not present"
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, bad, ["photosynthesis", "mitochondria"])
    r = check_quiz(ws, cfg); assert r["ok"] is False and "ground" in r["reason"].lower()

def test_source_tamper_fails(tmp_path):
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, QUIZ, ["photosynthesis", "mitochondria"],
                  tamper={"m.txt": "edited material\n"})
    r = check_quiz(ws, cfg); assert r["ok"] is False and ("integrity" in r["reason"].lower() or "tamper" in r["reason"].lower())

def test_too_few_questions_fails(tmp_path):
    one = {"topic": "x", "questions": QUIZ["questions"][:1]}
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, one, ["photosynthesis"])
    assert check_quiz(ws, cfg)["ok"] is False

def test_mcq_answer_not_an_option_fails(tmp_path):
    bad = json.loads(json.dumps(QUIZ)); bad["questions"][0]["answer"] = "Z"
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, bad, ["photosynthesis", "mitochondria"])
    assert check_quiz(ws, cfg)["ok"] is False

def test_missing_answer_fails(tmp_path):
    bad = json.loads(json.dumps(QUIZ)); del bad["questions"][1]["answer"]
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, bad, ["photosynthesis", "mitochondria"])
    assert check_quiz(ws, cfg)["ok"] is False

def test_duplicate_id_fails(tmp_path):
    bad = json.loads(json.dumps(QUIZ)); bad["questions"][1]["id"] = "q1"
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, bad, ["photosynthesis", "mitochondria"])
    assert check_quiz(ws, cfg)["ok"] is False

def test_uncovered_point_fails(tmp_path):
    ws, cfg = _ws(tmp_path, MATERIAL, GUIDE, QUIZ, ["photosynthesis", "ribosome assembly"])
    r = check_quiz(ws, cfg); assert r["ok"] is False and "coverage" in r["reason"].lower()

def test_missing_quiz_file_fails(tmp_path):
    (tmp_path / "study_guide.md").write_text(GUIDE)
    cfg = {"study_guide": "study_guide.md", "quiz": "quiz.json", "sources": {},
           "min_questions": 1, "coverage_points": []}
    assert check_quiz(tmp_path, cfg)["ok"] is False

def test_sha256_file_helper(tmp_path):
    p = tmp_path / "x.txt"; p.write_text("hi\n")
    assert sha256_file(p) == hashlib.sha256(b"hi\n").hexdigest()
