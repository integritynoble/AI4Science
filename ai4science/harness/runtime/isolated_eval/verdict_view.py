from __future__ import annotations

from pathlib import Path

from .errors import TamperDetected
from .store import EvaluatorStore


class AgentVerdictView:
    """The only handle on the evaluator the agent is meant to hold.

    It answers one question — what was the decision — and refuses to be turned
    into a path. An optimizer that reaches for the store through this object is
    refused with a named incident rather than an ``AttributeError`` it can route
    around.
    """

    def __init__(self, store: EvaluatorStore):
        object.__setattr__(self, "_store", store)

    def decision(self, run_id: str) -> str:
        return self._store.get_verdict(run_id)["decision"]

    def score(self, run_id: str) -> float:
        return float(self._store.get_verdict(run_id)["score"])

    def open_store(self, path: str | Path = ""):
        """Always refused, and recorded as an attempt."""
        self._store.record_incident("-", "store_access_refused",
                                    f"agent-side open of the evaluator store: {path!r}")
        raise PermissionError("the evaluator's store is not the agent's to open")

    def __setattr__(self, name, value):
        raise PermissionError(f"the verdict view is read-only (refused set of {name!r})")

    def __repr__(self) -> str:   # deliberately no path in it
        return "<AgentVerdictView: decisions only>"


__all__ = ["AgentVerdictView", "TamperDetected"]
