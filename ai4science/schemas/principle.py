"""L1 Principle schema."""
from __future__ import annotations

from typing import List, Literal

from pydantic import ConfigDict, Field

from ai4science.schemas.artifact import Artifact


class Principle(Artifact):
    """A physical-law artifact at PWM Layer 1."""
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["principle"]
    domain: str = Field(..., min_length=2, max_length=120)
    governing_equation_or_operator: str = Field(..., min_length=2, max_length=2000)
    inputs: List[str] = Field(..., min_length=1)
    outputs: List[str] = Field(..., min_length=1)
    assumptions: List[str] = Field(..., min_length=1)
    validity_range: str = Field(..., min_length=2, max_length=2000)
    known_limitations: List[str] = Field(default_factory=list)
    references: List[str] = Field(..., min_length=1)
