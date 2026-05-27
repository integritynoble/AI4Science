"""Pydantic schemas for the four PWM artifact types."""
from ai4science.schemas.artifact import Artifact, ArtifactType, parse_front_matter
from ai4science.schemas.principle import Principle
from ai4science.schemas.spec import Spec
from ai4science.schemas.benchmark import Benchmark
from ai4science.schemas.solution import Solution

__all__ = [
    "Artifact",
    "ArtifactType",
    "Principle",
    "Spec",
    "Benchmark",
    "Solution",
    "parse_front_matter",
    "SCHEMA_BY_TYPE",
]

SCHEMA_BY_TYPE = {
    "principle": Principle,
    "spec": Spec,
    "benchmark": Benchmark,
    "solution": Solution,
}
