"""Modal.com execution backend for the ai4science compute relay.

Modal is an *elastic, serverless* GPU provider: instead of a long-running box
that polls the relay, a founder-side bridge claims jobs for the ``modal-gpu``
provider and runs each one as a Modal function on an on-demand cloud GPU.

This module is two things:

1.  A deployable Modal app (``app`` + ``run_job``).  The founder deploys it once
    from a checkout that has ``packages/pwm_core`` on disk::

        modal deploy ai4science/compute/modal_runner.py

    The image bakes ``pwm_core`` (+ its MST weights) so the same solvers the
    sub-GPU runs (gap_tv, MST-L, …) run identically on Modal.

2.  A host-side shim ``run_solver_modal`` with the SAME signature/return shape as
    ``provider.run_solver`` — it tars the workspace, calls the deployed
    ``run_job`` on Modal, and untars the outputs back into the workspace so
    ``build_result_manifest`` works unchanged.  Users never deploy anything;
    they just dispatch to ``modal-gpu`` and the founder's bridge does the rest.
"""
from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path
from typing import Any, Dict

import modal

APP_NAME = "ai4science-compute"
DEFAULT_GPU = os.environ.get("AI4SCIENCE_MODAL_GPU", "T4")

# Where pwm_core lives at *deploy* time (only needed when deploying the app).
# This module is also imported INSIDE the Modal container, where __file__ lives
# at /root and parents[3] doesn't exist — so resolve defensively (never raise).
def _default_pwm_core_src() -> str:
    here = Path(__file__).resolve()
    if len(here.parents) > 3:
        cand = here.parents[3] / "packages" / "pwm_core"
        if cand.exists():
            return str(cand)
    return "/opt/pwm_core_src"  # already baked into the image at build time


_PWM_CORE_SRC = os.environ.get("AI4SCIENCE_MODAL_PWM_CORE", _default_pwm_core_src())

app = modal.App(APP_NAME)

# pwm_core's runtime deps (mirrors packages/pwm_core/pyproject.toml) + einops
# (used by the MST attention blocks).  torch's default wheel is CUDA-enabled.
_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "numpy>=1.24", "scipy>=1.10", "pydantic>=2.4", "pyyaml>=6.0",
        "tqdm>=4.66", "rich>=13.7", "typer>=0.12", "imageio>=2.31",
        "scikit-image>=0.22", "einops>=0.7", "torch>=2.1",
    )
)
# Bake pwm_core (package + sibling weights/) so PYTHONPATH resolves both the
# import and _find_mst_weights' pkg_top/weights/mst/*.pth lookup. Only added at
# deploy time (when the source is on disk); the container re-imports this module
# with the source absent, so guard it to avoid touching a missing path.
if Path(_PWM_CORE_SRC).exists():
    _image = _image.add_local_dir(_PWM_CORE_SRC, "/opt/pwm_core_src", copy=True)
_image = _image.env({"PYTHONPATH": "/opt/pwm_core_src"})


# Top-level workspace dirs that are INPUTS (shipped code + datasets), never
# returned — mirrors http_transport.pack_artifacts so Modal returns the same set
# of outputs (runs/, checkpoints, *.pt, logs) as the local/gpu providers.
_SKIP_TOP = {"code", "data", "datasets", "dataset", "raw", ".data", "input", "inputs"}
_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".cache", ".venv", "venv",
              "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _pack_outputs(ws: str) -> bytes:
    """Tar everything the job WROTE (runs/, results/, checkpoints, *.pt, logs) —
    the whole workspace except the shipped code/ + data/ inputs and venv/caches —
    so trained checkpoints come back regardless of the script's output layout."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for root, dirs, files in os.walk(ws):
            rel_root = os.path.relpath(root, ws)
            top = "" if rel_root == "." else rel_root.split(os.sep)[0]
            if top in _SKIP_TOP:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in files:
                if f.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, ws).replace(os.sep, "/")
                tf.add(full, arcname=rel)
    return buf.getvalue()


@app.function(image=_image, gpu=DEFAULT_GPU, timeout=900)
def run_job(workspace_tar: bytes, run_command: str, timeout_s: int) -> Dict[str, Any]:
    """Unpack a workspace, run the solver on a Modal GPU, return outcome + outputs.

    Mirrors provider.run_solver's outcome dict, plus wall_clock_s and an
    ``output_tar`` of the produced artifacts.
    """
    import shlex
    import subprocess
    import tempfile
    import time

    ws = tempfile.mkdtemp(prefix="modal_job_")
    with tarfile.open(fileobj=io.BytesIO(workspace_tar)) as tf:
        tf.extractall(ws)

    t0 = time.time()
    env = dict(os.environ, PYTHONPATH="/opt/pwm_core_src")
    try:
        proc = subprocess.run(
            shlex.split(run_command), cwd=ws, capture_output=True, text=True,
            timeout=timeout_s, check=False, env=env,
        )
        ok, rc = proc.returncode == 0, proc.returncode
        out, err = proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        ok, rc, out, err = False, None, "", f"solver timed out after {timeout_s}s"
    except (OSError, ValueError) as e:
        ok, rc, out, err = False, None, "", f"solver exec error: {type(e).__name__}: {e}"

    try:
        import torch  # noqa
        device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:
        device = "unknown"

    return {
        "ok": ok, "returncode": rc,
        "stdout_tail": out[-2000:], "stderr_tail": err[-2000:],
        "wall_clock_s": round(time.time() - t0, 2),
        "device": device,
        "output_tar": _pack_outputs(ws),
    }


def run_solver_modal(workspace: Path, run_command: str, timeout_s: int,
                     *, gpu: str = DEFAULT_GPU) -> Dict[str, Any]:
    """Host-side drop-in for provider.run_solver that executes on Modal.

    Tars the workspace, invokes the deployed ``run_job`` on a Modal GPU, and
    untars the returned artifacts back into ``workspace``.  Returns the same
    keys provider.run_solver does (ok/returncode/stdout_tail/stderr_tail) plus
    wall_clock_s + device.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        tf.add(str(workspace), arcname=".")

    fn = modal.Function.from_name(APP_NAME, "run_job")
    res = dict(fn.remote(buf.getvalue(), run_command, timeout_s))

    out_tar = res.pop("output_tar", b"") or b""
    if out_tar:
        with tarfile.open(fileobj=io.BytesIO(out_tar)) as tf:
            tf.extractall(str(workspace))
    return res


# MST-L is the GPU self-test: a deep transformer with pretrained weights, so it
# actually exercises CUDA on the Modal box (gap_tv is largely CPU-bound TV).
_MSTL_SELFTEST = '''\
import json, time, numpy as np
d = np.load("data/cassi_ref.npz"); img = d["img"].astype("float32"); mask = d["mask"].astype("float32")
H, W, L = img.shape; step = 2
y = np.zeros((H, W + (L - 1) * step), "float32")
for k in range(L):
    y[:, k*step:k*step+W] += mask * img[:, :, k]
out = {"modality": "cassi", "solver": "mst_l", "n_bands": L, "step": step}
t = time.time()
try:
    from pwm_core.recon.mst import mst_recon_cassi
    xhat = mst_recon_cassi(y, mask, nC=L, step=step, variant="mst_l")
    out["source"] = "pwm_core.recon.mst:mst_l"
    mse = float(np.mean((np.clip(np.asarray(xhat), 0, 1) - img) ** 2))
    out["psnr_db"] = round(10 * np.log10(1.0 / mse), 3)
    out["recon_shape"] = list(np.asarray(xhat).shape)
    import torch; out["cuda"] = bool(torch.cuda.is_available())
except Exception as e:
    out["error"] = "{}:{}".format(type(e).__name__, str(e)[:200])
out["seconds"] = round(time.time() - t, 1)
print("RESULT " + json.dumps(out))
'''


@app.local_entrypoint()
def _selftest():
    """`modal run ai4science/compute/modal_runner.py` — runs the bundled CASSI
    scene through MST-L (deep, GPU) on Modal end to end and prints RESULT."""
    import shutil
    import tempfile

    from ai4science.harness import algorithm_tools as A

    run_src = _MSTL_SELFTEST
    ref = Path(A.__file__).resolve().parent / "data" / "cassi_ref.npz"
    job = Path(tempfile.mkdtemp(prefix="modal_selftest_"))
    (job / "code").mkdir()
    (job / "data").mkdir()
    (job / "code" / "run_solver.py").write_text(run_src)
    shutil.copyfile(ref, job / "data" / "cassi_ref.npz")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        tf.add(str(job), arcname=".")
    res = run_job.remote(buf.getvalue(), "python code/run_solver.py", 600)
    print("ok:", res["ok"], "rc:", res["returncode"], "device:", res["device"],
          "wall_clock_s:", res["wall_clock_s"])
    for line in (res["stdout_tail"] or "").splitlines():
        if line.startswith("RESULT "):
            print(line)
    if not res["ok"]:
        print("stderr:", res["stderr_tail"][-600:])
