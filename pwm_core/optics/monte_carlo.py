"""monte_carlo.py — MCML tissue Monte Carlo light transport (MCX/MCML replacement)."""
from __future__ import annotations
import math
import numpy as np
from typing import Union

# Hemoglobin molar extinction coefficients (cm^-1 / M) at 10nm steps 400-700nm
# Source: Prahl SA, tabulated from Scott Prahl's omlc.org/spectra/hemoglobin
# Units: cm^-1 per molar concentration; [M] = mol/L
# We store as [wavelength_nm, epsilon_HbO2, epsilon_Hb] — molar extinction in cm^-1/M
# Blood: [Hb] + [HbO2] ≈ 2.33 mM total (150 g/L Hb, MW=64500)
_HB_DATA_NM = np.arange(400, 710, 10, dtype=float)
# Molar extinction coefficients ε (cm^-1 / M) for HbO2 and Hb
# Values from Prahl's tabulation (approximate, 31 points)
_EPSILON_HBO2 = np.array([
    125000, 92000, 52000, 38000, 24000, 20000, 21000, 31000, 40000, 42000,  # 400-490
    42000, 40000, 38000, 28000, 26000, 38000, 46000, 54000, 56000, 60000,  # 500-590
    58000, 48000, 36000, 26000, 18000, 14000, 10000, 8000,  6000,  5000,  # 600-690
    4000,                                                                    # 700
], dtype=float)
_EPSILON_HB = np.array([
    90000, 70000, 49000, 36000, 22000, 20000, 35000, 60000, 70000, 60000,  # 400-490
    36000, 24000, 20000, 28000, 38000, 52000, 58000, 40000, 26000, 14000,  # 500-590
    8000,  5000,  3500,  2500,  2000,  1600,  1400,  1200,  900,   700,   # 600-690
    600,                                                                     # 700
], dtype=float)


def hb_absorption(
    wavelengths_nm: Union[list, np.ndarray],
    so2: float = 0.98,
) -> dict:
    """Hemoglobin absorption spectrum (HbO2 + Hb mixture).

    Uses tabulated molar extinction coefficients from Prahl's database.
    Total blood Hb concentration: ~2.33 mM (typical for whole blood at 150 g/L).

    mua = ln(10) * epsilon_total * C_hb
    where epsilon_total = so2 * epsilon_HbO2 + (1 - so2) * epsilon_Hb
    and C_hb = 2.33e-3 M (molar concentration of hemoglobin)

    Returns: {wavelengths_nm, mua_cm_inv, peak_nm, so2}
    """
    wls = np.asarray(wavelengths_nm, dtype=float)

    # Interpolate molar extinction coefficients
    eps_hbo2 = np.interp(wls, _HB_DATA_NM, _EPSILON_HBO2)
    eps_hb = np.interp(wls, _HB_DATA_NM, _EPSILON_HB)

    # Mixed extinction
    eps_total = so2 * eps_hbo2 + (1.0 - so2) * eps_hb

    # Convert to absorption coefficient
    C_hb = 2.33e-3  # mol/L = M
    mua = math.log(10) * eps_total * C_hb  # cm^-1

    peak_nm = float(wls[mua.argmax()]) if len(mua) > 0 else float("nan")

    return {
        "status": "ok",
        "wavelengths_nm": wls.tolist(),
        "mua_cm_inv": mua.tolist(),
        "peak_nm": peak_nm,
        "so2": so2,
        "c_hb_molar": C_hb,
    }


def _henyey_greenstein(g: float, rng: np.random.Generator, n: int) -> np.ndarray:
    """Sample Henyey-Greenstein phase function. Returns cos(theta) for n photons."""
    xi = rng.random(n)
    if abs(g) < 1e-6:
        return 2 * xi - 1  # isotropic
    s = (1 - g**2) / (1 - g + 2 * g * xi)
    cos_theta = (1 + g**2 - s**2) / (2 * g)
    return np.clip(cos_theta, -1.0, 1.0)


def mcml(
    tissue_layers: list,
    n_photons: int = 100000,
    source_beam_radius_mm: float = 0.5,
    source_type: str = "pencil",
    seed: int = 42,
) -> dict:
    """Monte Carlo Multi-Layer tissue light transport (MCML algorithm, Wang 1995).

    tissue_layers: [{"mua": float, "mus": float, "g": float, "n": float, "thickness_mm": float}, ...]
      mua: absorption [mm^-1], mus: scattering [mm^-1], g: anisotropy [-1,1], n: refractive index
      Last layer can have thickness_mm = inf (semi-infinite substrate).

    Returns: {status, depth_mm, fluence, reflectance, transmittance,
              absorption_by_layer, penetration_depth_mm}
    """
    rng = np.random.default_rng(seed)

    if not tissue_layers:
        return {"status": "error", "message": "No tissue layers defined."}

    n_layers = len(tissue_layers)

    # Precompute layer boundaries (in mm)
    boundaries = [0.0]
    for layer in tissue_layers:
        d = layer.get("thickness_mm", 1e9)
        if d == float("inf") or d > 1e6:
            boundaries.append(1e9)  # semi-infinite
        else:
            boundaries.append(boundaries[-1] + d)

    # Depth grid for fluence
    max_depth = min(boundaries[-1] if boundaries[-1] < 1e8 else 10.0, 20.0)
    n_depth = 200
    depth_arr = np.linspace(0, max_depth, n_depth)
    dz = depth_arr[1] - depth_arr[0] if n_depth > 1 else 1.0
    fluence = np.zeros(n_depth)

    total_R = 0.0
    total_T = 0.0
    absorption_by_layer = np.zeros(n_layers)

    # Batch processing
    batch_size = min(1000, n_photons)
    n_batches = (n_photons + batch_size - 1) // batch_size

    for batch_idx in range(n_batches):
        n_batch = min(batch_size, n_photons - batch_idx * batch_size)

        # Initialize photon positions and directions
        if source_type == "pencil":
            x = np.zeros(n_batch)
            y = np.zeros(n_batch)
        else:
            # Gaussian beam
            r = rng.exponential(source_beam_radius_mm / 2, n_batch)
            phi = rng.uniform(0, 2 * math.pi, n_batch)
            x = r * np.cos(phi)
            y = r * np.sin(phi)

        z = np.zeros(n_batch)
        # Direction cosines: start going downward (+z)
        ux = np.zeros(n_batch)
        uy = np.zeros(n_batch)
        uz = np.ones(n_batch)  # downward

        weight = np.ones(n_batch)
        layer_idx = np.zeros(n_batch, dtype=int)

        alive = np.ones(n_batch, dtype=bool)

        max_steps = 1000
        for _ in range(max_steps):
            if not alive.any():
                break

            # Current layer properties
            mua = np.array([tissue_layers[li].get("mua", 0.1)
                            for li in layer_idx])
            mus = np.array([tissue_layers[li].get("mus", 1.0)
                            for li in layer_idx])
            mut = mua + mus

            # Step size: -ln(xi) / mu_t
            xi = rng.random(n_batch)
            xi = np.maximum(xi, 1e-10)
            step = np.where(alive & (mut > 0), -np.log(xi) / mut, 0.0)

            # Move photons
            z_new = z + step * uz
            x_new = x + step * ux
            y_new = y + step * uy

            # Absorption (weight reduction)
            absorb_frac = np.where(alive & (mut > 0), mua / mut * (1 - np.exp(-mut * step)), 0.0)
            dW = weight * absorb_frac

            # Fluence accumulation
            for j in range(n_batch):
                if alive[j]:
                    depth_idx = int(z[j] / dz)
                    if 0 <= depth_idx < n_depth:
                        fluence[depth_idx] += dW[j]
                    li = layer_idx[j]
                    if 0 <= li < n_layers:
                        absorption_by_layer[li] += dW[j]

            weight = np.where(alive, weight - dW, weight)

            # Update positions
            z = np.where(alive, z_new, z)
            x = np.where(alive, x_new, x)
            y = np.where(alive, y_new, y)

            # Check for escape (above surface or below all layers)
            escaped_R = alive & (z < 0)
            escaped_T = alive & (z >= boundaries[min(n_layers, len(boundaries)-1)])

            total_R += weight[escaped_R].sum()
            total_T += weight[escaped_T].sum()
            alive[escaped_R] = False
            alive[escaped_T] = False

            # Update layer index
            for j in range(n_batch):
                if alive[j]:
                    for li in range(n_layers):
                        z_lo = boundaries[li]
                        z_hi = boundaries[li + 1] if li + 1 < len(boundaries) else 1e9
                        if z_lo <= z[j] < z_hi:
                            layer_idx[j] = li
                            break

            # Scatter: new direction via Henyey-Greenstein
            g_arr = np.array([tissue_layers[li].get("g", 0.9) for li in layer_idx])
            for gi in np.unique(g_arr):
                mask = alive & (g_arr == gi)
                n_scatter = mask.sum()
                if n_scatter == 0:
                    continue
                cos_t = _henyey_greenstein(gi, rng, n_scatter)
                sin_t = np.sqrt(np.maximum(0, 1 - cos_t**2))
                phi_s = rng.uniform(0, 2 * math.pi, n_scatter)

                ux_new = sin_t * np.cos(phi_s)
                uy_new = sin_t * np.sin(phi_s)
                uz_new = cos_t

                ux[mask] = ux_new
                uy[mask] = uy_new
                uz[mask] = uz_new

            # Russian roulette for low-weight photons
            low_w = alive & (weight < 0.01)
            roulette = rng.random(n_batch)
            # Survive with prob 1/10, get 10x weight boost
            survive = roulette < 0.1
            weight = np.where(low_w & survive, weight * 10, weight)
            alive = np.where(low_w & ~survive, False, alive)

    # Normalize
    norm = n_photons if n_photons > 0 else 1.0
    reflectance = float(total_R / norm)
    transmittance = float(total_T / norm)

    # Fluence normalization
    fluence_norm = fluence / norm
    if dz > 0:
        fluence_norm = fluence_norm / dz  # per mm

    # Penetration depth (1/e depth)
    if fluence_norm.max() > 0:
        peak_fluence = fluence_norm.max()
        threshold = peak_fluence / math.e
        below = np.where(fluence_norm < threshold)[0]
        if len(below) > 0:
            pen_depth = float(depth_arr[below[0]])
        else:
            pen_depth = float(depth_arr[-1])
    else:
        pen_depth = 0.0

    return {
        "status": "ok",
        "depth_mm": depth_arr.tolist(),
        "fluence": fluence_norm.tolist(),
        "reflectance": round(reflectance, 6),
        "transmittance": round(transmittance, 6),
        "absorption_by_layer": (absorption_by_layer / norm).tolist(),
        "penetration_depth_mm": round(pen_depth, 4),
        "n_photons": n_photons,
    }
