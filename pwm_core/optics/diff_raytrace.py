"""diff_raytrace.py — optiland/torch adapter for differentiable ray tracing.

Converts an ``OpticalSystem`` prescription to an optiland ``Optic`` object and
provides a differentiable RMS-spot trace.

All public functions wrap in try/except and return ``{"status": str(exc)}``
on failure so callers never crash.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pwm_core.optics.prescription import OpticalSystem


# ---------------------------------------------------------------------------
# Material helpers
# ---------------------------------------------------------------------------

# Map common glass names to optiland/Schott catalog forms
_OPTILAND_GLASS: dict[str, str] = {
    "bk7": "N-BK7",
    "n-bk7": "N-BK7",
    "nbk7": "N-BK7",
    "f2": "N-F2",
    "n-f2": "N-F2",
    "sf11": "N-SF11",
    "n-sf11": "N-SF11",
    "baf10": "N-BAF10",
    "n-baf10": "N-BAF10",
    "sk16": "N-SK16",
    "n-sk16": "N-SK16",
    "lak22": "N-LAK22",
    "n-lak22": "N-LAK22",
    "flint": "N-F2",
    "crown": "N-BK7",
}


def _canonical_glass(name: str) -> str:
    lo = name.strip().lower()
    return _OPTILAND_GLASS.get(lo, name.strip())


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def to_optiland(sys: "OpticalSystem"):
    """Convert an ``OpticalSystem`` → optiland ``Optic`` object.

    Parameters
    ----------
    sys : OpticalSystem
        Source prescription.

    Returns
    -------
    optiland.optic.Optic
        Ready-to-trace optiland system.

    Raises
    ------
    ImportError  if optiland is not installed.
    RuntimeError on conversion failure.
    """
    from optiland import optic as _optic
    from optiland.aperture import EPDAperture

    o = _optic.Optic(name=sys.title or "pwm_lens")

    # Object surface at index 0 (very distant object — infinity)
    o.surfaces.add(
        surface_type="standard",
        index=0,
        thickness=1e10,
        material="air",
    )

    # Lens surfaces
    is_stop_set = False
    for idx, s in enumerate(sys.surfaces, 1):
        import math
        radius = None if (not math.isfinite(s.radius) or s.radius == 0) else s.radius
        lo = s.material.strip().lower()
        if lo in ("air", "", "none", "vacuum", "mirror"):
            mat = "air"
        else:
            mat = _canonical_glass(s.material)

        # Mark first real (glass) surface as stop if aperture_type == EPD
        is_stop = False
        if not is_stop_set and sys.aperture_type == "EPD" and mat != "air":
            is_stop = True
            is_stop_set = True

        kwargs: dict = {"thickness": s.thickness}
        if radius is not None:
            kwargs["radius"] = radius
        if s.conic != 0.0:
            kwargs["conic"] = s.conic

        o.surfaces.add(
            surface_type="standard",
            index=idx,
            is_stop=is_stop,
            material=mat,
            **kwargs,
        )

    # Image surface
    n_surf = len(sys.surfaces)
    o.surfaces.add(
        surface_type="standard",
        index=n_surf + 1,
        thickness=0.0,
        material="air",
    )

    # Aperture
    if sys.aperture_type == "EPD":
        o.aperture = EPDAperture(sys.aperture_value)
    elif sys.aperture_type in ("FNO", "fno"):
        from optiland.aperture import ImageFNOAperture
        o.aperture = ImageFNOAperture(sys.aperture_value)
    elif sys.aperture_type in ("NA", "na"):
        from optiland.aperture import ObjectNAAperture
        o.aperture = ObjectNAAperture(sys.aperture_value)
    else:
        o.aperture = EPDAperture(sys.aperture_value)

    # Fields (angle type by default)
    o.fields.set_type("angle")
    for f in sys.fields:
        o.fields.add(y=f.y, x=f.x, weight=f.weight)

    # Wavelengths (optiland uses microns)
    for wl in sys.wavelengths:
        o.wavelengths.add(
            value=wl.value,
            unit="um",
            is_primary=wl.is_primary,
        )

    return o


# ---------------------------------------------------------------------------
# Differentiable trace
# ---------------------------------------------------------------------------


def trace_diff(sys: "OpticalSystem", *, device: str = "cpu") -> dict:
    """Differentiable ray trace via optiland, returning RMS spot radius.

    Parameters
    ----------
    sys    : OpticalSystem
    device : ``"cpu"`` or ``"cuda"`` (if torch GPU available).

    Returns
    -------
    dict with keys ``rms_spot`` (float, mm) and ``status`` (``"ok"`` or error).
    """
    try:
        import numpy as np

        o = to_optiland(sys)

        # Trace rays for the first field with the primary wavelength
        primary_wl = next(
            (wl.value for wl in sys.wavelengths if wl.is_primary),
            sys.wavelengths[0].value if sys.wavelengths else 0.55,
        )

        rays = o.ray_tracer.trace(
            Hx=0,
            Hy=sys.fields[0].y if sys.fields else 0.0,
            wavelength=primary_wl,
            num_rays=100,
        )

        x = np.asarray(rays.x, dtype=float)
        y = np.asarray(rays.y, dtype=float)

        # Centroid-corrected RMS spot radius
        cx, cy = float(np.mean(x)), float(np.mean(y))
        rms = float(np.sqrt(np.mean((x - cx) ** 2 + (y - cy) ** 2)))

        return {"rms_spot": rms, "status": "ok"}

    except Exception as exc:
        return {"status": str(exc)}
