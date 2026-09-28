#!/usr/bin/env python3
"""Tiny loopback-only OpenAI chat-completion SSE server for install rehearsals."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(size)
        print(f"{self.client_address[0]} {self.path}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        chunks = [
            {"id": "local-test", "object": "chat.completion.chunk", "created": 0,
             "model": "local-model", "choices": [{"index": 0,
             "delta": {"role": "assistant", "content": "LOCAL_OK"}, "finish_reason": None}]},
            {"id": "local-test", "object": "chat.completion.chunk", "created": 0,
             "model": "local-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        if self.path.endswith("/responses"):
            item = {"id": "msg_local", "type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "annotations": [], "text": "LOCAL_OK"}]}
            events = [
                {"type": "response.created", "response": {"id": "resp_local", "object": "response", "created_at": 0, "status": "in_progress", "model": "local-model", "output": []}},
                {"type": "response.output_item.added", "output_index": 0, "item": {"id": "msg_local", "type": "message", "role": "assistant", "content": []}},
                {"type": "response.content_part.added", "item_id": "msg_local", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": ""}},
                {"type": "response.output_text.delta", "item_id": "msg_local", "output_index": 0, "content_index": 0, "delta": "LOCAL_OK"},
                {"type": "response.output_text.done", "item_id": "msg_local", "output_index": 0, "content_index": 0, "text": "LOCAL_OK"},
                {"type": "response.content_part.done", "item_id": "msg_local", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "annotations": [], "text": "LOCAL_OK"}},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": {"id": "resp_local", "object": "response", "created_at": 0, "status": "completed", "model": "local-model", "output": [item], "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}},
            ]
            for event in events:
                self.wfile.write(("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
        else:
            for chunk in chunks:
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
