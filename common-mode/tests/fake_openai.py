#!/usr/bin/env python3
"""Local test fixture. No credentials or prompt contents are written to logs."""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve(port=0, ready=None, log=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            record = {"path": self.path, "model": body.get("model"), "stream": body.get("stream", False)}
            if log:
                with Path(log).open("a") as out:
                    out.write(json.dumps(record) + "\n")
            base = {"id": "chatcmpl-local-test", "created": int(time.time()), "model": body["model"]}
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for delta, finish in [({"role": "assistant", "content": "AI4SCIENCE_LOCAL_OK"}, None), ({}, "stop")]:
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
