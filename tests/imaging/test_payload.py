from pathlib import Path
from ai4science.harness.agents.imaging import PAYLOAD_DIR

REQUIRED = ["cassi.py", "gap_tv.py", "run_solver.py", "generate_data.py", "spec.md", "benchmark.md"]

def test_payload_files_present():
    for name in REQUIRED:
        assert (PAYLOAD_DIR / name).is_file(), f"missing vendored payload file {name}"

def test_payload_code_is_numpy_only_no_ai4science():
    # The payload runs inside the sandbox (numpy/scipy only) — it must not import ai4science.
    for name in ["cassi.py", "gap_tv.py", "run_solver.py", "generate_data.py"]:
        text = (PAYLOAD_DIR / name).read_text()
        assert "import ai4science" not in text and "from ai4science" not in text, f"{name} imports ai4science"
