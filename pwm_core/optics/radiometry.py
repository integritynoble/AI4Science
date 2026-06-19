"""radiometry.py — Detector radiometry and SNR budget (MATLAB radiometry replacement)."""
from __future__ import annotations
import math


def snr_budget(
    signal_photons_per_pixel: float,
    qe: float = 0.7,
    read_noise_e: float = 3.0,
    dark_current_e_per_s: float = 0.01,
    exposure_s: float = 1.0,
    n_accumulations: int = 1,
    bit_depth: int = 16,
    full_well_e: float = 30000.0,
) -> dict:
    """Detector radiometry + SNR budget.

    Signal chain:
      signal_e = signal_photons_per_pixel * qe * n_accumulations
      shot_noise = sqrt(signal_e)
      dark_noise = sqrt(dark_current_e_per_s * exposure_s * n_accumulations)
      total_noise = sqrt(shot_noise^2 + read_noise^2 + dark_noise^2)
      SNR = signal_e / total_noise

    Dynamic range = full_well_e / read_noise_e
    NEP = read_noise_e / qe  (noise-equivalent photons at read-noise floor)

    Returns: {status, signal_e, shot_noise_e, read_noise_e, dark_noise_e,
              total_noise_e, snr_db, dynamic_range_db, nep_photons,
              saturation_fraction, recommendations}
    """
    # Signal electrons
    signal_e = signal_photons_per_pixel * qe * n_accumulations

    # Noise components
    shot_noise = math.sqrt(max(signal_e, 0.0))
    dark_e = dark_current_e_per_s * exposure_s * n_accumulations
    dark_noise = math.sqrt(dark_e)
    # Read noise adds in quadrature for each accumulation
    total_read = read_noise_e * math.sqrt(n_accumulations)

    total_noise = math.sqrt(shot_noise**2 + total_read**2 + dark_noise**2)

    # SNR
    if total_noise > 0:
        snr_linear = signal_e / total_noise
        snr_db = 20 * math.log10(max(snr_linear, 1e-12))
    else:
        snr_linear = float("inf")
        snr_db = float("inf")

    # Dynamic range
    dr_db = 20 * math.log10(full_well_e / max(total_read, 1e-6))

    # NEP (noise equivalent power in photons)
    nep_photons = total_read / qe if qe > 0 else float("inf")

    # Saturation check
    saturation_fraction = min(1.0, signal_e / max(full_well_e, 1.0))

    # Digitization check
    adc_steps = 2**bit_depth
    adc_electrons_per_dn = full_well_e / adc_steps
    quantization_noise = adc_electrons_per_dn / math.sqrt(12)

    # Recommendations
    recs = []
    if saturation_fraction > 0.9:
        recs.append(f"Detector near saturation ({saturation_fraction*100:.1f}%) — reduce exposure or use ND filter.")
    if snr_linear < 5:
        recs.append(f"SNR = {snr_linear:.1f} is low — increase exposure, QE, or bin pixels.")
    if dark_noise > total_read:
        recs.append("Dark current dominates read noise — consider cooling detector.")
    if qe < 0.5:
        recs.append(f"QE = {qe:.2f} is low — consider back-illuminated sensor.")
    if quantization_noise > total_read * 0.5:
        recs.append(f"Quantization noise significant at {bit_depth}-bit depth — consider higher bit depth.")
    if not recs:
        recs.append("Detector operating in optimal regime.")

    return {
        "status": "ok",
        "signal_e": round(signal_e, 3),
        "shot_noise_e": round(shot_noise, 3),
        "read_noise_e": round(total_read, 3),
        "dark_noise_e": round(dark_noise, 3),
        "total_noise_e": round(total_noise, 3),
        "snr_linear": round(snr_linear, 3) if math.isfinite(snr_linear) else snr_linear,
        "snr_db": round(snr_db, 2) if math.isfinite(snr_db) else snr_db,
        "dynamic_range_db": round(dr_db, 2),
        "nep_photons": round(nep_photons, 3),
        "saturation_fraction": round(saturation_fraction, 4),
        "adc_electrons_per_dn": round(adc_electrons_per_dn, 4),
        "recommendations": recs,
    }


def irradiance_at_sensor(
    source_radiance_W_per_sr_m2: float,
    collection_solid_angle_sr: float,
    transmission: float,
    pixel_area_m2: float,
    wavelength_band_nm: float,
) -> dict:
    """Radiometric chain: source → sensor irradiance and photon flux.

    Irradiance at sensor:
      E = L * Omega * T  [W/m^2]
    where:
      L = source_radiance [W/sr/m^2]
      Omega = collection solid angle [sr]
      T = system transmission (0..1)

    Photon energy: E_photon = h*c / lambda

    Returns: {irradiance_W_m2, power_per_pixel_W, photon_flux_per_s,
              signal_photons_per_pixel (for 1s)}
    """
    # Irradiance at sensor aperture
    irradiance = source_radiance_W_per_sr_m2 * collection_solid_angle_sr * transmission

    # Power collected per pixel
    power_per_pixel = irradiance * pixel_area_m2

    # Photon energy (use center of band)
    h = 6.626e-34   # J·s
    c = 2.998e8     # m/s
    # Center wavelength: approximate as input wavelength_band_nm for spectral band
    lam_center_m = wavelength_band_nm * 1e-9  # crude: band width ≈ center wavelength
    E_photon = h * c / lam_center_m if lam_center_m > 0 else 1e-19

    photon_flux = power_per_pixel / E_photon  # photons/s

    return {
        "status": "ok",
        "irradiance_W_m2": irradiance,
        "power_per_pixel_W": power_per_pixel,
        "photon_flux_per_s": photon_flux,
        "signal_photons_per_pixel": photon_flux,  # for 1s exposure
        "E_photon_J": E_photon,
    }


def noise_equivalent_power(
    snr: float,
    signal_photons: float,
    wavelength_nm: float = 550.0,
) -> dict:
    """NEP and detectivity for a given operating point.

    NEP = signal_power / SNR  [W/sqrt(Hz)]
    Detectivity D* = sqrt(pixel_area) / NEP  (normalized; here use 1 cm^2 reference)

    Returns: {nep_W_per_sqrtHz, detectivity_cm_sqrtHz_per_W,
              nep_photons_per_sqrtHz, wavelength_nm, snr}
    """
    # Photon energy
    h = 6.626e-34
    c = 2.998e8
    lam_m = wavelength_nm * 1e-9
    E_photon = h * c / lam_m

    # Signal power
    signal_power_W = signal_photons * E_photon

    # NEP = signal / SNR (for 1 Hz bandwidth)
    nep_W = signal_power_W / max(snr, 1e-12)
    nep_photons = signal_photons / max(snr, 1e-12)

    # Detectivity D* (normalized to 1 cm^2 area, 1 Hz BW)
    ref_area_cm2 = 1.0
    detectivity = math.sqrt(ref_area_cm2) / max(nep_W, 1e-30)

    return {
        "status": "ok",
        "nep_W_per_sqrtHz": nep_W,
        "detectivity_cm_sqrtHz_per_W": detectivity,
        "nep_photons_per_sqrtHz": nep_photons,
        "wavelength_nm": wavelength_nm,
        "snr": snr,
        "E_photon_J": E_photon,
    }
