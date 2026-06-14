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


def algorithm_tools() -> List[Tool]:
    return [_modalities_tool(), _algorithms_tool(), _info_tool(), _run_tool()]
