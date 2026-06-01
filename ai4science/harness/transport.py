from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Iterator


def get_json(url: str, timeout: int = 60) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _request(url: str, headers: Dict[str, str], payload: Dict[str, Any]):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", **headers}
    return urllib.request.Request(url, data=data, headers=h, method="POST")


def post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any],
              timeout: int = 120) -> Dict[str, Any]:
    with urllib.request.urlopen(_request(url, headers, payload), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sse_post(url: str, headers: Dict[str, str], payload: Dict[str, Any],
             timeout: int = 600) -> Iterator[Dict[str, Any]]:
    """POST and iterate Server-Sent-Event `data:` JSON chunks (stops at [DONE])."""
    with urllib.request.urlopen(_request(url, headers, payload), timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            body = line[len("data:"):].strip()
            if body == "[DONE]":
                break
            try:
                yield json.loads(body)
            except json.JSONDecodeError:
                continue
