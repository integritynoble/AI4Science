from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
from . import PAYLOAD_DIR

_CODE_FILES = ["cassi.py", "gap_tv.py", "run_solver.py", "generate_data.py"]

def seed_cassi_workspace(workspace: Path, *, seed: int = 42,
                         real: bool = True) -> dict:
    """Populate ``workspace`` with a CASSI benchmark + the vendored solver,
    ready for ``python3 code/run_solver.py --workspace .``. Deterministic
    given ``seed``.

    The scene is a **real hyperspectral capture** from the CAVE database,
    chosen by seed. It used to be synthesised from Gaussian blobs — the
    generator's own docstring called it "a synthetic stand-in for real
    KAIST-like data" — and blobs are trivially sparse and unusually kind to a
    total-variation prior. Real scenes carry the spectral correlation a
    reconstruction prior actually has to work with: adjacent bands correlate
    at 0.93 here, and across 400-700nm at 0.78.

    **The measurement is still simulated.** A real scene pushed through the
    forward model is not a capture from a physical CASSI instrument, and this
    benchmark does not claim to close the sim-to-real gap its own design file
    names as the field's chief shortage. It closes the easier half: the scene.
    """
    workspace = Path(workspace)
    (workspace / "code").mkdir(parents=True, exist_ok=True)
    (workspace / "data").mkdir(parents=True, exist_ok=True)
    for name in _CODE_FILES:
        shutil.copy(PAYLOAD_DIR / name, workspace / "code" / name)
    for doc in ("spec.md", "benchmark.md"):
        shutil.copy(PAYLOAD_DIR / doc, workspace / doc)

    scene = None
    if real:
        from ai4science.harness.agents.research_agents.runners import corpus
        root = corpus.CAVE.require()          # refuses rather than falling back
        import json as _json
        meta = _json.loads((root / "metadata.json").read_text())
        names = sorted(meta["scenes"])
        scene = names[seed % len(names)]
        cube = np.load(root / "scenes.npz")[scene].astype(np.float32)
        np.save(workspace / "data" / "ground_truth_x.npy", cube)

    # Build mask and measurement with the SAME forward model the solver uses.
    cmd = [sys.executable, "code/generate_data.py", "--workspace", ".",
           "--seed", str(seed)]
    if scene is not None:
        cmd.append("--from-truth")
    subprocess.run(cmd, cwd=str(workspace), check=True, capture_output=True, text=True)
    y = np.load(workspace / "data" / "measurement_y.npy")
    return {"seed": seed, "y_shape": list(y.shape), "workspace": str(workspace),
            "scene": scene, "real_scene": scene is not None,
            "measurement": "simulated from the forward model"}
