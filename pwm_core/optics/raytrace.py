"""raytrace.py — thin adapter wrapping rayoptics for sequential ray trace and
paraxial analysis.

The round-trip strategy is:
  1. Convert OpticalSystem → minimal .zmx string
  2. Write to a temp file and load with rayoptics ``open_model``
  3. Run paraxial / ray-trace analysis
  4. Return JSON-serialisable dicts

All public functions wrap in try/except and return ``{"status": str(exc)}``
on failure so callers never see an unhandled exception.
"""

from __future__ import annotations
import math
import tempfile
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pwm_core.optics.prescription import OpticalSystem


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Map common glass names to Zemax catalog forms understood by rayoptics
_GLASS_ALIAS: dict[str, str] = {
    "bk7": "BK7",
    "n-bk7": "N-BK7",
    "nbk7": "N-BK7",
    "f2": "F2",
    "n-f2": "N-F2",
    "sf11": "SF11",
    "n-sf11": "N-SF11",
    "baf10": "BAF10",
    "n-baf10": "N-BAF10",
    "sk16": "SK16",
    "n-sk16": "N-SK16",
    "lak22": "LAK22",
    "n-lak22": "N-LAK22",
    "flint": "F2",
    "crown": "BK7",
}


def _glass_tag(mat: str) -> str:
    """Return the GLAS line for a surface, or empty string for air."""
    lo = mat.strip().lower()
    if lo in ("air", "", "none", "vacuum"):
        return ""
    canonical = _GLASS_ALIAS.get(lo, mat.strip())
    # Minimal GLAS entry — rayoptics will look up the glass in its catalog.
    # We use 0 0 for the index/V-number so rayoptics reads from catalog.
    return f"  GLAS {canonical} 0 0 0 0 0 0 0 0 0 0\n"


def _to_zmx_str(sys: "OpticalSystem") -> str:
    """Produce a minimal but valid .zmx string that rayoptics can load."""
    from pwm_core.optics.prescription import OpticalSystem  # avoid circ import

    # Header
    lines = [
        "VERS 160720 18 100027\n",
        "MODE SEQ\n",
        f"NAME {sys.title or 'pwm_lens'}\n",
        "UNIT MM X W X CM MR CPMM\n",
    ]

    # Aperture
    epd = sys.aperture_value if sys.aperture_type == "EPD" else 10.0
    lines.append(f"ENPD {epd:.6E}\n")

    # Fields
    ftype = 0  # angle
    nf = len(sys.fields)
    lines.append(f"FTYP 0 0 {nf} {nf} 0 0 0\n")
    xf = " ".join("0" for _ in sys.fields)
    yf = " ".join(f"{f.y:.6g}" for f in sys.fields)
    wg = " ".join(f"{f.weight:.6g}" for f in sys.fields)
    lines.append(f"XFLN {xf}\n")
    lines.append(f"YFLN {yf}\n")
    lines.append(f"FWGN {wg}\n")

    # Wavelengths
    for i, wl in enumerate(sys.wavelengths, 1):
        wl_nm = wl.value * 1000  # microns → nm
        lines.append(f"WAVM {i} {wl_nm:.5E} {wl.weight:.0f}\n")
    # Primary wavelength index
    primary_idx = next(
        (i for i, w in enumerate(sys.wavelengths, 1) if w.is_primary), 1
    )
    lines.append(f"PWAV {primary_idx}\n")

    # Object surface (SURF 0)
    lines.append("SURF 0\n")
    lines.append("  TYPE STANDARD\n")
    lines.append("  CURV 0.0 0 0 0 0 \"\"\n")
    lines.append("  DISZ INFINITY\n")
    lines.append("  DIAM 0 0 0 0 1 \"\"\n")

    # Lens surfaces
    for i, s in enumerate(sys.surfaces, 1):
        curv = 0.0 if not math.isfinite(s.radius) or s.radius == 0 else 1.0 / s.radius
        thickness = s.thickness
        semi_d = s.semi_diameter if s.semi_diameter is not None else epd / 2.0

        lines.append(f"SURF {i}\n")
        lines.append("  TYPE STANDARD\n")
        lines.append(f"  CURV {curv:.8E} 0 0 0 0 \"\"\n")
        if math.isfinite(thickness):
            lines.append(f"  DISZ {thickness:.8E}\n")
        else:
            lines.append("  DISZ INFINITY\n")
        gtag = _glass_tag(s.material)
        if gtag:
            lines.append(gtag)
        lines.append(f"  DIAM {semi_d:.6E} 0 0 0 1 \"\"\n")

    # Image surface
    img_idx = len(sys.surfaces) + 1
    lines.append(f"SURF {img_idx}\n")
    lines.append("  TYPE STANDARD\n")
    lines.append("  CURV 0.0 0 0 0 0 \"\"\n")
    lines.append("  DISZ 0\n")
    lines.append("  DIAM 5.0 0 0 0 1 \"\"\n")

    return "".join(lines)


def _load_opm(sys: "OpticalSystem"):
    """Convert OpticalSystem → rayoptics OpticalModel via ZMX round-trip."""
    from rayoptics.environment import open_model

    zmx = _to_zmx_str(sys)
    with tempfile.NamedTemporaryFile(
        suffix=".zmx", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(zmx)
        tmp_path = f.name
    try:
        opm = open_model(tmp_path)
        opm.update_model()
    finally:
        os.unlink(tmp_path)
    return opm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def trace_system(sys: "OpticalSystem") -> dict:
    """Sequential ray trace via rayoptics.

    Returns
    -------
    dict with keys:
      ``surfaces``  — list of per-surface dicts with ``height`` and ``angle``
                       (marginal ray y-height and paraxial slope).
      ``opd``       — OPD of the marginal ray in waves (scalar, on-axis field).
      ``status``    — ``"ok"`` or an error string.
    """
    try:
        from rayoptics.raytr import analyses

        opm = _load_opm(sys)
        sm = opm.seq_model
        pm = opm.parax_model

        # Marginal ray data from paraxial model: ax[i] = [y, u]
        ax = pm.ax
        surfaces = []
        for i, (y_u) in enumerate(ax):
            surfaces.append({"height": float(y_u[0]), "angle": float(y_u[1])})

        # OPD: use on-axis field, primary wavelength fan
        wvl = sm.wvlns[primary_wvl_idx(sm)]
        fld, _, foc = opm.optical_spec.lookup_fld_wvl_focus(0, 0)
        rf = analyses.RayFan(opm, f=0, wl=wvl, foc=foc, num_rays=3, xyfan="y")
        # fan[-1] is the marginal ray (py=+1)
        opd_val = float(rf.fan[-1][1][2]) if rf.fan else 0.0

        return {"surfaces": surfaces, "opd": opd_val, "status": "ok"}

    except Exception as exc:
        return {"status": str(exc)}


def paraxial_data(sys: "OpticalSystem") -> dict:
    """Paraxial (first-order) data via rayoptics.

    Returns
    -------
    dict with keys ``efl``, ``bfd``, ``ffd``, ``na``, ``fno``,
    ``magnification``, ``status``.
    """
    try:
        opm = _load_opm(sys)
        sm = opm.seq_model
        pm = opm.parax_model

        ax = pm.ax   # marginal ray  [y, u] per surface
        pr = pm.pr   # chief ray     [ybar, ubar] per surface

        # EFL = -h_entrance / u_image
        h_entrance = float(ax[1][0]) if len(ax) > 1 else 0.0
        u_img = float(ax[-1][1])
        efl = -h_entrance / u_img if abs(u_img) > 1e-20 else float("inf")

        # BFD = thickness of last gap
        bfd = float(sm.gaps[-1].thi)

        # FFD = -(efl + pp1)  where pp1 = bfd - efl
        pp1 = bfd - efl
        ffd = -(efl + pp1)

        # NA_image
        na_img = abs(u_img)

        # f/# = 1 / (2 * NA)
        fno = 1.0 / (2.0 * na_img) if na_img > 0 else float("inf")

        # Paraxial lateral magnification: ybar_img / ybar_entrance
        ybar_in = float(pr[1][0]) if len(pr) > 1 else 0.0
        ybar_out = float(pr[-1][0])
        mag = ybar_out / ybar_in if abs(ybar_in) > 1e-20 else 0.0

        return {
            "efl": efl,
            "bfd": bfd,
            "ffd": ffd,
            "na": na_img,
            "fno": fno,
            "magnification": mag,
            "status": "ok",
        }

    except Exception as exc:
        return {"status": str(exc)}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def primary_wvl_idx(sm) -> int:
    """Return index into sm.wvlns for the primary wavelength (nearest to primary)."""
    try:
        primary_nm = sm.opt_model.optical_spec.spectral_region.central_wvl
        diffs = [abs(w - primary_nm) for w in sm.wvlns]
        return diffs.index(min(diffs))
    except Exception:
        return len(sm.wvlns) // 2
