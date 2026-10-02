#!/usr/bin/env python3
"""Local test fixture. No credentials or prompt contents are written to logs."""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve(port=0, ready=None, log=None, tool_call=None, sentinels=()):
    """tool_call: optional {"name": ..., "arguments": {...}}. When the request offers that tool and the last
    message is not a tool result, the reply is that one tool call; otherwise it is AI4SCIENCE_LOCAL_OK.
    sentinels: strings whose presence in a request is logged (as booleans, never the prompt itself)."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            tools = sorted(t.get("function", {}).get("name", "") for t in body.get("tools") or [])
            messages = body.get("messages") or []
            after_tool = bool(messages) and messages[-1].get("role") == "tool"
            call = tool_call if tool_call and tool_call["name"] in tools and not after_tool else None
            record = {"path": self.path, "model": body.get("model"), "stream": body.get("stream", False),
                      "tools": tools, "after_tool_result": after_tool, "replied_tool_call": bool(call),
                      "sentinels_seen": [x for x in sentinels if x.encode() in raw]}
            if log:
                with Path(log).open("a") as out:
                    out.write(json.dumps(record) + "\n")
            base = {"id": "chatcmpl-local-test", "created": int(time.time()), "model": body["model"]}
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if call:
                    steps = [({"role": "assistant", "tool_calls": [{"index": 0, "id": "call_ai4science_test", "type": "function",
                               "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])}}]}, None),
                             ({}, "tool_calls")]
                else:
                    steps = [({"role": "assistant", "content": "AI4SCIENCE_LOCAL_OK"}, None), ({}, "stop")]
                for delta, finish in steps:
                    event = {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                result = {**base, "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": "AI4SCIENCE_LOCAL_OK"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
                payload = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    if ready:
        Path(ready).write_text(str(server.server_port))
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ready")
    parser.add_argument("--log")
    args = parser.parse_args()
    server = serve(args.port, args.ready, args.log)
    print(f"Fake own LLM listening on http://127.0.0.1:{server.server_port}/v1", flush=True)
    server.serve_forever()
