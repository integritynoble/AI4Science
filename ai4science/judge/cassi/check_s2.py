"""S2 — Hadamard stability check (well-posedness signals).

v0.1 implementation:
- If required physical parameters (omega_domain, observable, equations,
  boundary_conditions, initial_conditions, tolerance_epsilon) are all
  present, return "warning" with a note that a full well-posedness proof
  is not encoded yet. Per spec, missing-proof is a *warning*, not a
  *fatal failure*.
- If those parameters themselves are missing, return "fail" (which
  S1 would already have caught — included here for defence-in-depth).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from ai4science.judge import CheckResult
from ai4science.schemas import parse_front_matter

REQUIRED_PHYSICAL_PARAMETERS: List[str] = [
    "omega_domain", "equations", "observable",
    "boundary_conditions", "initial_conditions", "tolerance_epsilon",
]


def check_s2(workspace: Path) -> CheckResult:
    """S2 returns 'warning' for v0.1: well-posedness proof not encoded."""
    spec_path = workspace / "spec.md"
    data, err = parse_front_matter(spec_path)
    if err:
        return CheckResult("fail", f"spec.md unreadable: {err}")

    missing = [f for f in REQUIRED_PHYSICAL_PARAMETERS if f not in data]
    if missing:
        return CheckResult(
            "fail",
            f"spec.md missing required physical parameters: {missing}",
            evidence={"missing_parameters": missing},
        )

    return CheckResult(
        "warning",
        ("required physical parameters present, but full well-posedness "
         "(Hadamard stability) proof is not encoded in v0.1. Treat S2 as "
         "advisory until a proof artifact is supplied."),
        evidence={"parameters_present": REQUIRED_PHYSICAL_PARAMETERS},
    )
