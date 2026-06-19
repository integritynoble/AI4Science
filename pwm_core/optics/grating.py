"""grating.py — Scalar diffraction grating efficiency (PCGrate replacement)."""
from __future__ import annotations
import math
import numpy as np
from typing import Union


def grating_efficiency(
    groove_density_lpmm: float,
    wavelengths_nm: Union[list, np.ndarray],
    blaze_angle_deg: float = 0.0,
    order: int = 1,
    polarization: str = "avg",
    n_grooves: int = 1000,
    incident_angle_deg: float = 0.0,
) -> dict:
    """Scalar diffraction grating efficiency via blazed grating formula.

    Physics: grating equation sin(α) + sin(β) = m*λ/d
    Efficiency envelope: sinc²((β - β_B) / Δβ) normalized
    Blaze wavelength: λ_B = (2*d/m) * sin(blaze_angle_deg) * cos((α - blaze_angle_deg))
    Angular dispersion: dβ/dλ = m / (d * cos(β))
    Resolving power: R = m * n_grooves

    Returns dict with status, wavelengths_nm, efficiency, peak_wavelength_nm,
    resolving_power, free_spectral_range_nm, angular_dispersion_deg_per_nm.
    """
    wls = np.asarray(wavelengths_nm, dtype=float)
    d_mm = 1.0 / groove_density_lpmm          # grating period in mm
    d_nm = d_mm * 1e6                          # grating period in nm

    alpha_rad = math.radians(incident_angle_deg)
    blaze_rad = math.radians(blaze_angle_deg)

    efficiencies = []
    dispersions = []

    for lam in wls:
        sin_beta = order * lam / d_nm - math.sin(alpha_rad)
        # TIR check
        if abs(sin_beta) >= 1.0:
            efficiencies.append(0.0)
            dispersions.append(0.0)
            continue
        beta_rad = math.asin(sin_beta)

        # Blaze wavelength for this geometry:
        # At blaze condition beta = blaze_angle when alpha = incident_angle
        # Peak efficiency when beta == blaze_angle (Littrow: alpha==blaze, beta==blaze)
        # Use the standard sinc² envelope: argument = (beta - blaze_rad) / (half-period in beta)
        # The width parameter: Δβ ≈ lambda / (d * cos(beta)) (1 groove width)
        cos_beta = math.cos(beta_rad)
        if cos_beta < 1e-10:
            efficiencies.append(0.0)
            dispersions.append(0.0)
            continue

        # sinc² envelope argument
        # Properly: eff = sinc²(d/lambda * (sin(beta) - sin(blaze_rad)))
        # but normalized so peak = 1
        arg = (d_nm / lam) * (math.sin(beta_rad) - math.sin(blaze_rad))
        sinc_val = np.sinc(arg)  # numpy sinc = sin(pi*x)/(pi*x)
        eff = sinc_val ** 2

        # For TE/TM polarization (simplified: use flat polarization factor)
        if polarization == "TE":
            eff *= 1.0
        elif polarization == "TM":
            eff *= 0.9  # simplified reduction
        else:  # avg
            eff *= 0.95

        efficiencies.append(float(np.clip(eff, 0, 1)))

        # Angular dispersion dβ/dλ in deg/nm
        disp_rad_per_nm = order / (d_nm * cos_beta)
        dispersions.append(math.degrees(disp_rad_per_nm))

    eff_arr = np.array(efficiencies)
    disp_arr = np.array(dispersions)

    # Peak wavelength
    if len(eff_arr) > 0 and eff_arr.max() > 0:
        peak_nm = float(wls[eff_arr.argmax()])
    else:
        peak_nm = float("nan")

    # Blaze wavelength (analytic): lambda_B = (2*d/m) * sin(blaze_angle) for Littrow
    lambda_blaze = (2.0 * d_nm / abs(order)) * math.sin(blaze_rad) if blaze_rad > 0 else d_nm / abs(order)

    # Resolving power R = m * N
    resolving_power = abs(order) * n_grooves

    # Free spectral range: FSR = lambda / m (nm)
    if len(wls) > 0:
        center_lam = float(wls[len(wls) // 2])
        fsr_nm = center_lam / abs(order) if order != 0 else float("inf")
    else:
        fsr_nm = float("nan")

    return {
        "status": "ok",
        "wavelengths_nm": wls.tolist(),
        "efficiency": eff_arr.tolist(),
        "peak_wavelength_nm": peak_nm,
        "blaze_wavelength_nm": lambda_blaze,
        "resolving_power": resolving_power,
        "free_spectral_range_nm": fsr_nm,
        "angular_dispersion_deg_per_nm": disp_arr.tolist(),
        "order": order,
        "groove_density_lpmm": groove_density_lpmm,
    }


def grating_crosstalk(
    groove_density_lpmm: float,
    wavelengths_nm: Union[list, np.ndarray],
    order: int = 1,
    channel_bw_nm: float = 1.0,
) -> dict:
    """Order crosstalk between adjacent spectral channels.

    Computes the fraction of signal from adjacent orders (m±1) that falls
    within the channel bandwidth at each wavelength.
    Returns: {status, wavelengths_nm, crosstalk_fraction, adjacent_order_wavelengths_nm}
    """
    wls = np.asarray(wavelengths_nm, dtype=float)
    d_nm = 1e6 / groove_density_lpmm  # period in nm

    crosstalk = []
    adj_wls = []

    for lam in wls:
        # Wavelength of adjacent order (m+1) that would land at same angle as lam in order m
        # sin(alpha)+sin(beta) = m*lam/d = (m+1)*lam_adj/d
        # => lam_adj = m*lam/(m+1)
        adj_m_plus = order * lam / (order + 1) if (order + 1) != 0 else float("nan")
        adj_m_minus = order * lam / (order - 1) if (order - 1) != 0 else float("nan")

        # Crosstalk: fraction of adjacent order power within channel_bw_nm
        # Use sinc² model: power in bandwidth ~ integral of sinc²
        # Simplified: crosstalk ≈ (channel_bw_nm / FSR) using sinc integral estimate
        fsr = lam / abs(order)
        xt = min(1.0, (channel_bw_nm / fsr) ** 2 * 0.1)  # empirical factor
        crosstalk.append(float(xt))
        adj_wls.append(float(adj_m_plus) if not math.isnan(adj_m_plus) else None)

    return {
        "status": "ok",
        "wavelengths_nm": wls.tolist(),
        "crosstalk_fraction": crosstalk,
        "adjacent_order_wavelengths_nm": adj_wls,
        "channel_bw_nm": channel_bw_nm,
        "order": order,
    }
