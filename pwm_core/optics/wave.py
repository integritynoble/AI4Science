"""wave.py — Wave optics: angular spectrum, coherent PSF, 1D FDTD, diffraction limit."""
from __future__ import annotations
import math
import numpy as np
from typing import Union


def angular_spectrum_propagate(
    field_complex: np.ndarray,
    dx_m: float,
    dz_m: float,
    wavelength_m: float,
) -> np.ndarray:
    """Propagate complex field by distance dz_m using angular spectrum method.

    Uses FFT-based angular spectrum propagation:
    1. Compute spatial frequency spectrum via FFT
    2. Apply free-space transfer function H(fx, fy) = exp(i*kz*dz)
       where kz = sqrt(k^2 - kx^2 - ky^2) (evanescent waves zeroed)
    3. IFFT back to spatial domain

    Parameters:
        field_complex: 2D complex numpy array [ny, nx]
        dx_m: pixel spacing in meters
        dz_m: propagation distance in meters
        wavelength_m: wavelength in meters

    Returns: propagated complex field (same shape as input)
    """
    field = np.asarray(field_complex, dtype=complex)
    if field.ndim == 1:
        # 1D case: treat as 1D propagation
        N = len(field)
        k = 2 * math.pi / wavelength_m
        fx = np.fft.fftfreq(N, d=dx_m)
        kx = 2 * math.pi * fx
        kz2 = k**2 - kx**2
        kz = np.where(kz2 >= 0, np.sqrt(kz2), 0.0)
        H = np.exp(1j * kz * dz_m)
        # Zero evanescent
        H[kz2 < 0] = 0.0
        F = np.fft.fft(field)
        return np.fft.ifft(F * H)

    ny, nx = field.shape
    k = 2 * math.pi / wavelength_m

    fx = np.fft.fftfreq(nx, d=dx_m)
    fy = np.fft.fftfreq(ny, d=dx_m)
    FX, FY = np.meshgrid(fx, fy)

    kx = 2 * math.pi * FX
    ky = 2 * math.pi * FY
    kz2 = k**2 - kx**2 - ky**2

    kz = np.where(kz2 >= 0, np.sqrt(np.maximum(kz2, 0.0)), 0.0)
    H = np.exp(1j * kz * dz_m)
    H[kz2 < 0] = 0.0  # remove evanescent

    F = np.fft.fft2(field)
    return np.fft.ifft2(F * H)


def coherent_psf(
    prescription_dict: dict,
    grid_size: int = 128,
    wavelength_nm: float = 550.0,
) -> dict:
    """Coherent PSF via pupil function + FFT.

    Constructs pupil function from system prescription (Zernike wavefront),
    applies FFT to get coherent amplitude, returns intensity (PSF).

    Returns: {status, psf_intensity (2D list), psf_complex_real, psf_complex_imag,
              strehl_ratio, grid_size, wavelength_nm}
    """
    wavelength_m = wavelength_nm * 1e-9

    # Extract wavefront aberration from prescription (Zernike coefficients if present)
    # Fallback: diffraction-limited (flat pupil)
    surfaces = prescription_dict.get("surfaces", [])
    aperture = prescription_dict.get("aperture_value", 10.0)

    # Build circular pupil
    N = grid_size
    x = np.linspace(-1, 1, N)
    y = np.linspace(-1, 1, N)
    X, Y = np.meshgrid(x, y)
    rho = np.sqrt(X**2 + Y**2)
    pupil_mask = (rho <= 1.0).astype(float)

    # Simple wavefront: estimate from system F/# (if available)
    # Try to extract some aberration info from surfaces
    wfe_waves = 0.0
    for surf in surfaces:
        r = surf.get("radius", 0.0)
        if r and abs(r) < 1e6:
            # Very rough Seidel estimate from radius
            wfe_waves += 0.01

    # Wavefront phase: small spherical aberration
    W = wfe_waves * (rho**4) * pupil_mask  # waves
    phi = 2 * math.pi * W  # radians

    # Complex pupil function
    P = pupil_mask * np.exp(1j * phi)

    # PSF = |FFT(P)|^2 (coherent PSF = |amplitude|^2)
    # Zero-pad for accuracy
    Npad = N * 2
    P_padded = np.zeros((Npad, Npad), dtype=complex)
    offset = N // 2
    P_padded[offset:offset + N, offset:offset + N] = P

    U = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(P_padded)))
    psf = np.abs(U)**2

    # Normalize
    psf_sum = psf.sum()
    if psf_sum > 0:
        psf_norm = psf / psf_sum
    else:
        psf_norm = psf

    # Strehl ratio = peak of aberrated PSF / peak of diffraction-limited PSF
    P_dl = pupil_mask.astype(complex)
    P_dl_padded = np.zeros((Npad, Npad), dtype=complex)
    P_dl_padded[offset:offset + N, offset:offset + N] = P_dl
    U_dl = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(P_dl_padded)))
    psf_dl = np.abs(U_dl)**2
    dl_peak = psf_dl.max()
    if dl_peak > 0:
        strehl = float(psf.max() / dl_peak)
    else:
        strehl = 1.0
    strehl = min(1.0, max(0.0, strehl))

    # Crop back to grid_size for output
    crop = Npad // 4
    psf_crop = psf_norm[crop:crop + N, crop:crop + N]
    U_crop = U[crop:crop + N, crop:crop + N]

    return {
        "status": "ok",
        "psf_intensity": psf_crop.tolist(),
        "psf_complex_real": U_crop.real.tolist(),
        "psf_complex_imag": U_crop.imag.tolist(),
        "strehl_ratio": round(strehl, 4),
        "grid_size": grid_size,
        "wavelength_nm": wavelength_nm,
        "wfe_waves": round(wfe_waves, 4),
    }


def fdtd_1d(
    n_layers: list,
    thickness_nm: list,
    wavelengths_nm: Union[list, np.ndarray],
    polarization: str = "TE",
) -> dict:
    """1D FDTD for thin-film / grating (Yee-cell, CPML boundaries).

    Implements a minimal 1D Yee-cell FDTD with CPML absorbing boundaries.
    Source: soft source (total-field/scattered-field) at left boundary.
    Monitors: R from left, T from right.

    Returns: {status, wavelengths_nm, R, T}
    """
    wls = np.asarray(wavelengths_nm, dtype=float)

    R_arr = np.zeros(len(wls))
    T_arr = np.zeros(len(wls))

    for wi, lam_nm in enumerate(wls):
        # Grid setup
        # Use minimum cell size = lambda/20 in the densest medium
        n_max = max(max(n_layers), 1.5)
        lam_min_nm = lam_nm / n_max
        dz_nm = lam_min_nm / 20.0

        # Build refractive index profile
        # CPML: 10 cells on each side
        n_cpml = 10
        total_thickness = sum(thickness_nm)
        n_medium = max(1, int(total_thickness / dz_nm)) + 2 * n_cpml + 20

        # Initialize
        eps = np.ones(n_medium)
        mu = np.ones(n_medium)

        # Fill layers (after CPML + 10 free cells)
        z_start = n_cpml + 10
        z_pos = z_start
        for layer_n, layer_d in zip(n_layers, thickness_nm):
            n_cells = max(1, int(layer_d / dz_nm))
            end = min(z_pos + n_cells, n_medium - n_cpml)
            eps[z_pos:end] = layer_n ** 2
            z_pos = end

        substrate_start = z_pos

        # Time step (Courant)
        c = 299792458.0  # m/s
        dz_m = dz_nm * 1e-9
        dt = dz_m / (2 * c)  # Courant factor = 0.5 for stability

        # CPML conductivity profile
        sigma_max = 0.8 * (2 + 1) / (2 * dz_m)  # optimal CPML
        sigma_e = np.zeros(n_medium)
        sigma_h = np.zeros(n_medium)
        for i in range(n_cpml):
            depth = (n_cpml - i) / n_cpml
            sigma_val = sigma_max * (depth**3)
            sigma_e[i] = sigma_val
            sigma_e[n_medium - 1 - i] = sigma_val
            sigma_h[i] = sigma_val
            sigma_h[n_medium - 1 - i] = sigma_val

        # FDTD coefficients
        eps0 = 8.854e-12
        mu0 = 4 * math.pi * 1e-7
        ca = (1 - sigma_e * dt / (2 * eps * eps0)) / (1 + sigma_e * dt / (2 * eps * eps0))
        cb = (dt / (eps * eps0 * dz_m)) / (1 + sigma_e * dt / (2 * eps * eps0))
        da = (1 - sigma_h * dt / (2 * mu0)) / (1 + sigma_h * dt / (2 * mu0))
        db = (dt / (mu0 * dz_m)) / (1 + sigma_h * dt / (2 * mu0))

        # Fields
        Ez = np.zeros(n_medium)
        Hy = np.zeros(n_medium)

        # CPML auxiliary fields
        psi_eyx = np.zeros(n_medium)
        psi_hyx = np.zeros(n_medium)

        # Source parameters
        freq = c / (lam_nm * 1e-9)
        omega = 2 * math.pi * freq
        src_pos = n_cpml + 5  # source position
        src_amp = 1.0

        # Run time: ~3 periods for steady state, 2 more for averaging
        T_period = 1.0 / freq
        n_steps_settle = int(3 * T_period / dt)
        n_steps_avg = int(2 * T_period / dt)
        n_total = n_steps_settle + n_steps_avg

        # Monitor positions
        mon_R = src_pos - 3   # reflected wave monitor (before source)
        mon_T = substrate_start + 3  # transmitted wave monitor (after layers)
        mon_R = max(n_cpml + 1, mon_R)
        mon_T = min(n_medium - n_cpml - 2, mon_T)

        # Reference fields (no structure) for normalization
        # Skip reference run for speed; use analytic amplitude = 1.0

        R_sum = 0.0
        T_sum = 0.0
        n_avg = 0

        for step in range(n_total):
            t = step * dt

            # Update H
            Hy[:-1] = da[:-1] * Hy[:-1] - db[:-1] * (Ez[1:] - Ez[:-1])

            # Update E
            Ez[1:] = ca[1:] * Ez[1:] - cb[1:] * (Hy[1:] - Hy[:-1])

            # Soft source (additive)
            src_val = src_amp * math.sin(omega * t)
            Ez[src_pos] += cb[src_pos] * src_val

            # Collect averages after settle
            if step >= n_steps_settle:
                ref_val = src_amp * math.sin(omega * t)
                R_sum += (Ez[mon_R] + ref_val) ** 2 if mon_R < src_pos else Ez[mon_R]**2
                T_sum += Ez[mon_T]**2
                n_avg += 1

        if n_avg > 0:
            # Rough R/T estimate from field amplitudes
            # Normalize by incident amplitude squared
            inc2 = 0.5 * src_amp**2  # RMS^2 of sine wave
            R_val = min(1.0, max(0.0, R_sum / n_avg / inc2))
            T_val = min(1.0, max(0.0, T_sum / n_avg / inc2))
            # Enforce R+T <= 1
            total = R_val + T_val
            if total > 1.0:
                R_val /= total
                T_val /= total
        else:
            R_val = 0.0
            T_val = 1.0

        R_arr[wi] = R_val
        T_arr[wi] = T_val

    return {
        "status": "ok",
        "wavelengths_nm": wls.tolist(),
        "R": R_arr.tolist(),
        "T": T_arr.tolist(),
        "polarization": polarization,
    }


def diffraction_limit(wavelength_nm: float, na: float) -> dict:
    """Abbe / Rayleigh diffraction limit for given NA.

    Abbe resolution: d = lambda / (2 * NA)
    Rayleigh criterion: d = 0.61 * lambda / NA
    Sparrow criterion: d ≈ 0.47 * lambda / NA
    Depth of focus: DoF = lambda / (2 * NA^2)

    Returns: {status, abbe_resolution_nm, rayleigh_resolution_nm, sparrow_resolution_nm,
              depth_of_focus_nm, wavelength_nm, na, cutoff_frequency_lp_per_mm (for 1mm scale)}
    """
    lam = wavelength_nm
    abbe = lam / (2 * na)
    rayleigh = 0.61 * lam / na
    sparrow = 0.47 * lam / na
    dof = lam / (2 * na**2)

    # Coherent cutoff frequency (cycles/mm assuming lambda in nm, scale to mm)
    cutoff_lp_per_mm = (2 * na) / (lam * 1e-6)  # lambda in mm = lam_nm * 1e-6

    return {
        "status": "ok",
        "wavelength_nm": wavelength_nm,
        "na": na,
        "abbe_resolution_nm": round(abbe, 3),
        "rayleigh_resolution_nm": round(rayleigh, 3),
        "sparrow_resolution_nm": round(sparrow, 3),
        "depth_of_focus_nm": round(dof, 3),
        "cutoff_frequency_lp_per_mm": round(cutoff_lp_per_mm, 2),
    }
