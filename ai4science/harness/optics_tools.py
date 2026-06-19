from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, List, Optional

from ai4science.harness.tools.base import Tool

_WALLET = os.environ.get("OPTICS_TOOL_WALLET", "0x3CeA937cd8114Efa8120C011f1035c9b428C9d05")

TOOL_PRICES: dict = {
    # OPEN tools
    "optics_define":             0.5,
    "optics_import":             1.0,
    "optics_raytrace":           1.0,
    "optics_layout":             0.5,
    "optics_paraxial":           0.5,
    "optics_spot":               1.0,
    "optics_rayfan":             1.0,
    "optics_zernike":            1.5,
    "optics_psf_mtf":            2.0,
    "optics_aberrations":        1.0,
    # CLOSED tools (Phase 1)
    "optics_to_digital_twin":    3.0,
    "optics_coded_design":       2.5,
    "optics_ground":             1.5,
    # OPEN tools (Phase 2)
    "optics_grating":            1.5,
    "optics_thinfilm":           2.0,
    "optics_stray_light":        2.5,
    "optics_wave":               2.0,
    "optics_monte_carlo":        3.0,
    "optics_snr":                1.0,
}


def _charge(gate, tool_name: str, idem_key: str) -> tuple:
    """Charge PWM for a tool call. Returns (allowed: bool, msg: str)."""
    price = TOOL_PRICES.get(tool_name, 1.0)
    if gate is None or not gate.enabled:
        return True, ""
    ok, msg = gate.charge(price, _WALLET, f"optics-{tool_name}", idem_key)
    return ok, msg


def _idem(tool_name: str) -> str:
    return f"optics-{tool_name}-{int(time.time())}"


def _load_sys(workspace: Path, prescription_file: str = "system.json"):
    """Load OpticalSystem from workspace file."""
    from pwm_core.optics import load_system
    path = (workspace / prescription_file).resolve()
    if not str(path).startswith(str(workspace.resolve())):
        raise ValueError("path escapes workspace")
    return load_system(str(path))


def optics_tools(*, gate_provider: Optional[Callable] = None,
                  workspace: Optional[Path] = None) -> List[Tool]:
    """Return all optical design tools (OPEN + CLOSED Phase 1) for the computational-imaging agent."""
    ws = Path(workspace) if workspace else Path(".")

    def _gate():
        return gate_provider() if gate_provider is not None else None

    # ── optics_define ────────────────────────────────────────────────────────
    def _optics_define(workspace_path, *, surfaces: list, fields: list = None,
                       wavelengths: list = None, aperture_type: str = "EPD",
                       aperture_value: float = 10.0, title: str = "") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_define", _idem("optics_define"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import OpticalSystem, Surface, Field, Wavelength, save_system
            surfs = [Surface(**s) for s in surfaces]
            flds = [Field(**f) for f in (fields or [{"y": 0.0}])]
            wls = [Wavelength(**w) for w in (wavelengths or [{"value": 0.55, "is_primary": True}])]
            sys = OpticalSystem(surfaces=surfs, fields=flds, wavelengths=wls,
                                aperture_type=aperture_type, aperture_value=aperture_value,
                                title=title)
            out = Path(workspace_path) / "system.json"
            save_system(sys, str(out))
            return json.dumps({"ok": True, "file": "system.json",
                               "surfaces": len(surfs), "title": title})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_import ─────────────────────────────────────────────────────────
    def _optics_import(workspace_path, *, path: str) -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_import", _idem("optics_import"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import import_zmx, save_system
            src = (Path(workspace_path) / path).resolve()
            sys = import_zmx(str(src))
            out = Path(workspace_path) / "system.json"
            save_system(sys, str(out))
            return json.dumps({"ok": True, "file": "system.json",
                               "surfaces": len(sys.surfaces), "title": sys.title})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_raytrace ───────────────────────────────────────────────────────
    def _optics_raytrace(workspace_path, *, prescription: str = "system.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_raytrace", _idem("optics_raytrace"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, trace_system
            sys = load_system(str(Path(workspace_path) / prescription))
            result = trace_system(sys)
            return json.dumps(result)
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_layout (paraxial summary) ─────────────────────────────────────
    def _optics_layout(workspace_path, *, prescription: str = "system.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_layout", _idem("optics_layout"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, paraxial_data
            sys = load_system(str(Path(workspace_path) / prescription))
            return json.dumps(paraxial_data(sys))
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_paraxial ───────────────────────────────────────────────────────
    def _optics_paraxial(workspace_path, *, prescription: str = "system.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_paraxial", _idem("optics_paraxial"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, paraxial_data
            sys = load_system(str(Path(workspace_path) / prescription))
            return json.dumps(paraxial_data(sys))
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_spot ──────────────────────────────────────────────────────────
    def _optics_spot(workspace_path, *, prescription: str = "system.json",
                     field_idx: int = 0) -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_spot", _idem("optics_spot"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, spot_diagram
            sys = load_system(str(Path(workspace_path) / prescription))
            return json.dumps(spot_diagram(sys, field_idx=field_idx))
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_rayfan ─────────────────────────────────────────────────────────
    def _optics_rayfan(workspace_path, *, prescription: str = "system.json",
                       field_idx: int = 0) -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_rayfan", _idem("optics_rayfan"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, ray_fan
            sys = load_system(str(Path(workspace_path) / prescription))
            return json.dumps(ray_fan(sys, field_idx=field_idx))
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_zernike ────────────────────────────────────────────────────────
    def _optics_zernike(workspace_path, *, prescription: str = "system.json",
                        field_idx: int = 0, num_pts: int = 64) -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_zernike", _idem("optics_zernike"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, wavefront
            sys = load_system(str(Path(workspace_path) / prescription))
            return json.dumps(wavefront(sys, field_idx=field_idx, num_pts=num_pts))
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_psf_mtf ────────────────────────────────────────────────────────
    def _optics_psf_mtf(workspace_path, *, prescription: str = "system.json",
                        field_idx: int = 0, grid_size: int = 128) -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_psf_mtf", _idem("optics_psf_mtf"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, psf_mtf
            sys = load_system(str(Path(workspace_path) / prescription))
            result = psf_mtf(sys, field_idx=field_idx, grid_size=grid_size)
            # PSF is a 2D array — keep it but truncate for readability
            if "psf" in result:
                psf = result["psf"]
                result["psf_shape"] = [len(psf), len(psf[0]) if psf else 0]
                result["psf"] = "see psf_shape (omitted for brevity)"
            return json.dumps(result)
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── optics_aberrations (Seidel) ──────────────────────────────────────────
    def _optics_aberrations(workspace_path, *, prescription: str = "system.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_aberrations", _idem("optics_aberrations"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system, seidel_aberrations
            sys = load_system(str(Path(workspace_path) / prescription))
            return json.dumps(seidel_aberrations(sys))
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── CLOSED: optics_to_digital_twin ───────────────────────────────────────
    def _optics_to_digital_twin(workspace_path, *,
                                 prescription: str = "system.json",
                                 modality: str = "psf_convolution",
                                 H: int = 256, W: int = 256,
                                 N_bands: int = 1,
                                 noise_level: float = 0.01,
                                 mask_density: float = 0.5,
                                 disp_a1: float = 1.0,
                                 output_file: str = "digital_twin_spec.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_to_digital_twin", _idem("optics_to_digital_twin"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system
            from pwm_core.optics.pwm_bridge import optical_to_spec_fields
            sys = load_system(str(Path(workspace_path) / prescription))
            fields = optical_to_spec_fields(
                sys, modality=modality, H=H, W=W, N_bands=N_bands,
                noise_level=noise_level, mask_density=mask_density,
                disp_a1=disp_a1, grid_size=64,
            )
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(fields, indent=2))
            note = ("Submit this spec to the PWM registry for L2 registration "
                    "(requires founder review at physicsworldmodel.org).")
            return json.dumps({"ok": True, "file": output_file,
                               "d_spec": fields["d_spec"],
                               "spec_type": fields["spec_type"],
                               "title": fields["title"],
                               "note": note})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── CLOSED: optics_coded_design ──────────────────────────────────────────
    def _optics_coded_design(workspace_path, *,
                              prescription: str = "system.json",
                              modality: str = "cassi",
                              H: int = 256, W: int = 256,
                              N_bands: int = 28,
                              mask_density: float = 0.5,
                              disp_a1: float = 1.0,
                              optimize: bool = False,
                              seed: int = 42,
                              output_file: str = "coded_design.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_coded_design", _idem("optics_coded_design"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            import numpy as np
            from pwm_core.optics.coded import (binary_mask, optimized_mask,
                                                cassi_forward, lensless_forward,
                                                doe_phase_fresnel_lens)
            if modality == "cassi":
                if optimize:
                    mask = optimized_mask(H, W, N_bands=N_bands, disp_a1=disp_a1, seed=seed)
                else:
                    mask = binary_mask(H, W, density=mask_density, seed=seed)
                # Save mask
                mask_path = Path(workspace_path) / "mask.npy"
                np.save(str(mask_path), mask)
                density_actual = float(mask.mean())
                design = {
                    "modality": "cassi",
                    "H": H, "W": W, "N_bands": N_bands,
                    "disp_a1": disp_a1,
                    "mask_density_target": mask_density,
                    "mask_density_actual": round(density_actual, 4),
                    "optimized": optimize,
                    "mask_file": "mask.npy",
                    "seed": seed,
                }
            elif modality == "lensless":
                phase = doe_phase_fresnel_lens(H, W,
                    focal_length_m=0.05, wavelength_m=550e-9,
                    pixel_pitch_m=5.5e-6)
                mask_path = Path(workspace_path) / "phase_mask.npy"
                import numpy as _np
                _np.save(str(mask_path), phase)
                design = {
                    "modality": "lensless",
                    "H": H, "W": W,
                    "focal_length_m": 0.05,
                    "wavelength_m": 550e-9,
                    "phase_mask_file": "phase_mask.npy",
                }
            else:
                return f"[optics error] unknown modality {modality!r}; use 'cassi' or 'lensless'"
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(design, indent=2))
            return json.dumps({"ok": True, "file": output_file, **design})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── CLOSED: optics_ground ────────────────────────────────────────────────
    def _optics_ground(workspace_path, *,
                        prescription: str = "system.json",
                        query: str = "",
                        output_file: str = "grounding.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_ground", _idem("optics_ground"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics import load_system
            from pwm_core.optics.pwm_bridge import optical_to_spec_fields
            from ai4science.harness.pwm_data import search as pwm_search, specs as pwm_specs
            sys = load_system(str(Path(workspace_path) / prescription))
            # Auto-derive search terms from system title + query
            title = sys.title or ""
            q = f"{title} {query}".strip() or "cassi imaging"
            results = pwm_search(q, limit=5)
            spec_list = results.get("specs", [])
            # Also include matching principles
            matched_principles = results.get("principles", [])
            grounding = {
                "query": q,
                "matched_specs": [
                    {
                        "artifact_id": s.get("artifact_id"),
                        "title": s.get("title"),
                        "spec_type": s.get("spec_type"),
                        "d_spec": s.get("d_spec"),
                        "parent_l1": s.get("parent_l1"),
                    }
                    for s in spec_list
                ],
                "matched_principles": [
                    {
                        "artifact_id": p.get("artifact_id"),
                        "title": p.get("title"),
                    }
                    for p in matched_principles
                ],
                "system_title": title,
                "recommendation": (
                    f"Design targets {spec_list[0]['artifact_id']} ({spec_list[0]['title']}) "
                    f"if you want to register a benchmark under {spec_list[0].get('parent_l1','?')}. "
                    "Use optics_to_digital_twin to generate the spec fields."
                ) if spec_list else "No matching PWM specs found. Consider defining a new principle.",
            }
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(grounding, indent=2))
            return json.dumps({"ok": True, "file": output_file, **grounding})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── Phase 2: optics_grating ─────────────────────────────────────────────
    def _optics_grating(workspace_path, *,
                        groove_density_lpmm: float = 600.0,
                        wavelengths_nm: list = None,
                        blaze_angle_deg: float = 0.0,
                        order: int = 1,
                        polarization: str = "avg",
                        n_grooves: int = 1000,
                        incident_angle_deg: float = 0.0,
                        output_file: str = "grating.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_grating", _idem("optics_grating"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics.grating import grating_efficiency
            wls = wavelengths_nm or list(range(400, 801, 10))
            result = grating_efficiency(
                groove_density_lpmm=groove_density_lpmm,
                wavelengths_nm=wls,
                blaze_angle_deg=blaze_angle_deg,
                order=order,
                polarization=polarization,
                n_grooves=n_grooves,
                incident_angle_deg=incident_angle_deg,
            )
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(result, indent=2))
            return json.dumps({"ok": True, "file": output_file,
                               "peak_wavelength_nm": result["peak_wavelength_nm"],
                               "resolving_power": result["resolving_power"],
                               "free_spectral_range_nm": result["free_spectral_range_nm"]})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── Phase 2: optics_thinfilm ─────────────────────────────────────────────
    def _optics_thinfilm(workspace_path, *,
                         layers: list = None,
                         substrate_n: float = 1.52,
                         incident_n: float = 1.0,
                         wavelengths_nm: list = None,
                         angle_deg: float = 0.0,
                         polarization: str = "avg",
                         design_type: str = None,
                         center_nm: float = 550.0,
                         bandwidth_nm: float = 50.0,
                         cutoff_nm: float = 550.0,
                         n_high: float = 2.35,
                         n_low: float = 1.46,
                         n_design_layers: int = 7,
                         output_file: str = "thinfilm.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_thinfilm", _idem("optics_thinfilm"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            from pwm_core.optics.thinfilm import tmm, design_bandpass, design_longpass
            wls = wavelengths_nm or list(range(400, 801, 5))
            # Auto-design if no layers given
            if layers is None:
                if design_type == "longpass":
                    layers = design_longpass(cutoff_nm, n_high, n_low, n_design_layers)
                else:
                    layers = design_bandpass(center_nm, bandwidth_nm, n_high, n_low, n_design_layers)
            result = tmm(layers=layers, substrate_n=substrate_n, incident_n=incident_n,
                         wavelengths_nm=wls, angle_deg=angle_deg, polarization=polarization)
            result["layers"] = layers
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(result, indent=2))
            # Peak transmission
            T = result["T"]
            peak_T = max(T) if T else 0.0
            return json.dumps({"ok": True, "file": output_file,
                               "n_layers": len(layers),
                               "peak_transmission": round(peak_T, 4)})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── Phase 2: optics_stray_light ──────────────────────────────────────────
    def _optics_stray_light(workspace_path, *,
                             prescription: str = "system.json",
                             n_rays: int = 10000,
                             bsdf_roughness_nm: float = 2.0,
                             baffle_transmission: float = 0.0,
                             seed: int = 42,
                             output_file: str = "stray_light.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_stray_light", _idem("optics_stray_light"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            import json as _json
            from pwm_core.optics.stray_light import stray_light_analysis
            presc_path = Path(workspace_path) / prescription
            presc_dict = _json.loads(presc_path.read_text()) if presc_path.exists() else {}
            result = stray_light_analysis(
                prescription_dict=presc_dict,
                n_rays=n_rays,
                bsdf_roughness_nm=bsdf_roughness_nm,
                baffle_transmission=baffle_transmission,
                seed=seed,
            )
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(result, indent=2))
            return json.dumps({"ok": True, "file": output_file,
                               "ghost_fraction": result["ghost_fraction"],
                               "veiling_glare_index": result["veiling_glare_index"],
                               "recommendations": result["recommendations"]})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── Phase 2: optics_wave ─────────────────────────────────────────────────
    def _optics_wave(workspace_path, *,
                     prescription: str = "system.json",
                     mode: str = "psf",
                     grid_size: int = 128,
                     wavelength_nm: float = 550.0,
                     dz_mm: float = 1.0,
                     n_fdtd_layers: list = None,
                     thickness_fdtd_nm: list = None,
                     na: float = 0.5,
                     output_file: str = "wave.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_wave", _idem("optics_wave"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            import json as _json
            if mode == "psf":
                from pwm_core.optics.wave import coherent_psf
                presc_path = Path(workspace_path) / prescription
                presc_dict = _json.loads(presc_path.read_text()) if presc_path.exists() else {}
                result = coherent_psf(presc_dict, grid_size=grid_size, wavelength_nm=wavelength_nm)
                # Compact PSF for JSON
                result["psf_shape"] = [len(result["psf_intensity"]),
                                       len(result["psf_intensity"][0]) if result["psf_intensity"] else 0]
                result["psf_intensity"] = "see psf_shape (omitted for brevity)"
                result["psf_complex_real"] = "omitted"
                result["psf_complex_imag"] = "omitted"
            elif mode == "fdtd":
                from pwm_core.optics.wave import fdtd_1d
                n_layers = n_fdtd_layers or [1.5, 1.0]
                t_layers = thickness_fdtd_nm or [100.0, 50.0]
                result = fdtd_1d(n_layers=n_layers, thickness_nm=t_layers,
                                 wavelengths_nm=[wavelength_nm])
            elif mode == "diffraction_limit":
                from pwm_core.optics.wave import diffraction_limit
                result = diffraction_limit(wavelength_nm=wavelength_nm, na=na)
            else:
                return f"[optics error] unknown mode {mode!r}; use 'psf', 'fdtd', or 'diffraction_limit'"
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(result, indent=2))
            return json.dumps({"ok": True, "file": output_file, "mode": mode, **{
                k: v for k, v in result.items() if k not in ("psf_intensity",
                "psf_complex_real", "psf_complex_imag", "wavelengths_nm")}})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── Phase 2: optics_monte_carlo ──────────────────────────────────────────
    def _optics_monte_carlo(workspace_path, *,
                             tissue_layers: list = None,
                             n_photons: int = 10000,
                             source_beam_radius_mm: float = 0.5,
                             source_type: str = "pencil",
                             seed: int = 42,
                             mode: str = "mcml",
                             wavelengths_nm: list = None,
                             so2: float = 0.98,
                             output_file: str = "monte_carlo.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_monte_carlo", _idem("optics_monte_carlo"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            if mode == "hb":
                from pwm_core.optics.monte_carlo import hb_absorption
                wls = wavelengths_nm or list(range(400, 710, 10))
                result = hb_absorption(wavelengths_nm=wls, so2=so2)
            else:
                from pwm_core.optics.monte_carlo import mcml
                layers = tissue_layers or [
                    {"mua": 0.02, "mus": 1.0, "g": 0.9, "n": 1.37, "thickness_mm": 2.0},
                    {"mua": 0.01, "mus": 0.5, "g": 0.9, "n": 1.37, "thickness_mm": 8.0},
                ]
                result = mcml(tissue_layers=layers, n_photons=n_photons,
                              source_beam_radius_mm=source_beam_radius_mm,
                              source_type=source_type, seed=seed)
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(result, indent=2))
            summary = {k: v for k, v in result.items()
                       if k not in ("depth_mm", "fluence", "absorption_by_layer",
                                    "wavelengths_nm", "mua_cm_inv")}
            return json.dumps({"ok": True, "file": output_file, **summary})
        except Exception as exc:
            return f"[optics error] {exc}"

    # ── Phase 2: optics_snr ──────────────────────────────────────────────────
    def _optics_snr(workspace_path, *,
                    signal_photons_per_pixel: float = 1000.0,
                    qe: float = 0.7,
                    read_noise_e: float = 3.0,
                    dark_current_e_per_s: float = 0.01,
                    exposure_s: float = 1.0,
                    n_accumulations: int = 1,
                    bit_depth: int = 16,
                    full_well_e: float = 30000.0,
                    mode: str = "snr",
                    source_radiance: float = 1.0,
                    collection_solid_angle_sr: float = 0.01,
                    transmission: float = 0.8,
                    pixel_area_m2: float = 25e-12,
                    wavelength_band_nm: float = 550.0,
                    output_file: str = "snr.json") -> str:
        gate = _gate()
        ok, msg = _charge(gate, "optics_snr", _idem("optics_snr"))
        if not ok:
            return f"[optics error] {msg}"
        try:
            if mode == "irradiance":
                from pwm_core.optics.radiometry import irradiance_at_sensor
                result = irradiance_at_sensor(
                    source_radiance_W_per_sr_m2=source_radiance,
                    collection_solid_angle_sr=collection_solid_angle_sr,
                    transmission=transmission,
                    pixel_area_m2=pixel_area_m2,
                    wavelength_band_nm=wavelength_band_nm,
                )
            else:
                from pwm_core.optics.radiometry import snr_budget
                result = snr_budget(
                    signal_photons_per_pixel=signal_photons_per_pixel,
                    qe=qe,
                    read_noise_e=read_noise_e,
                    dark_current_e_per_s=dark_current_e_per_s,
                    exposure_s=exposure_s,
                    n_accumulations=n_accumulations,
                    bit_depth=bit_depth,
                    full_well_e=full_well_e,
                )
            out_path = Path(workspace_path) / output_file
            out_path.write_text(json.dumps(result, indent=2))
            return json.dumps({"ok": True, "file": output_file, **result})
        except Exception as exc:
            return f"[optics error] {exc}"

    return [
        Tool(name="optics_define",
             description=("Define a new optical system prescription from surfaces, fields, "
                          "and wavelengths. Saves as system.json in the workspace. "
                          f"Cost: {TOOL_PRICES['optics_define']} PWM."),
             parameters={"type": "object", "properties": {
                 "surfaces": {"type": "array", "items": {"type": "object"},
                              "description": "List of surface dicts (radius, thickness, material, etc.)"},
                 "fields": {"type": "array", "items": {"type": "object"}},
                 "wavelengths": {"type": "array", "items": {"type": "object"}},
                 "aperture_type": {"type": "string", "enum": ["EPD", "FNO", "NA"]},
                 "aperture_value": {"type": "number"},
                 "title": {"type": "string"}},
                 "required": ["surfaces"]},
             func=_optics_define, mutating=True),

        Tool(name="optics_import",
             description=("Import a Zemax .zmx or CODE V .seq file from the workspace. "
                          "Saves prescription as system.json. "
                          f"Cost: {TOOL_PRICES['optics_import']} PWM."),
             parameters={"type": "object", "properties": {
                 "path": {"type": "string",
                          "description": "Relative path to .zmx or .seq file in workspace"},
                 "prescription": {"type": "string", "default": "system.json"}},
                 "required": ["path"]},
             func=_optics_import, mutating=True),

        Tool(name="optics_raytrace",
             description=(f"Trace rays through the system. Returns per-surface heights and OPD. Cost: {TOOL_PRICES['optics_raytrace']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"}},
                 "required": []},
             func=_optics_raytrace, mutating=False),

        Tool(name="optics_layout",
             description=(f"Paraxial layout: EFL, BFD, FFD, NA, f-number, magnification. Cost: {TOOL_PRICES['optics_layout']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"}},
                 "required": []},
             func=_optics_layout, mutating=False),

        Tool(name="optics_paraxial",
             description=(f"Paraxial analysis (alias for optics_layout). Cost: {TOOL_PRICES['optics_paraxial']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"}},
                 "required": []},
             func=_optics_paraxial, mutating=False),

        Tool(name="optics_spot",
             description=(f"Spot diagram: RMS spot radius per field. Cost: {TOOL_PRICES['optics_spot']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "field_idx": {"type": "integer", "default": 0}},
                 "required": []},
             func=_optics_spot, mutating=False),

        Tool(name="optics_rayfan",
             description=(f"Tangential and sagittal ray-fan aberration curves. Cost: {TOOL_PRICES['optics_rayfan']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "field_idx": {"type": "integer", "default": 0}},
                 "required": []},
             func=_optics_rayfan, mutating=False),

        Tool(name="optics_zernike",
             description=(f"Zernike wavefront decomposition and RMS WFE. Cost: {TOOL_PRICES['optics_zernike']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "field_idx": {"type": "integer", "default": 0},
                 "num_pts": {"type": "integer", "default": 64}},
                 "required": []},
             func=_optics_zernike, mutating=False),

        Tool(name="optics_psf_mtf",
             description=(f"PSF and MTF via pupil-function FFT. Returns Strehl ratio and MTF curves. Cost: {TOOL_PRICES['optics_psf_mtf']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "field_idx": {"type": "integer", "default": 0},
                 "grid_size": {"type": "integer", "default": 128}},
                 "required": []},
             func=_optics_psf_mtf, mutating=False),

        Tool(name="optics_aberrations",
             description=(f"Seidel primary aberration sums (SA, Coma, Ast, FieldCurv, Distortion). Cost: {TOOL_PRICES['optics_aberrations']} PWM."),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"}},
                 "required": []},
             func=_optics_aberrations, mutating=False),

        # ── CLOSED Phase 1 tools ─────────────────────────────────────────────
        Tool(name="optics_to_digital_twin",
             description=(
                 "[CLOSED] Convert the optical system prescription to a PWM L2 digital-twin "
                 "spec (six_tuple / protocol_fields / d_spec). Saves digital_twin_spec.json. "
                 f"Cost: {TOOL_PRICES['optics_to_digital_twin']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "modality": {"type": "string",
                              "enum": ["psf_convolution", "cassi", "lensless"],
                              "description": "Forward-model type"},
                 "H": {"type": "integer", "default": 256,
                       "description": "Spatial height of the benchmark scene"},
                 "W": {"type": "integer", "default": 256},
                 "N_bands": {"type": "integer", "default": 1,
                             "description": "Spectral bands (>1 for CASSI/multispectral)"},
                 "noise_level": {"type": "number", "default": 0.01},
                 "mask_density": {"type": "number", "default": 0.5},
                 "disp_a1": {"type": "number", "default": 1.0,
                             "description": "CASSI dispersion (pixels/band)"},
                 "output_file": {"type": "string", "default": "digital_twin_spec.json"}},
                 "required": []},
             func=_optics_to_digital_twin, mutating=True),

        Tool(name="optics_coded_design",
             description=(
                 "[CLOSED] Design a coded aperture or DOE for CI modalities. "
                 "Generates mask.npy (CASSI binary mask) or phase_mask.npy (lensless Fresnel). "
                 f"Cost: {TOOL_PRICES['optics_coded_design']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "modality": {"type": "string",
                              "enum": ["cassi", "lensless"],
                              "description": "Imaging modality"},
                 "H": {"type": "integer", "default": 256},
                 "W": {"type": "integer", "default": 256},
                 "N_bands": {"type": "integer", "default": 28},
                 "mask_density": {"type": "number", "default": 0.5},
                 "disp_a1": {"type": "number", "default": 1.0},
                 "optimize": {"type": "boolean", "default": False,
                              "description": "Use rank-optimized mask (vs random)"},
                 "seed": {"type": "integer", "default": 42},
                 "output_file": {"type": "string", "default": "coded_design.json"}},
                 "required": []},
             func=_optics_coded_design, mutating=True),

        Tool(name="optics_ground",
             description=(
                 "[CLOSED] Ground the optical design against the PWM registry: search for "
                 "matching L2 specs and L1 principles, and recommend a benchmark target. "
                 f"Cost: {TOOL_PRICES['optics_ground']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "query": {"type": "string", "default": "",
                           "description": "Optional extra search terms"},
                 "output_file": {"type": "string", "default": "grounding.json"}},
                 "required": []},
             func=_optics_ground, mutating=True),

        # ── Phase 2 tools ───────────────────────────────────────────────────
        Tool(name="optics_grating",
             description=(
                 "Diffraction grating efficiency + dispersion via scalar blazed-grating "
                 "theory (PCGrate replacement). Computes sinc² efficiency envelope, "
                 "resolving power, FSR, and angular dispersion vs wavelength. "
                 f"Cost: {TOOL_PRICES['optics_grating']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "groove_density_lpmm": {"type": "number", "default": 600.0,
                                         "description": "Groove density in lines/mm"},
                 "wavelengths_nm": {"type": "array", "items": {"type": "number"},
                                    "description": "Wavelengths to evaluate (nm). Default: 400-800 @ 10nm."},
                 "blaze_angle_deg": {"type": "number", "default": 0.0,
                                     "description": "Blaze angle in degrees"},
                 "order": {"type": "integer", "default": 1,
                           "description": "Diffraction order"},
                 "polarization": {"type": "string", "enum": ["TE", "TM", "avg"],
                                  "default": "avg"},
                 "n_grooves": {"type": "integer", "default": 1000,
                               "description": "Number of illuminated grooves (for resolving power)"},
                 "incident_angle_deg": {"type": "number", "default": 0.0,
                                        "description": "Angle of incidence in degrees"},
                 "output_file": {"type": "string", "default": "grating.json"}},
                 "required": []},
             func=_optics_grating, mutating=True),

        Tool(name="optics_thinfilm",
             description=(
                 "Multi-layer thin-film filter design via Transfer Matrix Method (TMM) — "
                 "Essential Macleod replacement. Computes T, R, A vs wavelength for "
                 "arbitrary stacks, or auto-designs bandpass / longpass filters. "
                 f"Cost: {TOOL_PRICES['optics_thinfilm']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "layers": {"type": "array", "items": {"type": "object"},
                            "description": "List of {n, k, thickness_nm} dicts. If omitted, use design_type."},
                 "substrate_n": {"type": "number", "default": 1.52,
                                 "description": "Substrate refractive index"},
                 "incident_n": {"type": "number", "default": 1.0,
                                "description": "Incident medium refractive index (1.0 = air)"},
                 "wavelengths_nm": {"type": "array", "items": {"type": "number"},
                                    "description": "Wavelengths to evaluate (nm). Default: 400-800 @ 5nm."},
                 "angle_deg": {"type": "number", "default": 0.0,
                               "description": "Angle of incidence in degrees"},
                 "polarization": {"type": "string", "enum": ["TE", "TM", "avg"], "default": "avg"},
                 "design_type": {"type": "string", "enum": ["bandpass", "longpass"],
                                 "description": "Auto-design type (used if layers is omitted)"},
                 "center_nm": {"type": "number", "default": 550.0,
                               "description": "Center wavelength for bandpass design (nm)"},
                 "bandwidth_nm": {"type": "number", "default": 50.0,
                                  "description": "Bandwidth for bandpass design (nm)"},
                 "cutoff_nm": {"type": "number", "default": 550.0,
                               "description": "Cutoff wavelength for longpass design (nm)"},
                 "n_high": {"type": "number", "default": 2.35,
                            "description": "High-index material (e.g. TiO2=2.35)"},
                 "n_low": {"type": "number", "default": 1.46,
                           "description": "Low-index material (e.g. SiO2=1.46)"},
                 "n_design_layers": {"type": "integer", "default": 7,
                                     "description": "Number of layers in auto-designed stack"},
                 "output_file": {"type": "string", "default": "thinfilm.json"}},
                 "required": []},
             func=_optics_thinfilm, mutating=True),

        Tool(name="optics_stray_light",
             description=(
                 "Monte Carlo non-sequential stray light analysis (LightTools replacement). "
                 "Computes ghost fraction, veiling glare index (VGI), scatter map, and "
                 "baffle recommendations via Harvey-Shack BSDF model. "
                 f"Cost: {TOOL_PRICES['optics_stray_light']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json",
                                  "description": "System prescription file in workspace"},
                 "n_rays": {"type": "integer", "default": 10000,
                            "description": "Number of Monte Carlo rays"},
                 "bsdf_roughness_nm": {"type": "number", "default": 2.0,
                                       "description": "Surface roughness RMS (nm) for TIS calculation"},
                 "baffle_transmission": {"type": "number", "default": 0.0,
                                         "description": "Baffle transmission (0=perfect absorber)"},
                 "seed": {"type": "integer", "default": 42},
                 "output_file": {"type": "string", "default": "stray_light.json"}},
                 "required": []},
             func=_optics_stray_light, mutating=True),

        Tool(name="optics_wave",
             description=(
                 "Wave-optics suite (Lumerical FDTD replacement): coherent PSF via pupil "
                 "function FFT (mode='psf'), 1D FDTD for thin-film R/T (mode='fdtd'), "
                 "or Abbe/Rayleigh diffraction limits (mode='diffraction_limit'). "
                 f"Cost: {TOOL_PRICES['optics_wave']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "prescription": {"type": "string", "default": "system.json"},
                 "mode": {"type": "string",
                          "enum": ["psf", "fdtd", "diffraction_limit"],
                          "default": "psf",
                          "description": "Wave-optics calculation mode"},
                 "grid_size": {"type": "integer", "default": 128,
                               "description": "PSF grid size (for mode=psf)"},
                 "wavelength_nm": {"type": "number", "default": 550.0},
                 "dz_mm": {"type": "number", "default": 1.0,
                           "description": "Propagation distance for angular spectrum (mm)"},
                 "n_fdtd_layers": {"type": "array", "items": {"type": "number"},
                                   "description": "Refractive indices for FDTD layers (mode=fdtd)"},
                 "thickness_fdtd_nm": {"type": "array", "items": {"type": "number"},
                                       "description": "Layer thicknesses in nm (mode=fdtd)"},
                 "na": {"type": "number", "default": 0.5,
                        "description": "Numerical aperture (for mode=diffraction_limit)"},
                 "output_file": {"type": "string", "default": "wave.json"}},
                 "required": []},
             func=_optics_wave, mutating=True),

        Tool(name="optics_monte_carlo",
             description=(
                 "Tissue light transport via MCML (MCX/MCML replacement). "
                 "Mode 'mcml': full photon Monte Carlo — fluence, reflectance, transmittance, "
                 "absorption by layer, 1/e penetration depth. "
                 "Mode 'hb': hemoglobin absorption spectrum (HbO2+Hb) with SO2 control. "
                 f"Cost: {TOOL_PRICES['optics_monte_carlo']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "tissue_layers": {"type": "array", "items": {"type": "object"},
                                   "description": "List of {mua, mus, g, n, thickness_mm} dicts"},
                 "n_photons": {"type": "integer", "default": 10000,
                               "description": "Number of photon packets"},
                 "source_beam_radius_mm": {"type": "number", "default": 0.5},
                 "source_type": {"type": "string", "enum": ["pencil", "gaussian"],
                                 "default": "pencil"},
                 "seed": {"type": "integer", "default": 42},
                 "mode": {"type": "string", "enum": ["mcml", "hb"], "default": "mcml"},
                 "wavelengths_nm": {"type": "array", "items": {"type": "number"},
                                    "description": "Wavelengths for Hb absorption (mode=hb)"},
                 "so2": {"type": "number", "default": 0.98,
                         "description": "Oxygen saturation 0..1 (mode=hb)"},
                 "output_file": {"type": "string", "default": "monte_carlo.json"}},
                 "required": []},
             func=_optics_monte_carlo, mutating=True),

        Tool(name="optics_snr",
             description=(
                 "Detector radiometry + SNR budget (MATLAB radiometry replacement). "
                 "Mode 'snr': full noise budget (shot/read/dark, SNR dB, dynamic range, NEP, "
                 "saturation). Mode 'irradiance': source → sensor photon flux chain. "
                 f"Cost: {TOOL_PRICES['optics_snr']} PWM."
             ),
             parameters={"type": "object", "properties": {
                 "signal_photons_per_pixel": {"type": "number", "default": 1000.0},
                 "qe": {"type": "number", "default": 0.7,
                        "description": "Quantum efficiency (0..1)"},
                 "read_noise_e": {"type": "number", "default": 3.0,
                                  "description": "Read noise in electrons RMS"},
                 "dark_current_e_per_s": {"type": "number", "default": 0.01},
                 "exposure_s": {"type": "number", "default": 1.0},
                 "n_accumulations": {"type": "integer", "default": 1},
                 "bit_depth": {"type": "integer", "default": 16},
                 "full_well_e": {"type": "number", "default": 30000.0},
                 "mode": {"type": "string", "enum": ["snr", "irradiance"], "default": "snr"},
                 "source_radiance": {"type": "number", "default": 1.0,
                                     "description": "Source radiance W/sr/m² (mode=irradiance)"},
                 "collection_solid_angle_sr": {"type": "number", "default": 0.01},
                 "transmission": {"type": "number", "default": 0.8},
                 "pixel_area_m2": {"type": "number", "default": 25e-12},
                 "wavelength_band_nm": {"type": "number", "default": 550.0},
                 "output_file": {"type": "string", "default": "snr.json"}},
                 "required": []},
             func=_optics_snr, mutating=True),
    ]
