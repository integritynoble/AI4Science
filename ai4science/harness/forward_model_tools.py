"""Forward-model compiler agent tools (science-tier, PWM-metered).

Exposes the pwm_core.forward_compiler to agents: list primitives, compile a
structured ForwardModel (with validation), validate an existing compiled model,
and run the compiled forward to produce a measurement. Array params (masks etc.)
are externalized to .npy + {"$ref": ...} for JSON persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from ai4science.harness.tools.base import Tool
from pwm_core.forward_compiler import (
    ForwardModel, Stage, PRIMITIVES, compile_model, validate_forward_model,
)

# PWM price per call (moat tool; mirrors optics-design metering).
TOOL_PRICES: Dict[str, float] = {
    "fm_primitives": 0.0,     # read-only discovery, free
    "fm_compile": 0.02,
    "fm_validate": 0.01,
    "fm_simulate": 0.02,
}


# --- JSON <-> IR with array externalization ---------------------------------

def dump_model_json(model: ForwardModel, workspace: Path, name: str) -> Path:
    workspace = Path(workspace)
    d = model.to_dict()
    for i, stage in enumerate(d["stages"]):
        for key, val in list(stage["params"].items()):
            if isinstance(val, np.ndarray):
                ref = f"_fm_{model.name}_{i}_{key}.npy"
                np.save(workspace / ref, val)
                stage["params"][key] = {"$ref": ref}
    path = workspace / name
    path.write_text(json.dumps(d, indent=2))
    return path


def load_model_json(workspace: Path, name: str) -> ForwardModel:
    workspace = Path(workspace)
    d = json.loads((workspace / name).read_text())
    for stage in d["stages"]:
        for key, val in list(stage["params"].items()):
            if isinstance(val, dict) and "$ref" in val:
                stage["params"][key] = np.load(workspace / val["$ref"])
    return ForwardModel.from_dict(d)


# --- tool funcs -------------------------------------------------------------

def _fm_primitives(workspace: str) -> str:
    prims = [{"name": p.name, "is_linear": p.is_linear,
              "has_adjoint": p.adjoint is not None}
             for p in PRIMITIVES.values()]
    return json.dumps({"ok": True, "primitives": sorted(prims, key=lambda p: p["name"])})


def _resolve_model(workspace: Path, model: Optional[str], model_path: str) -> ForwardModel:
    if model:
        d = json.loads(model)
        for stage in d.get("stages", []):
            for key, val in list(stage.get("params", {}).items()):
                if isinstance(val, dict) and "$ref" in val:
                    stage["params"][key] = np.load(workspace / val["$ref"])
        return ForwardModel.from_dict(d)
    return load_model_json(workspace, model_path)


def _fm_compile(workspace: str, model: Optional[str] = None,
                model_path: str = "forward_model_in.json",
                out: str = "forward_model.json") -> str:
    ws = Path(workspace)
    fm = _resolve_model(ws, model, model_path)
    report = validate_forward_model(fm)
    dump_model_json(fm, ws, out)
    (ws / "forward_model_report.json").write_text(json.dumps(report.to_dict(), indent=2))
    return json.dumps({"ok": report.ok, "model": out,
                       "report": "forward_model_report.json",
                       "summary": report.summary()})


def _fm_validate(workspace: str, model_path: str = "forward_model.json") -> str:
    ws = Path(workspace)
    fm = load_model_json(ws, model_path)
    report = validate_forward_model(fm)
    (ws / "forward_model_report.json").write_text(json.dumps(report.to_dict(), indent=2))
    return json.dumps({"ok": report.ok, "summary": report.summary(),
                       "report": report.to_dict()})


def _fm_simulate(workspace: str, model_path: str = "forward_model.json",
                 x: Optional[str] = None, out: str = "y.npy", seed: int = 0) -> str:
    ws = Path(workspace)
    fm = load_model_json(ws, model_path)
    op = compile_model(fm)
    if x:
        x_arr = np.load(ws / x)
    else:
        x_arr = np.random.default_rng(int(seed)).standard_normal(op.x_shape)
    y = op.forward(x_arr.astype(np.float64))
    np.save(ws / out, y)
    return json.dumps({"ok": True, "x_shape": list(op.x_shape),
                       "y_shape": list(np.asarray(y).shape), "out": out})


def forward_model_tools(gate_provider: Optional[Callable] = None,
                        workspace: Optional[Path] = None) -> List[Tool]:
    """Build the forward-model tool bundle.

    gate_provider is accepted for parity with other moat bundles (optics);
    PWM metering is applied by the harness via TOOL_PRICES when a gate exists.
    """
    return [
        Tool(name="fm_primitives",
             description="List the forward-model compiler's primitive ops "
                         "(name, linear, has_adjoint). Use this to compose a model.",
             parameters={"type": "object", "properties": {}},
             func=_fm_primitives, mutating=False),
        Tool(name="fm_compile",
             description="Compile + validate a structured ForwardModel. Provide "
                         "either `model` (JSON string of {name,x_shape,stages,...}) "
                         "or `model_path` (a JSON file in the workspace). Writes "
                         "forward_model.json + forward_model_report.json. Array "
                         "params use {\"$ref\":\"file.npy\"}.",
             parameters={"type": "object", "properties": {
                 "model": {"type": "string", "description": "Inline ForwardModel JSON"},
                 "model_path": {"type": "string", "default": "forward_model_in.json"},
                 "out": {"type": "string", "default": "forward_model.json"}}},
             func=_fm_compile, mutating=True),
        Tool(name="fm_validate",
             description="Validate an already-compiled forward_model.json: adjoint "
                         "dot-product test, linearity, conditioning. Writes the report.",
             parameters={"type": "object", "properties": {
                 "model_path": {"type": "string", "default": "forward_model.json"}}},
             func=_fm_validate, mutating=True),
        Tool(name="fm_simulate",
             description="Run the compiled forward operator to produce a measurement "
                         "y.npy (random x if none supplied).",
             parameters={"type": "object", "properties": {
                 "model_path": {"type": "string", "default": "forward_model.json"},
                 "x": {"type": "string", "description": "optional input .npy"},
                 "out": {"type": "string", "default": "y.npy"},
                 "seed": {"type": "integer", "default": 0}}},
             func=_fm_simulate, mutating=True),
    ]
