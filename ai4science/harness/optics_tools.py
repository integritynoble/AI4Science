from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, List, Optional

from ai4science.harness.tools.base import Tool

_WALLET = os.environ.get("OPTICS_TOOL_WALLET", "0x3CeA937cd8114Efa8120C011f1035c9b428C9d05")

TOOL_PRICES: dict = {
    "optics_define":      0.5,
    "optics_import":      1.0,
    "optics_raytrace":    1.0,
    "optics_layout":      0.5,
    "optics_paraxial":    0.5,
    "optics_spot":        1.0,
    "optics_rayfan":      1.0,
    "optics_zernike":     1.5,
    "optics_psf_mtf":     2.0,
    "optics_aberrations": 1.0,
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
    """Return all OPEN optical design tools for the computational-imaging agent."""
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
    ]
