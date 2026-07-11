from __future__ import annotations
from typing import Any
import httpx

_DENY = {"allowed": False, "reason": "control plane unreachable", "scope": {}}

class ControlPlaneClient:
    """Untrusted-side stub. Speaks only the wire protocol; fails closed."""

    def __init__(self, socket_path: str, timeout: float = 5.0):
        self._transport = httpx.HTTPTransport(uds=socket_path)
        self._client = httpx.Client(transport=self._transport, base_url="http://cp",
                                    timeout=timeout)

    def healthz(self) -> bool:
        try:
            return self._client.get("/healthz").json().get("status") == "ok"
        except Exception:
            return False

    def open_run(self, goal: str, capability_profile: str, hard_limits: dict) -> dict:
        r = self._client.post("/open_run", json={
            "goal": goal, "capability_profile": capability_profile,
            "hard_limits": hard_limits})
        r.raise_for_status()
        return r.json()

    def authorize(self, run_id: str, proposal: dict[str, Any]) -> dict:
        try:
            r = self._client.post("/authorize",
                                  json={"run_id": run_id, "proposal": proposal})
            r.raise_for_status()
            return r.json()
        except Exception:
            return dict(_DENY)  # fail closed

    def audit_append(self, kind: str, run_id: str | None, payload: dict) -> dict:
        r = self._client.post("/audit",
                              json={"kind": kind, "run_id": run_id, "payload": payload})
        r.raise_for_status()
        return r.json()
