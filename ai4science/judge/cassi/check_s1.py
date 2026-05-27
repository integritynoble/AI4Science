"""S1 — finite specifiability check (spec.md exists and is well-formed)."""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import ValidationError

from ai4science.judge import CheckResult
from ai4science.schemas import Spec, parse_front_matter

REQUIRED_FIELDS: List[str] = [
    "name", "parent_principle_id", "domain", "problem_statement",
    "omega_domain", "equations", "boundary_conditions", "initial_conditions",
    "observable", "tolerance_epsilon", "input_format", "output_format",
]


def check_s1(workspace: Path) -> CheckResult:
    """S1 holds if spec.md exists, has valid YAML front matter, and every
    required field is present and well-typed.
    """
    spec_path = workspace / "spec.md"
    data, err = parse_front_matter(spec_path)
    if err:
        return CheckResult("fail", f"spec.md unreadable: {err}")

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        return CheckResult(
            "fail",
            f"spec.md missing required fields: {missing}",
            evidence={"missing_fields": missing},
        )

    try:
        Spec.model_validate(data)
    except ValidationError as e:
        return CheckResult(
            "fail",
            f"spec.md validation failed: {len(e.errors())} error(s)",
            evidence={"errors": [str(err) for err in e.errors()]},
        )

    return CheckResult(
        "pass",
        "spec.md present and finitely specifies the problem",
        evidence={"spec_name": data["name"], "epsilon": float(data["tolerance_epsilon"])},
    )
