"""analysis.py — pure analysis functions for optical systems.

All functions return JSON-serialisable dicts and wrap computation in
try/except, returning ``{"status": str(exc)}`` on failure.

Backends
--------
* :mod:`pwm_core.optics.raytrace`     — rayoptics-backed analyses
* :mod:`pwm_core.optics.diff_raytrace` — optiland-backed RMS spot
* numpy                                — FFT-based PSF / MTF and Zernike fit
"""

from __future__ import annotations
import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pwm_core.optics.prescription import OpticalSystem


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_opm(sys: "OpticalSystem"):
    """Load a rayoptics OpticalModel from an OpticalSystem (via ZMX round-trip)."""
    from pwm_core.optics.raytrace import _load_opm as _ro_load
    return _ro_load(sys)


def _primary_wvl(sm) -> float:
    """Return the primary wavelength value (nm) from a rayoptics seq_model."""
    from pwm_core.optics.raytrace import primary_wvl_idx
    idx = primary_wvl_idx(sm)
    return float(sm.wvlns[idx])


# ---------------------------------------------------------------------------
# Spot diagram
# ---------------------------------------------------------------------------


def spot_diagram(
    sys: "OpticalSystem",
    field_idx: int = 0,
    num_rays: int = 100,
) -> dict:
    """Compute RMS spot radius for each field.

    Uses optiland for ray tracing (centroid-corrected).

    Returns
    -------
    ``{"rms_spot_mm": float, "fields": [{"y": float, "rms": float}, ...], "status": "ok"}``
    """
    try:
        from pwm_core.optics.diff_raytrace import to_optiland

        o = to_optiland(sys)
        primary_wl = next(
            (wl.value for wl in sys.wavelengths if wl.is_primary),
            sys.wavelengths[0].value if sys.wavelengths else 0.55,
        )

        field_results = []
        for fi, fld in enumerate(sys.fields):
            try:
                rays = o.ray_tracer.trace(
                    Hx=0,
                    Hy=fld.y,
                    wavelength=primary_wl,
                    num_rays=num_rays,
                )
                x = np.asarray(rays.x, dtype=float)
                y_arr = np.asarray(rays.y, dtype=float)
                cx, cy = float(np.mean(x)), float(np.mean(y_arr))
                rms = float(np.sqrt(np.mean((x - cx) ** 2 + (y_arr - cy) ** 2)))
            except Exception:
                rms = float("nan")
            field_results.append({"y": float(fld.y), "rms": rms})

        # Return primary field RMS
        pri_rms = field_results[field_idx]["rms"] if field_results else float("nan")

        return {
            "rms_spot_mm": pri_rms,
            "fields": field_results,
            "status": "ok",
        }

    except Exception as exc:
        # Fallback to diff_raytrace
        try:
            from pwm_core.optics.diff_raytrace import trace_diff
            r = trace_diff(sys)
            if r.get("status") == "ok":
                rms = r["rms_spot"]
                flds = [{"y": float(f.y), "rms": rms} for f in sys.fields]
                return {
                    "rms_spot_mm": rms,
                    "fields": flds,
                    "status": "ok (diff_raytrace fallback)",
                }
        except Exception:
            pass
        return {"status": str(exc)}


# ---------------------------------------------------------------------------
# Ray fan
# ---------------------------------------------------------------------------


def ray_fan(sys: "OpticalSystem", field_idx: int = 0) -> dict:
    """Tangential and sagittal ray-fan transverse aberration.

    Uses rayoptics ``RayFan`` analysis.

    Returns
    -------
    ``{"tangential": [[py, ey], ...], "sagittal": [[px, ex], ...], "status": "ok"}``
    """
    try:
        from rayoptics.raytr.analyses import RayFan
        from pwm_core.optics.raytrace import primary_wvl_idx

        opm = _load_opm(sys)
        sm = opm.seq_model
        wvl = _primary_wvl(sm)
        _, _, foc = opm.optical_spec.lookup_fld_wvl_focus(field_idx, 0)

        # Tangential fan (vary py)
        rf_y = RayFan(opm, f=field_idx, wl=wvl, foc=foc, num_rays=21, xyfan="y")
        # fan[i] = ((px, py), (ex, ey, opd))
        tangential = []
        for pupil, aberr in rf_y.fan:
            py = float(pupil[1])
            ey = float(aberr[1])
            tangential.append([py, ey])

        # Sagittal fan (vary px)
        rf_x = RayFan(opm, f=field_idx, wl=wvl, foc=foc, num_rays=21, xyfan="x")
        sagittal = []
        for pupil, aberr in rf_x.fan:
            px = float(pupil[0])
            ex = float(aberr[0])
            sagittal.append([px, ex])

        return {"tangential": tangential, "sagittal": sagittal, "status": "ok"}

    except Exception as exc:
        return {"status": str(exc)}


# ---------------------------------------------------------------------------
# Wavefront / Zernike
# ---------------------------------------------------------------------------

def _zernike_basis(rho: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Return (9, N) Zernike basis array for Z1–Z9 (Noll ordering).

    Parameters
    ----------
    rho   : normalised pupil radius (0–1), shape (N,)
    theta : pupil azimuth angle (radians), shape (N,)

    Returns
    -------
    Z : ndarray of shape (9, N)
    """
    r = rho
    r2 = r ** 2
    r3 = r ** 3
    r4 = r ** 4
    t = theta

    Z = np.zeros((9, len(r)))
    Z[0] = 1.0                                          # Z1  piston
    Z[1] = 2.0 * r * np.cos(t)                         # Z2  x-tilt
    Z[2] = 2.0 * r * np.sin(t)                         # Z3  y-tilt
    Z[3] = math.sqrt(3) * (2.0 * r2 - 1.0)             # Z4  defocus
    Z[4] = math.sqrt(6) * r2 * np.sin(2.0 * t)         # Z5  45° astig
    Z[5] = math.sqrt(6) * r2 * np.cos(2.0 * t)         # Z6  0° astig
    Z[6] = math.sqrt(8) * (3.0 * r3 - 2.0 * r) * np.sin(t)  # Z7 y-coma
    Z[7] = math.sqrt(8) * (3.0 * r3 - 2.0 * r) * np.cos(t)  # Z8 x-coma
    Z[8] = math.sqrt(5) * (6.0 * r4 - 6.0 * r2 + 1.0) # Z9  primary sph
    return Z


def _fit_zernike(px: np.ndarray, py: np.ndarray, opd: np.ndarray):
    """Least-squares fit Z1–Z9 Zernike to OPD samples on unit disk.

    Parameters
    ----------
    px, py : pupil coordinates (each 1-D, values in [-1, 1])
    opd    : OPD in waves, same shape as px

    Returns
    -------
    coeffs : ndarray of shape (9,) — Zernike coefficients
    rms    : float — RMS WFE (waves)
    """
    rho = np.sqrt(px ** 2 + py ** 2)
    theta = np.arctan2(py, px)

    # Keep only points inside unit pupil with valid OPD
    mask = (rho <= 1.0) & np.isfinite(opd)
    if mask.sum() < 10:
        return np.zeros(9), 0.0

    rho_m = rho[mask]
    theta_m = theta[mask]
    opd_m = opd[mask]

    Z = _zernike_basis(rho_m, theta_m)  # (9, M)
    # Fit: opd_m = Z.T @ coeffs  (least squares)
    A = Z.T  # (M, 9)
    coeffs, _, _, _ = np.linalg.lstsq(A, opd_m, rcond=None)

    # RMS of residual + fit  ~ RMS WFE of the sampled wavefront
    fitted = A @ coeffs
    rms = float(np.sqrt(np.mean((opd_m - np.mean(opd_m)) ** 2)))

    return coeffs, rms


def wavefront(
    sys: "OpticalSystem",
    field_idx: int = 0,
    num_pts: int = 64,
) -> dict:
    """Wavefront analysis: Zernike coefficients and RMS WFE.

    Uses rayoptics ``eval_wavefront`` to sample the OPD grid on the pupil,
    then fits Z1–Z9 by least squares.

    Returns
    -------
    ``{"zernike": {"Z1": float, ...}, "rms_wfe_waves": float, "status": "ok"}``
    """
    try:
        from rayoptics.raytr.analyses import eval_wavefront

        opm = _load_opm(sys)
        sm = opm.seq_model
        wvl = _primary_wvl(sm)
        fld, _, foc = opm.optical_spec.lookup_fld_wvl_focus(field_idx, 0)

        # eval_wavefront returns (N, N, 3) array: [px, py, opd_in_waves]
        wf = eval_wavefront(opm, fld, wvl, foc, num_rays=num_pts)

        px_grid = wf[:, :, 0].ravel()
        py_grid = wf[:, :, 1].ravel()
        opd_waves = wf[:, :, 2].ravel()

        coeffs, rms = _fit_zernike(px_grid, py_grid, opd_waves)

        zernike = {f"Z{i+1}": float(c) for i, c in enumerate(coeffs)}

        return {
            "zernike": zernike,
            "rms_wfe_waves": rms,
            "status": "ok",
        }

    except Exception as exc:
        return {"status": str(exc)}


# ---------------------------------------------------------------------------
# Seidel aberrations
# ---------------------------------------------------------------------------


def seidel_aberrations(sys: "OpticalSystem") -> dict:
    """Third-order (Seidel) aberration coefficients via rayoptics.

    Uses ``rayoptics.parax.thirdorder.compute_third_order`` which returns a
    per-surface pandas DataFrame with columns S-I…S-V.

    Returns
    -------
    ``{"SA": float, "Coma": float, "Ast": float, "FieldCurv": float,
       "Distortion": float, "status": "ok"}``
    """
    try:
        from rayoptics.parax.thirdorder import compute_third_order

        opm = _load_opm(sys)
        df = compute_third_order(opm)

        # Sum contributions from all surfaces
        sa   = float(df["S-I"].sum())
        coma = float(df["S-II"].sum())
        ast  = float(df["S-III"].sum())
        fc   = float(df["S-IV"].sum())
        dist = float(df["S-V"].sum())

        return {
            "SA": sa,
            "Coma": coma,
            "Ast": ast,
            "FieldCurv": fc,
            "Distortion": dist,
            "status": "ok",
        }

    except Exception as exc:
        return {
            "SA": 0.0,
            "Coma": 0.0,
            "Ast": 0.0,
            "FieldCurv": 0.0,
            "Distortion": 0.0,
            "status": f"seidel unavailable: {exc}",
        }


# ---------------------------------------------------------------------------
# PSF / MTF
# ---------------------------------------------------------------------------


def psf_mtf(
    sys: "OpticalSystem",
    field_idx: int = 0,
    grid_size: int = 128,
) -> dict:
    """Compute PSF and MTF via pupil-function FFT.

    Algorithm
    ---------
    1. Sample OPD on a square pupil grid (rayoptics ``eval_wavefront``).
       Fall back to zero OPD (diffraction-limited) if rayoptics fails.
    2. Build pupil function ``P = circ(r) * exp(2π i OPD)``.
    3. PSF = |FFT2(P)|² (normalised to unit peak for ideal system).
    4. Strehl = max(PSF_aberrated) / max(PSF_ideal).
    5. MTF = |FFT2(PSF)| (auto-correlation / OTF magnitude).

    Returns
    -------
    ``{"psf": [[float,...], ...], "strehl": float,
       "mtf_freq": [float,...], "mtf_t": [float,...],
       "mtf_s": [float,...], "status": "ok"}``
    """
    try:
        N = grid_size

        # --- Build pupil grid ---
        px_lin = np.linspace(-1, 1, N)
        py_lin = np.linspace(-1, 1, N)
        px_grid, py_grid = np.meshgrid(px_lin, py_lin)
        r_grid = np.sqrt(px_grid ** 2 + py_grid ** 2)
        circ = (r_grid <= 1.0).astype(float)

        # --- Try to get OPD from rayoptics ---
        opd_waves = np.zeros((N, N))
        try:
            from rayoptics.raytr.analyses import eval_wavefront

            opm = _load_opm(sys)
            sm = opm.seq_model
            wvl = _primary_wvl(sm)
            fld, _, foc = opm.optical_spec.lookup_fld_wvl_focus(field_idx, 0)

            # eval_wavefront uses its own grid size (num_rays); we request N but
            # interpolate onto our grid regardless.
            num_ro = min(N, 64)  # keep rayoptics grid manageable
            wf_data = eval_wavefront(opm, fld, wvl, foc, num_rays=num_ro)

            # wf_data shape (num_ro, num_ro, 3): [px, py, opd_in_waves]
            px_ro = wf_data[:, :, 0]
            py_ro = wf_data[:, :, 1]
            opd_ro = wf_data[:, :, 2]

            # Interpolate onto our (N×N) grid using scipy if available,
            # otherwise use nearest-neighbour from the raw points.
            try:
                from scipy.interpolate import griddata
                pts = np.column_stack([px_ro.ravel(), py_ro.ravel()])
                vals = opd_ro.ravel()
                finite = np.isfinite(vals)
                if finite.sum() > 4:
                    zi = griddata(
                        pts[finite],
                        vals[finite],
                        (px_grid, py_grid),
                        method="linear",
                        fill_value=0.0,
                    )
                    opd_waves = np.where(circ > 0, zi, 0.0)
            except ImportError:
                # scipy not available — use raw OPD grid (may differ in size)
                # Resize by simple repeat/crop
                from numpy import nan_to_num
                opd_rs = nan_to_num(opd_ro, nan=0.0)
                if opd_rs.shape[0] != N:
                    # bilinear-ish via numpy interp along each axis
                    from numpy import interp
                    xi = np.linspace(0, opd_rs.shape[1] - 1, N)
                    yi = np.linspace(0, opd_rs.shape[0] - 1, N)
                    tmp = np.array(
                        [interp(xi, np.arange(opd_rs.shape[1]), row)
                         for row in opd_rs]
                    )
                    opd_waves = np.array(
                        [interp(yi, np.arange(tmp.shape[0]), tmp[:, col])
                         for col in range(N)]
                    ).T
                    opd_waves = np.where(circ > 0, opd_waves, 0.0)
                else:
                    opd_waves = np.where(circ > 0, nan_to_num(opd_waves, nan=0.0), 0.0)

        except Exception:
            pass  # Fall through with zero OPD (diffraction-limited)

        # --- Ideal PSF (zero OPD) ---
        P_ideal = circ.astype(complex)
        psf_ideal = np.abs(np.fft.fftshift(np.fft.fft2(P_ideal))) ** 2
        peak_ideal = float(psf_ideal.max()) if psf_ideal.max() > 0 else 1.0

        # --- Aberrated PSF ---
        P_aber = circ * np.exp(2j * np.pi * opd_waves)
        psf_aber = np.abs(np.fft.fftshift(np.fft.fft2(P_aber))) ** 2

        # Strehl ratio
        strehl = float(psf_aber.max()) / peak_ideal

        # Normalise PSF for output (peak = 1)
        psf_norm = psf_aber / (psf_aber.max() if psf_aber.max() > 0 else 1.0)

        # --- MTF from PSF auto-correlation ---
        # OTF = FFT(PSF), MTF = |OTF|
        otf = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(psf_norm)))
        mtf = np.abs(otf)
        mtf /= mtf[N // 2, N // 2] if mtf[N // 2, N // 2] > 0 else 1.0  # normalise

        # Spatial frequency axis (cycles / pixel — not physical units without plate scale)
        freq = np.fft.fftshift(np.fft.fftfreq(N))  # [-0.5, +0.5)

        # Tangential MTF: row through centre (constant py=0, vary px)
        # Sagittal MTF: column through centre (constant px=0, vary py)
        mid = N // 2
        mtf_t = mtf[mid, :].tolist()
        mtf_s = mtf[:, mid].tolist()
        mtf_freq = freq.tolist()

        return {
            "psf": psf_norm.tolist(),
            "strehl": strehl,
            "mtf_freq": mtf_freq,
            "mtf_t": mtf_t,
            "mtf_s": mtf_s,
            "status": "ok",
        }

    except Exception as exc:
        return {"status": str(exc)}
