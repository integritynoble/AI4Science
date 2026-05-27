"""L3 Benchmark schema."""
from __future__ import annotations

from typing import List, Literal

from pydantic import ConfigDict, Field

from ai4science.schemas.artifact import Artifact


class Benchmark(Artifact):
    """A reproducible task at PWM Layer 3."""
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["benchmark"]
    parent_spec_id: str = Field(..., min_length=2, max_length=60)
    dataset_description: str = Field(..., min_length=10, max_length=4000)
    data_paths: List[str] = Field(..., min_length=1,
                                  description="Relative paths to input data files")
    train_validation_test_split: str = Field(..., min_length=2, max_length=500,
                                              description="e.g. '70/15/15' or 'fixed splits in data/splits.json'")
    metrics: List[str] = Field(..., min_length=1,
                               description="e.g. ['PSNR', 'SSIM']")
    physics_checks: List[str] = Field(..., min_length=1,
                                      description="S1..S4 checks this benchmark requires")
    baseline_methods: List[str] = Field(..., min_length=1)
    success_threshold: str = Field(..., min_length=2, max_length=500,
                                   description="Quantitative passing bar, e.g. 'PSNR ≥ 25 dB on test split'")
    reproducibility_command: str = Field(..., min_length=2, max_length=1000,
                                          description="One-liner that reproduces results from data/")
