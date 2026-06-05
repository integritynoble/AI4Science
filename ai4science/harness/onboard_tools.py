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


def _post_form(path: str, fields: dict):
    data = urllib.parse.urlencode({k: str(v) for k, v in fields.items()}).encode()
    req = urllib.request.Request(_base() + path, data=data, method="POST", headers={
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _extract_badge(html: str):
    m = re.search(r"(accepted|rejected|pending|verifying|under review)", html or "", re.I)
    return m.group(1).lower() if m else None


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


def _submit_tool() -> Tool:
    def _submit(workspace, *, artifact_type: str, fields, confirm: bool = False) -> str:
        confirm = confirm is True   # strict: a string "true"/"false" never submits
        t = _TYPES.get(artifact_type)
        if not t:
            return (f"[onboard error] unknown type {artifact_type!r}; one of: "
                    f"{', '.join(_TYPES)}")
        slug, req, opt = t
        if not isinstance(fields, dict):
            return "[onboard error] fields must be an object of field->value"
        missing = [f for f in req if not str(fields.get(f, "")).strip()]
        if missing:
            return f"[onboard error] missing fields: {', '.join(missing)}"
        if not _token():
            return ("[onboard error] set PWM_ONBOARD_TOKEN (your pwm_ API key from "
                    "physicsworldmodel.org)")
        allowed = set(req) | set(opt)
        payload = {k: v for k, v in fields.items() if k in allowed}
        if not confirm:
            body = "\n".join(f"  {k}: {v}" for k, v in payload.items())
            return (f"[preview] would submit a {artifact_type} to "
                    f"{_base()}/api/v1/pwm-submit/{slug}\n{body}\n"
                    "Pass confirm=true to submit to the LIVE platform "
                    "(it runs the S1-S4 quality gate and may award PWM).")
        try:
            status, text = _post_form(f"/api/v1/pwm-submit/{slug}", payload)
        except Exception as exc:
            return f"[onboard error] {exc}"
        if status >= 400:
            return f"[onboard error] submit failed (HTTP {status})"
        badge = _extract_badge(text)
        return (f"Submitted {artifact_type} (HTTP {status}"
                f"{', status: ' + badge if badge else ''}). "
                "Check onboard_status / onboard_balance for the gate result + reward.")

    return Tool(
        name="onboard_submit",
        description=("Submit an authored PWM artifact to the live platform. Args: "
                     "artifact_type (principle/digital-twin/benchmark/solution), "
                     "fields (an object of the required fields from onboard_guide), "
                     "confirm. Without confirm=true it PREVIEWS (no write); confirm=true "
                     "submits to the live platform (runs the S1-S4 gate, may award PWM)."),
        parameters={"type": "object", "properties": {
            "artifact_type": {"type": "string"},
            "fields": {"type": "object"},
            "confirm": {"type": "boolean"}},
            "required": ["artifact_type", "fields"]},
        func=_submit, mutating=False)


def onboard_tools() -> List[Tool]:
    return [_guide_tool(), _submit_tool(), _status_tool(), _balance_tool()]
