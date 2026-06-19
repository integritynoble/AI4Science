from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json

@dataclass
class Surface:
    surface_type: str = "standard"   # standard | stop | image | object | even_asphere
    radius: float = float("inf")     # radius of curvature (mm); inf = flat
    thickness: float = 0.0           # axial distance to next surface (mm)
    material: str = "air"            # glass name or "air" / "mirror"
    semi_diameter: Optional[float] = None
    conic: float = 0.0
    comment: str = ""

@dataclass
class Field:
    y: float = 0.0
    x: float = 0.0
    weight: float = 1.0

@dataclass
class Wavelength:
    value: float = 0.55       # microns
    weight: float = 1.0
    is_primary: bool = False

@dataclass
class OpticalSystem:
    surfaces: List[Surface] = field(default_factory=list)
    fields: List[Field] = field(default_factory=lambda: [Field(0.0)])
    wavelengths: List[Wavelength] = field(
        default_factory=lambda: [Wavelength(0.55, is_primary=True)])
    aperture_type: str = "EPD"     # EPD | FNO | NA
    aperture_value: float = 10.0
    field_type: str = "angle"      # angle | height
    title: str = ""
    notes: str = ""

def save_system(sys: OpticalSystem, path: str) -> None:
    with open(path, "w") as f:
        json.dump(asdict(sys), f, indent=2)

def load_system(path: str) -> OpticalSystem:
    with open(path) as f:
        d = json.load(f)
    surfaces = [Surface(**s) for s in d.get("surfaces", [])]
    fields = [Field(**fi) for fi in d.get("fields", [])]
    wls = [Wavelength(**w) for w in d.get("wavelengths", [])]
    return OpticalSystem(
        surfaces=surfaces, fields=fields, wavelengths=wls,
        aperture_type=d.get("aperture_type", "EPD"),
        aperture_value=d.get("aperture_value", 10.0),
        field_type=d.get("field_type", "angle"),
        title=d.get("title", ""),
        notes=d.get("notes", ""),
    )
