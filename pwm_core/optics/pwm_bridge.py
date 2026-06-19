"""pwm_bridge.py — optical system → PWM L2 digital-twin spec fields.

Converts an OpticalSystem (with computed PSF / paraxial data) into the
six_tuple / protocol_fields / d_spec bundle that a PWM L2 spec requires,
enabling the designed optical front-end to seed a benchmark.

Key output keys (matching L2-003 / L2-004 shape):
  d_spec          — float 0–1  (difficulty; 1 – Strehl for convolution)
  spec_type       — "psf_convolution" | "cassi_dispersion" | "lensless"
  six_tuple       — {omega, E, B, I, O, epsilon_fn}
  protocol_fields — {input_format, output_format, …}
  title           — suggested title string
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pwm_core.optics.prescription import OpticalSystem

_MODALITIES = ("psf_convolution", "cassi", "lensless")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def optical_to_spec_fields(
    sys: "OpticalSystem",
    *,
    modality: str = "psf_convolution",
    H: int = 256,
    W: int = 256,
    N_bands: int = 1,
    noise_level: float = 0.01,
    mask_density: float = 0.5,
    disp_a1: float = 1.0,
    grid_size: int = 64,
) -> dict:
    """Convert an OpticalSystem prescription to PWM L2 spec fields.

    Parameters
    ----------
    sys        : OpticalSystem to characterise
    modality   : "psf_convolution" | "cassi" | "lensless"
    H, W       : spatial dimensions for the benchmark
    N_bands    : spectral bands (>1 activates multispectral omega keys)
    noise_level: noise level in [0,1] for the omega_tier center
    mask_density: coded-aperture density (CASSI / lensless)
    disp_a1    : dispersion shift (pixels/band) for CASSI
    grid_size  : PSF FFT grid for Strehl estimation

    Returns
    -------
    dict with keys: d_spec, spec_type, six_tuple, protocol_fields, title,
                    psf_strehl, paraxial
    """
    if modality not in _MODALITIES:
        raise ValueError(f"modality must be one of {_MODALITIES}")

    # --- paraxial summary ---
    paraxial: dict = {}
    try:
        from pwm_core.optics.raytrace import paraxial_data
        paraxial = paraxial_data(sys)
    except Exception:
        pass

    # --- PSF / Strehl ---
    strehl = 1.0
    try:
        from pwm_core.optics.analysis import psf_mtf
        pm = psf_mtf(sys, field_idx=0, grid_size=grid_size)
        if pm.get("status") == "ok":
            strehl = float(pm.get("strehl", 1.0))
    except Exception:
        pass

    # d_spec: harder problem → higher d_spec.
    # Perfect system (Strehl=1): d_spec=0.3 (still non-trivial deconvolution).
    # Degraded system (Strehl→0): d_spec→0.95.
    d_spec = round(min(0.95, 0.3 + 0.65 * (1.0 - max(0.0, min(1.0, strehl)))), 3)

    title = f"{sys.title or 'Optical System'} — {modality} digital twin"

    if modality == "cassi":
        spec = _cassi_spec(H, W, N_bands, noise_level, mask_density, disp_a1, paraxial)
    elif modality == "lensless":
        spec = _lensless_spec(H, W, noise_level, mask_density, paraxial)
    else:
        spec = _psf_convolution_spec(H, W, N_bands, noise_level, paraxial)

    return {
        "d_spec": d_spec,
        "spec_type": modality,
        "title": title,
        "psf_strehl": round(strehl, 4),
        "paraxial": paraxial,
        **spec,
    }


# ---------------------------------------------------------------------------
# Per-modality builders
# ---------------------------------------------------------------------------

def _psf_convolution_spec(H: int, W: int, N_bands: int, noise_level: float,
                           paraxial: dict) -> dict:
    omega: dict = {
        "H": [64, max(H * 4, 2048)],
        "W": [64, max(W * 4, 2048)],
        "noise_level": [0.001, 0.1],
        "psf_radius_px": [0.5, 20.0],
    }
    if N_bands > 1:
        omega["N_bands"] = [3, max(N_bands * 4, 64)]

    E = {
        "forward": "y(x,y) = (h * f)(x,y) + n(x,y)",
        "operator": "psf_convolution",
        "primitive_chain": "L.conv2d -> int.spatial",
        "inverse": "recover f in R^{H x W} from noisy observation y = h*f + n",
    }
    if N_bands > 1:
        E["forward"] = "y(x,y,lambda) = (h_lambda * f)(x,y,lambda) + n(x,y,lambda)"
        E["inverse"] = f"recover f in R^{{H x W x {N_bands}}} from noisy convolved observation"

    B = {
        "nonnegativity": True,
        "psf_normalised": True,
    }
    O = ["PSNR", "SSIM", "residual_norm", "convergence_curve"]
    if N_bands > 1:
        O.append("SAM_deg")

    efl = paraxial.get("efl_mm", 50.0) or 50.0
    epsilon_fn = f"28.0 + 1.5 * log2(H / 64)"

    return {
        "six_tuple": {
            "omega": omega,
            "E": E,
            "B": B,
            "I": {"strategy": "zero_init"},
            "O": O,
            "epsilon_fn": epsilon_fn,
        },
        "protocol_fields": {
            "input_format": {
                "measurement": f"float32(H, W)",
                "psf": "float32(kH, kW) — normalised, provided as prior",
            },
            "output_format": {
                "reconstruction": f"float32(H, W)",
            },
            "efl_mm": efl,
            "modality": "psf_convolution",
        },
    }


def _cassi_spec(H: int, W: int, N_bands: int, noise_level: float,
                mask_density: float, disp_a1: float, paraxial: dict) -> dict:
    omega: dict = {
        "H": [64, max(H * 4, 2048)],
        "W": [64, max(W * 4, 2048)],
        "N_bands": [8, max(N_bands * 4, 128)],
        "mask_density": [0.3, 0.7],
        "noise_level": [0.001, 0.1],
        "disp_a1_error": [0.0, 0.05],
        "disp_alpha_error": [0.0, 0.3],
        "mask_dx": [0.0, 1.0],
        "mask_dy": [0.0, 1.0],
        "mask_theta": [0.0, 0.15],
    }

    E = {
        "forward": "y(x,y) = sum_lambda C(x,y) * f(x, y + a1*lambda, lambda) + n(x,y)",
        "operator": "cassi_forward",
        "primitive_chain": "L.broadcast.spectral -> L.diag.binary -> L.shear.spectral -> int.spectral",
        "inverse": f"recover f in R^{{H x W x N_bands}} from a single 2D snapshot y",
        "disp_a1_nominal": disp_a1,
    }

    B = {
        "nonnegativity": True,
        "spectral_smoothness": True,
        "mask_binary": "C(x,y) in {0,1}",
    }
    O = ["per_channel_PSNR", "SSIM", "SAM_deg", "residual_norm", "convergence_curve"]
    epsilon_fn = f"25.0 + 2.0 * log2(H / 64) + 1.5 * log10(photon_count / 50)"

    return {
        "six_tuple": {
            "omega": omega,
            "E": E,
            "B": B,
            "I": {"strategy": "zero_init"},
            "O": O,
            "epsilon_fn": epsilon_fn,
        },
        "protocol_fields": {
            "input_format": {
                "measurement": f"float32(H, W + a1*N_bands)",
                "mask": "bool(H, W)",
            },
            "output_format": {
                "reconstruction": f"float32(H, W, N_bands)",
                "per_band_metrics": "dict",
            },
            "disp_a1_nominal": disp_a1,
            "mask_density_nominal": mask_density,
            "modality": "cassi",
        },
    }


def _lensless_spec(H: int, W: int, noise_level: float, mask_density: float,
                    paraxial: dict) -> dict:
    omega: dict = {
        "H": [64, max(H * 4, 2048)],
        "W": [64, max(W * 4, 2048)],
        "noise_level": [0.001, 0.1],
        "mask_density": [0.2, 0.8],
        "propagation_distance_m": [0.001, 1.0],
    }

    E = {
        "forward": "y(u,v) = |F{A(x,y) * exp(i*phi(x,y)) * f(x,y)}|^2 + n(u,v)",
        "operator": "lensless_diffraction",
        "primitive_chain": "L.modulate.phase -> L.propagate.diffraction -> int.intensity",
        "inverse": "recover f in R^{H x W} from intensity measurement y",
    }

    B = {
        "nonnegativity": True,
        "real_valued_object": True,
    }
    O = ["PSNR", "SSIM", "residual_norm"]
    epsilon_fn = "22.0 + 2.0 * log2(H / 64)"

    return {
        "six_tuple": {
            "omega": omega,
            "E": E,
            "B": B,
            "I": {"strategy": "zero_init"},
            "O": O,
            "epsilon_fn": epsilon_fn,
        },
        "protocol_fields": {
            "input_format": {
                "measurement": "float32(H, W) — intensity at sensor",
                "mask": "complex64(H, W) — coded aperture / phase mask",
            },
            "output_format": {
                "reconstruction": "float32(H, W)",
            },
            "mask_density_nominal": mask_density,
            "modality": "lensless",
        },
    }
