from __future__ import annotations
from pwm_core.optics.prescription import OpticalSystem, Surface, Field, Wavelength


def import_zmx(path: str) -> OpticalSystem:
    """Import a Zemax .zmx or CODE V .seq file -> OpticalSystem prescription.

    Uses rayoptics for parsing. rayoptics is imported lazily so the rest of
    pwm_core.optics can load without it installed.
    """
    try:
        from rayoptics.environment import open_model
    except ImportError as exc:
        raise ImportError("rayoptics is required for .zmx import: pip install rayoptics") from exc

    opm = open_model(str(path))
    sm = opm['seq_model']
    osp = opm['optical_spec']

    # --- Surfaces ---
    surfaces = []
    for i, ifc in enumerate(sm.ifcs):
        # thickness: distance to next surface (0 for last)
        t = sm.gaps[i].thi if i < len(sm.gaps) else 0.0
        # material
        if i < len(sm.gaps):
            med = sm.gaps[i].medium
            mat = (med.name() if hasattr(med, 'name') else str(med)) if med is not None else "air"
            mat = "air" if mat.lower() in ("air", "", "none") else mat
        else:
            mat = "air"
        # radius
        try:
            r = ifc.profile.cv  # curvature -> radius = 1/cv
            radius = (1.0 / r) if abs(r) > 1e-12 else float("inf")
        except AttributeError:
            radius = float("inf")
        # semi-diameter
        try:
            sd = ifc.max_aperture
        except AttributeError:
            sd = None
        # surface type
        stype = "stop" if getattr(ifc, 'interact_mode', '') == 'Stop' else "standard"
        surfaces.append(Surface(
            surface_type=stype,
            radius=radius,
            thickness=float(t),
            material=mat,
            semi_diameter=float(sd) if sd else None,
        ))

    # --- Fields ---
    fields = []
    try:
        fov = osp.field_of_view
        for f in fov.fields:
            fields.append(Field(y=float(f.y), x=float(f.x), weight=float(f.wt)))
    except Exception:
        fields = [Field(0.0)]
    if not fields:
        fields = [Field(0.0)]

    # --- Wavelengths ---
    wavelengths = []
    try:
        sr = osp.spectral_region
        ref_wl = sr.reference_wvl
        for i, wl in enumerate(sr.wavelengths):
            wavelengths.append(Wavelength(
                value=float(wl),
                weight=float(sr.spectral_wts[i]) if i < len(sr.spectral_wts) else 1.0,
                is_primary=(i == ref_wl),
            ))
    except Exception:
        wavelengths = [Wavelength(0.55, is_primary=True)]
    if not wavelengths:
        wavelengths = [Wavelength(0.55, is_primary=True)]

    # --- Aperture ---
    aperture_type = "EPD"
    aperture_value = 10.0
    try:
        pupil = osp.pupil
        aperture_value = float(pupil.value)
        ptype = str(pupil.key).upper()
        if "FNO" in ptype or "F/" in ptype:
            aperture_type = "FNO"
        elif "NA" in ptype:
            aperture_type = "NA"
    except Exception:
        pass

    title = ""
    try:
        n = opm.name
        title = (n() if callable(n) else n) or ""
    except Exception:
        pass

    return OpticalSystem(
        surfaces=surfaces,
        fields=fields,
        wavelengths=wavelengths,
        aperture_type=aperture_type,
        aperture_value=aperture_value,
        title=title,
    )
