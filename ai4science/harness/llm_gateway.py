"""Host LLM gateway — serves the founder-credentialed LLMs to remote users.

Runs on the agent host (where the founder API keys + Claude/codex/Gemini
subscription logins live), bound to 172.17.0.1:<port> so the backend container
can reach it but the outside world cannot. The backend's /api/v1/llm/proxy
authenticates the user + charges PWM, then forwards here; this gateway runs the
real harness adapter and streams events back as JSONL.

This is the piece that makes "founder providers serve the LLM, you just pay
PWM" true for users who have no LLM credentials of their own (e.g. on a campus
cluster) — the generalization of scripts/haiku_bridge.py to every backend.

Run (systemd on the host):
    AI4SCIENCE_GATEWAY_TOKEN=<shared-secret> \
    python3 -m ai4science.harness.llm_gateway          # binds 172.17.0.1:8791
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai4science.harness import proxy_proto as proto
from ai4science.harness.adapters.factory import adapter_for, harness_available
from ai4science.llm import pricing, routing

TOKEN = os.environ.get("AI4SCIENCE_GATEWAY_TOKEN", "")
HOST = os.environ.get("AI4SCIENCE_GATEWAY_HOST", "172.17.0.1")
PORT = int(os.environ.get("AI4SCIENCE_GATEWAY_PORT", "8791"))

app = FastAPI(title="ai4science-llm-gateway")


class StreamReq(BaseModel):
    backend: str
    model: str
    messages: list
    tools: list = []
    reasoning: str = "low"


@app.get("/health")
def health() -> dict:
    return {"ok": True,
            "backends": {b: harness_available(b)
                         for b in ("anthropic", "openai", "gemini")}}


@app.post("/v1/stream")
def stream(req: StreamReq, x_bridge_token: str = Header(default="")):
    if not TOKEN or x_bridge_token != TOKEN:
        raise HTTPException(status_code=401, detail="bad gateway token")
    if not harness_available(req.backend):
        raise HTTPException(status_code=503,
                            detail=f"backend '{req.backend}' has no founder credential here")

    messages = [proto.msg_from_wire(m) for m in req.messages]
    tools = [proto.tool_from_wire(t) for t in req.tools]
    adapter = adapter_for(req.backend)

    def _gen():
        in_tok = out_tok = 0
        try:
            for ev in adapter.stream(messages, tools, model=req.model,
                                     reasoning=req.reasoning):
                w = proto.event_to_wire(ev)
                if w.get("t") == "usage":
                    in_tok = w.get("input") or in_tok
                    out_tok = w.get("output") or out_tok
                if w.get("t") != "ignore":
                    yield json.dumps(w) + "\n"
        except Exception as exc:  # surface as a text event, never 500 mid-stream
            yield json.dumps({"t": "text",
                              "text": f"[gateway error: {type(exc).__name__}: {exc}]"}) + "\n"
            yield json.dumps({"t": "done", "stop_reason": "error"}) + "\n"
        # final billing line the backend reads to charge PWM
        usage = {"input": in_tok, "output": out_tok}
        pwm = pricing.price_call(req.model, usage)["pwm"]
        try:
            _src, _pid, wallet, _mult = routing._select_source(req.backend)
        except Exception:
            wallet = None
        yield json.dumps({"t": "bill", "pwm": round(float(pwm), 6),
                          "wallet": wallet, "model": req.model,
                          "input": in_tok, "output": out_tok}) + "\n"

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


def main() -> None:
    import uvicorn
    if not TOKEN:
        raise SystemExit("set AI4SCIENCE_GATEWAY_TOKEN")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
