from ai4science.harness.agents.social.agent import run_social_task

class StubClient:
    def __init__(self, timeline_json, post_json):
        self._tl = timeline_json; self._post = post_json; self.calls = []
    def open_run(self, *a, **k):
        return {"run_id": "R", "capability_profile": "A2", "limits": {}, "workspace_path": "/tmp/ws"}
    def classify(self, run_id, boundary_kind, **k): return {"decision": "ASK"}
    def sandbox_execute(self, run_id, command, *, scope=None, net_allowlist=None, **k):
        self.calls.append((command, scope, net_allowlist))
        out = self._post if any("/api/v1/statuses" in c for c in command if isinstance(c, str)) else self._tl
        return {"is_error": False, "exit_code": 0, "stdout": out, "stderr": ""}

def test_drafts_and_does_not_post_without_approval(tmp_path):
    import json
    tl = json.dumps([{"account": {"acct": "alice"}, "content": "hi"}])
    c = StubClient(tl, json.dumps({"id": "99"}))
    out = run_social_task(client=c, store=None, task_id="t", mastodon_host="m.example",
                          approve=None)                    # no approval
    assert out["status"] == "drafted"
    assert not any("/api/v1/statuses" in cmd for (cmdlist, _, _) in c.calls for cmd in cmdlist if isinstance(cmd, str))

def test_posts_on_approval_and_no_token_in_result(tmp_path):
    import json
    tl = json.dumps([{"account": {"acct": "alice"}, "content": "hi"}])
    c = StubClient(tl, json.dumps({"id": "99"}))
    out = run_social_task(client=c, store=None, task_id="t", mastodon_host="m.example",
                          approve=lambda draft: True)
    assert out["status"] == "posted" and out["id"] == "99"
    assert "token" not in json.dumps(out).lower() and "Bearer" not in json.dumps(out)
    # the read used net_allowlist=[host]+scope, and a POST /api/v1/statuses call was made
    assert any("/api/v1/statuses" in cmd for (cmdlist, _, _) in c.calls for cmd in cmdlist if isinstance(cmd, str))
    assert all(nl == ["m.example"] and sc == "mastodon" for (_, sc, nl) in c.calls)
