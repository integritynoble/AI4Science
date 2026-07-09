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


def test_fm_modalities_lists_all_ten(tmp_path):
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["fm_modalities"].func(str(tmp_path)))
    assert out["ok"] is True
    assert {"cassi", "mri", "ct", "lensless", "holography", "ptychography",
            "fluorescence", "lightsheet", "ultrasound", "photoacoustic"} == set(out["modalities"])


def test_fm_compile_modality_shortcut(tmp_path):
    # The agent can build a model from a modality template without authoring JSON.
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    c = json.loads(tools["fm_compile"].func(
        str(tmp_path), None, "forward_model_in.json", "mri.json",
        "mri", '{"H": 32, "W": 32, "sampling_rate": 0.3}'))
    assert c["ok"] is True and (tmp_path / "mri.json").exists()
    s = json.loads(tools["fm_simulate"].func(str(tmp_path), "mri.json", None, "y.npy", 0))
    assert s["ok"] is True and tuple(s["y_shape"]) == (32, 32)


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


def test_fm_compile_bad_json_returns_error(tmp_path):
    from ai4science.harness.forward_model_tools import forward_model_tools
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["fm_compile"].func(str(tmp_path), model="{not valid json"))
    assert out["ok"] is False
    assert "error" in out


def test_dump_model_json_sanitizes_name(tmp_path):
    import numpy as np
    from ai4science.harness.forward_model_tools import dump_model_json, load_model_json
    from pwm_core.forward_compiler.bridge import from_modality
    m = from_modality("cassi", H=4, W=4, N_bands=2,
                      mask=np.ones((4, 4), dtype=np.float64))
    m.name = "weird/name with spaces"   # must not crash or escape the workspace
    dump_model_json(m, tmp_path, "fm.json")
    raw = json.loads((tmp_path / "fm.json").read_text())
    ref = [s for s in raw["stages"] if s["op"] == "mask_multiply"][0]["params"]["mask"]["$ref"]
    assert "/" not in ref                      # sanitized
    assert (tmp_path / ref).exists()
    m2 = load_model_json(tmp_path, "fm.json")  # round-trips
    assert m2.name == "weird/name with spaces"


def test_fm_compile_validate_simulate_end_to_end(tmp_path):
    import numpy as np
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}

    mask = np.random.default_rng(0).integers(0, 2, (8, 8)).astype(np.float64)
    model = from_modality("cassi", H=8, W=8, N_bands=4, mask=mask)
    dump_model_json(model, tmp_path, "forward_model_in.json")

    out = json.loads(tools["fm_compile"].func(str(tmp_path)))
    assert out["ok"] is True
    assert (tmp_path / "forward_model.json").exists()
    assert (tmp_path / "forward_model_report.json").exists()

    val = json.loads(tools["fm_validate"].func(str(tmp_path)))
    assert val["ok"] is True
    assert val["report"]["is_linear"] is True
    assert val["report"]["adjoint"]["passed"] is True

    sim = json.loads(tools["fm_simulate"].func(str(tmp_path)))
    assert sim["ok"] is True
    assert sim["y_shape"] == [8, 8]
    assert (tmp_path / "y.npy").exists()


def test_fm_compile_inline_model_json(tmp_path):
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    model_json = json.dumps({
        "name": "intensity", "x_shape": [4, 4],
        "stages": [{"op": "square_magnitude", "params": {}}],
    })
    out = json.loads(tools["fm_compile"].func(str(tmp_path), model=model_json))
    # nonlinear: compiles & validates, but flagged non-linear (adjoint skipped)
    assert "non-linear" in json.loads(
        (tmp_path / "forward_model_report.json").read_text())["warnings"][0]


def test_forward_model_capability_bundle_resolves():
    from ai4science.harness.agents.capabilities import resolve_capability, CAPABILITY_BUNDLES
    from ai4science.harness.agents.context import BuildContext

    assert "forward-model" in CAPABILITY_BUNDLES
    ctx = BuildContext(workspace=None, brand_provider=None, session_factory=None)
    tools = resolve_capability("forward-model", ctx)
    names = {t.name for t in tools}
    assert {"fm_primitives", "fm_compile", "fm_validate", "fm_simulate"} <= names


def test_ci_and_research_specs_have_forward_model_capability():
    # computational-imaging and research are now sourced from their packages
    # via entry point (no local specs/computational_imaging.py or specs/research.py
    # files to import) — fetch them through the registry instead.
    from ai4science.harness.agents import registry
    registry.reload()
    CI_SPEC = registry.get("computational-imaging")
    RESEARCH_SPEC = registry.get("research")
    assert "forward-model" in CI_SPEC.capabilities
    assert "forward-model" in RESEARCH_SPEC.capabilities


# ── multi-modality bridge tests ───────────────────────────────────────────────

import pytest
import numpy as np
from pwm_core.forward_compiler import from_modality, compile_model, NativeCompiledOperator

NATIVE_MODALITIES = [
    ("mri",          dict(H=16, W=16)),
    ("ct",           dict(H=16, W=16, n_angles=18)),
    ("lensless",     dict(H=16, W=16)),
    ("holography",   dict(H=16, W=16)),
    ("ptychography", dict(H=16, W=16, probe_size=4, n_positions=3)),
    ("fluorescence", dict(H=16, W=16)),
    ("lightsheet",   dict(H=8,  W=8,  D=4)),
    ("ultrasound",   dict(H=16, W=16)),
    ("photoacoustic",dict(H=16, W=16)),
]


@pytest.mark.parametrize("modality,kw", NATIVE_MODALITIES)
def test_native_modality_forward(modality, kw):
    fm = from_modality(modality, **kw)
    op = compile_model(fm)
    assert isinstance(op, NativeCompiledOperator)
    x = np.random.default_rng(0).standard_normal(op.x_shape).astype(np.float64)
    y = op.forward(x)
    assert np.all(np.isfinite(y)), f"{modality}: non-finite output"
    assert tuple(op.x_shape) == tuple(fm.x_shape)
    assert tuple(op.y_shape) == tuple(np.asarray(y).shape)


@pytest.mark.parametrize("modality,kw", NATIVE_MODALITIES)
def test_native_modality_validate_and_simulate_through_tools(modality, kw, tmp_path):
    # The full path the agent uses: fm_validate + fm_simulate via the tool layer.
    # Native operators have reconstruction-style adjoints → validate.ok stays
    # True (advisory warning, not a crash); simulate always produces output.
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    dump_model_json(from_modality(modality, **kw), tmp_path, "fm.json")
    v = json.loads(tools["fm_validate"].func(str(tmp_path), "fm.json"))
    assert v["ok"] is True, f"{modality}: {v}"
    s = json.loads(tools["fm_simulate"].func(str(tmp_path), "fm.json", None, "y.npy", 0))
    assert s["ok"] is True and (tmp_path / "y.npy").exists()


def test_from_modality_unknown_raises():
    with pytest.raises(ValueError, match="unknown modality"):
        from_modality("xray_banana", H=8, W=8)
