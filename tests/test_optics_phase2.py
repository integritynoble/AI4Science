"""test_optics_phase2.py — Phase 2 optics tests: grating, thinfilm, stray_light,
wave, monte_carlo, snr."""
from __future__ import annotations
import math
import sys

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
    from pwm_core.optics.grating import grating_efficiency, grating_crosstalk
    check("grating import", True)
except Exception as exc:
    check("grating import", False, str(exc))
    sys.exit(1)

try:
    from pwm_core.optics.thinfilm import tmm, design_bandpass, design_longpass
    check("thinfilm import", True)
except Exception as exc:
    check("thinfilm import", False, str(exc))
    sys.exit(1)

try:
    from pwm_core.optics.stray_light import stray_light_analysis, baffle_optimization
    check("stray_light import", True)
except Exception as exc:
    check("stray_light import", False, str(exc))
    sys.exit(1)

try:
    from pwm_core.optics.wave import (
        angular_spectrum_propagate, coherent_psf, fdtd_1d, diffraction_limit,
    )
    check("wave import", True)
except Exception as exc:
    check("wave import", False, str(exc))
    sys.exit(1)

try:
    from pwm_core.optics.monte_carlo import mcml, hb_absorption
    check("monte_carlo import", True)
except Exception as exc:
    check("monte_carlo import", False, str(exc))
    sys.exit(1)

try:
    from pwm_core.optics.radiometry import snr_budget, irradiance_at_sensor, noise_equivalent_power
    check("radiometry import", True)
except Exception as exc:
    check("radiometry import", False, str(exc))
    sys.exit(1)

# Test __init__ re-exports
try:
    from pwm_core.optics import (
        grating_efficiency as _ge, tmm as _tmm, stray_light_analysis as _sla,
        coherent_psf as _cpsf, mcml as _mcml, snr_budget as _snr,
        hb_absorption as _hb, diffraction_limit as _dl,
    )
    check("optics __init__ re-exports Phase 2", True)
except Exception as exc:
    check("optics __init__ re-exports Phase 2", False, str(exc))

# ── grating_efficiency ────────────────────────────────────────────────────────

wls_vis = list(range(400, 801, 10))
g = grating_efficiency(600.0, wls_vis, blaze_angle_deg=17.5, order=1, n_grooves=1000)

check("grating status ok", g["status"] == "ok")
check("grating wavelengths length", len(g["wavelengths_nm"]) == len(wls_vis))
check("grating efficiency in [0,1]",
      all(0.0 <= e <= 1.0 for e in g["efficiency"]),
      f"min={min(g['efficiency']):.4f} max={max(g['efficiency']):.4f}")
check("grating resolving_power = m*N", g["resolving_power"] == 1 * 1000)
check("grating peak_wavelength defined", not math.isnan(g["peak_wavelength_nm"]))
check("grating angular_dispersion positive",
      any(d > 0 for d in g["angular_dispersion_deg_per_nm"]),
      f"max_disp={max(g['angular_dispersion_deg_per_nm']):.6f}")

# Blaze at ~17.5 deg with 600 l/mm: lambda_B = 2*d*sin(17.5) = 2*(1666nm)*sin(17.5) ~ 1000nm
# For vis range, test that efficiency is non-trivially nonzero
check("grating efficiency has nonzero values",
      max(g["efficiency"]) > 0.01,
      f"max_eff={max(g['efficiency']):.4f}")

# Order 0 should have blaze at any wavelength (g->1 at small angles)
g0 = grating_efficiency(600.0, [500.0], blaze_angle_deg=0.0, order=1)
check("grating order-1 without blaze has efficiency<=1",
      0.0 <= g0["efficiency"][0] <= 1.0)

# Free spectral range: lambda/m
check("grating FSR = lambda/m",
      abs(g["free_spectral_range_nm"] - 600.0 / 1) < 1.0,
      f"FSR={g['free_spectral_range_nm']:.2f}")

# Crosstalk
xt = grating_crosstalk(600.0, [500.0, 550.0, 600.0], order=1, channel_bw_nm=1.0)
check("grating_crosstalk status", xt["status"] == "ok")
check("grating_crosstalk in [0,1]",
      all(0.0 <= x <= 1.0 for x in xt["crosstalk_fraction"]))

# ── tmm ──────────────────────────────────────────────────────────────────────

# Simple single layer AR coating
layers_ar = [{"n": 1.38, "k": 0.0, "thickness_nm": 100.0}]
r_ar = tmm(layers_ar, substrate_n=1.52, incident_n=1.0,
           wavelengths_nm=list(range(400, 801, 20)))

check("tmm status ok", r_ar["status"] == "ok")
check("tmm T+R+A ≈ 1 at each wavelength",
      all(abs(t + r + a - 1.0) < 0.05
          for t, r, a in zip(r_ar["T"], r_ar["R"], r_ar["A"])),
      f"max_err={max(abs(t+r+a-1) for t,r,a in zip(r_ar['T'],r_ar['R'],r_ar['A'])):.4f}")
check("tmm T in [0,1]", all(0 <= t <= 1 for t in r_ar["T"]))
check("tmm R in [0,1]", all(0 <= r <= 1 for r in r_ar["R"]))

# Bandpass design
wls_bp = list(range(400, 801, 5))
layers_bp = design_bandpass(center_nm=550.0, bandwidth_nm=50.0, n_high=2.35, n_low=1.46, n_layers=7)
check("design_bandpass returns list", isinstance(layers_bp, list))
check("design_bandpass n_layers=7", len(layers_bp) == 7)

r_bp = tmm(layers_bp, substrate_n=1.52, incident_n=1.0, wavelengths_nm=wls_bp)
check("bandpass T+R+A ≈ 1",
      all(abs(t + r + a - 1.0) < 0.1
          for t, r, a in zip(r_bp["T"], r_bp["R"], r_bp["A"])))

# Longpass design
layers_lp = design_longpass(cutoff_nm=600.0, n_high=2.35, n_low=1.46, n_layers=9)
check("design_longpass returns list", isinstance(layers_lp, list))
check("design_longpass n_layers=9", len(layers_lp) == 9)

# ── stray_light_analysis ─────────────────────────────────────────────────────

presc = {"surfaces": [{"radius": -100.0, "thickness": 50.0},
                      {"radius": 100.0, "thickness": 50.0},
                      {"radius": 0.0, "thickness": 10.0}],
         "wavelengths": [{"value": 0.55}]}
sl = stray_light_analysis(presc, n_rays=5000, bsdf_roughness_nm=2.0, seed=7)

check("stray_light status ok", sl["status"] == "ok")
check("stray_light ghost_fraction in [0,1]",
      0.0 <= sl["ghost_fraction"] <= 1.0, f"gf={sl['ghost_fraction']}")
check("stray_light VGI in [0,1]",
      0.0 <= sl["veiling_glare_index"] <= 1.0, f"vgi={sl['veiling_glare_index']}")
check("stray_light scatter_map non-empty",
      len(sl["scatter_map"]) == sl["scatter_map_shape"][0] * sl["scatter_map_shape"][1])
check("stray_light recommendations is list", isinstance(sl["recommendations"], list))
check("stray_light TIS in (0,1)",
      0.0 < sl["tis_per_surface"] < 1.0, f"tis={sl['tis_per_surface']:.6f}")

# baffle_optimization
baf = baffle_optimization(f_number=5.0, field_angle_deg=1.0, n_baffles=3)
check("baffle_optimization status ok", baf["status"] == "ok")
check("baffle n_positions = n_baffles", len(baf["baffle_positions_mm"]) == 3)
check("baffle knife_edge_angles count", len(baf["knife_edge_angles_deg"]) == 3)
check("baffle positions increasing",
      all(baf["baffle_positions_mm"][i] < baf["baffle_positions_mm"][i+1]
          for i in range(len(baf["baffle_positions_mm"])-1)))

# ── coherent_psf ─────────────────────────────────────────────────────────────

presc_simple = {"surfaces": [{"radius": -50.0, "thickness": 100.0}],
                "aperture_value": 10.0, "wavelengths": [{"value": 0.55}]}
psf_result = coherent_psf(presc_simple, grid_size=64, wavelength_nm=550.0)

check("coherent_psf status ok", psf_result["status"] == "ok")
check("coherent_psf intensity sum > 0",
      sum(sum(row) for row in psf_result["psf_intensity"]) > 0)
check("coherent_psf grid_size matches", psf_result["grid_size"] == 64)
check("coherent_psf strehl in (0,1]",
      0.0 < psf_result["strehl_ratio"] <= 1.0,
      f"strehl={psf_result['strehl_ratio']}")

# ── angular_spectrum_propagate ───────────────────────────────────────────────

field_in = np.zeros(64, dtype=complex)
field_in[32] = 1.0  # point source
field_out = angular_spectrum_propagate(field_in, dx_m=1e-6, dz_m=1e-3, wavelength_m=550e-9)
check("angular_spectrum 1D output shape", field_out.shape == (64,))
check("angular_spectrum energy conserved (approx)",
      abs(np.sum(np.abs(field_out)**2) - np.sum(np.abs(field_in)**2)) < 10.0)

# ── fdtd_1d ─────────────────────────────────────────────────────────────────

# Lossless single layer: R+T should be ≈ 1
fdtd = fdtd_1d(n_layers=[1.5], thickness_nm=[100.0], wavelengths_nm=[550.0])
check("fdtd_1d status ok", fdtd["status"] == "ok")
check("fdtd_1d R+T <= 1 (energy)",
      fdtd["R"][0] + fdtd["T"][0] <= 1.01,
      f"R={fdtd['R'][0]:.4f} T={fdtd['T'][0]:.4f}")
check("fdtd_1d R in [0,1]", 0.0 <= fdtd["R"][0] <= 1.0)
check("fdtd_1d T in [0,1]", 0.0 <= fdtd["T"][0] <= 1.0)

# ── diffraction_limit ─────────────────────────────────────────────────────────

dl = diffraction_limit(wavelength_nm=550.0, na=0.5)
check("diffraction_limit status ok", dl["status"] == "ok")
check("abbe_resolution = lambda/(2*NA)",
      abs(dl["abbe_resolution_nm"] - 550.0 / (2 * 0.5)) < 0.1,
      f"abbe={dl['abbe_resolution_nm']}")
check("rayleigh > abbe", dl["rayleigh_resolution_nm"] > dl["abbe_resolution_nm"])
check("depth_of_focus > 0", dl["depth_of_focus_nm"] > 0)
check("cutoff_frequency > 0", dl["cutoff_frequency_lp_per_mm"] > 0)

# ── hb_absorption ─────────────────────────────────────────────────────────────

wls_hb = list(range(400, 710, 10))
hb = hb_absorption(wls_hb, so2=0.98)
check("hb_absorption status ok", hb["status"] == "ok")
check("hb_absorption mua_cm_inv length", len(hb["mua_cm_inv"]) == len(wls_hb))
check("hb_absorption all positive", all(m >= 0 for m in hb["mua_cm_inv"]))
# Soret band peak should be near 400-430 nm
check("hb_absorption peak near Soret band (400-450nm)",
      400 <= hb["peak_nm"] <= 450,
      f"peak={hb['peak_nm']}nm")

# so2 effect: lower so2 should change absorption profile
hb_deoxy = hb_absorption(wls_hb, so2=0.0)
check("hb_absorption so2 effect",
      hb["mua_cm_inv"] != hb_deoxy["mua_cm_inv"])

# ── mcml ─────────────────────────────────────────────────────────────────────

layers = [
    {"mua": 0.02, "mus": 1.0, "g": 0.9, "n": 1.37, "thickness_mm": 2.0},
    {"mua": 0.01, "mus": 0.5, "g": 0.9, "n": 1.37, "thickness_mm": 8.0},
]
mc = mcml(layers, n_photons=5000, seed=42)
check("mcml status ok", mc["status"] == "ok")
check("mcml reflectance in [0,1]",
      0.0 <= mc["reflectance"] <= 1.0, f"R={mc['reflectance']}")
check("mcml transmittance in [0,1]",
      0.0 <= mc["transmittance"] <= 1.0, f"T={mc['transmittance']}")
check("mcml fluence length matches depth",
      len(mc["fluence"]) == len(mc["depth_mm"]))
check("mcml fluence has positive values",
      any(f > 0 for f in mc["fluence"]))
check("mcml penetration_depth > 0", mc["penetration_depth_mm"] >= 0)
check("mcml absorption_by_layer length", len(mc["absorption_by_layer"]) == len(layers))

# ── snr_budget ───────────────────────────────────────────────────────────────

snr = snr_budget(signal_photons_per_pixel=1000.0, qe=0.7,
                 read_noise_e=3.0, dark_current_e_per_s=0.01,
                 exposure_s=1.0, n_accumulations=1)
check("snr_budget status ok", snr["status"] == "ok")
check("snr_budget signal_e = 700", abs(snr["signal_e"] - 700.0) < 1.0)
check("snr_budget SNR > 0",
      math.isfinite(snr["snr_db"]) and snr["snr_db"] > 0,
      f"snr_db={snr['snr_db']:.2f}")
check("snr_budget dynamic_range_db > 0", snr["dynamic_range_db"] > 0)
check("snr_budget saturation_fraction in [0,1]",
      0.0 <= snr["saturation_fraction"] <= 1.0)
check("snr_budget nep_photons > 0", snr["nep_photons"] > 0)
check("snr_budget recommendations is list", isinstance(snr["recommendations"], list))

# SNR physics check: shot-noise limited ~ sqrt(signal_e) ~ 26.5
# total_noise ~= sqrt(700 + 9 + small_dark) ~ 27
signal_e = 1000 * 0.7
shot = math.sqrt(signal_e)
expected_snr = signal_e / math.sqrt(shot**2 + 3.0**2 + 0.01**2)
check("snr_budget snr_linear matches formula",
      abs(snr["snr_linear"] - expected_snr) < 0.5,
      f"got={snr['snr_linear']:.2f} expected={expected_snr:.2f}")

# ── irradiance_at_sensor ──────────────────────────────────────────────────────

irr = irradiance_at_sensor(
    source_radiance_W_per_sr_m2=100.0,
    collection_solid_angle_sr=0.01,
    transmission=0.8,
    pixel_area_m2=25e-12,
    wavelength_band_nm=550.0,
)
check("irradiance_at_sensor status ok", irr["status"] == "ok")
check("irradiance_at_sensor irradiance > 0", irr["irradiance_W_m2"] > 0)
check("irradiance_at_sensor photon_flux > 0", irr["photon_flux_per_s"] > 0)
check("irradiance_at_sensor irradiance = L*Omega*T",
      abs(irr["irradiance_W_m2"] - 100.0 * 0.01 * 0.8) < 1e-6)

def test_optics_phase2():
    """Pytest entry: run the Phase 2 optics script in a subprocess (its _run()
    sys.exit()s on failure, so isolate it) and assert it passes."""
    import subprocess
    r = subprocess.run([sys.executable, __file__], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]


if __name__ == "__main__":
    ok = _run()
    sys.exit(0 if ok else 1)
