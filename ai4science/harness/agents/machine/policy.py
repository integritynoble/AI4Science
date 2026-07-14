"""The tunable operation-selection policy — the Machine Agent's RSI harness knob.

Layers learned extra keywords onto the fixed operation registry (keyed by op
name), reusing run_machine's `select=` seam. The incumbent policy is empty
(== today's op.match keywords). Like pocket/manager, this policy sits DOWNSTREAM
of run_machine's owner gate: a learned routing can never cause an unapproved
consequential action, because consequential ops are gated by approve() AFTER
selection.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from ai4science.harness.agents.machine.operations import Operation, default_operations


class OperationPolicy:
    def __init__(self, extra: Dict[str, Tuple[str, ...]]):
        self.extra: Dict[str, Tuple[str, ...]] = {k: tuple(dict.fromkeys(v)) for k, v in extra.items()}

    def select(self, intent: str, registry: Sequence[Operation]) -> Optional[Operation]:
        low = (intent or "").lower()
        for op in registry:
            kws = tuple(op.match) + self.extra.get(op.name, ())
            if kws and any(kw in low for kw in kws):
                return op
        return None

    def with_added(self, op_name: str, phrases: Sequence[str]) -> "OperationPolicy":
        new = {k: tuple(v) for k, v in self.extra.items()}
        new[op_name] = tuple(dict.fromkeys(new.get(op_name, ()) + tuple(phrases)))
        return OperationPolicy(new)

    def added_since(self, base: "OperationPolicy") -> Dict[str, Tuple[str, ...]]:
        diff: Dict[str, Tuple[str, ...]] = {}
        for name, kws in self.extra.items():
            extra = tuple(k for k in kws if k not in set(base.extra.get(name, ())))
            if extra:
                diff[name] = extra
        return diff

    def as_map(self) -> Dict[str, Tuple[str, ...]]:
        return {k: tuple(v) for k, v in self.extra.items()}


def incumbent_operation_policy() -> OperationPolicy:
    """Shipped baseline: no extra keywords (== the registry's built-in op.match)."""
    return OperationPolicy({})
