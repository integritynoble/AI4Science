"""S3 — Approximability check (benchmark is well-defined and reproducible)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from ai4science.judge import CheckResult
from ai4science.schemas import Benchmark, parse_front_matter

REQUIRED_FIELDS: List[str] = [
    "name", "parent_spec_id", "dataset_description", "data_paths",
    "train_validation_test_split", "metrics", "physics_checks",
    "baseline_methods", "success_threshold", "reproducibility_command",
]


def check_s3(workspace: Path, benchmark_path: Optional[Path] = None) -> CheckResult:
    """Validate the benchmark artifact. ``benchmark_path`` selects which
    tier file to check; defaults to benchmark.md for backward compat."""
    bench_path = benchmark_path if benchmark_path is not None else workspace / "benchmark.md"
    label = bench_path.name
    data, err = parse_front_matter(bench_path)
    if err:
        return CheckResult("fail", f"{label} unreadable: {err}")

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        return CheckResult(
            "fail",
            f"{label} missing required fields: {missing}",
            evidence={"missing_fields": missing},
        )

    try:
        Benchmark.model_validate(data)
    except ValidationError as e:
        return CheckResult(
            "fail",
            f"{label} validation failed: {len(e.errors())} error(s)",
            evidence={"errors": [str(err) for err in e.errors()]},
        )

    return CheckResult(
        "pass",
        f"{label} well-formed; metrics, threshold, and reproducibility command declared",
        evidence={
            "metrics": list(data["metrics"]),
            "success_threshold": data["success_threshold"],
            "reproducibility_command": data["reproducibility_command"],
        },
    )
