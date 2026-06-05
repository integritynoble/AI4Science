from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import List

from ai4science.harness.tools.base import Tool

# artifact_type -> (endpoint_slug, required_fields, optional_fields)
_TYPES = {
    "principle": ("principle",
                  ("name", "domain", "rule", "formula", "reference"), ()),
    "digital-twin": ("spec",
                     ("principle_id", "operator_type", "omega_description",
                      "epsilon", "reference"), ()),
    "benchmark": ("benchmark",
                  ("spec_id", "tier", "dataset_description", "metric",
                   "metric_threshold"), ("dataset_url",)),
    "solution": ("solution",
                 ("principle_id", "ai_system", "task_description",
                  "artifact_description"), ("self_reported_metric",)),
}
_HOWTO = {
    "principle": "A physical law: a named rule + formula + a citation, in a domain.",
    "digital-twin": "An L2 spec under a principle: the operator/Omega/epsilon of a simulation.",
    "benchmark": "An L3 benchmark under a spec: dataset + metric + threshold (+ tier).",
    "solution": "An L4 solution under a principle: the AI system, task, and artifact.",
}


def _base() -> str:
    return os.environ.get("PWM_ONBOARD_BASE", "https://physicsworldmodel.org").rstrip("/")


def _token():
    return os.environ.get("PWM_ONBOARD_TOKEN")


def _get_json(path: str) -> dict:
    req = urllib.request.Request(_base() + path, method="GET", headers={
        "Authorization": f"Bearer {_token()}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _balance_tool() -> Tool:
    def _balance(workspace) -> str:
        if not _token():
            return ("[onboard error] set PWM_ONBOARD_TOKEN (your pwm_ API key from "
                    "physicsworldmodel.org)")
        try:
            d = _get_json("/api/v1/pwm-token/balance")
        except Exception as exc:
            return f"[onboard error] {exc}"
        return json.dumps({k: v for k, v in d.items() if k != "success"},
                          indent=2, default=str)[:20000]

    return Tool(
        name="onboard_balance",
        description="Show the contributor's PWM token balance + caps (needs PWM_ONBOARD_TOKEN).",
        parameters={"type": "object", "properties": {}, "required": []},
        func=_balance, mutating=False)


def _status_tool() -> Tool:
    def _status(workspace) -> str:
        if not _token():
            return ("[onboard error] set PWM_ONBOARD_TOKEN (your pwm_ API key from "
                    "physicsworldmodel.org)")
        try:
            d = _get_json("/api/v1/pwm-token/transactions?limit=20")
        except Exception as exc:
            return f"[onboard error] {exc}"
        txns = d.get("transactions") or []
        if not txns:
            return "no PWM transactions yet."
        lines = []
        for t in txns[:20]:
            lines.append(f"- {t.get('kind') or t.get('type') or '?'} "
                         f"{t.get('amount')} ({t.get('status') or ''}) "
                         f"{t.get('created_at') or t.get('timestamp') or ''}")
        return "\n".join(lines)[:20000]

    return Tool(
        name="onboard_status",
        description=("Show recent PWM ledger entries (the accept-reward trail for your "
                     "submissions; needs PWM_ONBOARD_TOKEN)."),
        parameters={"type": "object", "properties": {}, "required": []},
        func=_status, mutating=False)


def _guide_tool() -> Tool:
    def _guide(workspace, *, artifact_type: str) -> str:
        t = _TYPES.get(artifact_type)
        if not t:
            return (f"[onboard error] unknown type {artifact_type!r}; one of: "
                    f"{', '.join(_TYPES)}")
        slug, req, opt = t
        lines = [f"{artifact_type} (POST /api/v1/pwm-submit/{slug})",
                 "required: " + ", ".join(req)]
        if opt:
            lines.append("optional: " + ", ".join(opt))
        lines.append(_HOWTO[artifact_type])
        return "\n".join(lines)

    return Tool(
        name="onboard_guide",
        description=("Show the required/optional fields + how-to for authoring a PWM "
                     "artifact to submit: artifact_type one of principle / "
                     "digital-twin / benchmark / solution."),
        parameters={"type": "object", "properties": {
            "artifact_type": {"type": "string"}}, "required": ["artifact_type"]},
        func=_guide, mutating=False)


def onboard_tools() -> List[Tool]:
    return [_guide_tool(), _status_tool(), _balance_tool()]
