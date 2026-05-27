"""L4 Solution schema."""
from __future__ import annotations

from typing import List, Literal

from pydantic import ConfigDict, Field

from ai4science.schemas.artifact import Artifact


class Solution(Artifact):
    """A solver / AI-assisted submission at PWM Layer 4."""
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["solution"]
    parent_benchmark_id: str = Field(..., min_length=2, max_length=60)
    method_name: str = Field(..., min_length=2, max_length=200)
    code_path: str = Field(..., min_length=2, max_length=500,
                           description="Relative path to code/ directory or main script")
    run_command: str = Field(..., min_length=2, max_length=1000)
    environment: str = Field(..., min_length=2, max_length=500,
                             description="Path to environment.yml / requirements.txt / Dockerfile")
    results_path: str = Field(..., min_length=2, max_length=500,
                              description="Relative path to results/ directory")
    claims: List[str] = Field(..., min_length=1,
                              description="Quantitative claims, e.g. ['PSNR = 28.4 dB on test split']")
    limitations: List[str] = Field(default_factory=list)
    license: str = Field(..., min_length=2, max_length=60,
                         description="SPDX identifier, e.g. 'MIT', 'Apache-2.0', 'CC-BY-4.0'")
