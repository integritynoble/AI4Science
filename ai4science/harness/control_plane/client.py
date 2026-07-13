from __future__ import annotations
from typing import Any
import httpx

SANDBOX_EXEC_TIMEOUT = 180.0  # generous per-call timeout for sandbox reconstruction (exceeds 60s server budget)
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

    def open_run(self, goal: str, capability_profile: str, hard_limits: dict,
                 interaction_profile: str = "I1", agent_id: str | None = None) -> dict:
        body = {
            "goal": goal, "capability_profile": capability_profile,
            "hard_limits": hard_limits, "interaction_profile": interaction_profile}
        if agent_id is not None:
            body["agent_id"] = agent_id
        r = self._client.post("/open_run", json=body)
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

    def credential_lease(self, run_id: str, scope: str) -> dict:
        try:
            r = self._client.post("/credential_lease", json={"run_id": run_id, "scope": scope})
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"lease_id": None, "active": False}

    def sandbox_execute(self, run_id: str, command: list, *, scope=None,
                        net_allowlist=None, workspace_target=None) -> dict:
        try:
            r = self._client.post("/sandbox_execute", json={
                "run_id": run_id, "command": command, "scope": scope,
                "net_allowlist": net_allowlist, "workspace_target": workspace_target},
                timeout=SANDBOX_EXEC_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"is_error": True, "reason": "control plane unreachable"}

    def classify(self, run_id: str, boundary_kind: str, *, step_summary: str = "",
                 action_type=None) -> dict:
        try:
            r = self._client.post("/classify", json={
                "run_id": run_id, "boundary_kind": boundary_kind,
                "step_summary": step_summary, "action_type": action_type})
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"decision": "ASK", "reason": "gateway unreachable"}

    def set_interaction_profile(self, run_id: str, profile: str, approval_token=None) -> dict:
        try:
            r = self._client.post("/set_interaction_profile", json={
                "run_id": run_id, "profile": profile, "approval_token": approval_token})
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable", "profile": profile}

    def stage_input(self, run_id: str, rel_path: str, content: bytes) -> dict:
        import base64
        try:
            r = self._client.post("/stage_input", json={
                "run_id": run_id, "rel_path": rel_path,
                "content_b64": base64.b64encode(content).decode()})
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def llm_egress(self, run_id: str, request: dict) -> dict:
        try:
            r = self._client.post("/llm_egress", json={"run_id": run_id, "request": request},
                                  timeout=180.0)
            r.raise_for_status(); return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def inspect_for_tripwires(self, run_id: str, action: dict, result: dict) -> dict:
        try:
            r = self._client.post("/inspect_tripwires",
                                  json={"run_id": run_id, "action": action, "result": result})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"tripped": True, "reason": "control plane unreachable"}

    def tripwire_triggered(self, run_id: str) -> bool:
        try:
            r = self._client.get(f"/tripwire_status/{run_id}"); r.raise_for_status()
            return r.json().get("active") is not True
        except Exception:
            return True

    def emergency_stop(self, run_id: str, reason: str = "client") -> dict:
        try:
            r = self._client.post("/emergency_stop", json={"run_id": run_id, "reason": reason})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"stopped": False, "reason": "control plane unreachable"}

    def evaluate(self, run_id: str, domain: str = "cassi") -> dict:
        try:
            r = self._client.post("/evaluate", json={"run_id": run_id, "domain": domain})
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"decision": "fail", "score": 0.0,
                    "feedback": {"error": "control plane unreachable"}}

    def set_criteria(self, run_id: str, verify_commands: list, required_artifacts: list) -> dict:
        try:
            r = self._client.post("/set_criteria", json={
                "run_id": run_id, "verify_commands": verify_commands,
                "required_artifacts": required_artifacts})
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def stage_heldout(self, run_id, scene_id, domain="cassi"):
        try:
            r = self._client.post("/stage_heldout",
                                  json={"run_id": run_id, "scene_id": scene_id, "domain": domain})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def score_heldout(self, run_id, scene_id, version=None, domain="cassi"):
        try:
            r = self._client.post("/score_heldout",
                                  json={"run_id": run_id, "scene_id": scene_id,
                                        "version": version, "domain": domain})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"psnr": None}

    def stage_worktask(self, run_id, task_id, domain="work_search"):
        try:
            r = self._client.post("/stage_worktask",
                                  json={"run_id": run_id, "task_id": task_id, "domain": domain})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def score_worktask(self, run_id, task_id, domain="work_search", version=None):
        try:
            r = self._client.post("/score_worktask",
                                  json={"run_id": run_id, "task_id": task_id,
                                        "domain": domain, "version": version})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"pass": 0.0, "steps": 0}

    def register_version(self, kind, name, version, metadata):
        try:
            r = self._client.post("/register_version",
                                  json={"kind": kind, "name": name, "version": version, "metadata": metadata})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def evaluate_candidates(self, run_id, results, domain="cassi"):
        try:
            r = self._client.post("/evaluate_candidates", json={"run_id": run_id, "results": results, "domain": domain})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def get_last_known_good(self, kind, name):
        try:
            r = self._client.get(f"/last_known_good/{kind}/{name}"); r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def broker_send(self, sender_id, recipient_id, msg_type, payload, run_id=None):
        try:
            body = {"sender_id": sender_id, "recipient_id": recipient_id,
                    "msg_type": msg_type, "payload": payload}
            if run_id is not None:
                body["run_id"] = run_id
            r = self._client.post("/broker/send", json=body)
            r.raise_for_status(); return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}

    def broker_inbox(self, agent_id, unread_only=False):
        try:
            r = self._client.get(f"/broker/inbox/{agent_id}", params={"unread_only": unread_only})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"messages": []}

    def broker_ack(self, agent_id, msg_id):
        try:
            r = self._client.post("/broker/ack", json={"agent_id": agent_id, "msg_id": msg_id})
            r.raise_for_status(); return r.json()
        except Exception:
            return {"ok": False, "reason": "control plane unreachable"}
