from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field, asdict

_ACTIVE_MODES = {"I0", "I1", "I2"}

@dataclass
class TaskContract:
    objective: str
    capability_profile: str
    interaction_mode: str = "I1"
    deliverables: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    authority: dict = field(default_factory=lambda: {"workspace": "read_write", "network": "none"})
    success_criteria: list = field(default_factory=list)
    budget: dict = field(default_factory=lambda: {"tool_calls": 100, "runtime_minutes": 90})
    approval_required_for: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TaskContract":
        return cls(**d)

    def hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()

def compile_contract(*, objective: str, capability_profile: str, interaction_mode: str = "I1",
                     deliverables=(), constraints=(), authority=None, success_criteria=(),
                     budget=None, approval_required_for=()) -> TaskContract:
    if interaction_mode not in _ACTIVE_MODES:
        raise ValueError(f"inactive interaction mode {interaction_mode!r}")
    return TaskContract(
        objective=objective, capability_profile=capability_profile,
        interaction_mode=interaction_mode,
        deliverables=list(deliverables), constraints=list(constraints),
        authority=authority or {"workspace": "read_write", "network": "none"},
        success_criteria=list(success_criteria),
        budget=budget or {"tool_calls": 100, "runtime_minutes": 90},
        approval_required_for=list(approval_required_for),
    )
