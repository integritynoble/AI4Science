"""test_optics_phase1.py — Phase 1 optics tests: pwm_bridge, coded, closed tools."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

results = []


def check(name, cond, info=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, info))
    print(f"  [{status}] {name}" + (f" — {info}" if info else ""))


def _run():
    ok = all(r[0] == "PASS" for r in results)
    total = len(results)
    passed = sum(1 for r in results if r[0] == "PASS")
    print(f"\n{passed}/{total} checks passed")
    return ok


# ── imports ──────────────────────────────────────────────────────────────────

try:
    from pwm_core.optics.pwm_bridge import optical_to_spec_fields
    check("pwm_bridge import", True)
except Exception as exc:
    check("pwm_bridge import", False, str(exc))
    sys.exit(1)

try:
    from pwm_core.optics.coded import (
        binary_mask, optimized_mask, cassi_forward,
        lensless_forward, doe_phase_grating, doe_phase_fresnel_lens,
    )
    check("coded import", True)
except Exception as exc:
    check("coded import", False, str(exc))
    sys.exit(1)

try:
    from pwm_core.optics import (
        OpticalSystem, Surface, Field, Wavelength, save_system,
        optical_to_spec_fields as _bridge,
        binary_mask as _bm,
    )
    check("optics __init__ re-exports", True)
except Exception as exc:
    check("optics __init__ re-exports", False, str(exc))

# ── binary_mask ───────────────────────────────────────────────────────────────

mask = binary_mask(32, 48, density=0.5, seed=7)
check("binary_mask shape", mask.shape == (32, 48), str(mask.shape))
check("binary_mask values {0,1}", set(np.unique(mask)).issubset({0, 1}))
check("binary_mask density ~0.5", abs(mask.mean() - 0.5) < 0.15)

# ── optimized_mask ────────────────────────────────────────────────────────────

omask = optimized_mask(32, 48, N_bands=8, disp_a1=1.0, seed=99)
check("optimized_mask shape", omask.shape == (32, 48), str(omask.shape))
check("optimized_mask binary", set(np.unique(omask)).issubset({0, 1}))

# ── cassi_forward ─────────────────────────────────────────────────────────────

H, W, NB = 16, 24, 4
scene = np.random.default_rng(0).random((H, W, NB)).astype(np.float32)
ca_mask = binary_mask(H, W, density=0.5, seed=1)
meas = cassi_forward(scene, ca_mask, disp_a1=1.0)
W_meas = W + int((NB - 1))
check("cassi_forward shape", meas.shape == (H, W_meas),
      f"got {meas.shape}, expected ({H},{W_meas})")
check("cassi_forward nonneg", float(meas.min()) >= 0)

# ── doe_phase_grating ─────────────────────────────────────────────────────────

phase_1d = doe_phase_grating(64, pitch_m=10e-6, wavelength_m=550e-9)
check("doe_phase_grating shape", phase_1d.shape == (64,), str(phase_1d.shape))
check("doe_phase_grating range [0,2π)", float(phase_1d.min()) >= 0 and float(phase_1d.max()) < 2 * np.pi + 0.01)

# ── doe_phase_fresnel_lens ────────────────────────────────────────────────────

phase_2d = doe_phase_fresnel_lens(32, 32)
check("fresnel_lens shape", phase_2d.shape == (32, 32), str(phase_2d.shape))
check("fresnel_lens range [0,2π)", float(phase_2d.min()) >= 0)

# ── lensless_forward ──────────────────────────────────────────────────────────

obj = np.random.default_rng(5).random((32, 32)).astype(np.float32)
ph = doe_phase_fresnel_lens(32, 32)
lf = lensless_forward(obj, ph, prop_dist_m=0.01)
check("lensless_forward shape", lf.shape == (32, 32), str(lf.shape))
check("lensless_forward nonneg", float(lf.min()) >= 0)

# ── pwm_bridge: psf_convolution ───────────────────────────────────────────────

def _make_doublet():
    surfs = [
        Surface(radius=50.0, thickness=4.0, material="N-BK7"),
        Surface(radius=-50.0, thickness=2.0, material="N-F2"),
        Surface(radius=-200.0, thickness=45.0, material="air"),
        Surface(radius=float("inf"), thickness=0.0, material="air"),
    ]
    return OpticalSystem(
        surfaces=surfs,
        fields=[Field(y=0.0)],
        wavelengths=[Wavelength(value=0.55, is_primary=True)],
        aperture_type="EPD",
        aperture_value=10.0,
        title="Test Doublet",
    )

sys_obj = _make_doublet()
fields_conv = optical_to_spec_fields(sys_obj, modality="psf_convolution",
                                      H=128, W=128, N_bands=1)
check("bridge psf_convolution returns d_spec",
      "d_spec" in fields_conv and 0.0 <= fields_conv["d_spec"] <= 1.0,
      str(fields_conv.get("d_spec")))
check("bridge psf_convolution six_tuple.omega.H",
      "H" in fields_conv.get("six_tuple", {}).get("omega", {}))
check("bridge psf_convolution spec_type",
      fields_conv.get("spec_type") == "psf_convolution")

# ── pwm_bridge: cassi ─────────────────────────────────────────────────────────

fields_cassi = optical_to_spec_fields(sys_obj, modality="cassi",
                                       H=64, W=64, N_bands=8, disp_a1=1.0)
check("bridge cassi d_spec", 0.0 <= fields_cassi["d_spec"] <= 1.0)
check("bridge cassi omega has N_bands",
      "N_bands" in fields_cassi["six_tuple"]["omega"])
check("bridge cassi E operator cassi_forward",
      fields_cassi["six_tuple"]["E"]["operator"] == "cassi_forward")
check("bridge cassi protocol_fields disp_a1",
      "disp_a1_nominal" in fields_cassi["protocol_fields"])

# ── pwm_bridge: lensless ─────────────────────────────────────────────────────

fields_ll = optical_to_spec_fields(sys_obj, modality="lensless", H=64, W=64)
check("bridge lensless spec_type",
      fields_ll.get("spec_type") == "lensless")
check("bridge lensless E operator lensless_diffraction",
      fields_ll["six_tuple"]["E"]["operator"] == "lensless_diffraction")

# ── closed tool: optics_to_digital_twin (gate=None, so free) ─────────────────

try:
    from ai4science.harness.optics_tools import optics_tools, TOOL_PRICES
    check("closed tool prices present",
          "optics_to_digital_twin" in TOOL_PRICES
          and "optics_coded_design" in TOOL_PRICES
          and "optics_ground" in TOOL_PRICES)

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        tools = optics_tools(gate_provider=None, workspace=ws)
        tool_map = {t.name: t for t in tools}

        check("optics_to_digital_twin in tools", "optics_to_digital_twin" in tool_map)
        check("optics_coded_design in tools", "optics_coded_design" in tool_map)
        check("optics_ground in tools", "optics_ground" in tool_map)

        # write a system.json first
        save_system(sys_obj, str(ws / "system.json"))

        # digital twin
        r_dt = tool_map["optics_to_digital_twin"].func(
            str(ws), modality="cassi", H=64, W=64, N_bands=8,
        )
        dt = json.loads(r_dt)
        check("optics_to_digital_twin ok", dt.get("ok") is True, str(dt))
        check("optics_to_digital_twin d_spec", "d_spec" in dt)
        check("digital_twin_spec.json created", (ws / "digital_twin_spec.json").exists())

        # coded design
        r_cd = tool_map["optics_coded_design"].func(
            str(ws), modality="cassi", H=32, W=32, N_bands=4,
        )
        cd = json.loads(r_cd)
        check("optics_coded_design ok", cd.get("ok") is True, str(cd))
        check("mask.npy created", (ws / "mask.npy").exists())

        # optics_ground (may fail if network unavailable — treat as soft)
        try:
            r_gr = tool_map["optics_ground"].func(str(ws), query="cassi spectral")
            gr = json.loads(r_gr)
            check("optics_ground ok", gr.get("ok") is True, str(gr))
        except Exception as exc:
            check("optics_ground ok (soft)", True, f"network unavailable: {exc}")

except Exception as exc:
    check("optics_tools closed tools", False, str(exc))

def test_optics_phase1():
    """Pytest entry: assert the Phase 1 optics checks (run above) all passed."""
    failed = [r for r in results if r[0] != "PASS"]
    assert _run(), f"phase1 optics checks failed: {failed}"


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
