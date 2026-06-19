"""Phase 0 smoke tests for pwm_core.optics and the optics-design tool bundle."""
import sys
import tempfile
import os
from pathlib import Path

# Ensure the repo root is on sys.path so pwm_core.optics is importable when
# this script is run directly (python3 tests/test_optics_phase0.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TESTS_DIR = Path(__file__).resolve().parent

results = []


def check(name, cond, info=""):
    ok = bool(cond)
    results.append((name, ok, info))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {info}" if info else ""))


def _run():
    # ── shared fixture ────────────────────────────────────────────────────────
    try:
        from pwm_core.optics import (
            OpticalSystem, Surface, Field, Wavelength,
            save_system, load_system, import_zmx,
            paraxial_data, spot_diagram, seidel_aberrations, psf_mtf, wavefront,
        )
    except Exception as exc:
        print(f"  [FAIL] import_optics_module -- {exc}")
        results.append(("import_optics_module", False, str(exc)))
        # remaining tests would all crash; record them as failed and bail
        for name in (
            "prescription_round_trip",
            "title_and_notes_preserved",
            "paraxial_efl",
            "spot_rms_positive",
            "seidel_five_keys",
            "psf_mtf_strehl",
            "import_zmx_surfaces",
            "tools_and_capabilities",
        ):
            results.append((name, False, "import failed"))
            print(f"  [FAIL] {name} -- import failed")
        return

    SINGLET = OpticalSystem(
        surfaces=[
            Surface(radius=51.68, thickness=5.2, material="BK7"),
            Surface(radius=-51.68, thickness=46.6),
        ],
        aperture_value=12.5,
        title="Test singlet",
    )

    # ── Test 1: prescription round-trip ──────────────────────────────────────
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "singlet.json"
            save_system(SINGLET, str(tmp))
            loaded = load_system(str(tmp))
            ok = (len(loaded.surfaces) == 2 and
                  abs(loaded.surfaces[0].radius - 51.68) < 1e-6)
            check("prescription_round_trip", ok,
                  f"surfaces={len(loaded.surfaces)}, r0={loaded.surfaces[0].radius}")
    except Exception as exc:
        check("prescription_round_trip", False, str(exc))

    # ── Test 2: title and notes preserved ────────────────────────────────────
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "singlet.json"
            save_system(SINGLET, str(tmp))
            loaded = load_system(str(tmp))
            check("title_and_notes_preserved", loaded.title == "Test singlet",
                  f"title={loaded.title!r}")
    except Exception as exc:
        check("title_and_notes_preserved", False, str(exc))

    # ── Test 3: paraxial_data returns valid EFL ───────────────────────────────
    try:
        result = paraxial_data(SINGLET)
        ok = result.get("status") == "ok" and result.get("efl", 0) > 0
        check("paraxial_efl", ok,
              f"status={result.get('status')}, efl={result.get('efl')}")
    except Exception as exc:
        check("paraxial_efl", False, str(exc))

    # ── Test 4: spot_diagram returns positive RMS ─────────────────────────────
    try:
        result = spot_diagram(SINGLET)
        ok = result.get("status") == "ok" and result.get("rms_spot_mm", -1) > 0
        check("spot_rms_positive", ok,
              f"status={result.get('status')}, rms={result.get('rms_spot_mm')}")
    except Exception as exc:
        check("spot_rms_positive", False, str(exc))

    # ── Test 5: seidel_aberrations has 5 keys ────────────────────────────────
    try:
        result = seidel_aberrations(SINGLET)
        required = {"SA", "Coma", "Ast", "FieldCurv", "Distortion"}
        ok = result.get("status") == "ok" and required <= set(result.keys())
        check("seidel_five_keys", ok,
              f"status={result.get('status')}, keys={sorted(set(result.keys()) & required)}")
    except Exception as exc:
        check("seidel_five_keys", False, str(exc))

    # ── Test 6: psf_mtf returns Strehl in (0, 1.01] ──────────────────────────
    try:
        result = psf_mtf(SINGLET, grid_size=32)
        strehl = result.get("strehl", 0)
        ok = result.get("status") == "ok" and 0 < strehl <= 1.01
        check("psf_mtf_strehl", ok,
              f"status={result.get('status')}, strehl={strehl}")
    except Exception as exc:
        check("psf_mtf_strehl", False, str(exc))

    # ── Test 7: import_zmx round-trip ────────────────────────────────────────
    try:
        fixture = _TESTS_DIR / "fixtures" / "doublet.zmx"
        sys_zmx = import_zmx(str(fixture))
        ok = len(sys_zmx.surfaces) >= 2
        check("import_zmx_surfaces", ok,
              f"surfaces={len(sys_zmx.surfaces)}, title={sys_zmx.title!r}")
    except Exception as exc:
        check("import_zmx_surfaces", False, str(exc))

    # ── Test 8: tools + capabilities ─────────────────────────────────────────
    try:
        from ai4science.harness.optics_tools import optics_tools, TOOL_PRICES
        tools = optics_tools()
        tools_ok = len(tools) >= 10  # Phase 1 adds 3 closed tools (13 total)

        from ai4science.harness.agents.capabilities import BUILTIN_BUNDLES
        cap_ok = "optics-design" in BUILTIN_BUNDLES

        ok = tools_ok and cap_ok
        check("tools_and_capabilities", ok,
              f"num_tools={len(tools)}, optics-design_in_bundles={cap_ok}")
    except Exception as exc:
        check("tools_and_capabilities", False, str(exc))


_run()
ok = all(r[1] for r in results)
passed = sum(r[1] for r in results)
print(f"\n{passed}/{len(results)} checks passed")
sys.exit(0 if ok else 1)
