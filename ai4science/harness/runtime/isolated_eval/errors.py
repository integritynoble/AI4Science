from __future__ import annotations


class IsolationError(Exception):
    """Base for every boundary failure. Each subclass names what was caught."""


class TamperDetected(IsolationError):
    """Something the evaluator sealed no longer matches its seal.

    Carries ``kind`` (one of ``store.INCIDENT_KINDS``) and ``detail`` so the
    failure is named rather than swallowed.
    """

    def __init__(self, kind: str, detail: str):
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


class NetworkDenied(IsolationError):
    """The evaluator tried to open a socket. The evaluator has no network."""


class BoundaryViolation(IsolationError):
    """The evaluator child found the agent's world reachable from inside it."""
