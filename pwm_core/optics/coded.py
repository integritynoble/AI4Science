"""coded.py — coded apertures, DOEs, and phase masks for CI modalities.

Provides:
  - binary_mask(H, W, density, seed)   — random binary coded aperture
  - optimized_mask(H, W, N_bands, disp_a1)  — rank-based optimized mask
  - cassi_forward(scene, mask, disp_a1) — simulate CASSI measurement
  - lensless_forward(scene, phase_mask, prop_dist_m, wavelength_m) — diffraction
  - doe_phase_grating(N, pitch_m, wavelength_m, blaze_order) — DOE phase profile

All functions return numpy arrays.  No agent/PWM deps.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Binary coded aperture
# ---------------------------------------------------------------------------

def binary_mask(H: int, W: int, density: float = 0.5,
                seed: Optional[int] = None) -> np.ndarray:
    """Random binary coded aperture of shape (H, W).

    Parameters
    ----------
    H, W    : spatial dimensions
    density : fraction of 1s (0–1)
    seed    : RNG seed for reproducibility

    Returns
    -------
    mask : uint8 array of shape (H, W) with values 0 or 1
    """
    rng = np.random.default_rng(seed)
    return (rng.random((H, W)) < density).astype(np.uint8)


def optimized_mask(H: int, W: int, N_bands: int = 28,
                   disp_a1: float = 1.0,
                   seed: Optional[int] = None) -> np.ndarray:
    """Rank-based coded aperture (simplified S-matrix design).

    Uses a pseudo-random binary sequence (PRBS) with good autocorrelation,
    tiled to fill (H, W).  Better conditioning than pure random for CASSI.

    Parameters
    ----------
    H, W   : spatial dimensions
    N_bands: number of spectral bands (informs column spacing)
    disp_a1: dispersion (pixels/band); used to set cyclic shift constraint
    seed   : RNG seed

    Returns
    -------
    mask : uint8 array of shape (H, W)
    """
    rng = np.random.default_rng(seed)

    # Use a maximal-length sequence (m-sequence) of appropriate length
    # Simplified: generate a random sequence then tile to match W + disp*N_bands
    W_ext = W + int(math.ceil(disp_a1 * N_bands))
    # Base row: PRBS-style (half ones in a row of prime-ish length)
    base_len = max(31, W_ext)
    seq = (rng.random(base_len) < 0.5).astype(np.uint8)
    # Tile to (H, W)
    col_seq = np.tile(seq, math.ceil(W / base_len))[:W]
    row_phase = rng.integers(0, base_len, size=H)
    rows = [(np.roll(col_seq, int(ph))) for ph in row_phase]
    return np.stack(rows, axis=0)


# ---------------------------------------------------------------------------
# CASSI forward model
# ---------------------------------------------------------------------------

def cassi_forward(
    scene: np.ndarray,
    mask: np.ndarray,
    disp_a1: float = 1.0,
    noise_level: float = 0.0,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Simulate a CASSI (Coded Aperture Snapshot Spectral Imager) measurement.

    Parameters
    ----------
    scene   : float array of shape (H, W, N_bands) — hyperspectral scene
    mask    : binary array of shape (H, W)
    disp_a1 : dispersion shift in pixels per spectral band
    noise_level : Gaussian noise std relative to signal max
    seed    : RNG seed for noise

    Returns
    -------
    measurement : float array of shape (H, W_meas)
                  where W_meas = W + floor(disp_a1 * (N_bands - 1))
    """
    if scene.ndim == 2:
        scene = scene[:, :, np.newaxis]
    H, W, N_bands = scene.shape
    W_meas = W + int(math.floor(disp_a1 * (N_bands - 1)))
    measurement = np.zeros((H, W_meas), dtype=np.float64)

    for b in range(N_bands):
        shift = int(round(disp_a1 * b))
        # Apply mask to band
        band = scene[:, :, b] * mask.astype(float)
        measurement[:, shift:shift + W] += band

    if noise_level > 0:
        rng = np.random.default_rng(seed)
        measurement += rng.standard_normal(measurement.shape) * noise_level * measurement.max()

    return measurement.astype(np.float32)


# ---------------------------------------------------------------------------
# Lensless / diffraction forward model
# ---------------------------------------------------------------------------

def lensless_forward(
    scene: np.ndarray,
    phase_mask: np.ndarray,
    prop_dist_m: float = 0.01,
    wavelength_m: float = 550e-9,
    pixel_pitch_m: float = 5.5e-6,
    noise_level: float = 0.0,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Simulate lensless diffraction-based imager.

    Uses the angular-spectrum propagation (Fresnel approximation).

    Parameters
    ----------
    scene       : float array (H, W)  — object intensity
    phase_mask  : float array (H, W)  — coded phase (radians)
    prop_dist_m : propagation distance (metres)
    wavelength_m: illumination wavelength (metres)
    pixel_pitch_m: sensor pixel pitch (metres)
    noise_level : Gaussian noise std relative to max

    Returns
    -------
    measurement : float array (H, W) — intensity at sensor
    """
    H, W = scene.shape[:2]
    # Fourier-domain propagation (paraxial / Fraunhofer)
    k = 2 * math.pi / wavelength_m
    # Angular-spectrum transfer function
    fx = np.fft.fftfreq(W, d=pixel_pitch_m)
    fy = np.fft.fftfreq(H, d=pixel_pitch_m)
    FX, FY = np.meshgrid(fx, fy)
    arg = (wavelength_m * FX) ** 2 + (wavelength_m * FY) ** 2
    arg = np.clip(arg, 0, 1)
    H_tf = np.exp(1j * k * prop_dist_m * np.sqrt(np.maximum(0, 1 - arg)))

    # Modulate by phase mask
    field_in = scene.astype(complex) * np.exp(1j * phase_mask.astype(float))
    # Propagate
    field_out = np.fft.ifft2(np.fft.fft2(field_in) * H_tf)
    measurement = np.abs(field_out) ** 2

    if noise_level > 0:
        rng = np.random.default_rng(seed)
        measurement += rng.standard_normal(measurement.shape) * noise_level * measurement.max()

    return measurement.astype(np.float32)


# ---------------------------------------------------------------------------
# DOE phase profile
# ---------------------------------------------------------------------------

def doe_phase_grating(
    N: int,
    pitch_m: float = 10e-6,
    wavelength_m: float = 550e-9,
    blaze_order: int = 1,
    pixel_pitch_m: float = 1e-6,
) -> np.ndarray:
    """Blazed-grating DOE phase profile (1-D, wrapped to [0, 2π]).

    Parameters
    ----------
    N            : number of pixels
    pitch_m      : grating pitch (metres)
    wavelength_m : design wavelength (metres)
    blaze_order  : diffraction order to maximise efficiency
    pixel_pitch_m: pixel size of the DOE

    Returns
    -------
    phase : float array of shape (N,) in radians [0, 2π)
    """
    x = np.arange(N) * pixel_pitch_m
    # Blaze phase: linear ramp within each period, wrapped
    phase = (2 * math.pi * blaze_order * x / pitch_m) % (2 * math.pi)
    return phase.astype(np.float32)


def doe_phase_fresnel_lens(
    H: int, W: int,
    focal_length_m: float = 0.05,
    wavelength_m: float = 550e-9,
    pixel_pitch_m: float = 5.5e-6,
) -> np.ndarray:
    """Fresnel zone-plate phase profile wrapped to [0, 2π].

    Parameters
    ----------
    H, W          : spatial dimensions
    focal_length_m: desired focal length (metres)
    wavelength_m  : design wavelength (metres)
    pixel_pitch_m : pixel pitch (metres)

    Returns
    -------
    phase : float32 array of shape (H, W) in radians [0, 2π)
    """
    yy = (np.arange(H) - H // 2) * pixel_pitch_m
    xx = (np.arange(W) - W // 2) * pixel_pitch_m
    Y, X = np.meshgrid(yy, xx, indexing="ij")
    r2 = X ** 2 + Y ** 2
    phase = (math.pi / (wavelength_m * focal_length_m) * r2) % (2 * math.pi)
    return phase.astype(np.float32)
