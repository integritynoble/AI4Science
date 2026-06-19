"""thinfilm.py — Transfer Matrix Method for multi-layer thin films (Essential Macleod replacement)."""
from __future__ import annotations
import numpy as np
from typing import Union


def tmm(
    layers: list,
    substrate_n: float,
    incident_n: float,
    wavelengths_nm: Union[list, np.ndarray],
    angle_deg: float = 0.0,
    polarization: str = "avg",
) -> dict:
    """Multi-layer thin-film stack via Transfer Matrix Method.

    layers: list of {"n": float|list, "k": float|list, "thickness_nm": float}
    n and k can be floats (dispersionless) or lists matching wavelengths_nm.

    Returns: {status, wavelengths_nm, T, R, A, T_dB, R_dB}
    """
    wls = np.asarray(wavelengths_nm, dtype=float)
    N = len(wls)
    angle_rad = np.radians(angle_deg)

    T_arr = np.zeros(N)
    R_arr = np.zeros(N)
    A_arr = np.zeros(N)

    for i, lam in enumerate(wls):
        # Build complex refractive index arrays
        n_inc = complex(incident_n)
        n_sub = complex(substrate_n)

        # cos(theta) in incident medium (Snell)
        cos_i = np.cos(angle_rad)

        # Transfer matrix product for all layers
        M = np.eye(2, dtype=complex)

        for layer in layers:
            n_r = layer["n"]
            k_r = layer.get("k", 0.0)
            d = layer["thickness_nm"]

            # Dispersion: if n/k are lists, interpolate
            if isinstance(n_r, (list, np.ndarray)):
                n_r = float(np.interp(lam, wls, n_r))
            if isinstance(k_r, (list, np.ndarray)):
                k_r = float(np.interp(lam, wls, k_r))

            n_complex = complex(n_r, -k_r)  # convention: n - ik (absorption)

            # Snell's law: n_inc * sin(theta_i) = n_layer * sin(theta_l)
            sin_t = n_inc * np.sin(angle_rad) / n_complex
            cos_t = np.sqrt(1.0 - sin_t ** 2 + 0j)

            # Phase thickness
            delta = 2 * np.pi * n_complex * d * cos_t / lam

            # Admittance
            if polarization == "TE" or polarization == "avg":
                eta = n_complex * cos_t
            else:
                eta = n_complex / cos_t

            # Layer transfer matrix
            Ml = np.array([
                [np.cos(delta),          -1j * np.sin(delta) / eta],
                [-1j * eta * np.sin(delta),  np.cos(delta)],
            ], dtype=complex)
            M = M @ Ml

        # Admittance of substrate and incident
        if polarization == "TM":
            eta_i = n_inc / cos_i
            sin_sub = n_inc * np.sin(angle_rad) / n_sub
            cos_sub = np.sqrt(1 - sin_sub**2 + 0j)
            eta_s = n_sub / cos_sub
        else:
            eta_i = n_inc * cos_i
            sin_sub = n_inc * np.sin(angle_rad) / n_sub
            cos_sub = np.sqrt(1 - sin_sub**2 + 0j)
            eta_s = n_sub * cos_sub

        # Reflection and transmission coefficients
        # r = (M[0,0] + M[0,1]*eta_s)*eta_i - (M[1,0] + M[1,1]*eta_s)
        #     ----------------------------------------------------------------
        #     (M[0,0] + M[0,1]*eta_s)*eta_i + (M[1,0] + M[1,1]*eta_s)
        A_top = (M[0, 0] + M[0, 1] * eta_s) * eta_i - (M[1, 0] + M[1, 1] * eta_s)
        A_bot = (M[0, 0] + M[0, 1] * eta_s) * eta_i + (M[1, 0] + M[1, 1] * eta_s)

        if abs(A_bot) < 1e-30:
            R_arr[i] = 1.0
            T_arr[i] = 0.0
            A_arr[i] = 0.0
            continue

        r = A_top / A_bot
        t = 2 * eta_i / A_bot

        R_s = float(abs(r) ** 2)

        # T = (eta_s.real / eta_i.real) * |t|^2
        T_s = float(np.real(eta_s) / np.real(eta_i)) * float(abs(t) ** 2)
        T_s = max(0.0, min(1.0, T_s))
        R_s = max(0.0, min(1.0, R_s))

        if polarization == "avg":
            # Average TE and TM by re-running with TM
            result_TM = tmm(layers, substrate_n, incident_n, [lam], angle_deg, "TM")
            R_TM = result_TM["R"][0]
            T_TM = result_TM["T"][0]
            R_arr[i] = (R_s + R_TM) / 2
            T_arr[i] = (T_s + T_TM) / 2
        else:
            R_arr[i] = R_s
            T_arr[i] = T_s

        A_arr[i] = max(0.0, 1.0 - R_arr[i] - T_arr[i])

    eps = 1e-12
    T_dB = 10 * np.log10(T_arr + eps)
    R_dB = 10 * np.log10(R_arr + eps)

    return {
        "status": "ok",
        "wavelengths_nm": wls.tolist(),
        "T": T_arr.tolist(),
        "R": R_arr.tolist(),
        "A": A_arr.tolist(),
        "T_dB": T_dB.tolist(),
        "R_dB": R_dB.tolist(),
    }


def design_bandpass(
    center_nm: float,
    bandwidth_nm: float,
    n_high: float = 2.35,
    n_low: float = 1.46,
    n_layers: int = 7,
) -> list:
    """Quarter-wave stack bandpass filter recipe.

    Returns list of layer dicts for use with tmm().
    Uses H(LH)^N L(HL)^N H symmetric stack for bandpass.
    """
    # Quarter-wave thickness at center wavelength
    t_high = center_nm / (4 * n_high)
    t_low = center_nm / (4 * n_low)

    layers = []
    # Symmetric quarter-wave stack: alternating H and L, starting with H
    for i in range(n_layers):
        if i % 2 == 0:
            layers.append({"n": n_high, "k": 0.0, "thickness_nm": t_high})
        else:
            layers.append({"n": n_low, "k": 0.0, "thickness_nm": t_low})

    return layers


def design_longpass(
    cutoff_nm: float,
    n_high: float = 2.35,
    n_low: float = 1.46,
    n_layers: int = 9,
) -> list:
    """Edge filter (longpass) recipe.

    Uses a chirped quarter-wave stack where period thickness is scaled to
    shift the stopband edge to cutoff_nm.
    """
    t_high = cutoff_nm / (4 * n_high)
    t_low = cutoff_nm / (4 * n_low)

    layers = []
    for i in range(n_layers):
        # Slight chirp factor to broaden transition
        chirp = 1.0 + 0.02 * (i - n_layers // 2)
        if i % 2 == 0:
            layers.append({"n": n_high, "k": 0.0, "thickness_nm": t_high * chirp})
        else:
            layers.append({"n": n_low, "k": 0.0, "thickness_nm": t_low * chirp})

    return layers
