"""L2 Spec schema (the six-tuple expressed as Markdown front matter)."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import ConfigDict, Field

from ai4science.schemas.artifact import Artifact


class Spec(Artifact):
    """A formal problem statement at PWM Layer 2."""
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["spec"]
    parent_principle_id: str = Field(..., min_length=2, max_length=60)
    domain: str = Field(..., min_length=2, max_length=120)
    problem_statement: str = Field(..., min_length=10, max_length=4000)
    omega_domain: str = Field(..., min_length=2, max_length=2000,
                              description="Spatial / temporal / spectral domain Ω")
    equations: List[str] = Field(..., min_length=1,
                                 description="Governing equations or constraints")
    boundary_conditions: str = Field(..., min_length=2, max_length=2000)
    initial_conditions: str = Field(..., min_length=2, max_length=2000)
    observable: str = Field(..., min_length=2, max_length=2000,
                            description="The measurement / observable operator")
    tolerance_epsilon: float = Field(..., gt=0.0,
                                     description="Numerical tolerance ε used by S2 / S4 checks")
    input_format: str = Field(..., min_length=2, max_length=500)
    output_format: str = Field(..., min_length=2, max_length=500)

    # Optional noise parameters — only declared when the spec includes a
    # measurement noise model. When present, the noise-consistency S4 check
    # runs; when absent, it returns not_available.
    noise_sigma: Optional[float] = Field(default=None, gt=0.0,
                                          description="Std of additive Gaussian noise in the observable")
