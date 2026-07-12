from ai4science.harness.agents.imaging.llm.extract import extract_solver_key

KEYS = ["traditional_cpu", "best_quality", "small_gpu", "twist"]

def test_json_block():
    assert extract_solver_key('```json\n{"solver": "best_quality"}\n```', KEYS) == "best_quality"

def test_inline_json():
    assert extract_solver_key('I choose {"solver":"twist"} here.', KEYS) == "twist"

def test_single_bare_mention():
    assert extract_solver_key("I recommend best_quality for this.", KEYS) == "best_quality"

def test_invalid_key_returns_none():
    assert extract_solver_key('```json\n{"solver": "mst_l"}\n```', KEYS) is None

def test_ambiguous_bare_returns_none():
    assert extract_solver_key("either traditional_cpu or best_quality", KEYS) is None
