# AI4Science/tests/test_forward_model_tools.py
"""forward_model_tools: primitives listing + model JSON ref round-trip + tools."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ai4science.harness.forward_model_tools import (
    forward_model_tools, dump_model_json, load_model_json, TOOL_PRICES,
)
from pwm_core.forward_compiler.bridge import from_modality


def test_fm_primitives_lists_builtins(tmp_path):
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["fm_primitives"].func(str(tmp_path)))
    names = {p["name"] for p in out["primitives"]}
    assert {"scale", "mask_multiply", "band_shift", "band_sum",
            "square_magnitude", "gaussian_noise"} <= names
    linear = {p["name"]: p["is_linear"] for p in out["primitives"]}
    assert linear["mask_multiply"] is True
    assert linear["square_magnitude"] is False


def test_model_json_ref_roundtrip(tmp_path):
    mask = np.random.default_rng(0).integers(0, 2, (8, 8)).astype(np.float64)
    model = from_modality("cassi", H=8, W=8, N_bands=4, mask=mask)
    dump_model_json(model, tmp_path, "forward_model.json")
    # array param must be externalized as a $ref + a saved .npy
    raw = json.loads((tmp_path / "forward_model.json").read_text())
    mm = [s for s in raw["stages"] if s["op"] == "mask_multiply"][0]
    assert isinstance(mm["params"]["mask"], dict) and "$ref" in mm["params"]["mask"]
    assert (tmp_path / mm["params"]["mask"]["$ref"]).exists()
    # round-trip restores the array
    model2 = load_model_json(tmp_path, "forward_model.json")
    mm2 = [s for s in model2.stages if s.op == "mask_multiply"][0]
    assert np.allclose(mm2.params["mask"], mask)


def test_tool_prices_present():
    for name in ("fm_compile", "fm_validate", "fm_simulate"):
        assert name in TOOL_PRICES
