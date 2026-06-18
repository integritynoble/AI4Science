"""Reconstruction-algorithm tools — the PWM algorithm_base as agent tools.

Science-tier only (capability bundle "ci-algorithms"): research / paper /
computational-imaging agents can browse and run every reconstruction algorithm
registered in the monorepo's algorithm_base (170 modalities). The open tier
(claude-code, codex, unified-LLM) never receives this bundle — those agents
stay pure base coding agents.

algorithm_base lives at the Physics_World_Model repo root, outside this
package; it is resolved via PWM_REPO_ROOT or by walking up from this file.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from ai4science.harness.tools.base import Tool


class AlgorithmsError(Exception):
    pass


def _contained(workspace: Path, rel: str) -> Path:
    target = (Path(workspace) / rel).resolve()
    try:
        target.relative_to(Path(workspace).resolve())
    except ValueError:
        raise AlgorithmsError(f"path escapes the workspace: {rel}")
    return target


def _repo_root() -> Optional[Path]:
    env = os.environ.get("PWM_REPO_ROOT", "")
    if env and (Path(env) / "algorithm_base" / "_registry.py").exists():
        return Path(env)
    for p in Path(__file__).resolve().parents:
        if (p / "algorithm_base" / "_registry.py").exists():
            return p
    return None


def _algorithm_base():
    """Import the monorepo algorithm_base package (adds repo root to sys.path)."""
    try:
        import algorithm_base
        return algorithm_base
    except ImportError:
        root = _repo_root()
        if root is None:
            raise AlgorithmsError(
                "algorithm_base not importable — set PWM_REPO_ROOT to the "
                "Physics_World_Model checkout")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import algorithm_base
        return algorithm_base


def _solver_info(ab, modality: str, solver: str) -> dict:
    for key, info in ab.list_solvers(modality):
        if key == solver:
            return dict(info)
    keys = ", ".join(k for k, _ in ab.list_solvers(modality))
    raise AlgorithmsError(f"unknown solver {solver!r} for {modality!r}; have: {keys}")


def _modalities_tool() -> Tool:
    def _list(workspace, *, filter: str = "") -> str:
        try:
            ab = _algorithm_base()
            mods = [m for m in ab.list_modalities() if filter.lower() in m.lower()]
            return (f"{len(mods)} modalities:\n" + "\n".join(mods))[:20000] \
                if mods else f"(no modality matches {filter!r})"
        except Exception as exc:
            return f"[ci error] {exc}"

    return Tool(
        name="ci_modalities",
        description=("List computational-imaging modalities in the PWM algorithm "
                     "base (cassi, ct, mri, cacti, spc, …). Optional substring filter."),
        parameters={"type": "object", "properties": {
            "filter": {"type": "string"}}, "required": []},
        func=_list, mutating=False)


def _algorithms_tool() -> Tool:
    def _list(workspace, *, modality: str) -> str:
        try:
            ab = _algorithm_base()
            lines = []
            for key, info in ab.list_solvers(modality):
                gpu = "GPU" if info.get("gpu") else "CPU"
                lines.append(f"{key}: {info.get('name', '?')} [{gpu}] — "
                             f"{info.get('reference', '')}")
            return "\n".join(lines)[:20000] if lines else f"(no solvers for {modality!r})"
        except Exception as exc:
            return f"[ci error] {exc}"

    return Tool(
        name="ci_algorithms",
        description=("List ALL registered reconstruction algorithms for a "
                     "modality (key, name, CPU/GPU, reference). e.g. "
                     "modality='cassi' → GAP-TV, MST-L, HDNet, DAUHST…"),
        parameters={"type": "object", "properties": {
            "modality": {"type": "string"}}, "required": ["modality"]},
        func=_list, mutating=False)


def _info_tool() -> Tool:
    def _info(workspace, *, modality: str, solver: str) -> str:
        try:
            ab = _algorithm_base()
            info = _solver_info(ab, modality, solver)
            return json.dumps({"modality": modality, "solver": solver, **info},
                              indent=2, default=str)[:20000]
        except Exception as exc:
            return f"[ci error] {exc}"

    return Tool(
        name="ci_algorithm_info",
        description=("Full metadata for one reconstruction algorithm: "
                     "implementation module/function, GPU requirement, default "
                     "hyperparameters, paper reference."),
        parameters={"type": "object", "properties": {
            "modality": {"type": "string"}, "solver": {"type": "string"}},
            "required": ["modality", "solver"]},
        func=_info, mutating=False)


def _run_tool() -> Tool:
    def _run(workspace, *, modality: str, solver: str, measurement: str,
             output: str = "x_hat.npy", config: str = "") -> str:
        try:
            ab = _algorithm_base()
            info = _solver_info(ab, modality, solver)
            if info.get("gpu"):
                return (f"[ci error] {solver} ({info.get('name')}) is GPU-class: "
                        "run it on a compute provider instead — use cassi_dispatch "
                        "or compute_dispatch (costs PWM), not a local run.")
            import numpy as np
            y = np.load(_contained(Path(workspace), measurement))
            cfg = json.loads(config) if config else None
            x_hat = ab.run_solver(modality, solver, y, None, cfg)
            out = _contained(Path(workspace), output)
            out.parent.mkdir(parents=True, exist_ok=True)
            np.save(out, x_hat)
            return (f"{info.get('name', solver)} on {modality}: reconstructed "
                    f"{x_hat.shape} from {y.shape}; saved to {output}")
        except AlgorithmsError as exc:
            return f"[ci error] {exc}"
        except Exception as exc:
            return f"[ci error] {exc}"

    return Tool(
        name="ci_run_algorithm",
        description=("Run a CPU reconstruction algorithm locally on workspace "
                     "data: loads the measurement .npy, runs the algorithm_base "
                     "solver, saves the reconstruction .npy. GPU algorithms are "
                     "refused — dispatch those to a compute provider. config is "
                     "an optional JSON dict of hyperparameter overrides."),
        parameters={"type": "object", "properties": {
            "modality": {"type": "string"}, "solver": {"type": "string"},
            "measurement": {"type": "string"}, "output": {"type": "string"},
            "config": {"type": "string"}},
            "required": ["modality", "solver", "measurement"]},
        func=_run, mutating=True)


# ── run_algorithm: run a reconstruction on the sub-GPU and return metrics ────
# Science agents (research/paper/computational-imaging/physics-reviewer) can run
# real algorithms even though an INSTALLED user has no algorithm_base/pwm_core/
# data locally — we ship a tiny run_solver.py + a bundled standard scene to the
# founder-GPU (which HAS pwm_core), dispatch over the relay, and return the PSNR.

_CASSI_PRESETS = {              # solver name -> (iterations, lam) for GAP-TV
    "gap_tv": (100, 0.1), "traditional_cpu": (100, 0.1),
    "best_quality": (200, 0.01), "small": (50, 0.1),
}

_RUN_SOLVER_TMPL = '''\
import json, time, numpy as np
d = np.load("data/cassi_ref.npz"); img = d["img"].astype("float32"); mask = d["mask"].astype("float32")
H, W, L = img.shape; step = 2
y = np.zeros((H, W + (L - 1) * step), "float32")
for k in range(L):
    y[:, k*step:k*step+W] += mask * img[:, :, k]
iters, lam = {iters}, {lam}
out = {{"modality": "cassi", "solver": "{solver}", "n_bands": L, "step": step, "iters": iters, "lam": lam}}
t = time.time()
try:
    from pwm_core.recon.gap_tv import gap_tv_cassi
    xhat = gap_tv_cassi(y, mask, n_bands=L, iterations=iters, lam=lam, step=step)
    out["source"] = "pwm_core.recon.gap_tv"
    mse = float(np.mean((np.clip(np.asarray(xhat), 0, 1) - img) ** 2))
    out["psnr_db"] = round(10 * np.log10(1.0 / mse), 3)
    out["recon_shape"] = list(np.asarray(xhat).shape)
except Exception as e:
    out["error"] = "{{}}:{{}}".format(type(e).__name__, str(e)[:160])
out["seconds"] = round(time.time() - t, 1)
print("RESULT " + json.dumps(out))
'''

# Spec-driven modalities: run pwm_core's simulate→recon→analyze pipeline from a
# tiny self-contained spec (synthetic phantom, no bundled data). Only modalities
# VERIFIED to return a finite, positive PSNR via the generic tv_fista pipeline
# are listed — the other shipped example specs are untuned (degenerate metrics).
_SPEC_MODALITIES = ("mri", "lensless")

_SPEC_RUN_TMPL = '''\
import json, time
out = {"mode": "spec"}
t = time.time()
try:
    from pwm_core.api.types import ExperimentSpec
    from pwm_core.api.endpoints import simulate
    spec = ExperimentSpec.model_validate(json.load(open("data/spec.json")))
    res = simulate(spec)
    r = res.recon[0] if res.recon else None
    out["solver"] = getattr(r, "solver_id", None)
    m = dict(getattr(r, "metrics", {}) or {})
    p = m.get("psnr")
    out["psnr_db"] = round(float(p), 3) if isinstance(p, (int, float)) else None
    out["metrics"] = {k: m.get(k) for k in ("psnr", "ssim", "mse") if k in m}
    out["source"] = "pwm_core.api.simulate"
except Exception as e:
    out["error"] = "{}:{}".format(type(e).__name__, str(e)[:160])
out["seconds"] = round(time.time() - t, 1)
print("RESULT " + json.dumps(out, default=str))
'''


def _run_algorithm_tool() -> Tool:
    def _run(workspace, *, modality: str = "cassi", solver: str = "gap_tv",
             provider: str = "founder-gpu", max_runtime_s: int = 600,
             confirm: bool = False) -> str:
        import json as _json
        import shutil
        import tempfile
        import time as _time
        from pathlib import Path as _P

        modality = (modality or "cassi").strip().lower()
        data_dir = _P(__file__).resolve().parent / "data"

        # Build (run_solver source, inputs to ship, label) per modality.
        if modality == "cassi":
            solver = (solver or "gap_tv").strip().lower()
            iters, lam = _CASSI_PRESETS.get(solver, (100, 0.1))
            ref = data_dir / "cassi_ref.npz"
            if not ref.exists():
                return f"[run_algorithm] bundled CASSI scene missing at {ref}"
            run_src = _RUN_SOLVER_TMPL.format(iters=iters, lam=lam, solver=solver)
            inputs = [(ref, "data/cassi_ref.npz")]
            label = (f"CASSI/{solver} (GAP-TV {iters} iters, lam={lam}) on the bundled "
                     "128×128×28 KAIST scene")
        elif modality in _SPEC_MODALITIES:
            spec = data_dir / "specs" / f"{modality}.json"
            if not spec.exists():
                return f"[run_algorithm] bundled spec missing at {spec}"
            run_src = _SPEC_RUN_TMPL
            inputs = [(spec, "data/spec.json")]
            label = f"{modality} (pwm_core simulate→recon→analyze, synthetic phantom)"
        else:
            return ("[run_algorithm] supported modalities (verified to run + return a "
                    f"finite, positive metric): cassi, {', '.join(_SPEC_MODALITIES)}. "
                    "Other modalities' shipped example specs are untuned (degenerate "
                    "metrics) — use compute_dispatch with your own code for those.")

        from ai4science.harness import compute_tools as _ct
        prov = _ct._resolve(provider)
        if prov is None:
            return ("[run_algorithm] no remote provider resolved for "
                    f"{provider!r}; pass provider=founder-gpu (see compute_providers).")
        from ai4science.compute import billing as _billing
        est = _billing.compute_pwm(prov.pwm_per_hour(), max_runtime_s)
        if confirm is not True:
            return (f"[preview] would run {label} on {prov.provider_id} over the relay.\n"
                    f"  est PWM: up to {est} → {prov.wallet_address}\n"
                    "Pass confirm=true to run (~40–90s; returns the metric).")

        # Build the throwaway job workspace: run_solver.py + the modality inputs.
        job = _P(tempfile.mkdtemp(prefix="ai4s_runalgo_"))
        (job / "code").mkdir(); (job / "data").mkdir()
        (job / "code" / "run_solver.py").write_text(run_src)
        for _src, _rel in inputs:
            shutil.copyfile(_src, job / _rel)
        try:
            from ai4science.compute.transport import select
            _mode, tx = select(prov)
            if not getattr(tx, "token", ""):
                return ("[run_algorithm] not logged in — run /login (or `ai4science "
                        "login`) so the relay can dispatch as you.")
            jb = tx.dispatch(provider_id=prov.provider_id,
                             run_command="python code/run_solver.py",
                             workspace=job, max_runtime_s=max_runtime_s)
            jid = jb.get("job_id")
            # inline poll up to ~3 min
            deadline = _time.time() + min(max_runtime_s, 200)
            while _time.time() < deadline:
                _time.sleep(8)
                st = tx.poll(jid)
                state = st.get("state")
                if state in ("done", "completed", "succeeded", "failed", "error"):
                    res = st.get("result") or {}
                    tail = res.get("solver_stdout_tail", "") if isinstance(res, dict) else ""
                    line = next((l for l in tail.splitlines() if l.startswith("RESULT ")), "")
                    if line:
                        m = _json.loads(line[len("RESULT "):])
                        if m.get("psnr_db") is not None:
                            return (f"✓ ran {modality} on {prov.provider_id}: "
                                    f"PSNR={m['psnr_db']} dB  ({m.get('seconds')}s, "
                                    f"solver {m.get('solver') or m.get('source', '-')}). "
                                    f"job {jid}")
                        return (f"[run_algorithm] ran on GPU but no finite metric: "
                                f"{m.get('error') or m}  job {jid}")
                    return (f"[run_algorithm] job {jid} {state} but no RESULT line; "
                            f"poll with compute_result(job_id=\"{jid}\", "
                            f"provider=\"{prov.provider_id}\").")
            return (f"[run_algorithm] dispatched job {jid} (still running) — poll with "
                    f"compute_result(job_id=\"{jid}\", provider=\"{prov.provider_id}\").")
        finally:
            shutil.rmtree(job, ignore_errors=True)

    return Tool(
        name="run_algorithm",
        description=("Run a reconstruction algorithm on a compute provider (the "
                     "sub-GPU) and return its quality metric (PSNR) — for users who "
                     "don't have the algorithm stack/data locally. Verified modalities: "
                     "'cassi' (solver in {gap_tv, traditional_cpu, best_quality, small}, "
                     "bundled KAIST scene), 'mri', 'lensless' (pwm_core simulate "
                     "pipeline, synthetic phantom). Pass confirm=true to run (ships a "
                     "tiny solver + inputs to provider=founder-gpu over the relay, "
                     "~40–90s, PWM charged on a verified pass); without confirm you get "
                     "a cost preview. Needs `ai4science login`. Other modalities' specs "
                     "are untuned — use compute_dispatch with your own code for those."),
        parameters={"type": "object", "properties": {
            "modality": {"type": "string"}, "solver": {"type": "string"},
            "provider": {"type": "string"}, "max_runtime_s": {"type": "integer"},
            "confirm": {"type": "boolean"}}},
        func=_run, mutating=True)


def algorithm_tools() -> List[Tool]:
    return [_modalities_tool(), _algorithms_tool(), _info_tool(), _run_tool(),
            _run_algorithm_tool()]
