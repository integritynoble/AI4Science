from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
from . import PAYLOAD_DIR

_CODE_FILES = ["cassi.py", "gap_tv.py", "run_solver.py", "generate_data.py"]

def seed_cassi_workspace(workspace: Path, *, seed: int = 42) -> dict:
    """Populate ``workspace`` with a small synthetic CASSI benchmark + the vendored
    reconstruction code, ready for ``python3 code/run_solver.py --workspace .``.
    Deterministic given ``seed``."""
    workspace = Path(workspace)
    (workspace / "code").mkdir(parents=True, exist_ok=True)
    for name in _CODE_FILES:
        shutil.copy(PAYLOAD_DIR / name, workspace / "code" / name)
    for doc in ("spec.md", "benchmark.md"):
        shutil.copy(PAYLOAD_DIR / doc, workspace / doc)
    # Generate the benchmark data with the SAME forward model the solver uses.
    subprocess.run([sys.executable, "code/generate_data.py", "--workspace", ".", "--seed", str(seed)],
                   cwd=str(workspace), check=True, capture_output=True, text=True)
    y = np.load(workspace / "data" / "measurement_y.npy")
    return {"seed": seed, "y_shape": list(y.shape), "workspace": str(workspace)}
