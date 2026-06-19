"""stray_light.py — Monte Carlo non-sequential stray light (LightTools replacement)."""
from __future__ import annotations
import math
import numpy as np
from typing import Optional


def stray_light_analysis(
    prescription_dict: dict,
    n_rays: int = 10000,
    bsdf_roughness_nm: float = 2.0,
    baffle_transmission: float = 0.0,
    seed: int = 42,
) -> dict:
    """Monte Carlo stray light analysis (simplified 2D geometry).

    Models each surface as Lambertian scatter + specular component.
    Harvey-Shack BSDF: BSDF(theta_s) = b0 / (b0 + tan²(theta_s))^(b/2)
    TIS ≈ (4*pi*sigma/lambda)^2

    prescription_dict: the dict from save_system (loaded via json).
    Returns: {status, ghost_fraction, veiling_glare_index, scatter_map_shape,
              scatter_map, recommendations}
    """
    rng = np.random.default_rng(seed)

    # Extract basic system info
    surfaces = prescription_dict.get("surfaces", [])
    wavelengths = prescription_dict.get("wavelengths", [{"value": 0.55}])
    lam_um = float(wavelengths[0].get("value", 0.55))  # primary wavelength in microns
    lam_nm = lam_um * 1000.0

    n_surfaces = len(surfaces)
    if n_surfaces < 2:
        n_surfaces = 4  # default minimal system

    # Harvey-Shack BSDF parameters from roughness
    sigma_nm = bsdf_roughness_nm
    # Total integrated scatter: TIS = (4*pi*sigma/lambda)^2 (fraction of power scattered)
    tis = min(1.0, (4 * math.pi * sigma_nm / lam_nm) ** 2)
    b0 = tis  # Harvey-Shack b0 parameter (scatter level)
    b_exp = 1.5  # Harvey-Shack exponent

    # Monte Carlo ray tracing (2D simplified)
    detector_size = 1.0  # normalized
    scatter_map = np.zeros((64, 64))
    ghost_hits = 0
    direct_hits = 0

    # Launch rays in batches
    batch = min(n_rays, 1000)
    n_batches = n_rays // batch

    for _ in range(n_batches):
        # Ray positions and directions (2D)
        x = rng.uniform(-0.5, 0.5, batch)
        theta = rng.uniform(-0.1, 0.1, batch)  # small angle near-axis

        is_ghost = np.zeros(batch, dtype=bool)
        weight = np.ones(batch)

        for surf_idx in range(n_surfaces):
            # Propagate to next surface (simplified: flat surfaces at z positions)
            z_surf = (surf_idx + 1) * 10.0  # 10mm spacing
            x = x + theta * 10.0

            # Specular reflection at each surface
            # Scatter: sample from Harvey-Shack BSDF
            scatter_prob = tis
            scattered = rng.random(batch) < scatter_prob

            if scattered.any():
                # Lambertian scatter direction
                theta_scatter = rng.normal(0, math.radians(2.0), batch)
                theta = np.where(scattered, theta_scatter, theta)
                is_ghost = is_ghost | scattered
                weight = np.where(scattered, weight * b0, weight)

            # Baffle absorption
            if baffle_transmission < 1.0:
                outside = np.abs(x) > (0.5 * (surf_idx + 1))
                weight = np.where(outside & is_ghost,
                                  weight * baffle_transmission, weight)

        # Final detector plane
        on_detector = np.abs(x) < detector_size / 2
        ghost_on_det = is_ghost & on_detector
        direct_on_det = (~is_ghost) & on_detector

        ghost_hits += int(ghost_on_det.sum())
        direct_hits += int(direct_on_det.sum())

        # Scatter map (2D)
        for xi in x[on_detector]:
            ix = int((xi + 0.5) * 63)
            iy = rng.integers(0, 64)
            if 0 <= ix < 64:
                scatter_map[iy, ix] += 1

    total = ghost_hits + direct_hits
    ghost_fraction = ghost_hits / n_rays if n_rays > 0 else 0.0

    # Veiling Glare Index: stray / (signal + stray)
    if direct_hits > 0:
        vgi = ghost_hits / (ghost_hits + direct_hits)
    else:
        vgi = 0.0

    # Recommendations
    recs = []
    if ghost_fraction > 0.01:
        recs.append(f"Ghost fraction {ghost_fraction:.3f} > 1% — add baffles or AR coatings.")
    if vgi > 0.05:
        recs.append(f"VGI {vgi:.3f} > 5% — consider light traps on internal walls.")
    if bsdf_roughness_nm > 5.0:
        recs.append(f"Surface roughness {bsdf_roughness_nm:.1f} nm is high — superpolish or coat.")
    if not recs:
        recs.append("Stray light within acceptable limits.")

    return {
        "status": "ok",
        "ghost_fraction": round(ghost_fraction, 6),
        "veiling_glare_index": round(vgi, 6),
        "tis_per_surface": round(tis, 6),
        "scatter_map_shape": list(scatter_map.shape),
        "scatter_map": scatter_map.flatten().tolist(),
        "n_rays": n_rays,
        "recommendations": recs,
    }


def baffle_optimization(
    f_number: float,
    field_angle_deg: float,
    n_baffles: int = 3,
) -> dict:
    """Return optimal baffle positions and knife-edge angles.

    Uses the standard vane-baffle design formula:
    - Baffle positions spaced to prevent direct line-of-sight from detector to entrance aperture.
    - Knife-edge angle = half-angle of cone subtended by detector at each baffle position.

    Returns: {status, baffle_positions_mm, knife_edge_angles_deg, obscuration_fractions,
              shadow_efficiency}
    """
    # Telescope geometry from f/# and field angle
    # Assume 100mm aperture diameter for normalization
    d_aperture = 100.0  # mm
    focal_length = f_number * d_aperture
    half_field = math.radians(field_angle_deg)

    # Tube length for baffle system
    tube_length = focal_length * 1.2  # 20% beyond focal plane

    positions = []
    ke_angles = []
    obscurations = []

    for i in range(n_baffles):
        # Position: evenly spaced but avoiding shadows
        z = tube_length * (i + 1) / (n_baffles + 1)
        positions.append(round(z, 2))

        # Baffle inner radius at position z
        # Must allow field rays: r_field = z * tan(half_field)
        r_field = z * math.tan(half_field)

        # Baffle must block direct line from detector edge to aperture edge
        # r_baffle ≈ d_aperture/2 * (1 - z/tube_length) + r_field
        r_baffle_outer = d_aperture / 2
        r_baffle_inner = r_field + 2.0  # 2mm clearance

        # Knife-edge angle: angle of the knife edge tip w.r.t. optical axis
        ke_angle = math.degrees(math.atan2(r_baffle_inner, z))
        ke_angles.append(round(ke_angle, 3))

        # Obscuration fraction
        obs = (r_baffle_inner / r_baffle_outer) ** 2
        obscurations.append(round(min(obs, 1.0), 4))

    # Shadow efficiency: fraction of stray light paths blocked
    shadow_eff = 1.0 - (1.0 / n_baffles) ** n_baffles

    return {
        "status": "ok",
        "f_number": f_number,
        "field_angle_deg": field_angle_deg,
        "n_baffles": n_baffles,
        "baffle_positions_mm": positions,
        "knife_edge_angles_deg": ke_angles,
        "obscuration_fractions": obscurations,
        "shadow_efficiency": round(shadow_eff, 4),
        "focal_length_mm": round(focal_length, 2),
    }
