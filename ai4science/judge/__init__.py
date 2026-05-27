"""ai4science.judge — deterministic Physics Judge modules.

The judge is the PWM moat. It is intentionally plain Python with no LLM
in the verdict path. All checks are deterministic functions returning a
``CheckResult`` (status, message, optional numeric evidence).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CheckResult:
    """One judge check's outcome.

    status:
      - "pass"           — the check confirms the property holds
      - "fail"           — the check confirms the property is violated
      - "warning"        — soft signal; should not fail the submission
      - "not_available"  — the data needed to run the check was not present
    """
    status: str
    message: str = ""
    evidence: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    @property
    def failed(self) -> bool:
        return self.status == "fail"


__all__ = ["CheckResult"]
